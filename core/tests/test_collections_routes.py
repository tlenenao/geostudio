import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INCIDENTS = TableInfo(
    table_name="incidents", pk_column="id", geometry_column="geom",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INCIDENTS


@pytest.fixture()
def env():
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
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    ddl_calls: list[str] = []
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: ddl_calls.append(table)
    )
    client = TestClient(app)
    return app, client, Session, admin, regular, ddl_calls


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_register_requires_admin(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, regular)
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 403


def test_register_and_get(env):
    app, client, _, admin, _regular, ddl_calls = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "incidents", "title": "Incidents"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "incidents" and body["geometryType"] == "Point"
    assert ddl_calls == ["incidents"]  # la RLS est appliquée à l'enregistrement
    assert client.get("/collections/incidents").status_code == 200


def test_register_unknown_table_400_and_duplicate_409(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    assert client.post("/collections", json={"tableName": "nope"}).status_code == 400
    client.post("/collections", json={"tableName": "incidents"})
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 409


def test_register_core_table_refused(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    # La denylist (Base.metadata + alembic_version) court-circuite AVANT l'introspection.
    assert client.post("/collections", json={"tableName": "items"}).status_code == 400
    assert client.post("/collections", json={"tableName": "alembic_version"}).status_code == 400


def test_private_collection_hidden_from_stranger_and_anonymous(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 404
    assert client.get("/collections").json()["collections"] == []
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)  # anonyme
    assert client.get("/collections").json()["collections"] == []
    assert client.get("/collections/incidents").status_code == 404


def test_public_collection_visible_to_anonymous(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    body = client.get("/collections").json()
    assert [c["id"] for c in body["collections"]] == ["incidents"]


def test_patch_and_delete(env):
    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.patch("/collections/incidents", json={"title": "Renommé", "isPublic": True})
    assert r.status_code == 200 and r.json()["title"] == "Renommé"
    _as(app, regular)
    assert client.delete("/collections/incidents").status_code == 403
    _as(app, admin)
    assert client.delete("/collections/incidents").status_code == 204
    assert client.get("/collections/incidents").status_code == 404


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch("/collections/incidents", json={"title": "X"})
    client.delete("/collections/incidents")
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    for expected in ("collection.create", "collection.update", "collection.delete"):
        assert expected in actions
