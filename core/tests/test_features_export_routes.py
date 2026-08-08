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

INFO = TableInfo(table_name="villes", pk_column="id", geometry_column="geometry",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="region", type="string", required=True),
                          ColumnInfo(name="pop", type="integer", required=True)])


def fake_introspector(session, table_name):
    if table_name != "villes":
        raise TableNotFound(table_name)
    return INFO


def make_fake_items_repo():
    # Task 3's fixture never wrote to the fake sqlite-backed "villes" table
    # (get_ddl_applier is a no-op, and the real repository's raw SQL relies
    # on PostGIS-only functions such as set_config for RLS) — only to the
    # CDC parquet lake via _seed(). Task 4's items export needs a real
    # write-then-read round trip through repo.insert_feature/select_features,
    # so a minimal in-memory fake stands in for the real repository here,
    # same pattern as make_fake_repo() in test_features_routes_read.py.
    state = {"rows": {}, "next": 1}

    def insert_feature(session, info, *, properties, geometry):
        fid = state["next"]
        state["next"] += 1
        state["rows"][fid] = {"properties": dict(properties), "geometry": geometry}
        return fid

    def select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None):
        items = sorted(state["rows"].items())
        page_items = items[offset:offset + limit]
        features = [
            {"type": "Feature", "id": fid, "properties": v["properties"], "geometry": v["geometry"]}
            for fid, v in page_items
        ]
        return FeaturePage(features=features, number_matched=len(items), number_returned=len(features))

    def get_feature(session, info, *, fid):
        v = state["rows"].get(int(fid))
        if v is None:
            return None
        return {"type": "Feature", "id": int(fid), "properties": v["properties"], "geometry": v["geometry"]}

    return SimpleNamespace(insert_feature=insert_feature, select_features=select_features,
                           get_feature=get_feature, state=state)


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-07"
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
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (lambda session, table: None)
    fake_items_repo = make_fake_items_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_items_repo
    # SQLite ne connaît pas set_config (GUC PostGIS RLS) : neutraliser le
    # scope, même patron que test_features_routes_read.py.
    app.dependency_overrides[features_routes.get_rls_scope] = (
        lambda: features_routes.null_rls_scope)

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: fake_duckdb_factory
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)

    client = TestClient(app)
    return app, client, admin, regular, tmp_path, tenant_id, Session


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    return client.post("/collections", json={"tableName": "villes", "isPublic": public}).json()


def _seed(tmp_path, tenant_id, collection_id):
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=collection_id, rows=[
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)},
        {"id": 2, "region": "Sud", "pop": 5, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(1, 1)},
    ])


def test_export_aggregate_csv_returns_a_csv_attachment(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert 'attachment; filename="' in resp.headers["content-disposition"]
    assert "region,value" in resp.text or "region" in resp.text.splitlines()[0]


def test_export_aggregate_xlsx_returns_an_xlsx_attachment(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    resp = client.post(f"/collections/{col['id']}/export?format=xlsx", json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_export_aggregate_rejects_unknown_format(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    resp = client.post(f"/collections/{col['id']}/export?format=pdf", json={"groupBy": "region"})
    assert resp.status_code == 400


def test_export_aggregate_requires_authentication(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    assert resp.status_code == 401


def test_export_aggregate_denies_a_user_without_read_access(env):
    # get_readable_collection() is deliberately 404-before-403 ("une collection
    # illisible est indistinguable d'une absente" — core/app/collections/routes.py):
    # the plan text for this test asserted 403, but that contradicts the actual,
    # reused-verbatim permission check (see sibling
    # test_aggregate_on_private_collection_by_non_owner_returns_404 in
    # test_features_aggregate_routes.py). Asserting the real behaviour here.
    app, client, admin, regular, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=False)
    _as(app, regular)
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    assert resp.status_code == 404


def test_export_aggregate_writes_an_audit_log_row(env):
    app, client, admin, _r, tmp_path, tenant_id, Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    with Session() as s:
        from app.audit.models import AuditLog
        rows = s.query(AuditLog).filter_by(action="export.run").all()
    assert len(rows) == 1
    assert rows[0].payload == {"format": "csv", "mode": "aggregate"}
    assert rows[0].object_id == col["id"]


def test_export_items_geojson_returns_a_feature_collection(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    # items export reads from the live PostGIS-backed collection table via
    # select_features, not the GeoParquet CDC lake used by aggregate — but
    # this fixture never wrote actual rows to the fake sqlite-backed
    # collection table, only to the CDC parquet lake (_seed). To exercise
    # the items path meaningfully, create features through the normal write
    # route first.
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "type": "Feature",
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=geojson")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/geo+json"
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["region"] == "Nord"


def test_export_items_csv_flattens_properties(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "type": "Feature",
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 200
    assert "Nord" in resp.text
    assert "geometry" not in resp.text.splitlines()[0]


def test_export_items_gpkg_returns_a_sqlite_container(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "type": "Feature",
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_rejects_unknown_format(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    resp = client.get(f"/collections/{col['id']}/export/items?format=pdf")
    assert resp.status_code == 400


def test_export_items_caps_at_10000_entities(env, monkeypatch):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    import app.features.routes as routes_module
    monkeypatch.setattr(routes_module, "EXPORT_ITEMS_CAP", 1)
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "type": "Feature",
        "properties": {"region": "Nord", "pop": 1}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    client.post(f"/collections/{col['id']}/items", json={
        "type": "Feature",
        "properties": {"region": "Sud", "pop": 2}, "geometry": {"type": "Point", "coordinates": [1, 1]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 413
