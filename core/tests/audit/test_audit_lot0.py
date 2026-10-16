# ruff: noqa: F811  (imports de fixtures pytest)
# SPDX-License-Identifier: Apache-2.0
"""Reproducteurs de bugs confirmés (audit lot 0). Chaque test affirme le comportement
CORRECT et est xfail(strict) : il passera en XPASS (= échec) le jour où le bug sera
corrigé, signal pour retirer le marqueur."""

import dataclasses
import re

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import ColumnInfo, TableInfo
from app.db import Base, make_session_factory
from app.features import routes as features_routes
from app.items import repository as items_repo  # noqa: F401
from app.pipelines import runtime
from app.pipelines.runtime import PipelineRuntimeError
from app.ratelimit.limiter import route_group
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_geo_limits_api_postgis import BASE, SQUARE, _limit
from tests.test_geo_limits_api_postgis import env as geo_env  # noqa: F401
from tests.test_items_permissions import env as items_env  # noqa: F401
from tests.test_mcp_tools_create import call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)
from tests.test_mcp_tools_run_analytics_query import (  # noqa: F401
    _create_collection_dataset,
    _local_duckdb,
)

_pg = pytest.mark.postgis
# captures avant le monkeypatch autouse de _local_duckdb (qui remplace l'attribut du module)
_FACTORY_DEP = features_routes.get_duckdb_connection_factory
_BASE_URI_DEP = features_routes.get_analytics_base_uri


def _local_lake(app, tmp_path, monkeypatch):
    for k in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.setenv(k, "http://localhost:9000" if k.endswith("URL") else "x")
    app.dependency_overrides[_FACTORY_DEP] = lambda: lambda: _duck()
    app.dependency_overrides[_BASE_URI_DEP] = lambda: str(tmp_path)


def _duck():
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


# --- 1/2/3. profile REST + MCP ignorent les limites géographiques -----------------


@_pg
def test_profile_route_refuses_geo_limited_user(geo_env, tmp_path, monkeypatch):  # noqa: F811
    client, app, as_user, admin, regular, gid = geo_env
    _local_lake(app, tmp_path, monkeypatch)
    assert _limit(client, gid, SQUARE).status_code == 200
    as_user(regular)
    # le jumeau /aggregate refuse (403 geo_limit_unsupported) ; le profil doit faire pareil
    assert client.post(f"{BASE}/aggregate", json={"agg": "count"}).status_code == 403
    r = client.get(f"{BASE}/profile")
    assert r.status_code == 403 and "geo_limit_unsupported" in r.text


@_pg
def test_profile_route_refuses_anonymous_on_limited_public_collection(
    geo_env,
    tmp_path,
    monkeypatch,  # noqa: F811
):  # noqa: F811
    client, app, as_user, admin, regular, gid = geo_env
    _local_lake(app, tmp_path, monkeypatch)
    assert _limit(client, gid, SQUARE).status_code == 200
    as_user(None)
    r = client.get(f"{BASE}/profile")
    assert r.status_code in (401, 403, 404), r.text


@_pg
def test_mcp_profile_dataset_refuses_geo_limited_user(app_client, _local_duckdb):  # noqa: F811
    from app.sharing.models import CollectionGeoLimit, Group, GroupMember

    with app_client:
        collection_id = _register_incidents_collection(app_client)
        dataset_id = _create_collection_dataset(app_client, collection_id)
        tid, uid = app_client.tenant.id, app_client.mock_user.id
        with app_client.session_factory() as s:
            s.add(Group(id="g-audit", tenant_id=tid, name="g", created_by=uid))
            s.flush()
            s.add(GroupMember(group_id="g-audit", user_id=uid, tenant_id=tid))
            s.add(
                CollectionGeoLimit(
                    id="gl-audit",
                    tenant_id=tid,
                    collection_id=collection_id,
                    target_type="group",
                    target_id="g-audit",
                    geometry=SQUARE,
                    created_by=uid,
                )
            )
            s.commit()
        # run_analytics_query refuse bien ; profile_dataset doit lever une erreur d'outil
        err = call_tool_expecting_error(app_client, "profile_dataset", {"datasetId": dataset_id})
    assert "geo" in err.lower()


# --- 4. PATCH /items : un éditeur publie à l'anonyme -----------------------------


def test_editor_cannot_publish_item_via_patch(items_env):  # noqa: F811
    client = items_env["as_user"](items_env["editor"])
    r = client.patch("/v1/items/shared", json={"isPublished": True})
    # PUT /items/{id}/sharing est réservé au rôle manager ; PATCH doit l'être aussi
    assert r.status_code == 403, r.text


# --- 5. Rate limiting absent sur aggregate/profile --------------------------------


@pytest.mark.parametrize(
    "method,path",
    [("POST", "/v1/collections/c1/aggregate"), ("GET", "/v1/collections/c1/profile")],
)
def test_analytic_routes_have_a_rate_limit_group(method, path):
    export_re = re.compile(r"^/v1/export$")
    assert route_group(path, method, export_re) is not None


# --- 6. writer.collection replace + colonne sensible = perte de données -----------


@_pg
def test_writer_replace_does_not_null_sensitive_columns(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    info = TableInfo(
        table_name="villes",
        pk_column="id",
        geometry_column="geometry",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="region", type="string", required=False),
            ColumnInfo(name="pop", type="integer", required=False),
        ],
    )
    try:
        with Session() as s:
            tenant = get_or_create_default_tenant(s)
            user = get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub="a",
                username="alice",
                email=None,
                first_name="",
                last_name="",
            )
            s.execute(
                text(
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "description, pk_column, geometry_column, is_public, editable, "
                    "created_at, updated_at) VALUES ('villes_audit', :t, :o, 'villes_audit', "
                    "'V', '', 'id', 'geometry', false, true, now(), now())"
                ),
                {"t": tenant.id, "o": user.id},
            )
            s.execute(
                text(
                    "CREATE TABLE villes_audit (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                    "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
                )
            )
            apply_collection_ddl(s, "villes_audit")
            s.execute(
                text(
                    "INSERT INTO villes_audit (tenant_id, region, pop, geometry) VALUES "
                    "(:t, 'Secret', 777, ST_SetSRID(ST_MakePoint(9,9),4326))"
                ),
                {"t": tenant.id},
            )
            s.commit()
            part = tmp_path / f"tenant_id={tenant.id}" / "collection_id=villes" / "dt=2026-08-05"
            part.mkdir(parents=True)
            gpd.GeoDataFrame(
                [
                    {
                        "id": 1,
                        "region": "Nord",
                        "pop": 10,
                        "_op": "insert",
                        "_lsn": 1,
                        "_ts": 1.0,
                        "geometry": Point(1, 45),
                    }
                ],
                geometry="geometry",
                crs="EPSG:4326",
            ).to_parquet(part / "part-1.parquet")

            # l'utilisateur est masqué sur 'pop' pour la source ; la cible n'est pas filtrée
            monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset({"pop"}))
            monkeypatch.setattr(
                runtime,
                "_table_info_for_collection",
                lambda session, name: dataclasses.replace(info, table_name=name),
            )
            monkeypatch.setattr(
                runtime,
                "_require_readable_collection_id",
                lambda session, *, tenant_id, user, collection_id: collection_id,
            )
            from app.configs.schemas import PipelinePayload

            payload = PipelinePayload.model_validate(
                {
                    "nodes": [
                        {
                            "id": "r1",
                            "kind": "reader",
                            "op": "reader.collection",
                            "params": {"collectionId": "villes"},
                        },
                        {
                            "id": "w1",
                            "kind": "writer",
                            "op": "writer.collection",
                            "params": {"collectionId": "villes_audit", "mode": "replace"},
                        },
                    ],
                    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                }
            )
            try:
                runtime.run_pipeline(
                    s,
                    payload=payload,
                    tenant_id=tenant.id,
                    user=user,
                    endpoint_url="http://localhost:9000",
                    access_key="x",
                    secret_key="y",
                    base_uri=str(tmp_path),
                )
                s.commit()
            except PipelineRuntimeError:
                s.rollback()  # un refus est un comportement correct
            pops = s.execute(text("SELECT pop FROM villes_audit")).scalars().all()
            assert 777 in pops or pops == []  # jamais des lignes réécrites avec pop=NULL
            assert None not in pops
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS villes_audit"))
            conn.execute(
                text(
                    "TRUNCATE pipeline_runs, items, configs, config_revisions, collections, "
                    "audit_log, users, tenants CASCADE"
                )
            )
