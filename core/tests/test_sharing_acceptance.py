# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        alice = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-alice",
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = alice  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def test_item_shared_to_a_group_is_visible_to_members_and_invisible_to_others(client):
    """Roadmap SP-1 acceptance criterion, reproduced verbatim: an item shared
    to a group is visible to its members and invisible to everyone else."""
    created = client.post(
        "/configs",
        json={
            "title": "Confidential map",
            "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
        },
    ).json()
    item_id = created["itemId"]

    with client.session_factory() as session:
        member = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-member",
            username="member", email=None, first_name="", last_name="",
        )
        outsider = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-outsider",
            username="outsider", email=None, first_name="", last_name="",
        )
        group = Group(id="g1", tenant_id=client.tenant.id, name="Trusted", created_by=client.user.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=member.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()
        session.refresh(member)
        session.refresh(outsider)

    client.app.dependency_overrides[get_current_user] = lambda: member
    member_response = client.get(f"/items/{item_id}")
    client.app.dependency_overrides[get_current_user] = lambda: outsider
    outsider_response = client.get(f"/items/{item_id}")
    client.app.dependency_overrides[get_current_user] = lambda: client.user

    assert member_response.status_code == 200
    assert outsider_response.status_code == 404


def test_published_item_accessible_anonymously_unpublished_is_not(client):
    """Roadmap SP-1 acceptance criterion: a published item is accessible
    anonymously at runtime; a non-published one returns 404."""
    created = client.post(
        "/configs",
        json={
            "title": "Runtime app",
            "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
        },
    ).json()
    item_id = created["itemId"]

    del client.app.dependency_overrides[get_current_user]
    assert client.get(f"/public/items/{item_id}").status_code == 404

    client.app.dependency_overrides[get_current_user] = lambda: client.user
    client.patch(f"/items/{item_id}", json={"isPublished": True})
    del client.app.dependency_overrides[get_current_user]

    assert client.get(f"/public/items/{item_id}").status_code == 200
