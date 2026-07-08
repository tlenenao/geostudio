import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def test_create_and_list_groups(client):
    create = client.post("/groups", json={"name": "Reviewers"})
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Reviewers"

    listed = client.get("/groups")
    assert listed.status_code == 200
    assert [g["name"] for g in listed.json()] == ["Reviewers"]


def test_add_member(client):
    group_id = client.post("/groups", json={"name": "Reviewers"}).json()["id"]
    with client.session_factory() as session:
        bob = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-bob",
            username="bob", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(bob)

    response = client.post(f"/groups/{group_id}/members", json={"userId": bob.id})
    assert response.status_code == 204


def test_add_member_cross_tenant_user_returns_404(client):
    import uuid
    from app.tenants.models import Tenant

    group_id = client.post("/groups", json={"name": "Reviewers"}).json()["id"]
    with client.session_factory() as session:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other")
        session.add(other_tenant)
        session.flush()
        mallory = get_or_create_user(
            session, tenant_id=other_tenant.id, oidc_sub="sub-mallory",
            username="mallory", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(mallory)

    response = client.post(f"/groups/{group_id}/members", json={"userId": mallory.id})
    assert response.status_code == 404


def test_add_member_to_unknown_group_returns_404(client):
    with client.session_factory() as session:
        bob = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-bob",
            username="bob", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(bob)
    response = client.post("/groups/nope/members", json={"userId": bob.id})
    assert response.status_code == 404


def test_create_group_writes_audit_log(client):
    from sqlalchemy import select
    from app.audit.models import AuditLog

    client.post("/groups", json={"name": "Reviewers"})
    with client.session_factory() as session:
        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        assert "group.create" in actions
