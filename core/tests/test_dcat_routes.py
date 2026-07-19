# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.dcat import routes as dcat_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="incidents", pk_column="id", geometry_column="geom",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="titre", type="string", required=True)])


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
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None)
    app.dependency_overrides[features_routes.get_rls_scope] = (
        lambda: features_routes.null_rls_scope)
    # ST_EstimatedExtent n'existe pas sur SQLite : stub d'emprise.
    app.dependency_overrides[dcat_routes.get_bbox_provider] = (
        lambda: lambda session, info: [1.0, 44.0, 2.0, 45.0])
    return app, TestClient(app), admin


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, *, public=False, description=""):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public,
                                      "description": description})


def test_catalog_content_type_and_shape(env):
    app, client, admin = env
    _register(app, client, admin, public=True, description="Réseau routier")
    resp = client.get("/dcat/catalog")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@type"] == "dcat:Catalog"
    assert len(body["dcat:dataset"]) == 1
    ds = body["dcat:dataset"][0]
    assert ds["dct:identifier"] == "incidents"
    assert ds["dct:description"] == "Réseau routier"
    assert ds["dct:accessRights"]["@id"].endswith("/PUBLIC")
    assert len(ds["dcat:distribution"]) == 2


def test_catalog_reflects_restricted_access_rights(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    resp = client.get("/dcat/catalog")  # vue admin : voit sa propre collection non publique
    ds = resp.json()["dcat:dataset"][0]
    assert ds["dct:accessRights"]["@id"].endswith("/RESTRICTED")


def test_dataset_detail_is_self_contained_with_context(env):
    app, client, admin = env
    _register(app, client, admin, public=True)
    resp = client.get("/dcat/datasets/incidents")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@context"] == {
        "dcat": "http://www.w3.org/ns/dcat#", "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/", "locn": "http://www.w3.org/ns/locn#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    assert body["dct:identifier"] == "incidents"


def test_dataset_detail_404_non_leaking(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    _as(app, admin)
    assert client.get("/dcat/datasets/nope").status_code == 404
    # Anonyme sur collection non publique → 404 non-fuyant.
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/dcat/datasets/incidents").status_code == 404


def test_anonymous_catalog_shows_public_only_no_leak(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    assert client.get("/dcat/catalog").json()["dcat:dataset"] == []
