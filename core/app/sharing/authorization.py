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

    Appelants réels (vérifié par lecture de code, pas par ce commentaire —
    piège CLAUDE.md n°3/12, cette liste a déjà dérivé une fois) :

    - `can()` ci-dessous (une ligne, une requête de rôles) ;
    - `app.items.repository._permissions()` (via `_permissions_by_id`,
      douze lignes, une requête de rôles pour toute une page) — pur
      passe-plat vers `decide()`, aucune surcharge ;
    - `app.collections.repository._collection_permissions()` (via
      `collection_permissions_by_id`) — **surcharge délibérément** le
      verdict de `decide()` pour deux actions : `delete` ignore `decide()`
      et vaut `can_manage_collections` (privilège `admin.collections.manage`,
      jamais un rôle de partage) ; `write` vaut
      `col.editable and decide(...)` (une collection non éditable refuse
      l'écriture même à un éditeur/au propriétaire). Seuls `read`/`share`
      sont le verdict brut de `decide()` ;
    - `app.harvest.routes` (`list_layers`/`list_feature_layers`, deux
      appels directs — ajoutés par SP-49 pour éviter le N+1, sans passer
      par `can()` ni par un `AccessFacts`) : appel direct, sans logique de
      surcharge, donc en phase avec `decide()` par construction, pas par
      preuve de parité.

    **Portée de la preuve de parité** : `tests/test_sharing_decide.py`
    prouve `can()` ≡ `decide()` sur le produit cartésien complet des
    situations (`test_parity_with_can_over_every_situation`), et prouve la
    parité `read`/`share` de `_permissions_by_id`/`collection_permissions_by_id`
    avec `decide()` (`test_parity_with_items_permissions_by_id`,
    `test_parity_with_collection_permissions_by_id` — ce dernier vérifie
    aussi explicitement les deux surcharges `delete`/`write` ci-dessus).
    Les deux appels directs d'`app.harvest.routes` ne sont couverts par
    aucun test de parité dédié : ils ne réimplémentent rien à comparer,
    ce sont des appels nus à cette fonction.
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
