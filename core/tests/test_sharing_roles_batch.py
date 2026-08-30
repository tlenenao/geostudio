# SPDX-License-Identifier: Apache-2.0
"""`roles_for_items` : exactitude, isolation par tenant, et **une seule
requête** quel que soit le nombre d'items — c'est ce dernier point qui est la
raison d'être de la fonction."""

import uuid

import pytest
from sqlalchemy import event

from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
from app.sharing.repository import has_any_editor_role, roles_for_items
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def engine():
    eng = make_engine("sqlite+pysqlite:///:memory:")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def _seed(session, *, n_items: int):
    tenant = get_or_create_default_tenant(session)
    member = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-m",
        username="member",
        email=None,
        first_name="",
        last_name="",
    )
    owner = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-o",
        username="owner",
        email=None,
        first_name="",
        last_name="",
    )
    viewers = Group(id="g-v", tenant_id=tenant.id, name="V", created_by=owner.id)
    editors = Group(id="g-e", tenant_id=tenant.id, name="E", created_by=owner.id)
    session.add_all([viewers, editors])
    session.flush()
    session.add(GroupMember(group_id="g-v", user_id=member.id, tenant_id=tenant.id))
    session.add(GroupMember(group_id="g-e", user_id=member.id, tenant_id=tenant.id))
    session.flush()
    ids = []
    for i in range(n_items):
        item_id = f"i-{i}"
        ids.append(item_id)
        session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_type="app",
                title="t",
            )
        )
    session.flush()
    # i-0 partagé en lecture, i-1 en écriture, i-2 les deux, le reste rien.
    session.add(ItemShare(item_id="i-0", group_id="g-v", tenant_id=tenant.id, role="viewer"))
    if n_items > 1:
        session.add(ItemShare(item_id="i-1", group_id="g-e", tenant_id=tenant.id, role="editor"))
    if n_items > 2:
        session.add(ItemShare(item_id="i-2", group_id="g-v", tenant_id=tenant.id, role="viewer"))
        session.add(ItemShare(item_id="i-2", group_id="g-e", tenant_id=tenant.id, role="editor"))
    session.flush()
    return tenant, member, ids


def test_returns_role_sets_per_item(session):
    tenant, member, ids = _seed(session, n_items=4)
    got = roles_for_items(session, tenant_id=tenant.id, user_id=member.id, item_ids=ids)
    assert got["i-0"] == frozenset({"viewer"})
    assert got["i-1"] == frozenset({"editor"})
    assert got["i-2"] == frozenset({"viewer", "editor"})
    assert got.get("i-3", frozenset()) == frozenset()


def test_empty_input_makes_no_query(session):
    tenant, member, _ = _seed(session, n_items=1)
    assert roles_for_items(session, tenant_id=tenant.id, user_id=member.id, item_ids=[]) == {}


def test_other_tenant_never_leaks(session):
    tenant, member, ids = _seed(session, n_items=1)
    intruder_tenant = Tenant(id="t2", slug="t2", name="T2")
    session.add(intruder_tenant)
    session.flush()
    got = roles_for_items(session, tenant_id="t2", user_id=member.id, item_ids=ids)
    assert got == {}


def test_one_query_regardless_of_item_count(engine):
    """Le cœur du sujet : douze items ne coûtent pas plus de requêtes que deux.
    On compte les requêtes émises, on ne mesure aucune durée — une durée ne
    prouverait rien d'autre que l'état de la machine."""
    Session = make_session_factory(engine)
    counts: list[int] = []
    for n in (2, 12):
        with Session() as s:
            tenant, member, ids = _seed(s, n_items=n)
            seen = 0

            def count(conn, cursor, statement, params, context, executemany):
                nonlocal seen
                seen += 1

            event.listen(engine, "before_cursor_execute", count)
            try:
                roles_for_items(s, tenant_id=tenant.id, user_id=member.id, item_ids=ids)
            finally:
                event.remove(engine, "before_cursor_execute", count)
            counts.append(seen)
    assert counts[0] == counts[1] == 1, f"attendu 1 requête dans les deux cas, obtenu {counts}"


# `has_any_editor_role` : signal d'orientation pour le badge de rôle du
# shell (« Créateur » vs « Lecteur »), jamais une frontière de sécurité —
# recalculé à chaque `GET /me`, jamais stocké.


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def owner(session, tenant):
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-owner-editor-role",
        username="owner",
        email=None,
        first_name="",
        last_name="",
    )


@pytest.fixture()
def other(session, tenant):
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-other-editor-role",
        username="other",
        email=None,
        first_name="",
        last_name="",
    )


def test_has_any_editor_role_false_with_no_shares(session, tenant, owner):
    assert has_any_editor_role(session, tenant_id=tenant.id, user_id=owner.id) is False


def test_has_any_editor_role_true_via_item_share(session, tenant, owner, other):
    session.add(
        Item(id="i-1", tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="I")
    )
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id="i-1", group_id=group.id, tenant_id=tenant.id, role="editor"))
    session.flush()
    assert has_any_editor_role(session, tenant_id=tenant.id, user_id=other.id) is True


def test_has_any_editor_role_true_via_collection_share(session, tenant, owner, other):
    session.add(
        Collection(
            id="c-1",
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="c_1",
            title="C",
            pk_column="id",
        )
    )
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g2", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(
        CollectionShare(collection_id="c-1", group_id=group.id, tenant_id=tenant.id, role="editor")
    )
    session.flush()
    assert has_any_editor_role(session, tenant_id=tenant.id, user_id=other.id) is True


def test_has_any_editor_role_false_with_viewer_only(session, tenant, owner, other):
    session.add(
        Item(id="i-2", tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="I2")
    )
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g3", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id="i-2", group_id=group.id, tenant_id=tenant.id, role="viewer"))
    session.flush()
    assert has_any_editor_role(session, tenant_id=tenant.id, user_id=other.id) is False
