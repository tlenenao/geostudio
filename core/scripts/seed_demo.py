"""Déclare les tables de démo comme collections éditables publiques.
Idempotent — utilisable à chaque démarrage d'environnement de démo.

Usage : DATABASE_URL=postgresql+psycopg://… uv run python -m scripts.seed_demo [--owner alice]
"""

import argparse
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analytics.aggregate import AggregateRequestBody
from app.audit.writer import write_audit
from app.auth.dependency import is_etl_enabled
from app.collections import dataset_validation as _dataset_validation  # noqa: F401  (valideurs)
from app.collections.ddl import apply_collection_ddl, quote_ident
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection, get_collection
from app.configs.builder_templates import build_config_from_template
from app.configs.schemas import (
    AlertChannelWebhook,
    AlertCondition,
    AlertRulePayload,
    BaseMap,
    BuilderConfig,
    DatasetPayload,
    MapConfig,
    MapLayer,
    MapView,
    PipelineEdge,
    PipelineNode,
    PipelinePayload,
    PipelineRefreshPolicy,
)
from app.configs.service import create_config_service
from app.db import make_engine, make_session_factory
from app.ingestion.importer import default_basemap_style
from app.items.models import Item
from app.mcp.form_app import build_config
from app.pipelines import config_validation as _pipeline_validation  # noqa: F401  (valideurs)
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

DEMO_TABLES = {"incidents": "Incidents", "points_interet": "Points d'intérêt"}


def _owner(session: Session, tenant_id: str, username: str | None) -> User:
    if username:
        user = session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )
        if user is None:
            raise SystemExit(f"owner '{username}' introuvable")
        return user
    admin = session.scalar(select(User).where(User.tenant_id == tenant_id, User.is_admin.is_(True)))
    if admin:
        return admin
    subs = [s.strip() for s in os.environ.get("CORE_ADMIN_SUBS", "").split(",") if s.strip()]
    if not subs:
        raise SystemExit("aucun admin : définir CORE_ADMIN_SUBS ou passer --owner")
    return get_or_create_user(
        session,
        tenant_id=tenant_id,
        oidc_sub=subs[0],
        username=subs[0],
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=True,
    )


def seed(session: Session, owner_username: str | None = None) -> list[str]:
    tenant = get_or_create_default_tenant(session)
    owner = _owner(session, tenant.id, owner_username)
    created: list[str] = []
    for table, title in DEMO_TABLES.items():
        if get_collection(session, tenant_id=tenant.id, collection_id=table):
            continue
        try:
            info = introspect_table(session, table)
        except TableNotFound:
            print(f"table '{table}' absente — ignorée")
            continue
        except UnsupportedTable as exc:
            print(f"table '{table}' non enregistrable ({exc.reason}) — ignorée")
            continue
        apply_collection_ddl(session, table)
        t = quote_ident(session, table)
        feature_count = session.execute(text(f"SELECT count(*) FROM public.{t}")).scalar_one()
        create_collection(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name=table,
            title=title,
            description="Collection de démonstration",
            is_public=True,
            pk_column=info.pk_column,
            geometry_column=info.geometry_column,
            geometry_type=info.geometry_type,
            srid=info.srid,
            feature_count=feature_count,
        )
        write_audit(
            session,
            tenant_id=tenant.id,
            actor_id=owner.id,
            actor_kind="system",
            action="collection.create",
            object_type="collection",
            object_id=table,
            payload={"tableName": table, "seed": True},
        )
        created.append(table)
    return created


def seed_objects(session: Session, owner_username: str | None = None) -> list[str]:
    """AUD-118 : objets de démonstration (carte, app, dashboard) prêts à ouvrir, sur la
    collection `incidents` si elle est enregistrée. Idempotent (par titre et propriétaire)."""
    tenant = get_or_create_default_tenant(session)
    owner = _owner(session, tenant.id, owner_username)
    col = get_collection(session, tenant_id=tenant.id, collection_id="incidents")
    if col is None:
        return []
    core_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200") + "/v1"
    columns = [
        c.name
        for c in introspect_table(session, "incidents").columns
        if c.name != col.geometry_column
    ]
    wanted: list[tuple[str, BuilderConfig]] = [
        (
            "Carte des incidents",
            BuilderConfig(
                kind="map",
                map=MapConfig(
                    basemap=BaseMap(style=default_basemap_style()),
                    view=MapView(center=(2.4, 46.6), zoom=5.0),
                    layers=[
                        MapLayer(
                            id="incidents",
                            title="Incidents",
                            visible=True,
                            kind="vector",
                            tilesUrl=f"{core_url}/collections/incidents/tiles/{{z}}/{{x}}/{{y}}.mvt",
                            sourceLayer="incidents",
                            pkColumn=col.pk_column,
                            collectionId="incidents",
                            geometryKind="point",
                            renderAs="circle",
                        )
                    ],
                ),
            ),
        ),
        (
            "Suivi des incidents",
            build_config(
                collection_id="incidents",
                schema={"fields": [{"name": c} for c in columns], "geometry": None},
                include_form=False,
            ),
        ),
        ("Tableau de bord (modèle)", build_config_from_template("basic-dashboard")),
        (
            "Incidents (jeu de données)",
            BuilderConfig(
                kind="dataset",
                dataset=DatasetPayload(source="collection", collectionId="incidents"),
            ),
        ),
    ]
    if is_etl_enabled():  # sinon create_config_service refuse un pipeline (403)
        wanted.append(
            (
                "Export des incidents (pipeline)",
                BuilderConfig(
                    kind="pipeline",
                    pipeline=PipelinePayload(
                        nodes=[
                            PipelineNode(
                                id="lecture",
                                kind="reader",
                                op="reader.collection",
                                params={"collectionId": "incidents"},
                            ),
                            PipelineNode(
                                id="export",
                                kind="writer",
                                op="writer.export",
                                x=260,
                                params={"format": "geojson", "key": "demo/incidents.geojson"},
                            ),
                        ],
                        edges=[PipelineEdge(id="e1", **{"from": "lecture"}, to="export")],
                    ),
                ),
            )
        )
    created: list[str] = []
    ids: dict[str, str] = {}

    def _ensure(title: str, config: BuilderConfig) -> None:
        exists = session.scalar(
            select(Item.id).where(
                Item.tenant_id == tenant.id, Item.owner_id == owner.id, Item.title == title
            )
        )
        if exists:
            ids[title] = exists
            return
        done = create_config_service(session, config, title=title, user=owner)
        ids[title] = done.item.id
        write_audit(
            session,
            tenant_id=tenant.id,
            actor_id=owner.id,
            actor_kind="system",
            action="item.create",
            object_type="item",
            object_id=done.item.id,
            payload={"title": title, "seed": True},
        )
        created.append(title)

    for title, config in wanted:
        _ensure(title, config)
    # Règle d'alerte DÉSACTIVÉE (jamais évaluée, webhook factice) : montre l'écran sans livrer.
    _ensure(
        "Alerte : incidents nombreux (inactive)",
        BuilderConfig(
            kind="alert",
            alert=AlertRulePayload(
                datasetItemId=ids["Incidents (jeu de données)"],
                query=AggregateRequestBody(agg="count"),
                condition=AlertCondition(expr="value > 100"),
                refreshPolicy=PipelineRefreshPolicy(enabled=False, cron="0 * * * *"),
                channels=[AlertChannelWebhook(url="https://example.invalid/geostudio-demo")],
            ),
        ),
    )
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=None)
    args = parser.parse_args()
    engine = make_engine(os.environ["DATABASE_URL"])
    Session = make_session_factory(engine)
    with Session() as session:
        created = seed(session, owner_username=args.owner)
        objects = seed_objects(session, owner_username=args.owner)
        session.commit()
    print(f"collections créées : {created or 'aucune (déjà en place)'}")
    print(f"objets créés : {objects or 'aucun (déjà en place, ou collection incidents absente)'}")


if __name__ == "__main__":
    main()
