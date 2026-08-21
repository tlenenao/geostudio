# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

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

INFOS = {
    "roads": TableInfo(
        table_name="roads",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="n", type="string", required=False)],
    ),
    "rivers": TableInfo(
        table_name="rivers",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="n", type="string", required=False)],
    ),
}


def fake_introspector(session, table_name):
    if table_name not in INFOS:
        raise TableNotFound(table_name)
    return INFOS[table_name]


def feat(fid):
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {"type": "Point", "coordinates": [1.0, 44.0]},
        "properties": {},
    }


def make_repo():
    # Chaque collection a 2 features (ids 1,2). matched=2 par collection.
    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        rows = [feat(1), feat(2)][offset : offset + limit]
        return FeaturePage(features=rows, number_matched=2, number_returned=len(rows))

    def get_feature(session, info, *, fid):
        return None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature)


@pytest.fixture()
def env():
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
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table: None
    )
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    app.dependency_overrides[features_routes.get_features_repo] = lambda: make_repo()
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    for tn in ("roads", "rivers"):
        client.post("/collections", json={"tableName": tn})
    return app, client


def test_search_cross_collection(env):
    app, client = env
    body = client.get("/stac/search?limit=100").json()
    cols = {f["collection"] for f in body["features"]}
    assert cols == {"roads", "rivers"}
    assert len(body["features"]) == 4  # 2 + 2


def test_search_collections_filter(env):
    app, client = env
    body = client.get("/stac/search?collections=rivers").json()
    assert {f["collection"] for f in body["features"]} == {"rivers"}


def test_search_pagination_token(env):
    app, client = env
    page1 = client.get("/stac/search?limit=1").json()
    assert len(page1["features"]) == 1
    nxt = next(link["href"] for link in page1["links"] if link["rel"] == "next")
    page2 = client.get(nxt.replace("http://testserver", "")).json()
    assert len(page2["features"]) >= 1
    # Les deux pages ne renvoient pas exactement le même item du même collection.
    assert (page1["features"][0]["id"], page1["features"][0]["collection"]) != (
        page2["features"][0]["id"],
        page2["features"][0]["collection"],
    )


def test_search_post_body(env):
    app, client = env
    body = client.post("/stac/search", json={"collections": ["roads"], "limit": 100}).json()
    assert {f["collection"] for f in body["features"]} == {"roads"}


def test_search_filter_preserved_across_pagination(env):
    app, client = env
    page1 = client.get("/stac/search?collections=rivers&limit=1").json()
    assert len(page1["features"]) == 1
    assert page1["features"][0]["collection"] == "rivers"
    nxt = next(link["href"] for link in page1["links"] if link["rel"] == "next")
    assert "collections=rivers" in nxt
    page2 = client.get(nxt.replace("http://testserver", "")).json()
    assert len(page2["features"]) >= 1
    assert {f["collection"] for f in page2["features"]} == {"rivers"}


def test_search_post_rejects_zero_limit(env):
    app, client = env
    resp = client.post("/stac/search", json={"limit": 0})
    assert resp.status_code == 422


def test_search_post_rejects_malformed_bbox(env):
    app, client = env
    resp = client.post("/stac/search", json={"bbox": [1, 2, 3]})
    assert resp.status_code == 400


def test_search_post_accepts_valid_bbox(env):
    app, client = env
    resp = client.post("/stac/search", json={"bbox": [0, 40, 2, 46], "collections": ["roads"]})
    assert resp.status_code == 200
