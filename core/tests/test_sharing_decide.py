# SPDX-License-Identifier: Apache-2.0
"""Parité `decide()` ↔ ses appelants réels.

`decide()` est la règle d'autorisation, sans accès à la base. Trois de ses
quatre appelants réels sont testés ici pour la parité (le 4e,
`app.harvest.routes`, appelle `decide()` directement sans logique de
surcharge à comparer — cf. sa docstring, REV-017) :

- `can()` : le chemin « une ligne, une requête ».
- `app.items.repository._permissions_by_id` : « douze lignes, une requête
  pour toute une page », pur passe-plat vers `decide()`.
- `app.collections.repository.collection_permissions_by_id` : même patron,
  mais surcharge délibérément `delete`/`write` — testé explicitement, pas
  seulement en parité brute.

Tous doivent rendre le même verdict que `decide()` sur toute situation
(hors les deux surcharges collections, documentées et vérifiées), sinon
l'interface finira par afficher une action que le cœur refuse — exactement
ce que la refonte cherche à supprimer.
"""

import itertools

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.authorization import AccessFacts, can, decide
from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
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


def test_parity_with_items_permissions_by_id_over_every_situation(session):
    """`app.items.repository._permissions_by_id` (troisième appelant réel de
    `decide()`, REV-017) est un pur passe-plat — `actor_is_admin=False`
    toujours, aucune surcharge. Même produit cartésien que
    `test_parity_with_can_over_every_situation`, pour que la docstring de
    `decide()` n'ait plus à porter seule cette garantie."""
    from app.items.repository import _permissions_by_id

    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-owner-items",
        username="owner-items",
        email=None,
        first_name="",
        last_name="",
    )
    other = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-other-items",
        username="other-items",
        email=None,
        first_name="",
        last_name="",
    )
    groups = {}
    for role in ("viewer", "editor"):
        group = Group(id=f"gi-{role}", tenant_id=tenant.id, name=role, created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
        groups[role] = group
    session.flush()

    combos = itertools.product(ROLE_SETS, [False, True], [False, True], [False, True])
    for n, (roles, as_owner, is_public, is_published) in enumerate(combos):
        item_id = f"item-perm-{n}"
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

        actor = owner if as_owner else other
        item = session.get(Item, item_id)
        assert item is not None
        permissions = _permissions_by_id(
            session, tenant_id=tenant.id, current_user_id=actor.id, items=[item]
        )[item_id]
        for action in ACTIONS:
            expected = decide(
                action=action,
                kind="item",
                is_owner=as_owner,
                is_public=is_public,
                is_published=is_published,
                roles=frozenset() if as_owner else roles,
                actor_is_admin=False,
            )
            got = getattr(permissions, action)
            assert got == expected, (
                f"divergence action={action} roles={sorted(roles)} owner={as_owner} "
                f"public={is_public} published={is_published}"
            )


def test_parity_with_collection_permissions_by_id_over_every_situation(session):
    """`app.collections.repository._collection_permissions` (via
    `collection_permissions_by_id`, quatrième appelant réel de `decide()`,
    REV-017) surcharge délibérément `delete` (par `can_manage_collections`,
    jamais `decide()`) et `write` (par `col.editable and decide(...)`) — ce
    test prouve la parité `read`/`share` avec `decide()` **et** vérifie ces
    deux surcharges explicitement, plutôt que de la présumer."""
    from app.collections.models import Collection
    from app.collections.repository import collection_permissions_by_id

    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-owner-col",
        username="owner-col",
        email=None,
        first_name="",
        last_name="",
    )
    other = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-other-col",
        username="other-col",
        email=None,
        first_name="",
        last_name="",
    )
    groups = {}
    for role in ("viewer", "editor"):
        group = Group(id=f"gc-{role}", tenant_id=tenant.id, name=role, created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
        groups[role] = group
    session.flush()

    combos = itertools.product(
        ROLE_SETS, [False, True], [False, True], [False, True], [False, True], [False, True]
    )
    for n, (roles, as_owner, is_public, is_admin, can_manage, editable) in enumerate(combos):
        col_id = f"col-perm-{n}"
        session.add(
            Collection(
                id=col_id,
                tenant_id=tenant.id,
                owner_id=owner.id,
                table_name=col_id,
                title="t",
                pk_column="id",
                is_public=is_public,
                editable=editable,
            )
        )
        session.flush()
        for role in roles:
            session.add(
                CollectionShare(
                    collection_id=col_id,
                    group_id=groups[role].id,
                    tenant_id=tenant.id,
                    role=role,
                )
            )
        session.flush()

        actor = owner if as_owner else other
        col = session.get(Collection, col_id)
        assert col is not None
        permissions = collection_permissions_by_id(
            session,
            tenant_id=tenant.id,
            current_user_id=actor.id,
            actor_is_admin=is_admin,
            can_manage_collections=can_manage,
            collections=[col],
        )[col_id]
        effective_roles = frozenset() if as_owner else roles

        for action in ("read", "share"):
            expected = decide(
                action=action,
                kind="collection",
                is_owner=as_owner,
                is_public=is_public,
                is_published=False,
                roles=effective_roles,
                actor_is_admin=is_admin,
            )
            got = getattr(permissions, action)
            assert got == expected, (
                f"divergence action={action} roles={sorted(roles)} owner={as_owner} "
                f"public={is_public} admin={is_admin}"
            )

        # Surcharges délibérées documentées par la docstring de decide() :
        # delete ignore decide() (privilège de gestion, jamais un rôle de
        # partage), write exige en plus col.editable.
        assert permissions.delete == can_manage
        base_write = decide(
            action="write",
            kind="collection",
            is_owner=as_owner,
            is_public=is_public,
            is_published=False,
            roles=effective_roles,
            actor_is_admin=is_admin,
        )
        assert permissions.write == (editable and base_write)
