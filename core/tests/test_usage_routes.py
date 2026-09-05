# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="c",
            username="creator",
            email=None,
            first_name="",
            last_name="",
        )  # rôle "creator" par défaut -> porte tasks.view, pas tasks.view_all
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
        reader_role = create_role(s, tenant_id=tenant.id, name="Sans tâches", privileges=[])
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        reader.role_id = reader_role.id
        s.commit()
        write_audit(
            s,
            tenant_id=tenant.id,
            actor_id=creator.id,
            actor_kind="user",
            action="pipeline.run",
            object_type="pipeline",
            object_id="p1",
        )
        write_audit(
            s,
            tenant_id=tenant.id,
            actor_id=admin.id,
            actor_kind="user",
            action="export.run",
            object_type="dataset",
            object_id="d1",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, creator, admin, reader


def _as(app, Session, user):
    def override_user():
        with Session() as s:
            yield s.get(User, user.id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user


def test_tasks_view_holder_sees_only_own_actions(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["tasks"][0]["action"] == "pipeline.run"
    assert body["tasks"][0]["actorId"] == creator.id


def test_tasks_view_holder_gets_403_on_explicit_other_actor_id(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get(f"/usage/tasks?actorId={admin.id}")
    assert resp.status_code == 403


def test_tasks_view_all_holder_sees_every_actor(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, admin)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_no_tasks_privilege_is_rejected(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, reader)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 403


def test_summary_requires_tasks_view_all_not_just_tasks_view(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get("/usage/summary")
    assert resp.status_code == 403

    _as(app, Session, admin)
    resp = client.get("/usage/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totalActions"] == 2
    assert len(body["byActor"]) == 2
