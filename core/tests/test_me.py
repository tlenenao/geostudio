# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client(*, username: str, oidc_sub: str, bootstrap_admin: bool = False) -> TestClient:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub=oidc_sub,
            username=username,
            email=f"{username}@example.com",
            first_name="Alice",
            last_name="Doe",
            bootstrap_admin=bootstrap_admin,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def client():
    return _make_client(username="alice", oidc_sub="sub-1")


@pytest.fixture()
def admin_client():
    return _make_client(username="admin", oidc_sub="sub-admin", bootstrap_admin=True)


def _make_analyst_client() -> TestClient:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-analyst",
            username="analyst",
            email="analyst@example.com",
            first_name="Ana",
            last_name="Lyst",
            bootstrap_analyst=True,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def analyst_client():
    return _make_analyst_client()


def test_get_me_returns_the_resolved_user(client):
    response = client.get("/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert body["firstName"] == "Alice"
    assert body["isAdmin"] is False
    assert body["isAnalyst"] is False


def test_get_me_reflects_admin_flag(admin_client):
    response = admin_client.get("/me")
    assert response.json()["isAdmin"] is True


def test_me_exposes_is_analyst(analyst_client):
    response = analyst_client.get("/me")
    assert response.status_code == 200
    assert response.json()["isAnalyst"] is True
