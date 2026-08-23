# SPDX-License-Identifier: Apache-2.0
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
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


def fake_introspector(session, table_name):
    if table_name != "villes":
        raise TableNotFound(table_name)
    return INFO


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(tmp_path):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table: None
    )

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        fake_duckdb_factory
    )
    monkeypatch_base_uri = str(tmp_path)
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: monkeypatch_base_uri

    client = TestClient(app)
    return app, client, admin, regular, tmp_path, tenant_id


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    return client.post("/collections", json={"tableName": "villes", "isPublic": public}).json()


def test_aggregate_returns_wide_rows_for_a_readable_collection(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
            {
                "id": 2,
                "region": "Sud",
                "pop": 5,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1, 1),
            },
        ],
    )

    response = client.post(
        f"/collections/{col['id']}/aggregate",
        json={"groupBy": "region", "agg": "sum", "field": "pop"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["categoryKey"] == "region"
    assert sorted(body["rows"], key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10},
        {"region": "Sud", "value": 5},
    ]


def test_aggregate_on_unregistered_collection_returns_404(env):
    _app, client, _admin, regular, _tmp_path, _tenant_id = env
    _as(_app, regular)
    response = client.post("/collections/does-not-exist/aggregate", json={"groupBy": "region"})
    assert response.status_code == 404


def test_aggregate_on_private_collection_by_non_owner_returns_404(env):
    app, client, admin, regular, _tmp_path, _tenant_id = env
    col = _register(app, client, admin, public=False)
    _as(app, regular)
    response = client.post(f"/collections/{col['id']}/aggregate", json={"groupBy": "region"})
    assert response.status_code == 404  # cohérent avec GET /collections/{id}/items


def test_aggregate_unknown_group_by_field_returns_400(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
        ],
    )
    response = client.post(f"/collections/{col['id']}/aggregate", json={"groupBy": "inconnu"})
    assert response.status_code == 400


def test_aggregate_sample_returns_bare_values(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 42,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
        ],
    )

    response = client.post(
        f"/collections/{col['id']}/aggregate", json={"field": "pop", "sample": 10}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["categoryKey"] == "value"
    assert body["rows"] == [{"value": 42.0}]
