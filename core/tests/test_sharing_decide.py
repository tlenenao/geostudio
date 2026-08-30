# SPDX-License-Identifier: Apache-2.0
"""Parité `decide()` ↔ `can()`.

`decide()` est la règle d'autorisation ; `can()` est le chemin « une ligne,
une requête » et Task 4 est le chemin « douze lignes, une requête ». Les deux
doivent rendre le même verdict sur toute situation, sinon l'interface finira
par afficher une action que le cœur refuse — exactement ce que la refonte
cherche à supprimer.
"""

import itertools

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.authorization import AccessFacts, can, decide
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

ACTIONS = ["read", "write", "delete", "share"]
ROLE_SETS = [
    frozenset(),
    frozenset({"viewer"}),
    frozenset({"editor"}),
    frozenset({"viewer", "editor"}),
]


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_decide_owner_can_everything():
    for action in ACTIONS:
        assert (
            decide(
                action=action,
                kind="item",
                is_owner=True,
                is_public=False,
                is_published=False,
                roles=frozenset(),
                actor_is_admin=False,
            )
            is True
        )


def test_decide_admin_shortcut_applies_to_collections_only():
    # Spec SP-3 §2 : le rôle admin ne court-circuite QUE les collections.
    assert (
        decide(
            action="write",
            kind="collection",
            is_owner=False,
            is_public=False,
            is_published=False,
            roles=frozenset(),
            actor_is_admin=True,
        )
        is True
    )
    assert (
        decide(
            action="write",
            kind="item",
            is_owner=False,
            is_public=False,
            is_published=False,
            roles=frozenset(),
            actor_is_admin=True,
        )
        is False
    )


def test_decide_public_or_published_grants_read_only():
    for flag in ("is_public", "is_published"):
        kwargs = {"is_public": False, "is_published": False, flag: True}
        assert (
            decide(
                action="read",
                kind="item",
                is_owner=False,
                roles=frozenset(),
                actor_is_admin=False,
                **kwargs,
            )
            is True
        )
        assert (
            decide(
                action="write",
                kind="item",
                is_owner=False,
                roles=frozenset(),
                actor_is_admin=False,
                **kwargs,
            )
            is False
        )


def test_decide_viewer_reads_editor_writes():
    base = dict(
        kind="item", is_owner=False, is_public=False, is_published=False, actor_is_admin=False
    )
    assert decide(action="read", roles=frozenset({"viewer"}), **base) is True
    assert decide(action="write", roles=frozenset({"viewer"}), **base) is False
    for action in ("write", "delete", "share"):
        assert decide(action=action, roles=frozenset({"editor"}), **base) is True


def test_parity_with_can_over_every_situation(session):
    """Le produit cartésien complet : 4 actions × 4 jeux de rôles × propriétaire
    ou non × public × publié × admin ou non. `can()` et `decide()` doivent
    toujours conclure pareil."""
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
    other = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-other",
        username="other",
        email=None,
        first_name="",
        last_name="",
    )
    groups = {}
    for role in ("viewer", "editor"):
        group = Group(id=f"g-{role}", tenant_id=tenant.id, name=role, created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
        groups[role] = group
    session.flush()

    combos = itertools.product(
        ROLE_SETS, [False, True], [False, True], [False, True], [False, True]
    )
    for n, (roles, as_owner, is_public, is_published, is_admin) in enumerate(combos):
        item_id = f"item-{n}"
        session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_type="app",
                title="t",
                is_public=is_public,
                is_published=is_published,
            )
        )
        session.flush()
        for role in roles:
            session.add(
                ItemShare(
                    item_id=item_id,
                    group_id=groups[role].id,
                    tenant_id=tenant.id,
                    role=role,
                )
            )
        session.flush()

        facts = AccessFacts(
            id=item_id,
            tenant_id=tenant.id,
            owner_id=owner.id,
            is_public=is_public,
            is_published=is_published,
        )
        actor = owner if as_owner else other
        for action in ACTIONS:
            expected = can(
                session,
                user_id=actor.id,
                action=action,
                item=facts,
                kind="item",
                actor_is_admin=is_admin,
            )
            got = decide(
                action=action,
                kind="item",
                is_owner=as_owner,
                is_public=is_public,
                is_published=is_published,
                roles=frozenset() if as_owner else roles,
                actor_is_admin=is_admin,
            )
            assert got == expected, (
                f"divergence action={action} roles={sorted(roles)} owner={as_owner} "
                f"public={is_public} published={is_published} admin={is_admin}"
            )
