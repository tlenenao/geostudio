import pytest

from app.db import make_engine, make_session_factory, init_db
from app.items.models import Item
from app.sharing.authorization import ItemAccessFacts, can
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


@pytest.fixture()
def actors(session):
    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-owner",
        username="owner", email=None, first_name="", last_name="",
    )
    viewer = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-viewer",
        username="viewer", email=None, first_name="", last_name="",
    )
    editor = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-editor",
        username="editor", email=None, first_name="", last_name="",
    )
    stranger = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-stranger",
        username="stranger", email=None, first_name="", last_name="",
    )

    viewer_group = Group(id="viewers", tenant_id=tenant.id, name="Viewers")
    editor_group = Group(id="editors", tenant_id=tenant.id, name="Editors")
    session.add_all([viewer_group, editor_group])
    session.flush()
    session.add(GroupMember(group_id=viewer_group.id, user_id=viewer.id, tenant_id=tenant.id))
    session.add(GroupMember(group_id=editor_group.id, user_id=editor.id, tenant_id=tenant.id))
    session.flush()

    def make_item(item_id: str, *, is_public: bool = False, is_published: bool = False) -> ItemAccessFacts:
        item = Item(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id,
            resource_type="app", title="Test item",
            is_public=is_public, is_published=is_published,
        )
        session.add(item)
        session.flush()
        session.add(ItemShare(
            item_id=item_id, group_id=viewer_group.id, tenant_id=tenant.id, role="viewer",
        ))
        session.add(ItemShare(
            item_id=item_id, group_id=editor_group.id, tenant_id=tenant.id, role="editor",
        ))
        session.flush()
        return ItemAccessFacts(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id,
            is_public=is_public, is_published=is_published,
        )

    return {
        "owner": owner, "viewer": viewer, "editor": editor, "stranger": stranger,
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
