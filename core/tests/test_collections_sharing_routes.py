import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import Group, GroupMember
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
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="equipe",
                      created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=regular.id, tenant_id=tenant.id))
        group_id = group.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None
    )
    client = TestClient(app)
    return app, client, Session, admin, regular, group_id


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user

# (Adapter les constructeurs Group/GroupMember aux colonnes réelles de
#  app/sharing/models.py si elles diffèrent — vérifier le fichier avant d'écrire.)


def test_share_grants_read_to_group_member(env):
    app, client, Session, admin, regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 404
    _as(app, admin)
    r = client.put("/collections/incidents/sharing",
                   json={"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]})
    assert r.status_code == 200
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 200
    assert [c["id"] for c in client.get("/collections").json()["collections"]] == ["incidents"]


def test_put_sharing_replaces_all(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.put("/collections/incidents/sharing",
               json={"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]})
    client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    body = client.get("/collections/incidents/sharing").json()
    assert body == {"public": True, "groups": []}


def test_sharing_requires_owner_or_admin(env):
    app, client, _, admin, regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    _as(app, regular)  # lisible (publique) mais pas partageable
    r = client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403


def test_share_is_audited(env):
    app, client, Session, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        assert "collection.share" in list(s.scalars(select(AuditLog.action)))


def test_put_sharing_rejects_invalid_role(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.put("/collections/incidents/sharing",
                   json={"public": False, "groups": [{"groupId": group_id, "role": "owner"}]})
    assert r.status_code == 422
