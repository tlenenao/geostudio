# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import duckdb
import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FeaturePage
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-features-guest-access-secret-pad"

FEAT = {"type": "Feature", "id": 1, "geometry": None, "properties": {"titre": "a"}}


def _table_info(table_name: str) -> TableInfo:
    # register_collection() insère info.table_name (pas body.tableName) :
    # une TableInfo au table_name figé casserait l'enregistrement de la
    # seconde collection ("other") par collision d'unicité sur la première
    # ("incidents") — cf. app/collections/routes.py::register_collection.
    return TableInfo(
        table_name=table_name,
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="titre", type="string", required=True)],
    )


def fake_introspector(session, table_name):
    if table_name not in ("incidents", "other"):
        raise TableNotFound(table_name)
    return _table_info(table_name)


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    # aggregate_features lit un GeoParquet CDC réel (app.analytics.aggregate,
    # SP-11b) — le fournir vraiment est plus simple/fidèle qu'un double fake
    # de duckdb. Patron identique à test_features_aggregate_routes.py.
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geom", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def fake_repo():
    def select_features(
        session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None
    ):
        return FeaturePage(features=[FEAT], number_matched=1, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature)


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env(tmp_path):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table, tenant_id=None: None
    )
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo()
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        fake_duckdb_factory
    )
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, owner, tmp_path, tenant_id


def _register(client, table_name: str):
    client.post("/v1/collections", json={"tableName": table_name, "isPublic": False})


def _create_app_config(client, *, layer: str) -> str:
    body = {
        "kind": "app",
        "dataSources": [
            {"id": "ds1", "type": "features", "service": "core", "layer": layer, "query": {}}
        ],
        "layout": {"type": "grid", "items": []},
    }
    return client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]


def _mint_token(client, item_id: str) -> str:
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    return created["url"].rsplit("/", 1)[-1]


def test_guest_token_reads_features_of_a_referenced_private_collection(env):
    app, client, _owner, tmp_path, tenant_id = env
    _register(client, "incidents")
    _register(client, "other")
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id="incidents",
        rows=[
            {"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geom": Point(0, 0)},
        ],
    )
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/incidents/items", headers={"X-Share-Link-Token": token})
    assert r.status_code == 200
    assert r.json()["numberReturned"] == 1

    r2 = client.get("/v1/collections/incidents/items/1", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 200

    r3 = client.post(
        "/v1/collections/incidents/aggregate",
        json={"agg": "count"},
        headers={"X-Share-Link-Token": token},
    )
    assert r3.status_code == 200


def test_guest_token_does_not_grant_access_to_an_unreferenced_private_collection(env):
    app, client, _owner, _tmp_path, _tenant_id = env
    _register(client, "incidents")
    _register(client, "other")
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/other/items", headers={"X-Share-Link-Token": token})
    assert r.status_code == 404

    r2 = client.get("/v1/collections/other/items/1", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 404

    r3 = client.post(
        "/v1/collections/other/aggregate",
        json={"agg": "count"},
        headers={"X-Share-Link-Token": token},
    )
    assert r3.status_code == 404


def test_export_routes_still_require_a_real_user_even_with_a_guest_token(env):
    app, client, _owner, _tmp_path, _tenant_id = env
    _register(client, "incidents")
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/incidents/export/items?format=csv",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 401
