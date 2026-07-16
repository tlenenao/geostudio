# SPDX-License-Identifier: Apache-2.0
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


def test_get_sharing_requires_owner_or_admin(env):
    # get_sharing calls the same _require_share guard as put_sharing, but
    # every existing GET .../sharing call in this file runs as admin (after
    # a PUT) — the 403 branch on the read side was never exercised.
    app, client, _, admin, regular, _group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    _as(app, regular)  # lisible (publique) mais pas partageable
    r = client.get("/collections/incidents/sharing")
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


def test_put_sharing_unknown_group_is_404_and_keeps_existing(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.put("/collections/incidents/sharing",
               json={"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]})
    r = client.put("/collections/incidents/sharing",
                   json={"public": True, "groups": [{"groupId": "nope", "role": "viewer"}]})
    assert r.status_code == 404
    # Rien n'a été modifié : le partage existant survit, public reste False.
    body = client.get("/collections/incidents/sharing").json()
    assert body == {"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]}


def test_put_sharing_cross_tenant_group_is_404(env):
    app, client, Session, admin, _regular, group_id = env
    from app.tenants.models import Tenant
    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        outsider = get_or_create_user(s, tenant_id=other_tenant.id, oidc_sub="z",
                                      username="outsider", email=None,
                                      first_name="", last_name="")
        foreign_group = Group(id=uuid.uuid4().hex, tenant_id=other_tenant.id,
                              name="ailleurs", created_by=outsider.id)
        s.add(foreign_group)
        foreign_group_id = foreign_group.id
        s.commit()
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.put("/collections/incidents/sharing",
                   json={"public": False,
                         "groups": [{"groupId": foreign_group_id, "role": "viewer"}]})
    assert r.status_code == 404


def test_put_sharing_rejects_invalid_role(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.put("/collections/incidents/sharing",
                   json={"public": False, "groups": [{"groupId": group_id, "role": "owner"}]})
    assert r.status_code == 422


def test_put_sharing_duplicate_group_is_422(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.put("/collections/incidents/sharing", json={
        "public": False,
        "groups": [{"groupId": group_id, "role": "viewer"},
                   {"groupId": group_id, "role": "editor"}]})
    assert r.status_code == 422
