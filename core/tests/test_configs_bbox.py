# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.models import Collection
from app.configs.bbox import recompute_item_bbox
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapLayer, MapView
from app.db import Base, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        conn = s.connection()
        conn.execute(text("DROP TABLE IF EXISTS t_bbox_a"))
        conn.execute(
            text(
                "CREATE TABLE t_bbox_a (id serial PRIMARY KEY, nom text, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_bbox_a (nom, geom) VALUES "
                "('A', ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326)), "
                "('B', ST_SetSRID(ST_MakePoint(2.0, 46.0), 4326))"
            )
        )
        conn.execute(text("DROP TABLE IF EXISTS t_bbox_b"))
        conn.execute(
            text(
                "CREATE TABLE t_bbox_b (id serial PRIMARY KEY, nom text, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_bbox_b (nom, geom) VALUES "
                "('C', ST_SetSRID(ST_MakePoint(10.0, 50.0), 4326))"
            )
        )
        conn.execute(text("DROP TABLE IF EXISTS t_bbox_empty"))
        conn.execute(
            text(
                "CREATE TABLE t_bbox_empty (id serial PRIMARY KEY, nom text, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 4326))"
            )
        )
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
        col_a = Collection(
            id="t_bbox_a",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="t_bbox_a",
            title="A",
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        col_b = Collection(
            id="t_bbox_b",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="t_bbox_b",
            title="B",
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        col_empty = Collection(
            id="t_bbox_empty",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="t_bbox_empty",
            title="Empty",
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        s.add_all([col_a, col_b, col_empty])
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_bbox_a, t_bbox_b, t_bbox_empty"))
        conn.execute(
            text("TRUNCATE items, configs, config_revisions, collections, users, tenants CASCADE")
        )


def _map_config(*collection_ids: str) -> BuilderConfig:
    return BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style="https://demotiles.maplibre.org/style.json"),
            view=MapView(center=[0, 0], zoom=1),
            layers=[
                MapLayer(
                    id=f"l{i}",
                    title=f"Layer {i}",
                    visible=True,
                    kind="feature",
                    collectionId=cid,
                    url=f"https://core.test/collections/{cid}/items",
                )
                for i, cid in enumerate(collection_ids)
            ],
        ),
    )


def test_recompute_item_bbox_single_collection(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        config = _map_config("t_bbox_a")
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert [item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y] == [
            1.0,
            45.0,
            2.0,
            46.0,
        ]


def test_recompute_item_bbox_unions_multiple_collections(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        config = _map_config("t_bbox_a", "t_bbox_b")
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert [item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y] == [
            1.0,
            45.0,
            10.0,
            50.0,
        ]


def test_recompute_item_bbox_empty_collection_ignored_in_union(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        config = _map_config("t_bbox_a", "t_bbox_empty")
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert [item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y] == [
            1.0,
            45.0,
            2.0,
            46.0,
        ]


def test_recompute_item_bbox_all_collections_empty_clears_bbox(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y = (0.0, 0.0, 1.0, 1.0)
        config = _map_config("t_bbox_empty")
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert item.bbox_min_x is None
        assert item.bbox_min_y is None
        assert item.bbox_max_x is None
        assert item.bbox_max_y is None


def test_recompute_item_bbox_non_map_kind_clears_bbox(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="A"
        )
        item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y = (0.0, 0.0, 1.0, 1.0)
        config = BuilderConfig(kind="app", layout={"type": "grid", "breakpoints": {}, "items": []})
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert item.bbox_min_x is None


def test_backfill_item_bbox_recomputes_and_is_idempotent(env):
    from app.configs import repository as configs_repo
    from scripts.backfill_item_bbox import backfill

    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        s.flush()
        config = _map_config("t_bbox_a")
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        # Simule un item "map" créé AVANT SP-55 (config jamais réévaluée
        # depuis) : sa bbox n'a jamais été posée, même si create_config la
        # calcule désormais automatiquement pour toute nouvelle écriture.
        item.bbox_min_x = None
        item.bbox_min_y = None
        item.bbox_max_x = None
        item.bbox_max_y = None
        s.commit()
        item_id = item.id

    with Session() as s:
        count = backfill(s)
        assert count >= 1
        refreshed = s.get(type(item), item_id)
        assert [
            refreshed.bbox_min_x,
            refreshed.bbox_min_y,
            refreshed.bbox_max_x,
            refreshed.bbox_max_y,
        ] == [1.0, 45.0, 2.0, 46.0]

    # Rejouable sans effet de bord : même résultat au second passage.
    with Session() as s:
        backfill(s)
        refreshed = s.get(type(item), item_id)
        assert [
            refreshed.bbox_min_x,
            refreshed.bbox_min_y,
            refreshed.bbox_max_x,
            refreshed.bbox_max_y,
        ] == [1.0, 45.0, 2.0, 46.0]


def test_recompute_item_bbox_no_collection_id_clears_bbox(env):
    Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="M"
        )
        config = BuilderConfig(
            kind="map",
            map=MapConfig(
                basemap=BaseMap(style="https://demotiles.maplibre.org/style.json"),
                view=MapView(center=[0, 0], zoom=1),
                layers=[],
            ),
        )
        recompute_item_bbox(s, item=item, config=config, tenant_id=tenant.id)
        s.commit()
        assert item.bbox_min_x is None
