# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.authorization import ItemAccessFacts, can
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.models import Tenant
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


@pytest.fixture()
def actors(session):
    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-owner",
        username="owner",
        email=None,
        first_name="",
        last_name="",
    )
    viewer = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-viewer",
        username="viewer",
        email=None,
        first_name="",
        last_name="",
    )
    editor = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-editor",
        username="editor",
        email=None,
        first_name="",
        last_name="",
    )
    stranger = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-stranger",
        username="stranger",
        email=None,
        first_name="",
        last_name="",
    )
    dual_role_member = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-dual",
        username="dual_role_member",
        email=None,
        first_name="",
        last_name="",
    )

    viewer_group = Group(id="viewers", tenant_id=tenant.id, name="Viewers", created_by=owner.id)
    editor_group = Group(id="editors", tenant_id=tenant.id, name="Editors", created_by=owner.id)
    session.add_all([viewer_group, editor_group])
    session.flush()
    session.add(GroupMember(group_id=viewer_group.id, user_id=viewer.id, tenant_id=tenant.id))
    session.add(GroupMember(group_id=editor_group.id, user_id=editor.id, tenant_id=tenant.id))
    session.add(
        GroupMember(group_id=viewer_group.id, user_id=dual_role_member.id, tenant_id=tenant.id)
    )
    session.add(
        GroupMember(group_id=editor_group.id, user_id=dual_role_member.id, tenant_id=tenant.id)
    )
    session.flush()

    def make_item(
        item_id: str, *, is_public: bool = False, is_published: bool = False
    ) -> ItemAccessFacts:
        item = Item(
            id=item_id,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Test item",
            is_public=is_public,
            is_published=is_published,
        )
        session.add(item)
        session.flush()
        session.add(
            ItemShare(
                item_id=item_id,
                group_id=viewer_group.id,
                tenant_id=tenant.id,
                role="viewer",
            )
        )
        session.add(
            ItemShare(
                item_id=item_id,
                group_id=editor_group.id,
                tenant_id=tenant.id,
                role="editor",
            )
        )
        session.flush()
        return ItemAccessFacts(
            id=item_id,
            tenant_id=tenant.id,
            owner_id=owner.id,
            is_public=is_public,
            is_published=is_published,
        )

    return {
        "owner": owner,
        "viewer": viewer,
        "editor": editor,
        "stranger": stranger,
        "dual_role_member": dual_role_member,
        "make_item": make_item,
    }


@pytest.mark.parametrize("action", ["read", "write", "delete", "share"])
def test_owner_can_do_everything(session, actors, action):
    item = actors["make_item"]("item-owner")
    assert can(session, user_id=actors["owner"].id, action=action, item=item) is True


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_group_viewer(session, actors, action, expected):
    item = actors["make_item"]("item-viewer")
    assert can(session, user_id=actors["viewer"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", True), ("delete", True), ("share", True)]
)
def test_group_editor(session, actors, action, expected):
    item = actors["make_item"]("item-editor")
    assert can(session, user_id=actors["editor"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_public_item_stranger(session, actors, action, expected):
    item = actors["make_item"]("item-public", is_public=True)
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_published_item_stranger(session, actors, action, expected):
    item = actors["make_item"]("item-published", is_published=True)
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is expected


@pytest.mark.parametrize("action", ["read", "write", "delete", "share"])
def test_stranger_with_no_relation_is_denied(session, actors, action):
    item = actors["make_item"]("item-private")
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is False


def test_user_with_multiple_group_roles_uses_highest_permission(session, actors):
    """Test that a user in multiple groups on the same item is granted
    the highest permission (e.g. editor beats viewer)."""
    item = actors["make_item"]("item-dual-roles")
    dual_user = actors["dual_role_member"]
    # User is in both viewer_group and editor_group on the same item
    assert can(session, user_id=dual_user.id, action="read", item=item) is True
    assert can(session, user_id=dual_user.id, action="write", item=item) is True
    assert can(session, user_id=dual_user.id, action="delete", item=item) is True
    assert can(session, user_id=dual_user.id, action="share", item=item) is True


def test_viewer_only_cannot_write_even_if_editor_share_exists(session, actors):
    """Test that a user who is only a viewer is denied write,
    even though the item also has an editor share for another group."""
    item = actors["make_item"]("item-editor-exists")
    viewer_user = actors["viewer"]
    # Viewer is only in viewer_group; they should not get write access
    # even though the item is also shared to editor_group
    assert can(session, user_id=viewer_user.id, action="write", item=item) is False
    assert can(session, user_id=viewer_user.id, action="delete", item=item) is False
    assert can(session, user_id=viewer_user.id, action="share", item=item) is False


def test_cross_tenant_isolation_prevents_unauthorized_access(session, actors):
    """Test that tenant_id filtering in has_group_role prevents cross-tenant leaks.

    Scenario: A shared group exists in both tenants with the same id. A user in
    tenant2 is a member of that group (in tenant2). An item in tenant1 is shared
    to that same group id (in tenant1). The tenant2 user should NOT be able to
    access the tenant1 item, because has_group_role must filter by tenant_id
    on both ItemShare and GroupMember.
    """
    # Create a second tenant
    tenant2 = Tenant(id="tenant-2", slug="tenant-2", name="Tenant 2")
    session.add(tenant2)
    session.flush()

    # Create a user in the second tenant
    user_in_tenant2 = get_or_create_user(
        session,
        tenant_id=tenant2.id,
        oidc_sub="sub-tenant2-user",
        username="tenant2_user",
        email=None,
        first_name="",
        last_name="",
    )

    # Create a group in tenant2 with id that matches tenant1's viewer group
    # (This creates the scenario where cross-tenant filtering is critical)
    group_in_tenant2 = Group(
        id="shared-xgroup",
        tenant_id=tenant2.id,
        name="Shared Group in T2",
        created_by=user_in_tenant2.id,
    )
    session.add(group_in_tenant2)
    session.flush()

    # Add the tenant2 user to this group in tenant2
    session.add(
        GroupMember(group_id=group_in_tenant2.id, user_id=user_in_tenant2.id, tenant_id=tenant2.id)
    )
    session.flush()

    # Get the default tenant from actors
    tenant1 = session.query(Tenant).filter_by(slug="default").first()

    # Create an item in tenant1 and manually share it to a group with id="shared-xgroup"
    # This is a different tenant1 group, not the one the tenant2 user is in
    item_in_tenant1 = actors["make_item"]("item-cross-tenant-test")
    # Note: make_item shares to "viewers" and "editors" groups, not "shared-xgroup"
    # So we add an additional share to test
    session.add(
        ItemShare(
            item_id=item_in_tenant1.id,
            group_id="shared-xgroup",
            tenant_id=tenant1.id,
            role="viewer",
        )
    )
    session.flush()

    # Now the critical test: tenant2_user is in group "shared-xgroup" in tenant2,
    # and item_in_tenant1 is shared to group "shared-xgroup" in tenant1.
    # Without tenant_id filtering in has_group_role, the JOIN would succeed and
    # the user would incorrectly get access. The tenant_id filter should prevent this.
    assert can(session, user_id=user_in_tenant2.id, action="read", item=item_in_tenant1) is False
    assert can(session, user_id=user_in_tenant2.id, action="write", item=item_in_tenant1) is False
