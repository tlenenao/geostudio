# SPDX-License-Identifier: Apache-2.0
"""AUD-062 : requêtes SQL Lab enregistrées (CRUD privé, privilège SQL Lab, audit, RGPD)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user
from app.compliance.export import export_user_data
from app.compliance.service import anonymize_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.saved_queries.models import SavedQuery
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _user(s, tenant_id, sub, **kw):
    return get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
        **kw,
    )


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        tenant = get_or_create_default_tenant(s)
        _user(s, tenant.id, "admin", bootstrap_admin=True)
        alice = _user(s, tenant.id, "alice", bootstrap_analyst=True)
        bob = _user(s, tenant.id, "bob", bootstrap_analyst=True)
        reader = _user(s, tenant.id, "reader")
        s.commit()
        users = {"alice": alice, "bob": bob, "reader": reader}
    app = create_app()

    def override_session():
        with request_scoped_session(factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    def as_user(name):
        app.dependency_overrides[get_current_user] = lambda: users[name]

    return client, as_user, factory, users


def test_crud_roundtrip_is_audited(env):
    client, as_user, factory, _ = env
    as_user("alice")
    created = client.post("/v1/analytics/sql/saved", json={"name": "Top villes", "sql": "SELECT 1"})
    assert created.status_code == 201
    qid = created.json()["id"]
    assert client.get("/v1/analytics/sql/saved").json()[0]["name"] == "Top villes"
    upd = client.put(f"/v1/analytics/sql/saved/{qid}", json={"name": "Top 10", "sql": "SELECT 2"})
    assert upd.status_code == 200 and upd.json()["sql"] == "SELECT 2"
    assert client.delete(f"/v1/analytics/sql/saved/{qid}").status_code == 204
    assert client.get("/v1/analytics/sql/saved").json() == []
    with factory() as s:
        actions = [
            a.action
            for a in s.scalars(select(AuditLog).where(AuditLog.object_type == "saved_query"))
        ]
    assert sorted(actions) == ["saved_query.create", "saved_query.delete", "saved_query.update"]


def test_queries_are_private_to_their_author(env):
    client, as_user, _, _ = env
    as_user("alice")
    qid = client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "SELECT 1"}).json()["id"]
    as_user("bob")
    assert client.get("/v1/analytics/sql/saved").json() == []
    body = {"name": "x", "sql": "SELECT 9"}
    assert client.put(f"/v1/analytics/sql/saved/{qid}", json=body).status_code == 404
    assert client.delete(f"/v1/analytics/sql/saved/{qid}").status_code == 404
    # Le même nom reste libre pour un autre auteur.
    assert client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "S"}).status_code == 201


def test_requires_sql_lab_privilege(env):
    client, as_user, _, _ = env
    as_user("reader")
    assert client.get("/v1/analytics/sql/saved").status_code == 403
    assert client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "S"}).status_code == 403


def test_duplicate_name_and_validation(env):
    client, as_user, _, _ = env
    as_user("alice")
    assert client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "S"}).status_code == 201
    assert client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "T"}).status_code == 409
    assert client.post("/v1/analytics/sql/saved", json={"name": "", "sql": "S"}).status_code == 422


def test_per_user_cap(env, monkeypatch):
    from app.saved_queries import routes

    monkeypatch.setattr(routes, "MAX_PER_USER", 1)
    client, as_user, _, _ = env
    as_user("alice")
    assert client.post("/v1/analytics/sql/saved", json={"name": "a", "sql": "S"}).status_code == 201
    assert client.post("/v1/analytics/sql/saved", json={"name": "b", "sql": "S"}).status_code == 409


def test_rgpd_export_and_anonymization(env):
    client, as_user, factory, users = env
    as_user("alice")
    client.post("/v1/analytics/sql/saved", json={"name": "mine", "sql": "SELECT 42"})
    with factory() as s:
        export = export_user_data(s, tenant_id=users["alice"].tenant_id, user_id=users["alice"].id)
        assert export["savedQueries"][0]["sql"] == "SELECT 42"
        anonymize_user(s, tenant_id=users["alice"].tenant_id, user_id=users["alice"].id)
        s.commit()
        assert s.scalars(select(SavedQuery)).all() == []
