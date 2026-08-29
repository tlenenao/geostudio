# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.sharing.repository import roles_for_collections, roles_for_items

Action = Literal["read", "write", "delete", "share"]
ObjectKind = Literal["item", "collection"]


@dataclass(frozen=True)
class AccessFacts:
    """Everything `can()` needs about one object, without importing the model
    (app.sharing sits below app.items and app.collections in the layering).
    Callers build this from a row they already fetched."""

    id: str
    tenant_id: str
    owner_id: str
    is_public: bool
    is_published: bool


# Rétro-compatibilité : les routes items/configs existantes importent ce nom.
ItemAccessFacts = AccessFacts


def decide(
    *,
    action: Action,
    kind: ObjectKind,
    is_owner: bool,
    is_public: bool,
    is_published: bool,
    roles: frozenset[str],
    actor_is_admin: bool,
) -> bool:
    """La règle d'autorisation, sans accès à la base.

    Deux appelants : `can()` ci-dessous (une ligne, une requête de rôles) et
    `app.items.repository._permissions()` (douze lignes, une requête de rôles
    pour toutes). Ils doivent conclure pareil — `tests/test_sharing_decide.py`
    le prouve sur le produit cartésien complet des situations.
    """
    # Le rôle admin ne court-circuite QUE les collections (spec SP-3 §2) :
    # la sémantique de partage des items (SP-1, testée) ne bouge pas.
    if kind == "collection" and actor_is_admin:
        return True
    if is_owner:
        return True
    if action == "read":
        if is_public or is_published:
            return True
        return bool(roles & {"viewer", "editor"})
    if action in ("write", "delete", "share"):
        return "editor" in roles
    return False


def can(
    session: Session,
    *,
    user_id: str,
    action: Action,
    item: AccessFacts,
    kind: ObjectKind = "item",
    actor_is_admin: bool = False,
) -> bool:
    # Court-circuits conservés à l'identique : ils évitent une requête de
    # rôles quand la décision est déjà acquise. Sans eux, ce chemin ferait une
    # requête là où l'ancien code n'en faisait aucune.
    if kind == "collection" and actor_is_admin:
        return True
    if item.owner_id == user_id:
        return True
    if action == "read" and (item.is_public or item.is_published):
        return True

    if kind == "item":
        roles = roles_for_items(
            session, tenant_id=item.tenant_id, user_id=user_id, item_ids=[item.id]
        ).get(item.id, frozenset())
    else:
        roles = roles_for_collections(
            session, tenant_id=item.tenant_id, user_id=user_id, collection_ids=[item.id]
        ).get(item.id, frozenset())

    return decide(
        action=action,
        kind=kind,
        is_owner=False,
        is_public=item.is_public,
        is_published=item.is_published,
        roles=roles,
        actor_is_admin=actor_is_admin,
    )
