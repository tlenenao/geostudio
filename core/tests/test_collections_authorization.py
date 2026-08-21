# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest

from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.sharing.authorization import AccessFacts, can
from app.sharing.models import CollectionShare, Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        other = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="x",
            username="other",
            email=None,
            first_name="",
            last_name="",
        )
        # CollectionShare.collection_id has a real FK to collections.id (PRAGMA
        # foreign_keys=ON in tests) — AccessFacts is a detached view built by
        # callers, but the shares below reference a genuine Collection row.
        session.add(
            Collection(
                id="col-1",
                tenant_id=tenant.id,
                owner_id=owner.id,
                table_name="col_1",
                title="Col 1",
                pk_column="id",
            )
        )
        session.commit()
        yield session, tenant, owner, other


def _facts(tenant, owner, *, public=False):
    return AccessFacts(
        id="col-1", tenant_id=tenant.id, owner_id=owner.id, is_public=public, is_published=False
    )


def _share(session, tenant, user, role):
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g", created_by=user.id)
    session.add(group)
    # Flush the Group on its own: a single flush() mixing Group with rows that
    # FK to it (GroupMember/CollectionShare) can emit the dependent INSERTs
    # before the Group's own INSERT (no relationship() links these mapped
    # classes for the unit-of-work to order by) — see test_sharing_authorization.py,
    # which uses the same two-step flush for the identical reason.
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id, tenant_id=tenant.id))
    session.add(
        CollectionShare(collection_id="col-1", group_id=group.id, tenant_id=tenant.id, role=role)
    )
    session.flush()


@pytest.mark.parametrize(
    "action,expected",
    [
        ("read", True),
        ("write", True),
        ("delete", True),
        ("share", True),
    ],
)
def test_admin_full_rights_on_collections(env, action, expected):
    session, tenant, owner, other = env
    facts = _facts(tenant, owner)
    assert (
        can(
            session,
            user_id=other.id,
            action=action,
            item=facts,
            kind="collection",
            actor_is_admin=True,
        )
        is expected
    )


def test_admin_gets_nothing_extra_on_items(env):
    # Anti-régression SP-1 : le flag admin ne s'applique qu'aux collections.
    session, tenant, owner, other = env
    facts = _facts(tenant, owner)
    assert (
        can(session, user_id=other.id, action="write", item=facts, kind="item", actor_is_admin=True)
        is False
    )


@pytest.mark.parametrize(
    "role,action,expected",
    [
        ("viewer", "read", True),
        ("viewer", "write", False),
        ("editor", "read", True),
        ("editor", "write", True),
        ("editor", "share", True),
    ],
)
def test_collection_group_roles(env, role, action, expected):
    session, tenant, owner, other = env
    _share(session, tenant, other, role)
    facts = _facts(tenant, owner)
    assert can(session, user_id=other.id, action=action, item=facts, kind="collection") is expected


def test_stranger_reads_public_collection_only(env):
    session, tenant, owner, other = env
    assert (
        can(
            session,
            user_id=other.id,
            action="read",
            item=_facts(tenant, owner, public=True),
            kind="collection",
        )
        is True
    )
    assert (
        can(session, user_id=other.id, action="read", item=_facts(tenant, owner), kind="collection")
        is False
    )


def test_item_share_does_not_leak_to_collections(env):
    # Un ItemShare sur le même id ne doit pas ouvrir la collection (tables séparées).
    session, tenant, owner, other = env
    from app.items.models import Item
    from app.sharing.models import ItemShare

    # ItemShare.item_id FKs to items.id — need a real Item row sharing the
    # same id as the Collection ("col-1") to prove the two tables don't leak.
    session.add(
        Item(
            id="col-1",
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Item col-1",
        )
    )
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g2", created_by=other.id)
    session.add(group)
    session.flush()  # see comment in _share(): Group must flush before its dependents
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id="col-1", group_id=group.id, tenant_id=tenant.id, role="editor"))
    session.flush()
    assert (
        can(
            session, user_id=other.id, action="write", item=_facts(tenant, owner), kind="collection"
        )
        is False
    )
