# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.collections.repository import get_collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
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


def make_fake_write_repo():
    state = {"rows": {1: {"titre": "a"}}, "next": 2}

    def insert_feature(session, info, *, properties, geometry):
        if properties.get("titre") == "conflit":
            raise IntegrityError("dup", None, Exception("pk"))
        fid = state["next"]
        state["next"] += 1
        state["rows"][fid] = properties
        return fid

    def replace_feature(session, info, *, fid, properties, geometry):
        if fid == "1":
            state["rows"][1] = properties
            return True
        return False

    def delete_feature(session, info, *, fid):
        if fid == "1" and 1 in state["rows"]:
            del state["rows"][1]
            return True
        return False

    def select_features(session, info, **kw):  # inutilisé dans ce fichier
        raise AssertionError("read path should not be called")

    def get_feature(session, info, *, fid):
        return None

    return SimpleNamespace(
        insert_feature=insert_feature,
        replace_feature=replace_feature,
        delete_feature=delete_feature,
        select_features=select_features,
        get_feature=get_feature,
        state=state,
    )


VALID = {"type": "Feature", "properties": {"titre": "Nid de poule"}, "geometry": None}


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
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table: None
    )
    app.dependency_overrides[collections_routes.get_feature_counter] = lambda: (
        lambda session, table_name: 0
    )
    fake_repo = make_fake_write_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo
    # SQLite ne connaît ni SET LOCAL ROLE ni set_config : neutraliser le scope.
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    client = TestClient(app)
    return app, client, Session, admin, regular, fake_repo


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_anonymous_write_is_401(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin, public=True)
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.post("/collections/incidents/items", json=VALID).status_code == 401


def test_viewer_write_is_403_editor_ok(env):
    # regular lisible via isPublic mais sans rôle editor → 403 ;
    # admin (pleins droits collections) → 201 + Location.
    app, client, Session, admin, regular, _repo = env
    _register(app, client, admin, public=True)
    _as(app, regular)
    assert client.post("/collections/incidents/items", json=VALID).status_code == 403
    _as(app, admin)
    r = client.post("/collections/incidents/items", json=VALID)
    assert r.status_code == 201
    assert r.headers["Location"].endswith("/collections/incidents/items/2")


def test_non_owner_write_on_private_collection_is_404_not_403(env):
    # `_get_writable` calls `get_readable_collection` first (404-before-403,
    # same helper as app/collections/routes.py) — a user who cannot even
    # read the (private, unshared) collection must get 404, not 403, on
    # every write verb. Only the "can read (public) but not write" 403 case
    # was covered before this review (test_viewer_write_is_403_editor_ok);
    # this closes the "cannot even read" branch.
    app, client, Session, admin, regular, _repo = env
    _register(app, client, admin, public=False)
    _as(app, regular)
    assert client.post("/collections/incidents/items", json=VALID).status_code == 404
    assert client.put("/collections/incidents/items/1", json=VALID).status_code == 404
    assert client.delete("/collections/incidents/items/1").status_code == 404


def test_not_editable_collection_is_403(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/collections/incidents", json={"editable": False})
    r = client.post("/collections/incidents/items", json=VALID)
    assert r.status_code == 403 and r.json()["detail"] == "collection is not editable"


def test_validation_errors_are_structured_400(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    r = client.post(
        "/collections/incidents/items", json={"type": "Feature", "properties": {"inconnu": 1}}
    )
    assert r.status_code == 400
    codes = {(e["field"], e["code"]) for e in r.json()["detail"]["errors"]}
    assert ("inconnu", "unknown_property") in codes and ("titre", "missing_required") in codes


def test_pk_conflict_is_409(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    r = client.post(
        "/collections/incidents/items", json={"type": "Feature", "properties": {"titre": "conflit"}}
    )
    assert r.status_code == 409


def test_put_and_delete(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    assert client.put("/collections/incidents/items/1", json=VALID).status_code == 204
    assert client.put("/collections/incidents/items/999", json=VALID).status_code == 404
    assert client.delete("/collections/incidents/items/1").status_code == 204
    assert client.delete("/collections/incidents/items/999").status_code == 404


def test_writes_are_audited(env):
    # `Session` est la factory retournée par la fixture (adaptation n°1).
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.post("/collections/incidents/items", json=VALID)
    client.put("/collections/incidents/items/1", json=VALID)
    client.delete("/collections/incidents/items/1")
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"feature.create", "feature.update", "feature.delete"} <= actions


def _feature_count(Session, collection_id="incidents"):
    with Session() as s:
        return get_collection(s, tenant_id="default", collection_id=collection_id).feature_count


def test_create_and_delete_maintain_feature_count(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    assert _feature_count(Session) == 0
    client.post("/collections/incidents/items", json=VALID)
    assert _feature_count(Session) == 1
    client.delete("/collections/incidents/items/1")
    assert _feature_count(Session) == 0


def test_put_does_not_change_feature_count(env):
    app, client, Session, admin, _r, _repo = env
    _register(app, client, admin)
    _as(app, admin)
    client.put("/collections/incidents/items/1", json=VALID)
    assert _feature_count(Session) == 0  # remplacement, pas de création
