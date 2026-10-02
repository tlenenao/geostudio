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
        lambda session, table, tenant_id=None: None
    )
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    app.dependency_overrides[features_routes.get_features_repo] = lambda: make_repo()
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    for tn in ("roads", "rivers"):
        client.post("/v1/collections", json={"tableName": tn})
    return app, client


def test_search_cross_collection(env):
    app, client = env
    body = client.get("/v1/stac/search?limit=100").json()
    cols = {f["collection"] for f in body["features"]}
    assert cols == {"roads", "rivers"}
    assert len(body["features"]) == 4  # 2 + 2


def test_search_collections_filter(env):
    app, client = env
    body = client.get("/v1/stac/search?collections=rivers").json()
    assert {f["collection"] for f in body["features"]} == {"rivers"}


def test_search_pagination_token(env):
    app, client = env
    page1 = client.get("/v1/stac/search?limit=1").json()
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
    body = client.post("/v1/stac/search", json={"collections": ["roads"], "limit": 100}).json()
    assert {f["collection"] for f in body["features"]} == {"roads"}


def test_search_filter_preserved_across_pagination(env):
    app, client = env
    page1 = client.get("/v1/stac/search?collections=rivers&limit=1").json()
    assert len(page1["features"]) == 1
    assert page1["features"][0]["collection"] == "rivers"
    nxt = next(link["href"] for link in page1["links"] if link["rel"] == "next")
    assert "collections=rivers" in nxt
    page2 = client.get(nxt.replace("http://testserver", "")).json()
    assert len(page2["features"]) >= 1
    assert {f["collection"] for f in page2["features"]} == {"rivers"}


def test_search_post_rejects_zero_limit(env):
    app, client = env
    resp = client.post("/v1/stac/search", json={"limit": 0})
    assert resp.status_code == 422


def test_search_post_rejects_malformed_bbox(env):
    app, client = env
    resp = client.post("/v1/stac/search", json={"bbox": [1, 2, 3]})
    assert resp.status_code == 400


def test_search_post_accepts_valid_bbox(env):
    app, client = env
    resp = client.post("/v1/stac/search", json={"bbox": [0, 40, 2, 46], "collections": ["roads"]})
    assert resp.status_code == 200


def test_search_skips_broken_collection(env, monkeypatch):
    # P19.03 / j07-008 : une table disparue ne fait plus échouer toute la recherche.
    app, client = env
    monkeypatch.delitem(INFOS, "roads")
    resp = client.get("/v1/stac/search?limit=1000")
    assert resp.status_code == 200
    assert {f["collection"] for f in resp.json()["features"]} == {"rivers"}


def test_broken_collection_gives_stable_errors_not_500(env, monkeypatch):
    # P19.08 / j07-009 : STAC collection dégradée, items en 404 explicite.
    app, client = env
    monkeypatch.delitem(INFOS, "roads")
    assert client.get("/v1/stac/collections/roads").status_code == 200
    for path in ("/v1/stac/collections/roads/items", "/v1/collections/roads/items"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert r.json()["detail"] == "backing table not found"


def test_search_invalid_datetime_and_token_are_400(env):
    # P19.09 / j07-010 et P19.12 / j07-013
    app, client = env
    r = client.get("/v1/stac/search?datetime=garbage")
    assert r.status_code == 400 and "RFC 3339" in r.json()["detail"]
    assert client.post("/v1/stac/search", json={"datetime": "nope"}).status_code == 400
    assert client.get("/v1/stac/search?token=@@@").status_code == 400


def test_search_datetime_follows_declared_temporal_extent(env):
    # P19.10 / j07-011
    app, client = env
    patch = client.patch(
        "/v1/collections/roads", json={"temporalStart": "2020-01-01", "temporalEnd": "2020-12-31"}
    )
    assert patch.status_code == 200
    june = "datetime=2020-06-01T00:00:00Z/2020-06-30T00:00:00Z"
    cols = {f["collection"] for f in client.get(f"/v1/stac/search?{june}").json()["features"]}
    assert cols == {"roads"}
    later = client.get("/v1/stac/search?datetime=2021-06-01T00:00:00Z/..").json()["features"]
    assert {f["collection"] for f in later} == {"rivers"}
    props = client.get("/v1/stac/collections/roads/items").json()["features"][0]["properties"]
    assert props["datetime"].startswith("2020-01-01")
    assert props["end_datetime"].startswith("2020-12-31")


def test_collection_license_other_is_proprietary_with_license_link(env):
    # P19.11 / j07-012
    app, client = env
    client.patch(
        "/v1/collections/roads", json={"license": "other", "licenseUri": "https://e.org/l"}
    )
    doc = client.get("/v1/stac/collections/roads").json()
    assert doc["license"] == "proprietary"
    assert {"rel": "license", "href": "https://e.org/l"} in doc["links"]


def test_collection_patch_validates_dates_and_uris_on_write_only(env):
    # P19.13 / j07-014
    app, client = env
    bad_order = client.patch(
        "/v1/collections/roads", json={"temporalStart": "2021-01-01", "temporalEnd": "2020-01-01"}
    )
    assert bad_order.status_code == 422
    client.patch("/v1/collections/roads", json={"temporalStart": "2021-01-01"})
    assert (
        client.patch("/v1/collections/roads", json={"temporalEnd": "2020-01-01"}).status_code == 422
    )
    for body in ({"licenseUri": "javascript:alert(1)"}, {"contact": "pas un contact"}):
        assert client.patch("/v1/collections/roads", json=body).status_code == 422, body
    ok = client.patch(
        "/v1/collections/roads",
        json={"licenseUri": "https://e.org/l", "contact": "a@b.fr", "temporalEnd": "2021-06-01"},
    )
    assert ok.status_code == 200
    assert client.patch("/v1/collections/roads", json={"licenseUri": ""}).status_code == 200
