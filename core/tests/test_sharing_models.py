import pytest
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, make_session_factory, init_db
from app.items import repository as items_repo
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_group_member_and_item_share_round_trip(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    bob = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-2",
        username="bob", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="Shared app",
    )

    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers")
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    session.flush()

    member = session.get(GroupMember, {"group_id": group.id, "user_id": bob.id})
    assert member is not None
    share = session.get(ItemShare, {"item_id": item.id, "group_id": group.id})
    assert share is not None
    assert share.role == "viewer"


def test_item_share_cascades_on_item_delete(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="Will be deleted",
    )
    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers")
    session.add(group)
    session.flush()
    session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    session.flush()

    from sqlalchemy import delete
    from app.items.models import Item

    session.execute(delete(Item).where(Item.id == item.id))
    session.flush()

    assert session.get(ItemShare, {"item_id": item.id, "group_id": group.id}) is None


def test_item_is_public_defaults_false(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="X",
    )
    assert item.is_public is False
