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
from app.stac import routes as stac_routes
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="incidents",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


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
    # ST_EstimatedExtent n'existe pas sur SQLite : stub d'emprise.
    app.dependency_overrides[stac_routes.get_bbox_provider] = lambda: (
        lambda session, info: [1.0, 44.0, 2.0, 45.0]
    )
    return app, TestClient(app), admin


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_landing_advertises_conformance(env):
    app, client, _admin = env
    body = client.get("/stac").json()
    assert body["type"] == "Catalog"
    assert "https://api.stacspec.org/v1.0.0/item-search" in body["conformsTo"]


def test_conformance_endpoint(env):
    app, client, _admin = env
    body = client.get("/stac/conformance").json()
    assert "https://api.stacspec.org/v1.0.0/core" in body["conformsTo"]


def test_collections_list_shows_registered(env):
    app, client, admin = env
    _register(app, client, admin)
    body = client.get("/stac/collections").json()
    ids = [c["id"] for c in body["collections"]]
    assert "incidents" in ids
    assert body["collections"][0]["license"] == "other"


def test_collection_detail_and_leakproof_404(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    _as(app, admin)
    assert client.get("/stac/collections/incidents").json()["id"] == "incidents"
    assert client.get("/stac/collections/nope").status_code == 404
    # Anonyme sur collection non publique → 404 non-fuyant.
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/stac/collections/incidents").status_code == 404


def test_anonymous_lists_public_only(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    assert client.get("/stac/collections").json()["collections"] == []


FEAT = {
    "type": "Feature",
    "id": 1,
    "geometry": {"type": "Point", "coordinates": [1.0, 44.0]},
    "properties": {"titre": "a"},
}


def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox)
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature, calls=calls)


@pytest.fixture()
def env_repo(env):
    app, client, admin = env
    repo = make_fake_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: repo
    return app, client, admin, repo


def test_items_returns_stac_item_collection_with_next(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    body = client.get("/stac/collections/incidents/items?limit=1&offset=0").json()
    assert body["type"] == "FeatureCollection"
    it = body["features"][0]
    assert it["stac_version"] == "1.0.0" and it["collection"] == "incidents"
    assert it["properties"]["datetime"].endswith("Z")
    rels = {l["rel"]: l["href"] for l in body["links"]}
    assert "offset=1" in rels["next"]  # 1 renvoyé sur 3 → next
    assert repo.calls["limit"] == 1 and repo.calls["offset"] == 0


def test_items_bbox_forwarded(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    client.get("/stac/collections/incidents/items?bbox=0,40,2,46")
    assert repo.calls["bbox"] == (0.0, 40.0, 2.0, 46.0)


def test_single_item_and_404(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    assert client.get("/stac/collections/incidents/items/1").json()["id"] == "1"
    assert client.get("/stac/collections/incidents/items/999").status_code == 404
