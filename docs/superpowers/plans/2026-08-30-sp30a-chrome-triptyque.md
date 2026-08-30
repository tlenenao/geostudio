# SP-30a — Chrome triptyque + extension des permissions (collections) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le chrome triptyque neuf (TopBar, DomainBar, StatusBar, TriptychLayout) et l'assembler dans `AppLayout`, sans encore reconstruire le contenu d'aucune page métier — plus les changements transverses cœur/shell que ce chrome consomme (`CollectionPermissions`, `hasAnyEditorRole`, consolidation du verrou `ItemActions`).

**Architecture:** Le chrome est démonté en composants indépendants sous `shell/src/shell/chrome/` (TopBar, DomainBar, BottomNav, StatusBar, TriptychLayout, AccountMenu, CommandPalette), chacun testé seul (le dernier, `TriptychLayout`, avec une page factice — aucune page réelle n'est encore réécrite, c'est SP-30b). `AppLayout.tsx` redevient un simple assembleur. Côté cœur, `CollectionPermissions` (miroir d'`ItemPermissions`, batché comme `roles_for_items`) corrige au passage un N+1 réel sur `GET /collections`, jamais reporté depuis SP-29a.

**Tech Stack:** React 19, react-router-dom, @tanstack/react-query, Radix UI (kit SP-29b, `shell/src/ui/kit/`), FastAPI, SQLAlchemy, Pydantic.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune comparaison de droits en dur dans le shell : tout passe par `Gate`/`hasPermission`/`capabilities.ts` (spec §6.5, doc parent).
- Aucun contrôle de l'interface ne doit produire un 403 après clic — vérifier le vrai gate serveur avant de dériver une permission côté cœur (cf. Task 1 : `delete` sur une collection n'est PAS le verdict générique de `decide()`).
- Deux ambiances (clair/sombre) : tout nouveau composant de chrome utilise les tokens `shell/src/styles/tokens.css` existants, jamais une couleur en dur.
- Régénérer `openapi.json` + `core-schema.d.ts` dès qu'un schéma cœur change (piège n°1) — Task 3 dédiée, après Tasks 1+2.
- `canWrite` ne doit laisser aucune compat shim : les 3 call-sites shell sont mis à jour dans le même changement (Task 4), pas de champ dupliqué.
- Anti-N+1 : toute nouvelle route qui sert une liste doit avoir son test `test_*_no_nplus1.py` (Task 1).
- Régressions jsdom (piège n°10) : tout stub/polyfill de test (ResizeObserver, matchMedia, PointerEvent) est **local au fichier de test**, jamais dans `shell/src/test/setup.ts`.
- Aucune page métier (`CatalogPage`, `ItemDetailPage`, `MapEditorPage`, etc.) n'est basculée sur `TriptychLayout` dans ce plan — c'est le périmètre de SP-30b, écrit après celui-ci. La seule exception : `CatalogPage` gagne un filtre initial par `?type=` (Task 6), un changement isolé qui ne touche pas sa mise en page.

---

## Task 1: Cœur — `CollectionPermissions`

**Files:**
- Modify: `core/app/collections/schemas.py`
- Modify: `core/app/collections/repository.py`
- Modify: `core/app/collections/routes.py`
- Test: `core/tests/test_collections_repository.py`
- Test: `core/tests/test_collections_no_nplus1.py` (nouveau)
- Test: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes: `decide()`, `Action` (`app/sharing/authorization.py`) ; `roles_for_collections()` (`app/sharing/repository.py`) ; `Collection` (`app/collections/models.py`).
- Produces: `CollectionPermissions` (Pydantic, `{read,write,delete,share}: bool`) ; `collection_permissions_by_id(session, *, tenant_id, current_user_id, actor_is_admin, collections) -> dict[str, CollectionPermissions]`, consommée par Task 3 (régénération OpenAPI) et par le shell (Task 4).

Un vrai N+1 existe aujourd'hui : `list_collections` (`core/app/collections/routes.py:274`) appelle `_can_write_collection` par ligne, chacune refaisant sa propre requête de rôles via `can()`. `unregister_collection` (`DELETE /collections/{id}`) est gardé par `_require_admin(user)` seul, **pas** par `decide()` — un non-admin propriétaire ou éditeur y reçoit 403 même si `decide()` répondrait `True` pour lui (test existant : `test_admin_full_rights_on_collections` dans `test_collections_authorization.py`, qui ne couvre que le cas admin). `CollectionPermissions.delete` doit donc refléter le vrai gate (`actor_is_admin`), pas le verdict générique de `decide()` — sinon l'UI proposerait un bouton Supprimer qui 403.

- [ ] **Step 1: Écrire le test de la fonction batchée (rôles + admin + editable + delete-hardcodé)**

Ajouter à `core/tests/test_collections_repository.py` :

```python
import uuid

from app.collections.repository import collection_permissions_by_id
from app.collections.schemas import CollectionPermissions
from app.sharing.models import CollectionShare, Group, GroupMember


def _register(session, tenant, owner, *, id_="col-perm", editable=True, is_public=False):
    from app.collections.models import Collection

    col = Collection(
        id=id_,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name=id_,
        title=id_,
        pk_column="id",
        editable=editable,
        is_public=is_public,
    )
    session.add(col)
    session.flush()
    return col


def test_owner_gets_full_permissions_except_delete(session, tenant, owner):
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=owner.id,
        actor_is_admin=False,
        collections=[col],
    )
    assert result[col.id] == CollectionPermissions(read=True, write=True, delete=False, share=True)


def test_admin_gets_delete_even_as_stranger(session, tenant, owner, other):
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=other.id,
        actor_is_admin=True,
        collections=[col],
    )
    assert result[col.id].delete is True


def test_non_admin_owner_cannot_delete(session, tenant, owner):
    # Anti-régression : unregister_collection est _require_admin seul, pas
    # decide() — un propriétaire non-admin ne doit JAMAIS voir delete=True,
    # sinon le bouton Supprimer produirait un 403 après clic.
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=owner.id,
        actor_is_admin=False,
        collections=[col],
    )
    assert result[col.id].delete is False


def test_write_requires_editable_even_for_the_owner(session, tenant, owner):
    col = _register(session, tenant, owner, editable=False)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=owner.id,
        actor_is_admin=False,
        collections=[col],
    )
    assert result[col.id].write is False


def test_editor_role_grants_write_and_share_not_delete(session, tenant, owner, other):
    col = _register(session, tenant, owner)
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(
        CollectionShare(collection_id=col.id, group_id=group.id, tenant_id=tenant.id, role="editor")
    )
    session.flush()
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=other.id,
        actor_is_admin=False,
        collections=[col],
    )
    assert result[col.id] == CollectionPermissions(read=True, write=True, delete=False, share=True)


def test_anonymous_gets_read_only_on_a_public_collection(session, tenant, owner):
    col = _register(session, tenant, owner, is_public=True)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=None,
        actor_is_admin=False,
        collections=[col],
    )
    assert result[col.id] == CollectionPermissions(read=True, write=False, delete=False, share=False)
```

Vérifier au préalable que `test_collections_repository.py` a bien des fixtures `session`/`tenant`/`owner`/`other` (via `conftest.py` ou définies en tête du fichier) ; sinon les ajouter en tête de fichier sur le patron de `tests/test_collections_authorization.py` (fixture `env` déjà lue) :

```python
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def owner(session, tenant):
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="o",
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
        oidc_sub="x",
        username="other",
        email=None,
        first_name="",
        last_name="",
    )
```

Ne dupliquer ces fixtures que si le fichier ne les a pas déjà sous un autre nom — dans ce cas, adapter les tests ci-dessus aux noms existants plutôt que d'en recréer une seconde version.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_repository.py -k permissions -v`
Expected: FAIL — `ImportError: cannot import name 'collection_permissions_by_id'` (et `CollectionPermissions` inconnue de `app.collections.schemas`).

- [ ] **Step 3: `CollectionPermissions` dans `schemas.py`**

Ajouter à `core/app/collections/schemas.py` :

```python
class CollectionPermissions(BaseModel):
    """Miroir d'`ItemPermissions` (`app/items/schemas.py`) pour les
    collections. Calculé depuis `decide()`, jamais recalculé côté client.

    `delete` n'est PAS le verdict générique de `decide()` : `unregister_collection`
    (DELETE /collections/{id}) est gardé par `_require_admin` seul, pas par
    `can()`/`decide()` — refléter autre chose que `actor_is_admin` ici
    afficherait un bouton Supprimer qui produit un 403 après clic pour un
    propriétaire ou un éditeur non-admin.
    """

    read: bool
    write: bool
    delete: bool
    share: bool
```

- [ ] **Step 4: `collection_permissions_by_id` dans `repository.py`**

Ajouter à `core/app/collections/repository.py` (après les imports existants, ajouter `from app.sharing.authorization import Action, AccessFacts, decide` — `AccessFacts` déjà importé, ajouter `Action, decide` à côté — et `from app.sharing.repository import roles_for_collections` ; ajouter `from app.collections.schemas import CollectionPermissions` après l'import de `Collection`) :

```python
def _collection_permissions(
    col: Collection,
    *,
    current_user_id: str | None,
    roles: frozenset[str],
    actor_is_admin: bool,
) -> CollectionPermissions:
    is_owner = current_user_id is not None and col.owner_id == current_user_id

    def verdict(action: Action) -> bool:
        if action == "delete":
            return actor_is_admin
        base = decide(
            action=action,
            kind="collection",
            is_owner=is_owner,
            is_public=col.is_public,
            is_published=False,
            roles=roles,
            actor_is_admin=actor_is_admin,
        )
        return col.editable and base if action == "write" else base

    return CollectionPermissions(
        read=verdict("read"),
        write=verdict("write"),
        delete=verdict("delete"),
        share=verdict("share"),
    )


def collection_permissions_by_id(
    session: Session,
    *,
    tenant_id: str,
    current_user_id: str | None,
    actor_is_admin: bool,
    collections: list[Collection],
) -> dict[str, CollectionPermissions]:
    """Permissions de toute une page, avec **une** requête de rôles — pendant
    de `_permissions_by_id` dans `app.items.repository`. Anonyme (`current_user_id`
    absent) ne peut être ni propriétaire ni avoir de rôle : la requête de
    rôles est sautée."""
    roles_by_id = (
        roles_for_collections(
            session,
            tenant_id=tenant_id,
            user_id=current_user_id,
            collection_ids=[c.id for c in collections],
        )
        if current_user_id is not None
        else {}
    )
    return {
        c.id: _collection_permissions(
            c,
            current_user_id=current_user_id,
            roles=roles_by_id.get(c.id, frozenset()),
            actor_is_admin=actor_is_admin,
        )
        for c in collections
    }
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_repository.py -k permissions -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Écrire le test anti-N+1**

Créer `core/tests/test_collections_no_nplus1.py`, sur le patron exact de `test_items_no_nplus1.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde-fou permanent : le nombre de requêtes SQL d'un `GET /collections` ne
doit pas croître avec le nombre de collections. Pendant de
`test_items_no_nplus1.py` — la même classe de bug existait ici
(`_can_write_collection` appelé ligne par ligne dans `list_collections`),
jamais corrigée depuis SP-29a."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import CollectionShare, Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _build(n_collections: int):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-owner",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-reader",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=reader.id, tenant_id=tenant.id))
        for i in range(n_collections):
            s.add(
                Collection(
                    id=f"c-{i}",
                    tenant_id=tenant.id,
                    owner_id=owner.id,
                    table_name=f"c_{i}",
                    title=f"Collection {i}",
                    pk_column="id",
                )
            )
        s.flush()
        for i in range(n_collections):
            s.add(
                CollectionShare(
                    collection_id=f"c-{i}",
                    group_id="gv",
                    tenant_id=tenant.id,
                    role="viewer",
                )
            )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: reader
    return engine, TestClient(app)


def _count_queries(engine, fn):
    seen = 0

    def bump(conn, cursor, statement, params, context, executemany):
        nonlocal seen
        seen += 1

    event.listen(engine, "before_cursor_execute", bump)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", bump)
    return seen


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_query_count_does_not_grow_with_collection_count(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n)
        try:

            def call(client=client, n=n):
                response = client.get("/collections")
                assert response.status_code == 200, response.text
                assert len(response.json()["collections"]) == n

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec le nombre de collections : {counts} — "
        "c'est un N+1, probablement _can_write_collection appelé ligne par ligne"
    )
```

- [ ] **Step 7: Lancer le test anti-N+1, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_no_nplus1.py -v`
Expected: FAIL — le compte de requêtes croît avec `n` (le N+1 actuel).

- [ ] **Step 8: Brancher `collection_permissions_by_id` dans les routes, retirer `_can_write_collection`**

Dans `core/app/collections/routes.py` :

Remplacer l'import ligne 23 :
```python
from app.sharing.authorization import can
```
par :
```python
from app.sharing.authorization import can
```
(inchangé — `can` reste utilisé par `patch_collection`, `get_readable_collection`, `_require_share`).

Retirer la fonction `_can_write_collection` (lignes 119-129) entièrement.

Remplacer `_collection_json` (lignes 132-146) :

```python
def _collection_json(col, permissions, owner: str | None = None) -> dict:
    return {
        "id": col.id,
        "title": col.title,
        "description": col.description,
        "tableName": col.table_name,
        "isPublic": col.is_public,
        "editable": col.editable,
        "geometryType": col.geometry_type,
        "srid": col.srid,
        "pkColumn": col.pk_column,
        "permissions": permissions.model_dump(),
        "featureCount": col.feature_count,
        "owner": owner,
    }
```

`register_collection` (ligne 224), remplacer :
```python
    return _collection_json(col, _can_write_collection(session, user, col))
```
par :
```python
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

`create_empty_collection_route` (ligne 246), remplacer :
```python
    return _collection_json(col, True)
```
par :
```python
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

`list_collections` (lignes 272-279), remplacer le corps du `return` :
```python
    return {
        "collections": [
            _collection_json(
                c, _can_write_collection(session, user, c), owner=owners.get(c.owner_id)
            )
            for c in cols
        ]
    }
```
par :
```python
    permissions_by_id = repo.collection_permissions_by_id(
        session,
        tenant_id=tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        collections=cols,
    )
    return {
        "collections": [
            _collection_json(c, permissions_by_id[c.id], owner=owners.get(c.owner_id))
            for c in cols
        ]
    }
```

`get_collection` (ligne 329), remplacer :
```python
    body = _collection_json(col, _can_write_collection(session, user, col))
```
par :
```python
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=col.tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        collections=[col],
    )[col.id]
    body = _collection_json(col, permissions)
```

`patch_collection` (dernière ligne de la fonction, cf. lecture précédente), remplacer :
```python
    return _collection_json(col, _can_write_collection(session, user, col))
```
par :
```python
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

- [ ] **Step 9: Lancer le test anti-N+1 et la suite collections, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_no_nplus1.py tests/test_collections_routes.py tests/test_collections_repository.py tests/test_collections_authorization.py -v`
Expected: PASS.

- [ ] **Step 10: Mettre à jour les tests de routes qui affirment encore `canWrite`**

Chercher les occurrences dans `test_collections_routes.py` :

Run: `cd core && grep -n "canWrite" tests/test_collections_routes.py`

Pour chaque assertion `body["canWrite"] is True/False` ou `data["collections"][i]["canWrite"]`, remplacer par `body["permissions"]["write"] is True/False` (ou l'index de liste équivalent). Ne pas deviner le nombre d'occurrences à l'avance — les corriger toutes, une par une, contre le texte réel du fichier.

- [ ] **Step 11: Lancer toute la suite cœur, vérifier le succès**

Run: `cd core && uv run pytest -q`
Expected: PASS (hormis les 2 échecs préexistants documentés dans CLAUDE.md — `test_scope_preserves_original_sql_error` intermittent, `test_every_compose_substitution_is_documented` — à ne pas imputer à cette tâche).

- [ ] **Step 12: Portes de qualité**

Run: `cd core && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && uv run lint-imports`
Expected: tout passe, aucune nouvelle entrée de contrat de couches (`app.collections` importe déjà `app.sharing`).

- [ ] **Step 13: Commit**

```bash
git add core/app/collections/schemas.py core/app/collections/repository.py core/app/collections/routes.py core/tests/test_collections_repository.py core/tests/test_collections_no_nplus1.py core/tests/test_collections_routes.py
git commit -m "feat(core): CollectionPermissions, corrige le N+1 de GET /collections"
```

---

## Task 2: Cœur — `GET /me` gagne `hasAnyEditorRole`, `tenantSlug`, `version`

**Files:**
- Modify: `core/app/sharing/repository.py`
- Modify: `core/app/auth/routes.py`
- Test: `core/tests/test_sharing_repository.py` (ou fichier existant équivalent — vérifier son nom avant d'écrire)
- Test: `core/tests/test_auth_me_capabilities.py`

**Interfaces:**
- Consumes: `ItemShare`, `CollectionShare`, `GroupMember` (`app/sharing/models.py`) ; `Tenant` (`app/tenants/models.py`).
- Produces: `has_any_editor_role(session, *, tenant_id, user_id) -> bool` (`app/sharing/repository.py`), consommée par Task 3 (régénération) et le shell (Task 9, `AccountMenu`).

**Important** : `test_me_capabilities_match_the_instance_route` (`core/tests/test_auth_me_capabilities.py`) fait une égalité stricte entre `GET /me`'s `capabilities` (7 clés) et **tout** le corps de `GET /instance`. `version`/`tenantSlug` vont donc sur `MeResponse` **top-level**, jamais sur `/instance` ni dans `MeCapabilities` — sinon ce test casse. `/instance` reste intouché dans cette tâche.

- [ ] **Step 1: Écrire le test de `has_any_editor_role`**

Trouver le fichier de test existant pour `app/sharing/repository.py` :

Run: `cd core && ls tests/ | grep -i sharing`

Ajouter (dans ce fichier, en réutilisant ses fixtures existantes — lire son en-tête avant d'écrire pour matcher le nom réel des fixtures `session`/`tenant`, elles suivent probablement le même patron que `test_collections_authorization.py`) :

```python
import uuid

from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
from app.sharing.repository import has_any_editor_role


def test_has_any_editor_role_false_with_no_shares(session, tenant, owner):
    assert has_any_editor_role(session, tenant_id=tenant.id, user_id=owner.id) is False


def test_has_any_editor_role_true_via_item_share(session, tenant, owner, other):
    from app.items.models import Item

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
    from app.collections.models import Collection

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
    from app.items.models import Item

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
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/ -k has_any_editor_role -v`
Expected: FAIL — `ImportError: cannot import name 'has_any_editor_role'`.

- [ ] **Step 3: Implémenter `has_any_editor_role`**

Ajouter à `core/app/sharing/repository.py` (à la suite de `roles_for_collections`) :

```python
def has_any_editor_role(session: Session, *, tenant_id: str, user_id: str) -> bool:
    """Un signal d'orientation pour le badge de rôle affiché côté shell
    (« Créateur » vs « Lecteur ») — jamais une frontière de sécurité, jamais
    stocké : recalculé à chaque `GET /me`. Vrai dès qu'un rôle `editor` existe
    quelque part pour cet utilisateur, item ou collection."""
    item_hit = session.execute(
        select(ItemShare.item_id)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.tenant_id == tenant_id,
            ItemShare.role == "editor",
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
        .limit(1)
    ).first()
    if item_hit is not None:
        return True
    collection_hit = session.execute(
        select(CollectionShare.collection_id)
        .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
        .where(
            CollectionShare.tenant_id == tenant_id,
            CollectionShare.role == "editor",
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
        .limit(1)
    ).first()
    return collection_hit is not None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/ -k has_any_editor_role -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Écrire le test `/me` pour les trois nouveaux champs**

Ajouter à `core/tests/test_auth_me_capabilities.py` :

```python
def test_me_exposes_tenant_slug_version_and_editor_role(client):
    body = client.get("/me").json()
    assert isinstance(body["tenantSlug"], str) and body["tenantSlug"] != ""
    assert isinstance(body["version"], str) and body["version"] != ""
    assert body["hasAnyEditorRole"] is False  # aucun partage dans la fixture `client`
```

- [ ] **Step 6: Lancer le test, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_auth_me_capabilities.py -k tenant_slug -v`
Expected: FAIL — `KeyError: 'tenantSlug'`.

- [ ] **Step 7: Implémenter dans `app/auth/routes.py`**

Ajouter aux imports en tête de fichier :
```python
from fastapi import APIRouter, Depends, HTTPException, Request
```
(ajoute `Request` à la liste existante)
```python
from app.db import get_session
from app.sharing.repository import has_any_editor_role
from app.tenants.models import Tenant
```
(`get_session` déjà importé — vérifier avant d'ajouter un doublon ; sinon l'ajouter à côté de l'import `User` existant).

Étendre `MeResponse` :
```python
class MeResponse(BaseModel):
    id: str
    tenantId: str
    tenantSlug: str
    username: str
    email: str | None
    firstName: str
    lastName: str
    isAdmin: bool
    isAnalyst: bool
    hasAnyEditorRole: bool
    version: str
    capabilities: MeCapabilities
```

Remplacer `get_me` :
```python
@router.get("/me", response_model=MeResponse)
def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    tenant = session.get(Tenant, user.tenant_id)
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        tenantSlug=tenant.slug if tenant is not None else user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        isAdmin=user.is_admin,
        isAnalyst=user.is_analyst,
        hasAnyEditorRole=has_any_editor_role(session, tenant_id=user.tenant_id, user_id=user.id),
        version=request.app.version,
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
        ),
    )
```

`Session` (type de `session: Session = Depends(...)`) requiert `from sqlalchemy.orm import Session` — déjà présent en tête du fichier (vu à la lecture initiale).

- [ ] **Step 8: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_auth_me_capabilities.py -v`
Expected: PASS (tous, y compris `test_me_capabilities_match_the_instance_route` — `/instance` est intouché).

- [ ] **Step 9: Lancer toute la suite cœur + portes de qualité**

Run: `cd core && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS (mêmes 2 échecs préexistants tolérés qu'au Task 1/Step 11).

- [ ] **Step 10: Commit**

```bash
git add core/app/sharing/repository.py core/app/auth/routes.py core/tests/test_auth_me_capabilities.py core/tests/test_sharing_repository.py
git commit -m "feat(core): GET /me gagne tenantSlug, version, hasAnyEditorRole"
```

(Adapter le nom du fichier de test sharing dans la commande au nom réel trouvé au Step 1.)

---

## Task 3: Régénérer OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: les schémas Pydantic modifiés par Tasks 1+2 (`CollectionPermissions`, `MeResponse`).
- Produces: les types TS à jour, consommés par Task 4.

- [ ] **Step 1: Régénérer la spec OpenAPI**

Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
```
Expected: le fichier est réécrit. Vérifier par `git diff --stat core/openapi.json` qu'il change (diff non vide attendu — piège n°1) et que `CollectionPermissions`/`MeResponse.tenantSlug`/`MeResponse.version`/`MeResponse.hasAnyEditorRole` y apparaissent :

Run: `grep -c "CollectionPermissions\|tenantSlug\|hasAnyEditorRole" core/openapi.json`
Expected: > 0.

- [ ] **Step 2: Régénérer les types TS**

Run: `cd shell && npm run gen:api-types`
Expected: `src/api/generated/core-schema.d.ts` change (`git diff --stat` non vide).

- [ ] **Step 3: Vérifier que le build shell type-check toujours**

Run: `cd shell && npm run build`
Expected: PASS (les call-sites qui utilisent encore l'ancien `canWrite` échoueront ici — c'est attendu, Task 4 les corrige juste après. Si ce build échoue pour une autre raison que `canWrite`/`CollectionAdmin`, investiguer avant de continuer).

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(api): régénère OpenAPI + types TS (CollectionPermissions, /me)"
```

---

## Task 4: Shell — `canWrite` → `permissions` sur les collections

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/builder/pipeline/CollectionParamSelect.tsx`
- Modify: `shell/src/api/itemClient.test.ts`
- Modify: `shell/src/builder/pipeline/CollectionParamSelect.test.tsx`

**Interfaces:**
- Consumes: `ItemPermissions`, `hasPermission` (`shell/src/auth/permissions.ts`, déjà écrits SP-29a).
- Produces: `CollectionAdmin.permissions: ItemPermissions` (remplace `canWrite: boolean`), consommé par `CollectionParamSelect` (ce task) et par tout futur écran collections (SP-30b+).

Confirmé par `grep -rn "\.canWrite\b\|canWrite:"` : exactement 3 sites de production (`api/types.ts:551`, `api/itemClient.ts:1432`, `builder/pipeline/CollectionParamSelect.tsx:22`) + les tests qui les couvrent. `builder/widgets/form.tsx` mocke `client.getCollectionPermission` directement (au niveau `ItemClient`, pas au niveau JSON) : sa signature `Promise<boolean>` ne change pas, donc `form.tsx` et `form.test.tsx` sont **inchangés** par cette tâche.

- [ ] **Step 1: Écrire le test `itemClient` sur `getCollectionPermission`**

Dans `shell/src/api/itemClient.test.ts`, remplacer les deux tests existants (autour de la ligne 2092) :

```ts
test("getCollectionPermission returns permissions.write", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({
        id: "incidents",
        title: "Incidents",
        permissions: { read: true, write: true, delete: false, share: true },
      }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(true);
});

test("getCollectionPermission defaults to false when permissions is absent", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({ id: "incidents", title: "Incidents" }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(false);
});
```

Remplacer chaque `canWrite: true/false` restant dans ce fichier (les tests `getCollection returns the full collection metadata...`, `listCollections...`, `createCollection...` autour des lignes 2117-2350) par `permissions: { read: true, write: <même bool>, delete: false, share: true }` dans le mock MSW **et** dans l'assertion `toEqual` correspondante (les deux doivent changer ensemble — un mock à jour avec une assertion qui attend encore `canWrite` échouerait).

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "getCollectionPermission"`
Expected: FAIL — `getCollectionPermission` lit encore `data.canWrite`.

- [ ] **Step 3: `CollectionAdmin.permissions` dans `types.ts`**

Dans `shell/src/api/types.ts`, remplacer (ligne 551) :
```ts
  canWrite: boolean;
```
par :
```ts
  permissions: ItemPermissions;
```
(`ItemPermissions` déjà importée en tête de fichier, ligne 2 : `import type { ItemPermissions } from "../auth/permissions";`).

- [ ] **Step 4: `getCollectionPermission` dans `itemClient.ts`**

Remplacer (ligne 1430-1433) :
```ts
    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ canWrite?: boolean }>("GET", `/collections/${collectionId}`);
      return data.canWrite ?? false;
    },
```
par :
```ts
    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ permissions?: { write?: boolean } }>(
        "GET",
        `/collections/${collectionId}`,
      );
      return data.permissions?.write ?? false;
    },
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "getCollectionPermission"`
Expected: PASS.

- [ ] **Step 6: Mettre à jour les fixtures `CollectionAdmin` restantes de `itemClient.test.ts`**

Run: `cd shell && grep -n "canWrite" src/api/itemClient.test.ts`
Pour chaque occurrence restante, remplacer `canWrite: <bool>` par `permissions: { read: true, write: <bool>, delete: false, share: true }`, dans le mock MSW **et** l'assertion `toEqual` qui le lit.

- [ ] **Step 7: Lancer tout `itemClient.test.ts`, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 8: `CollectionParamSelect` — remplacer `c.canWrite`**

Dans `shell/src/builder/pipeline/CollectionParamSelect.tsx`, ajouter l'import :
```ts
import { hasPermission } from "../../auth/permissions";
```
Remplacer (ligne 22) :
```ts
  const options = (collectionsQuery.data ?? []).filter((c) => variant === "readable" || c.canWrite);
```
par :
```ts
  const options = (collectionsQuery.data ?? []).filter(
    (c) => variant === "readable" || hasPermission(c, "write"),
  );
```

- [ ] **Step 9: Mettre à jour `CollectionParamSelect.test.tsx`**

Remplacer les deux littéraux `canWrite: true`/`canWrite: false` dans `COLLECTIONS` (`shell/src/builder/pipeline/CollectionParamSelect.test.tsx`) par `permissions: { read: true, write: true, delete: true, share: true }` et `permissions: { read: true, write: false, delete: false, share: false }` respectivement.

- [ ] **Step 10: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/pipeline/CollectionParamSelect.test.tsx`
Expected: PASS.

- [ ] **Step 11: Build + suite complète**

Run: `cd shell && npm run build && npm run test`
Expected: PASS (le build qui échouait au Task 3/Step 3 passe maintenant).

- [ ] **Step 12: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/CollectionParamSelect.test.tsx
git commit -m "refactor(shell): collections — canWrite devient permissions (ItemPermissions)"
```

---

## Task 5: Shell — `ItemActions` : consolidation du verrou

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx`
- Modify: `shell/src/shell/ItemActions.test.tsx`

**Interfaces:**
- Consumes: `hasPermission` (`shell/src/auth/permissions.ts`), `Locked` (`shell/src/auth/Locked.tsx`) — déjà écrits.

Modifier/Publier/Miniature sont aujourd'hui trois `<Gate can="write">...<Locked reason={t("locked.needWrite")}>` indépendants — même item, même raison, trois fois. Remplacer par un seul `Locked` englobant les trois quand `write` est refusé.

- [ ] **Step 1: Réécrire le test « un lecteur voit... verrouillée »**

Dans `shell/src/shell/ItemActions.test.tsx`, remplacer le test (lignes 169-181) :

```tsx
  it("un lecteur voit Modifier, Publier et Miniature verrouillées en un seul message", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("button", { name: "Modifier" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Publier" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Miniature" })).toBeDisabled();
    // Un seul message de raison pour les trois, pas un par action verrouillée
    // (SP-29a review finale — regroupement décidé pour SP-30a).
    expect(
      screen.getAllByText("Modification réservée aux éditeurs de cet élément."),
    ).toHaveLength(1);
  });
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/ItemActions.test.tsx -t "un seul message"`
Expected: FAIL — `toHaveLength(1)` reçoit `3`.

- [ ] **Step 3: Regrouper dans `ItemActions.tsx`**

Remplacer les trois blocs `<Gate ... can="write">` (Modifier, Publier, Miniature — lignes 81-144 de l'original) par un seul bloc conditionnel, en gardant `Gate` pour Partager/Supprimer inchangés en dessous :

```tsx
          {hasPermission(item, "write") ? (
            <>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => setPanel("edit")}
              >
                {t("actions.edit")}
              </button>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => void togglePublish()}
              >
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => setPanel("thumbnail")}
              >
                {t("actions.thumbnail")}
              </button>
            </>
          ) : (
            <Locked reason={t("locked.needWrite")}>
              <button className="px-3 py-1 text-left">{t("actions.edit")}</button>
              <button className="px-3 py-1 text-left">
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button className="px-3 py-1 text-left">{t("actions.thumbnail")}</button>
            </Locked>
          )}
```

Ajouter l'import `hasPermission` :
```tsx
import { hasPermission } from "../auth/permissions";
```
`Gate` reste importé (toujours utilisé par Partager/Supprimer plus bas) ; si `Gate` n'est plus utilisé que pour ces deux, ne rien retirer — c'est le comportement voulu.

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/ItemActions.test.tsx`
Expected: PASS (tous les tests du fichier, y compris ceux inchangés — "un éditeur peut modifier et publier", "le propriétaire garde les cinq commandes").

- [ ] **Step 5: Suite complète shell**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx
git commit -m "fix(shell): ItemActions regroupe le verrou Modifier/Publier/Miniature en un message"
```

---

## Task 6: Shell — `CatalogPage` lit un filtre initial `?type=`

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Modify: `shell/src/pages/CatalogPage.test.tsx`

**Interfaces:**
- Produces: `CatalogPage` respecte un paramètre d'URL `type` comme valeur initiale du filtre — consommé par `DomainBar`/`domainRoutes.ts` (Task 7), qui pointera Cartes/Données/Apps & sites/Automatisation vers `/?type=<resourceType>` en l'absence de page dédiée pour ces domaines dans ce plan.

- [ ] **Step 1: Écrire le test**

Ajouter à `shell/src/pages/CatalogPage.test.tsx` (vérifier au préalable le wrapper de rendu utilisé par ce fichier — probablement un `MemoryRouter`, à réutiliser avec une prop `initialEntries`) :

```tsx
test("prend le type initial depuis le paramètre d'URL ?type=", async () => {
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <Harness />
    </MemoryRouter>,
  );
  await screen.findByText("GeoStudio").catch(() => {});
  expect(screen.getByLabelText("Type")).toHaveValue("map");
});
```

Adapter `Harness`/le wrapper exact au patron déjà présent dans ce fichier de test (lire son en-tête avant d'écrire cette addition — ne pas réinventer un second harnais si un existe déjà pour `CatalogPage`).

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx -t "paramètre d'URL"`
Expected: FAIL — le select `Type` vaut `""`, pas `"map"`.

- [ ] **Step 3: Implémenter**

Dans `shell/src/pages/CatalogPage.tsx`, ajouter l'import :
```ts
import { useSearchParams } from "react-router-dom";
```
Remplacer :
```ts
  const [type, setType] = useState<ResourceType | "">(fixedType ?? "");
```
par :
```ts
  const [searchParams] = useSearchParams();
  const initialType = searchParams.get("type");
  const validInitialType =
    initialType !== null && (RESOURCE_TYPE_ORDER as readonly string[]).includes(initialType)
      ? (initialType as ResourceType)
      : "";
  const [type, setType] = useState<ResourceType | "">(fixedType ?? validInitialType);
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: PASS (tout le fichier).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx
git commit -m "feat(shell): CatalogPage lit un type initial depuis ?type="
```

---

## Task 7: Shell — `domainRoutes.ts` + `DomainBar` + pages « à venir »

**Files:**
- Create: `shell/src/shell/chrome/domainRoutes.ts`
- Create: `shell/src/shell/chrome/DomainBar.tsx`
- Create: `shell/src/shell/chrome/DomainBar.test.tsx`
- Create: `shell/src/pages/TasksComingSoonPage.tsx`
- Create: `shell/src/pages/SettingsComingSoonPage.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `DOMAINS`, `navigableDomains`, `Profile`, `DomainId` (`shell/src/auth/capabilities.ts`, déjà écrits SP-29a) ; `EmptyState` (`shell/src/ui/kit/EmptyState.tsx`).
- Produces: `DOMAIN_PATHS: Record<DomainId, string>` (consommé par Task 10, `CommandPalette`) ; `DomainBar` (consommé par Task 10, `AppLayout`).

Faute de page dédiée pour Cartes/Données/Apps & sites/Automatisation dans ce plan (leurs pages réelles ne sont réécrites qu'à partir de SP-30b), ces quatre domaines pointent vers le Catalogue pré-filtré (Task 6). Analytique et Administration ont déjà une page standalone existante — on y pointe directement, sans rien inventer. Tâches et Paramètres n'ont **aucun** écran : ils pointent vers un `EmptyState` "à venir".

- [ ] **Step 1: `domainRoutes.ts`**

```ts
// SPDX-License-Identifier: Apache-2.0
import type { DomainId } from "../../auth/capabilities";

// Cartes/Données/Apps & sites/Automatisation n'ont pas encore de page dédiée
// (SP-30b+ les reconstruit sur TriptychLayout) : en attendant, leur entrée de
// la barre de domaines pointe vers le Catalogue pré-filtré par type
// (CatalogPage lit `?type=`, cf. Task 6) — pas une fausse promesse de
// fonctionnalité manquante, juste une réorganisation de ce qui existe déjà.
export const DOMAIN_PATHS: Record<DomainId, string> = {
  catalog: "/",
  maps: "/?type=map",
  data: "/?type=dataset",
  apps: "/?type=app",
  automation: "/?type=pipeline",
  analytics: "/analytics/sql",
  tasks: "/tasks",
  admin: "/admin/extensions",
  settings: "/settings",
};
```

- [ ] **Step 2: `TasksComingSoonPage` / `SettingsComingSoonPage`**

```tsx
// shell/src/pages/TasksComingSoonPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { EmptyState } from "../ui/kit/EmptyState";
import { t } from "../i18n";

export function TasksComingSoonPage() {
  return <EmptyState title={t("domain.tasks")} description={t("comingSoon.tasks")} />;
}
```

```tsx
// shell/src/pages/SettingsComingSoonPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { EmptyState } from "../ui/kit/EmptyState";
import { t } from "../i18n";

export function SettingsComingSoonPage() {
  return <EmptyState title={t("domain.settings")} description={t("comingSoon.settings")} />;
}
```

Ajouter à `shell/src/i18n/catalog.fr.ts` (après les clés `domain.*`) :
```ts
  "comingSoon.tasks": "Le centre de tâches arrive avec SP-31.",
  "comingSoon.settings": "Les paramètres d'instance arrivent avec SP-33.",
```

- [ ] **Step 3: Routes**

Dans `shell/src/shell/routes.tsx`, ajouter les imports :
```ts
import { TasksComingSoonPage } from "../pages/TasksComingSoonPage";
import { SettingsComingSoonPage } from "../pages/SettingsComingSoonPage";
```
Ajouter, dans le bloc `<Route element={<ProtectedLayout />}>`, après `/internal/kit-gallery` :
```tsx
        <Route path="/tasks" element={<TasksComingSoonPage />} />
        <Route path="/settings" element={<SettingsComingSoonPage />} />
```

- [ ] **Step 4: Écrire le test `DomainBar`**

```tsx
// shell/src/shell/chrome/DomainBar.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DomainBar } from "./DomainBar";
import type { Profile } from "../../auth/capabilities";

const BASE_PROFILE: Profile = {
  isAdmin: false,
  isAnalyst: false,
  capabilities: {
    readOnly: false,
    etlEnabled: true,
    exportEnabled: false,
    appExportEnabled: false,
    tileset3dEnabled: false,
    terrain3dEnabled: false,
    copilotEnabled: false,
  },
};

function renderBar(profile: Profile, initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <DomainBar profile={profile} />
    </MemoryRouter>,
  );
}

test("affiche les sept domaines accessibles à un créateur, sans Administration", () => {
  renderBar(BASE_PROFILE);
  for (const label of [
    "Catalogue",
    "Cartes",
    "Données",
    "Apps & sites",
    "Automatisation",
    "Analytique",
    "Tâches",
    "Paramètres",
  ]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
  expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
});

test("affiche Administration pour un administrateur", () => {
  renderBar({ ...BASE_PROFILE, isAdmin: true });
  expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
});

test("marque le domaine courant actif", () => {
  renderBar(BASE_PROFILE, "/analytics/sql");
  expect(screen.getByRole("link", { name: "Analytique" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "Catalogue" })).not.toHaveAttribute("aria-current");
});

test("distingue Cartes de Catalogue même si les deux mènent à /", () => {
  // Cartes/Données/Apps & sites/Automatisation pointent tous vers le
  // Catalogue pré-filtré par ?type= (Task 6) — sans comparer aussi la
  // recherche d'URL, les cinq domaines qui partagent le chemin "/"
  // paraîtraient actifs en même temps dès qu'on est sur "/".
  renderBar(BASE_PROFILE, "/?type=map");
  expect(screen.getByRole("link", { name: "Cartes" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Catalogue" })).not.toHaveAttribute("aria-current");
});

test("Automatisation verrouillée quand la capacité etlEnabled est coupée", () => {
  renderBar({ ...BASE_PROFILE, capabilities: { ...BASE_PROFILE.capabilities, etlEnabled: false } });
  const automation = screen.getByText("Automatisation");
  expect(automation.closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
});
```

- [ ] **Step 5: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/DomainBar.test.tsx`
Expected: FAIL — le module `./DomainBar` n'existe pas.

- [ ] **Step 6: Implémenter `DomainBar`**

```tsx
// shell/src/shell/chrome/DomainBar.tsx
// SPDX-License-Identifier: Apache-2.0
import { NavLink, useLocation } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS } from "./domainRoutes";
import { t } from "../../i18n";

export function DomainBar({ profile }: { profile: Profile }) {
  const location = useLocation();
  const domains = navigableDomains(profile);

  return (
    <nav aria-label={t("domainBar.label")} className="flex items-center gap-1 border-b border-rule px-4">
      {domains.map(({ domain, state }) => {
        const path = DOMAIN_PATHS[domain.id];
        // Plusieurs domaines (Cartes/Données/Apps & sites/Automatisation)
        // pointent tous vers "/" avec un ?type= différent (Task 6) : comparer
        // seulement le pathname les ferait paraître actifs tous en même
        // temps. Comparer aussi la recherche pour ceux dont le chemin en
        // porte une ; comparer le pathname seul pour les autres (dont
        // Catalogue, "/" sans ?type=).
        const currentHref = location.pathname + location.search;
        const isActive = path.includes("?") ? currentHref === path : location.pathname === path;
        if (state === "locked") {
          return (
            <span
              key={domain.id}
              aria-disabled="true"
              title={t("locked.capabilityOff")}
              className="px-3 py-2 text-sm text-ink-3 opacity-45"
            >
              {t(domain.labelKey)}
            </span>
          );
        }
        return (
          <NavLink
            key={domain.id}
            to={path}
            aria-current={isActive ? "page" : undefined}
            className={
              isActive
                ? "border-b-2 border-accent px-3 py-2 text-sm font-semibold text-ink"
                : "px-3 py-2 text-sm text-ink-2 hover:text-ink"
            }
          >
            {t(domain.labelKey)}
          </NavLink>
        );
      })}
    </nav>
  );
}
```

Ajouter la clé i18n manquante à `catalog.fr.ts` :
```ts
  "domainBar.label": "Domaines",
```

- [ ] **Step 7: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/DomainBar.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 8: Suite complète + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add shell/src/shell/chrome/domainRoutes.ts shell/src/shell/chrome/DomainBar.tsx shell/src/shell/chrome/DomainBar.test.tsx shell/src/pages/TasksComingSoonPage.tsx shell/src/pages/SettingsComingSoonPage.tsx shell/src/shell/routes.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): DomainBar + pages à venir (Tâches, Paramètres)"
```

---

## Task 8: Shell — `useNarrowViewport` + `BottomNav`

**Files:**
- Create: `shell/src/shell/chrome/useNarrowViewport.ts`
- Create: `shell/src/shell/chrome/useNarrowViewport.test.ts`
- Create: `shell/src/shell/chrome/BottomNav.tsx`
- Create: `shell/src/shell/chrome/BottomNav.test.tsx`

**Interfaces:**
- Produces: `useNarrowViewport(): boolean` (consommé par `BottomNav` ici, et par `TriptychLayout` en Task 12).

Règle de dégradation (§7 doc parent, maquette « Sur écran étroit ») : sous 390 px, la barre de domaines devient une barre de navigation basse à **4 entrées fixes** (Catalogue, Cartes, Tâches, Plus), indépendamment du profil — « Plus » ouvre un `Popover` listant les domaines restants que le profil courant peut voir.

- [ ] **Step 1: Écrire le test du hook**

```ts
// shell/src/shell/chrome/useNarrowViewport.test.ts
// SPDX-License-Identifier: Apache-2.0
import { renderHook, act } from "@testing-library/react";
import { useNarrowViewport } from "./useNarrowViewport";

function mockMatchMedia(initialMatches: boolean) {
  let listener: (() => void) | null = null;
  const mql = {
    matches: initialMatches,
    addEventListener: (_: string, cb: () => void) => {
      listener = cb;
    },
    removeEventListener: () => {
      listener = null;
    },
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mql));
  return {
    fireChange(matches: boolean) {
      mql.matches = matches;
      listener?.();
    },
  };
}

test("retourne false par défaut au-dessus de 390 px", () => {
  mockMatchMedia(false);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(false);
});

test("retourne true sous 390 px et suit les changements", () => {
  const { fireChange } = mockMatchMedia(true);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(true);
  act(() => fireChange(false));
  expect(result.current).toBe(false);
});
```

Ajouter en tête du fichier l'import de `vi` : `import { vi } from "vitest";` avant le premier test (jsdom n'implémente pas `matchMedia` — polyfill **local à ce fichier**, piège n°10).

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/useNarrowViewport.test.ts`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Implémenter le hook**

```ts
// shell/src/shell/chrome/useNarrowViewport.ts
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

const QUERY = "(max-width: 389px)";

export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setNarrow(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return narrow;
}
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/useNarrowViewport.test.ts`
Expected: PASS.

- [ ] **Step 5: Écrire le test `BottomNav`**

```tsx
// shell/src/shell/chrome/BottomNav.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { BottomNav } from "./BottomNav";
import type { Profile } from "../../auth/capabilities";

const PROFILE: Profile = {
  isAdmin: true,
  isAnalyst: false,
  capabilities: {
    readOnly: false,
    etlEnabled: true,
    exportEnabled: false,
    appExportEnabled: false,
    tileset3dEnabled: false,
    terrain3dEnabled: false,
    copilotEnabled: false,
  },
};

test("affiche toujours les quatre entrées fixes", () => {
  render(
    <MemoryRouter>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  for (const label of ["Catalogue", "Cartes", "Tâches", "Plus"]) {
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
  }
});

test("Plus ouvre les domaines restants accessibles au profil", async () => {
  render(
    <MemoryRouter>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Plus" }));
  expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Données" })).toBeInTheDocument();
});
```

- [ ] **Step 6: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/BottomNav.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 7: Implémenter `BottomNav`**

```tsx
// shell/src/shell/chrome/BottomNav.tsx
// SPDX-License-Identifier: Apache-2.0
import { NavLink } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS } from "./domainRoutes";
import { Popover } from "../../ui/kit/Popover";
import { t } from "../../i18n";

const FIXED_IDS = ["catalog", "maps", "tasks"] as const;

export function BottomNav({ profile }: { profile: Profile }) {
  const domains = navigableDomains(profile).filter((d) => d.state === "visible");
  const fixed = domains.filter((d) => (FIXED_IDS as readonly string[]).includes(d.domain.id));
  const rest = domains.filter((d) => !(FIXED_IDS as readonly string[]).includes(d.domain.id));

  return (
    <nav aria-label={t("bottomNav.label")} className="flex items-center border-t border-rule">
      {fixed.map(({ domain }) => (
        <NavLink
          key={domain.id}
          to={DOMAIN_PATHS[domain.id]}
          className="flex flex-1 flex-col items-center py-2 text-xs text-ink-2"
        >
          {t(domain.labelKey)}
        </NavLink>
      ))}
      <Popover
        aria-label={t("bottomNav.more")}
        trigger={
          <button className="flex flex-1 flex-col items-center py-2 text-xs text-ink-2">
            {t("bottomNav.more")}
          </button>
        }
      >
        <div className="flex flex-col gap-1">
          {rest.map(({ domain }) => (
            <NavLink key={domain.id} to={DOMAIN_PATHS[domain.id]} className="px-2 py-1 text-sm">
              {t(domain.labelKey)}
            </NavLink>
          ))}
        </div>
      </Popover>
    </nav>
  );
}
```

Ajouter à `catalog.fr.ts` :
```ts
  "bottomNav.label": "Navigation",
  "bottomNav.more": "Plus",
```

- [ ] **Step 8: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/BottomNav.test.tsx`
Expected: PASS.

- [ ] **Step 9: Suite complète**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add shell/src/shell/chrome/useNarrowViewport.ts shell/src/shell/chrome/useNarrowViewport.test.ts shell/src/shell/chrome/BottomNav.tsx shell/src/shell/chrome/BottomNav.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): BottomNav (dégradation 390px) + useNarrowViewport"
```

---

## Task 9: Shell — `AccountMenu` (badge de rôle) + `TopBar`

**Files:**
- Create: `shell/src/shell/chrome/AccountMenu.tsx`
- Create: `shell/src/shell/chrome/AccountMenu.test.tsx`
- Create: `shell/src/shell/chrome/TopBar.tsx`
- Create: `shell/src/shell/chrome/TopBar.test.tsx`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `useMe`, `useAuth` ; `Avatar`, `Popover`, `Badge` (kit) ; `NewItemButton`, `ImportFileButton`, `Tileset3DUploadButton` (inchangés, relocalisés).
- Produces: `TopBar` (consommé par Task 13, `AppLayout`).

- [ ] **Step 1: `Me.hasAnyEditorRole` côté shell**

Dans `shell/src/api/types.ts`, étendre `Me` :
```ts
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
  isAnalyst: boolean;
  hasAnyEditorRole: boolean;
};
```

Dans `shell/src/api/itemClient.ts`, `getMe()` (lignes 535-549) — ajouter le champ à l'objet destructuré et à la valeur de retour :
```ts
    async getMe(): Promise<Me> {
      const data = await request<{
        username: string;
        firstName: string;
        lastName: string;
        isAdmin: boolean;
        isAnalyst: boolean;
        hasAnyEditorRole: boolean;
      }>("GET", `/me`);
      return {
        username: data.username,
        firstName: data.firstName,
        lastName: data.lastName,
        isAdmin: data.isAdmin,
        isAnalyst: data.isAnalyst,
        hasAnyEditorRole: data.hasAnyEditorRole,
      };
    },
```

- [ ] **Step 2: Écrire le test `AccountMenu`**

```tsx
// shell/src/shell/chrome/AccountMenu.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AuthState } from "../../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

const { AccountMenu } = await import("./AccountMenu");

function renderMenu() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <AccountMenu />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

function meResponse(overrides: Partial<Record<string, unknown>> = {}) {
  return HttpResponse.json({
    id: "u1",
    username: "alice",
    firstName: "Alice",
    lastName: "Martin",
    isAdmin: false,
    isAnalyst: false,
    hasAnyEditorRole: false,
    ...overrides,
  });
}

test("ouvre le menu et affiche le nom, le badge Lecteur, puis se déconnecte", async () => {
  server.use(http.get("https://core.test/me", () => meResponse()));
  renderMenu();
  await userEvent.click(screen.getByRole("button", { name: "Compte" }));
  expect(await screen.findByText("alice")).toBeInTheDocument();
  expect(screen.getByText("Lecteur")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Déconnexion" }));
  expect(authState.signOut).toHaveBeenCalled();
});

test("affiche Créateur pour un compte avec un rôle éditeur quelque part", async () => {
  server.use(http.get("https://core.test/me", () => meResponse({ hasAnyEditorRole: true })));
  renderMenu();
  await userEvent.click(screen.getByRole("button", { name: "Compte" }));
  expect(await screen.findByText("Créateur")).toBeInTheDocument();
});

test("affiche Administrateur avant Analyste ou Créateur", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      meResponse({ isAdmin: true, isAnalyst: true, hasAnyEditorRole: true }),
    ),
  );
  renderMenu();
  await userEvent.click(screen.getByRole("button", { name: "Compte" }));
  expect(await screen.findByText("Administrateur")).toBeInTheDocument();
});
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/AccountMenu.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 4: Implémenter `AccountMenu`**

```tsx
// shell/src/shell/chrome/AccountMenu.tsx
// SPDX-License-Identifier: Apache-2.0
import { useAuth } from "../../auth/useAuth";
import { useMe } from "../../api/hooks";
import type { Me } from "../../api/types";
import { Avatar } from "../../ui/kit/Avatar";
import { Popover } from "../../ui/kit/Popover";
import { Badge } from "../../ui/kit/Badge";
import { t } from "../../i18n";

function roleLabel(me: Me | undefined): string {
  if (!me) return "";
  if (me.isAdmin) return t("account.roleAdmin");
  if (me.isAnalyst) return t("account.roleAnalyst");
  if (me.hasAnyEditorRole) return t("account.roleCreator");
  return t("account.roleReader");
}

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

export function AccountMenu() {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  const label = username ?? "";

  return (
    <Popover
      aria-label={t("account.menu")}
      trigger={
        <button aria-label={t("account.menu")} className="rounded-full">
          <Avatar alt={label} fallback={initials(label)} />
        </button>
      }
    >
      <div className="flex min-w-40 flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-ink">{label}</span>
          <Badge>{roleLabel(meQuery.data)}</Badge>
        </div>
        <button className="text-left text-sm text-ink-2 hover:text-ink" onClick={signOut}>
          {t("account.signOut")}
        </button>
      </div>
    </Popover>
  );
}
```

Ajouter à `catalog.fr.ts` :
```ts
  "account.menu": "Compte",
  "account.roleAdmin": "Administrateur",
  "account.roleAnalyst": "Analyste",
  "account.roleCreator": "Créateur",
  "account.roleReader": "Lecteur",
  "account.signOut": "Déconnexion",
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/AccountMenu.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Écrire le test `TopBar`**

```tsx
// shell/src/shell/chrome/TopBar.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { AuthState } from "../../auth/useAuth";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../NewItemButton", () => ({ NewItemButton: () => <button>Nouveau</button> }));
vi.mock("../ImportFileButton", () => ({
  ImportFileButton: () => <button>Importer un fichier</button>,
}));
vi.mock("../Tileset3DUploadButton", () => ({
  Tileset3DUploadButton: () => <button>Téléverser un tileset</button>,
}));

const { TopBar } = await import("./TopBar");

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <TopBar tileset3dEnabled={false} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche la marque, Nouveau, Importer, et le compte", () => {
  renderBar();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Importer un fichier" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compte" })).toBeInTheDocument();
});

test("masque le bouton tileset 3D quand la capacité est coupée", () => {
  renderBar();
  expect(screen.queryByRole("button", { name: "Téléverser un tileset" })).not.toBeInTheDocument();
});
```

- [ ] **Step 7: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/TopBar.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 8: Implémenter `TopBar`**

```tsx
// shell/src/shell/chrome/TopBar.tsx
// SPDX-License-Identifier: Apache-2.0
import { NewItemButton } from "../NewItemButton";
import { ImportFileButton } from "../ImportFileButton";
import { Tileset3DUploadButton } from "../Tileset3DUploadButton";
import { AccountMenu } from "./AccountMenu";

export function TopBar({ tileset3dEnabled }: { tileset3dEnabled: boolean }) {
  return (
    <header className="flex items-center justify-between border-b border-rule px-6 py-3">
      <span className="text-lg font-bold text-ink">GeoStudio</span>
      <div className="flex items-center gap-3 text-sm">
        <NewItemButton />
        <ImportFileButton />
        {tileset3dEnabled && <Tileset3DUploadButton />}
        <AccountMenu />
      </div>
    </header>
  );
}
```

`⌘K` (Omnibox/CommandPalette) est explicitement **hors périmètre de SP-30a** : la recherche sémantique du catalogue (SP-7) n'a nulle part où s'intégrer proprement avant que la famille Catalogue de SP-30b n'existe. Documenté ici pour ne pas être oublié, pas glissé sous le tapis : la palette de commandes (navigation entre domaines + recherche sémantique) est reprise dans le plan de SP-30b, une fois `TriptychLayout` réellement monté sur `CatalogPage`.

- [ ] **Step 9: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/TopBar.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 10: Suite complète + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add shell/src/shell/chrome/AccountMenu.tsx shell/src/shell/chrome/AccountMenu.test.tsx shell/src/shell/chrome/TopBar.tsx shell/src/shell/chrome/TopBar.test.tsx shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): TopBar + AccountMenu (badge de rôle, hasAnyEditorRole)"
```

---

## Task 10: Shell — `StatusBar`

**Files:**
- Create: `shell/src/shell/chrome/StatusBar.tsx`
- Create: `shell/src/shell/chrome/StatusBar.test.tsx`

**Interfaces:**
- Consumes: `useMe` (`version`, `tenantSlug` — Task 2/9).

Version+tenant seulement dans ce plan (décision de session, spec §2.1.3) — pas de lecture de la file `procrastinate`, réservée à SP-31.

- [ ] **Step 1: Écrire le test**

```tsx
// shell/src/shell/chrome/StatusBar.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { StatusBar } from "./StatusBar";

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <StatusBar />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche la version et le tenant depuis /me", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "",
        lastName: "",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: false,
        version: "0.1.0",
        tenantSlug: "correze",
      }),
    ),
  );
  renderBar();
  expect(await screen.findByText("v0.1.0 · correze")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/StatusBar.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Étendre `Me` avec `version`/`tenantSlug` (shell)**

Dans `shell/src/api/types.ts`, étendre `Me` (défini au Task 9) :
```ts
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
  isAnalyst: boolean;
  hasAnyEditorRole: boolean;
  version: string;
  tenantSlug: string;
};
```

Dans `shell/src/api/itemClient.ts`, `getMe()` — ajouter les deux champs au type destructuré et à la valeur de retour (mêmes emplacements que Task 9/Step 1) :
```ts
    async getMe(): Promise<Me> {
      const data = await request<{
        username: string;
        firstName: string;
        lastName: string;
        isAdmin: boolean;
        isAnalyst: boolean;
        hasAnyEditorRole: boolean;
        version: string;
        tenantSlug: string;
      }>("GET", `/me`);
      return {
        username: data.username,
        firstName: data.firstName,
        lastName: data.lastName,
        isAdmin: data.isAdmin,
        isAnalyst: data.isAnalyst,
        hasAnyEditorRole: data.hasAnyEditorRole,
        version: data.version,
        tenantSlug: data.tenantSlug,
      };
    },
```

- [ ] **Step 4: Implémenter `StatusBar`**

```tsx
// shell/src/shell/chrome/StatusBar.tsx
// SPDX-License-Identifier: Apache-2.0
import { useMe } from "../../api/hooks";

export function StatusBar() {
  const meQuery = useMe();
  if (!meQuery.data) return <div className="h-[21px] border-t border-rule" />;
  return (
    <div className="flex h-[21px] items-center gap-3 border-t border-rule px-2 font-mono text-[9px] text-ink-3">
      <span>
        v{meQuery.data.version} · {meQuery.data.tenantSlug}
      </span>
    </div>
  );
}
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/StatusBar.test.tsx`
Expected: PASS.

- [ ] **Step 6: Vérifier la non-régression des tests `AccountMenu`/`itemClient` touchés par l'extension de `Me`**

Run: `cd shell && npx vitest run src/shell/chrome/AccountMenu.test.tsx src/api/itemClient.test.ts`
Expected: PASS (les mocks `meResponse()` du Task 9 n'incluent pas `version`/`tenantSlug` — vérifier qu'aucune assertion stricte n'échoue ; sinon ajouter `version: "0.1.0", tenantSlug: "test"` à la fonction `meResponse()` de `AccountMenu.test.tsx`).

- [ ] **Step 7: Suite complète**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add shell/src/shell/chrome/StatusBar.tsx shell/src/shell/chrome/StatusBar.test.tsx shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/shell/chrome/AccountMenu.test.tsx
git commit -m "feat(shell): StatusBar (version + tenant depuis /me)"
```

---

## Task 11: Shell — `TriptychLayout`

**Files:**
- Create: `shell/src/shell/chrome/TriptychLayout.tsx`
- Create: `shell/src/shell/chrome/TriptychLayout.test.tsx`

**Interfaces:**
- Consumes: `useNarrowViewport` (Task 8).
- Produces: `TriptychLayout`, `type TriptychTab` — consommés par les pages réelles de SP-30b (aucune ici).

Testé avec une page factice (fixture littérale), comme prescrit par la spec (§6.1, famille Chrome).

- [ ] **Step 1: Écrire le test**

```tsx
// shell/src/shell/chrome/TriptychLayout.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TriptychLayout } from "./TriptychLayout";

vi.mock("./useNarrowViewport", () => ({ useNarrowViewport: vi.fn() }));
import { useNarrowViewport } from "./useNarrowViewport";

const TABS = {
  browse: { id: "browse", label: "Parcourir", content: <p>Contenu Parcourir</p> },
  work: { id: "work", label: "Travailler", content: <p>Contenu Travailler</p> },
  inspect: { id: "inspect", label: "Inspecter", content: <p>Contenu Inspecter</p> },
};

test("large : les trois volets sont visibles en même temps", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(false);
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

test("étroit : un seul volet à la fois, par défaut Travailler", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.queryByText("Contenu Parcourir")).not.toBeInTheDocument();
});

test("étroit : basculer d'onglet change le volet affiché", async () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} />);
  await userEvent.click(screen.getByRole("tab", { name: "Parcourir" }));
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.queryByText("Contenu Travailler")).not.toBeInTheDocument();
});

test("étroit : respecte defaultTabId quand fourni", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} defaultTabId="browse" />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/TriptychLayout.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Implémenter `TriptychLayout`**

```tsx
// shell/src/shell/chrome/TriptychLayout.tsx
// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";
import { useNarrowViewport } from "./useNarrowViewport";

export type TriptychTab = { id: string; label: string; content: ReactNode };

export function TriptychLayout({
  browse,
  work,
  inspect,
  defaultTabId,
}: {
  browse: TriptychTab;
  work: TriptychTab;
  inspect: TriptychTab;
  defaultTabId?: string;
}) {
  const narrow = useNarrowViewport();
  const tabs = [browse, work, inspect];
  const [activeId, setActiveId] = useState(defaultTabId ?? work.id);

  if (!narrow) {
    return (
      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)] overflow-hidden">
        <div className="overflow-y-auto border-r border-rule">{browse.content}</div>
        <div className="overflow-hidden">{work.content}</div>
        <div className="overflow-y-auto border-l border-rule">{inspect.content}</div>
      </div>
    );
  }

  const active = tabs.find((tabItem) => tabItem.id === activeId) ?? work;
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div role="tablist" className="flex border-b border-rule">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.id}
            role="tab"
            aria-selected={tabItem.id === activeId}
            className="flex-1 px-3 py-2 text-sm text-ink-2 aria-selected:border-b-2 aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink"
            onClick={() => setActiveId(tabItem.id)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="flex-1 overflow-y-auto">
        {active.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/chrome/TriptychLayout.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Suite complète + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/chrome/TriptychLayout.tsx shell/src/shell/chrome/TriptychLayout.test.tsx
git commit -m "feat(shell): TriptychLayout (volet1/2/3, collapse en onglets sous 390px)"
```

---

## Task 12: Shell — Assembler `AppLayout`

**Files:**
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/AppLayout.test.tsx`

**Interfaces:**
- Consumes: `TopBar` (Task 9), `DomainBar` (Task 7), `BottomNav` (Task 8), `StatusBar` (Task 10), `useNarrowViewport` (Task 8).

L'ancien chrome (nav à cinq liens texte) disparaît complètement. Toutes les pages protégées existantes (Catalogue, Cartes, Données, Apps & sites, etc.) restent **inchangées** à l'intérieur — seul ce qui les enveloppe change. C'est le seul écran où « aucun écran de l'ancien chrome ne subsiste » (critère de sortie §7.1 de la spec) s'applique déjà entièrement dans ce plan ; le contenu des pages elles-mêmes suit en SP-30b.

- [ ] **Step 1: Remplacer les tests obsolètes de `AppLayout.test.tsx`**

Les tests "shows the Extensions and Collections admin links...", "hides the admin links...", "shows the SQL Lab link...", "hides the SQL Lab link..." (lignes 57-118) vérifiaient l'ancien `<nav>` à cinq liens — remplacés par les tests de `DomainBar` (Task 7). Les retirer, garder les deux tests de bandeau lecture seule ("shows the read-only demo banner...", "hides the read-only demo banner...") inchangés, et remplacer le premier test ("shows brand, username and sign-out") par :

```tsx
test("assemble TopBar, DomainBar et StatusBar autour du contenu", async () => {
  renderLayout();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Catalogue" })).toBeInTheDocument();
  expect(screen.getByText("content")).toBeInTheDocument();
});
```

Garder les deux `vi.mock` pour `NewItemButton`/`ImportFileButton` en tête de fichier tels quels : `AppLayout` inclut `TopBar` réellement (sans le mocker), et `TopBar` rend les vrais `NewItemButton`/`ImportFileButton` sauf à les mocker ici — les retirer ferait fuiter leurs dialogues internes (non pertinents pour ce test) dans le rendu.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx`
Expected: FAIL — `DomainBar`/`TopBar` pas encore assemblés dans `AppLayout`.

- [ ] **Step 3: Réécrire `AppLayout.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useMe, useInstanceInfo } from "../api/hooks";
import { TopBar } from "./chrome/TopBar";
import { DomainBar } from "./chrome/DomainBar";
import { BottomNav } from "./chrome/BottomNav";
import { StatusBar } from "./chrome/StatusBar";
import { useNarrowViewport } from "./chrome/useNarrowViewport";
import { useIsExportRender } from "./useIsExportRender";
import { t } from "../i18n";
import type { Profile } from "../auth/capabilities";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const meQuery = useMe();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const tileset3dEnabled = instanceQuery.data?.tileset3dEnabled === true;
  const isExportRender = useIsExportRender();
  const narrow = useNarrowViewport();

  // Cf. commentaire d'origine (conservé à l'identique) : le worker d'export
  // Playwright navigue directement sur une route protégée avec
  // ?exportRender=1 — le chrome (TopBar/DomainBar/StatusBar) ne doit pas
  // apparaître dans la capture.
  if (isExportRender) {
    return <div className="h-screen w-screen">{children}</div>;
  }

  const profile: Profile = {
    isAdmin: meQuery.data?.isAdmin === true,
    isAnalyst: meQuery.data?.isAnalyst === true,
    capabilities: {
      readOnly,
      etlEnabled: instanceQuery.data?.etlEnabled === true,
      exportEnabled: instanceQuery.data?.exportEnabled === true,
      appExportEnabled: instanceQuery.data?.appExportEnabled === true,
      tileset3dEnabled,
      terrain3dEnabled: instanceQuery.data?.terrain3dEnabled === true,
      copilotEnabled: instanceQuery.data?.copilotEnabled === true,
    },
  };

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      {readOnly && (
        <p className="bg-amber-100 px-6 py-2 text-center text-sm text-amber-900">
          {t("layout.readOnlyBanner")}
        </p>
      )}
      <TopBar tileset3dEnabled={tileset3dEnabled} />
      {!narrow && <DomainBar profile={profile} />}
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
      {narrow && <BottomNav profile={profile} />}
      <StatusBar />
    </div>
  );
}
```

Ajouter à `catalog.fr.ts` la clé du bandeau (le texte littéral existant devient une clé i18n, pas un nouveau texte) :
```ts
  "layout.readOnlyBanner": "Mode démo — lecture seule, les modifications ne sont pas enregistrées.",
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx`
Expected: PASS.

- [ ] **Step 5: Suite complète shell + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS.

- [ ] **Step 6: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: la plupart des specs passent inchangées (le contenu des pages n'a pas changé). Des specs qui cherchaient les anciens liens de nav (`getByRole("link", { name: "Extensions" })` dans l'ancien `<nav>`, remplacés par `DomainBar`) peuvent échouer — corriger ces sélecteurs pour pointer vers les nouveaux liens de `DomainBar`/`BottomNav` (mêmes libellés visibles, structure DOM différente). Ne pas modifier le vocabulaire des specs au-delà de ce que la nouvelle structure exige (A2 : réécriture au fil de l'eau, pas un big-bang de vocabulaire).

Run: `grep -rln "role=\"link\"" e2e/*.spec.ts | xargs grep -ln "Extensions\|Collections\|SQL Lab\|Nouveau"` pour trouver les specs à vérifier en priorité.

- [ ] **Step 7: Portes de qualité shell**

Run: `cd shell && npm run lint && npm run format:check && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold`
Expected: PASS (nettoyer `dist/`/`dist-export/` avant de mesurer la couverture — piège documenté quatre fois).

- [ ] **Step 8: `uvx pre-commit run --all-files`**

Run: `uvx pre-commit run --all-files`
Expected: PASS (5 hooks).

- [ ] **Step 9: Commit**

```bash
git add shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx shell/src/i18n/catalog.fr.ts shell/e2e
git commit -m "feat(shell): AppLayout assemble le chrome triptyque, l'ancien nav disparaît"
```

---

## Vérification finale de branche

Avant de considérer SP-30a terminé :

1. `cd core && uv run pytest -q` — vert (hors les 2 échecs préexistants documentés).
2. `cd shell && npm run test && npm run e2e && npm run build` — vert.
3. Toutes les portes de qualité (`## Commandes` du CLAUDE.md) — vertes, seuils non régressés.
4. `git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts` — non vide, commité (Task 3).
5. Revue finale de branche (subagent-driven-development ou requesting-code-review) : chercher spécifiquement les défauts de croisement entre tâches (piège n°4) — en particulier, `Me`/`MeResponse` a été étendu trois fois (Tasks 2, 9, 10) : vérifier qu'aucun des trois changements n'a été oublié ou contredit par un autre dans le fichier final.
6. Ce que ce plan **ne fait pas**, à ne pas signaler comme un oubli en revue : aucune page métier n'est basculée sur `TriptychLayout`, `⌘K` n'existe pas encore, la file `procrastinate` n'est pas visible dans `StatusBar` — tout est explicitement différé à SP-30b (ou SP-31 pour la file de tâches), documenté dans la spec SP-30 §2.2 et rappelé à chaque tâche concernée ci-dessus.
