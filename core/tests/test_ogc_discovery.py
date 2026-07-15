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
from app.features.repository import FeaturePage, FilterError
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="incidents", pk_column="id", geometry_column="geom",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="titre", type="string", required=True)])

FEAT = {"type": "Feature", "id": 1, "geometry": None, "properties": {"titre": "a"}}

CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
]


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox, filters=filters)
        if filters and "inconnu" in filters:
            raise FilterError("inconnu", "unknown filter property 'inconnu'")
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature,
                           calls=calls)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r",
                                     username="regular", email=None,
                                     first_name="", last_name="")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None)
    fake_repo = make_fake_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo
    # SQLite ne connaît ni SET LOCAL ROLE ni set_config : neutraliser le scope.
    app.dependency_overrides[features_routes.get_rls_scope] = (
        lambda: features_routes.null_rls_scope)
    app.dependency_overrides[collections_routes.get_extent_provider] = (
        lambda: lambda session, info, tenant_id: [1.0, 45.0, 2.0, 46.0])
    client = TestClient(app)
    return app, client, admin, regular, fake_repo


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_landing_page_wins_over_mcp_mount(env):
    _app, client, *_ = env
    r = client.get("/")
    assert r.status_code == 200
    rels = {l["rel"] for l in r.json()["links"]}
    assert {"self", "conformance", "data", "service-desc"} <= rels
    assert client.get("/health").status_code == 200  # le mount MCP n'est pas cassé


def test_conformance(env):
    _app, client, *_ = env
    assert client.get("/conformance").json()["conformsTo"] == CONFORMANCE_CLASSES


def test_collection_description_is_ogc(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)
    body = client.get("/collections/incidents").json()
    assert body["itemType"] == "feature"
    assert body["extent"] == {"spatial": {"bbox": [[1.0, 45.0, 2.0, 46.0]]}}
    rels = {l["rel"]: l["href"] for l in body["links"]}
    assert rels["items"].endswith("/collections/incidents/items")


def test_extent_failure_degrades_to_none(env, caplog):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)

    def broken_provider(session, info, tenant_id):
        raise TableNotFound("gone")

    app.dependency_overrides[collections_routes.get_extent_provider] = (
        lambda: broken_provider)
    body = client.get("/collections/incidents").json()
    assert body["extent"] is None
    assert "extent lookup failed" in caplog.text


def test_extent_code_bug_is_not_swallowed(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)

    def buggy_provider(session, info, tenant_id):
        raise TypeError("bug")

    app.dependency_overrides[collections_routes.get_extent_provider] = (
        lambda: buggy_provider)
    # TestClient propage les exceptions non-HTTP (raise_server_exceptions=True
    # par défaut) : un bug de code doit remonter, pas être avalé en extent=None.
    with pytest.raises(TypeError):
        client.get("/collections/incidents")
