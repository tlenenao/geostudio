# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.notifications import repository as notifications_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        other_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), Session, tenant, user, other_user


@pytest.fixture()
def client():
    return _make_client()


def test_get_notifications_returns_only_the_caller_s_own(client):
    api, Session, tenant, user, other_user = client
    with Session() as s:
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="pipeline",
            status="failure",
            item_id=None,
            item_resource_type="pipeline",
            item_title="Pipeline A",
        )
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=other_user.id,
            kind="pipeline",
            status="failure",
            item_id=None,
            item_resource_type="pipeline",
            item_title="Pipeline B",
        )
        s.commit()

    res = api.get("/v1/notifications")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["notifications"][0]["itemTitle"] == "Pipeline A"


def test_unread_count_reflects_current_preference(client):
    api, Session, tenant, user, _other = client
    with Session() as s:
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="export",
            status="success",
            item_id=None,
            item_resource_type="map",
            item_title="Carte",
        )
        s.commit()

    assert api.get("/v1/notifications/unread-count").json() == {"count": 1}
    patch = api.patch("/v1/notifications/preference", json={"value": "failures_only"})
    assert patch.status_code == 200
    assert api.get("/v1/notifications/unread-count").json() == {"count": 0}


def test_patch_preference_rejects_unknown_value(client):
    api, *_ = client
    res = api.patch("/v1/notifications/preference", json={"value": "bogus"})
    assert res.status_code == 400


def test_mark_read_then_read_all(client):
    api, Session, tenant, user, _other = client
    with Session() as s:
        n1 = notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="report",
            status="success",
            item_id=None,
            item_resource_type="report",
            item_title="Rapport",
        )
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="appexport",
            status="failure",
            item_id=None,
            item_resource_type="app",
            item_title="App",
        )
        s.commit()
        n1_id = n1.id

    read_res = api.post(f"/v1/notifications/{n1_id}/read")
    assert read_res.status_code == 200
    assert read_res.json()["readAt"] is not None
    assert api.get("/v1/notifications/unread-count").json() == {"count": 1}

    all_res = api.post("/v1/notifications/read-all")
    assert all_res.status_code == 204
    assert api.get("/v1/notifications/unread-count").json() == {"count": 0}


def test_mark_read_unknown_id_is_404(client):
    api, *_ = client
    res = api.post("/v1/notifications/does-not-exist/read")
    assert res.status_code == 404
