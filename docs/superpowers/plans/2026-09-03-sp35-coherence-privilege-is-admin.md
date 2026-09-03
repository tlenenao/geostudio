# SP-35 — Cohérence privilège/`is_admin` sur 4 sites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sur 4 sites de `core/app`, remplacer une vérification directe de
`user.is_admin` par le privilège nommé qui gouverne déjà la même surface
ailleurs (`admin.collections.manage`, `admin.extensions.manage`,
`settings.instance.manage`) — pour qu'un rôle sur mesure porteur de ce
privilège, sans être le rôle prédéfini `admin`, obtienne le même
comportement qu'un utilisateur `admin`, au lieu d'être traité comme
non-privilégié.

**Architecture:** Un nouveau helper booléen `has_privilege(session, user,
privilege) -> bool` complète `require_privilege` (qui lève 403) dans
`app/roles/guards.py`. Les 3 sites qui calculent une *visibilité/portée*
(pas un refus de requête) utilisent `has_privilege` ; le 4e site
(`admin_tools`), qui doit refuser la requête, bascule sur `require_privilege`
comme les 5 modules déjà migrés par SP-31.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, pytest (SQLite mémoire
pour tous les tests de ce plan — aucun ne nécessite PostGIS).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-03-sp35-coherence-privilege-is-admin-design.md`.
- **Aucun changement de comportement pour un utilisateur avec le rôle
  prédéfini `admin`** (qui porte tous les privilèges) — seul un rôle sur
  mesure porteur du privilège concerné change de comportement.
- **Une seule requête de rôle par page** (doctrine SP-29a, déjà respectée par
  `roles_for_collections`) — ne pas introduire de lookup de rôle par
  collection dans une boucle. `has_privilege`/`require_privilege` ne sont
  appelés qu'une fois par requête HTTP sur les sites de ce plan.
- **Hors périmètre, ne pas toucher** : tout usage de `user.is_admin`/
  `actor_is_admin` qui alimente `decide()`/`can()` (bypass admin volontaire
  et documenté) — `app/pipelines/`, `app/mcp/`, `app/features/routes.py`,
  `app/dcat/`, `app/stac/`, `app/sharing/authorization.py`,
  `app/items/repository.py`, et les verdicts `read`/`write`/`share` de
  `_collection_permissions` (seul `delete` change dans ce plan).
- `mypy --strict app/admin_tools app/roles` doit rester vert — ces deux
  modules sont déjà dans le périmètre strict de la CI
  (`.github/workflows/ci.yml:60`). `app/collections`/`app/extensions` ne
  sont *pas* dans ce périmètre strict (seulement l'informatif `mypy app/ ||
  true`) — pas de nouvelle erreur bloquante attendue, mais pas de gate
  supplémentaire à faire passer non plus.
- TDD systématique : test rouge → implémentation minimale → test vert, à
  chaque étape.
- Commits conventionnels (`fix(core): …`), un sujet par commit.

---

## Task 1: `has_privilege` — helper booléen dans `app/roles/guards.py`

**Files:**
- Modify: `core/app/roles/guards.py`
- Test: `core/tests/test_roles_guards.py`

**Interfaces:**
- Produces: `has_privilege(session: Session, user: User, privilege: str) -> bool`
  dans `app.roles.guards` — retourne `True` si le rôle de `user` porte
  `privilege`, `False` sinon (y compris si le rôle est introuvable). Utilisé
  par les Tasks 2, 3, 4. `require_privilege` (signature inchangée) devient
  interne à `has_privilege` — les deux restent exportées.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `core/tests/test_roles_guards.py` (après le test
existant, même fichier, même style de fixture) :

```python
def test_has_privilege_returns_a_plain_bool_without_raising():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a2",
            username="a2",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r2",
            username="r2",
            email=None,
            first_name="",
            last_name="",
        )
        s.flush()

        assert has_privilege(s, admin, Privilege.ADMIN_ROLES_MANAGE.value) is True
        assert has_privilege(s, reader, Privilege.ADMIN_ROLES_MANAGE.value) is False
```

Et ajouter l'import en tête de fichier, à côté de l'import existant de
`require_privilege` :

```python
from app.roles.guards import has_privilege, require_privilege
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_roles_guards.py -v`
Expected: FAIL — `ImportError: cannot import name 'has_privilege' from 'app.roles.guards'`

- [ ] **Step 3: Write minimal implementation**

Remplacer le contenu de `core/app/roles/guards.py` par :

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def has_privilege(session: Session, user: User, privilege: str) -> bool:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    return role is not None and privilege in role.privileges


def require_privilege(session: Session, user: User, privilege: str) -> None:
    if not has_privilege(session, user, privilege):
        raise HTTPException(status_code=403, detail=f"privilege '{privilege}' required")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_roles_guards.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: mypy --strict**

Run: `cd core && uv run mypy --strict app/roles`
Expected: `Success: no issues found`

- [ ] **Step 6: Commit**

```bash
cd core
git add app/roles/guards.py tests/test_roles_guards.py
git commit -m "feat(core): ajoute has_privilege, variante booléenne de require_privilege

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Task 2: Collections — la portée de `GET /collections` reflète `admin.collections.manage`

**Files:**
- Modify: `core/app/collections/repository.py:101-108` (`list_visible_collections`)
- Modify: `core/app/collections/routes.py:247-263` (`list_collections`)
- Test: `core/tests/test_collections_repository.py:73-91,167-219,222-305`
- Test: `core/tests/test_ingestion_importer.py:211-215,324-328`
- Test: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes: `has_privilege(session, user, privilege) -> bool` (Task 1).
- Produces: `list_visible_collections(..., can_see_all: bool, ...)` — le
  paramètre `is_admin` est renommé `can_see_all`. `list_collections`
  (routes.py) calcule une variable locale `can_manage_collections: bool`,
  réutilisée par Task 3 dans la même fonction.

### Étape A — renommer le paramètre dans le repository

- [ ] **Step 1: Write the failing test (mise à jour des tests existants)**

Dans `core/tests/test_collections_repository.py`, remplacer les 3 occurrences
de `is_admin=` par `can_see_all=` (kwarg seul, valeur inchangée) :

Ligne 88-90 :
```python
    cols = repo.list_visible_collections(
        session, tenant_id=tenant.id, user_id=user.id, can_see_all=False
    )
```

Ligne 212-218 (dans `test_list_visible_collections_hybrid_search_never_leaks_an_invisible_collection`) :
```python
    cols = repo.list_visible_collections(
        pg_session,
        tenant_id=tenant.id,
        user_id=other.id,
        can_see_all=False,
        q="incidents",
    )
```

Ligne 296-302 (dans `test_list_visible_collections_hybrid_search_ranks_semantic_match_ahead_of_weak_text_match`) :
```python
    cols = repo.list_visible_collections(
        pg_session,
        tenant_id=tenant.id,
        user_id=user.id,
        can_see_all=False,
        q="incidents voirie",
    )
```

Dans `core/tests/test_ingestion_importer.py`, remplacer les 2 occurrences
(lignes 212-214 et 325-327) :
```python
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, can_see_all=True
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_collections_repository.py tests/test_ingestion_importer.py -v -k "not postgis"`
Expected: FAIL — `TypeError: list_visible_collections() got an unexpected keyword argument 'can_see_all'`

- [ ] **Step 3: Write minimal implementation**

Dans `core/app/collections/repository.py`, remplacer la signature et le
premier `if` de `list_visible_collections` (lignes 101-110) :

```python
def list_visible_collections(
    session: Session,
    *,
    tenant_id: str,
    user_id: str | None,
    can_see_all: bool,
    q: str | None = None,
) -> list[Collection]:
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not can_see_all:
```

(le reste du corps de la fonction, lignes 111-147, est inchangé.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_repository.py tests/test_ingestion_importer.py -v -k "not postgis"`
Expected: PASS

### Étape B — câbler le privilège dans la route

- [ ] **Step 5: Write the failing test**

Ajouter à `core/tests/test_collections_routes.py`, après
`test_public_collection_visible_to_anonymous` (après la ligne 203) :

```python
def test_custom_role_with_collections_manage_sees_a_private_collection(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # privée, admin owner

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)
        listed = client.get("/collections").json()["collections"]
        assert [c["id"] for c in listed] == ["incidents"]
```

Note : `get_or_create_default_tenant` est déjà importé en tête de
`test_collections_routes.py` (ligne 12).

- [ ] **Step 6: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k custom_role_with_collections_manage`
Expected: FAIL — `assert [] == ["incidents"]` (la collection privée reste invisible : `is_admin` du custom role est `False`)

- [ ] **Step 7: Write minimal implementation**

Dans `core/app/collections/routes.py`, ligne 23, étendre l'import :

```python
from app.roles.guards import has_privilege, require_privilege
```

Puis remplacer `list_collections` (lignes 247-263, la partie avant le
calcul de `owner_ids`) :

```python
@router.get("/collections")
def list_collections(
    q: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.models import User

    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    cols = repo.list_visible_collections(
        session,
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        can_see_all=can_manage_collections,
        q=q,
    )
```

(le reste de la fonction, à partir de `owner_ids = {...}` ligne 264, est
inchangé pour l'instant — Task 3 y ajoutera l'usage de
`can_manage_collections` sur l'appel à `collection_permissions_by_id`.)

- [ ] **Step 8: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k custom_role_with_collections_manage`
Expected: PASS

- [ ] **Step 9: Run the full collections test files**

Run: `cd core && uv run pytest tests/test_collections_repository.py tests/test_collections_routes.py tests/test_ingestion_importer.py -v -k "not postgis"`
Expected: PASS (tous)

- [ ] **Step 10: Commit**

```bash
cd core
git add app/collections/repository.py app/collections/routes.py \
  tests/test_collections_repository.py tests/test_collections_routes.py \
  tests/test_ingestion_importer.py
git commit -m "fix(core): la portée de GET /collections reflète admin.collections.manage

Un rôle sur mesure porteur du privilège admin.collections.manage voit
désormais toutes les collections du tenant, comme le rôle prédéfini admin
— au lieu d'être limité aux collections publiques/partagées/possédées.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Task 3: Collections — le verdict `delete` reflète `admin.collections.manage`

**Files:**
- Modify: `core/app/collections/repository.py:205-264` (`_collection_permissions`, `collection_permissions_by_id`)
- Modify: `core/app/collections/schemas.py:17-40` (docstring `CollectionPermissions`)
- Modify: `core/app/collections/routes.py` (5 sites : `register_collection`, `create_empty_collection_route`, `list_collections`, `get_collection`, `patch_collection`)
- Test: `core/tests/test_collections_repository.py:325-409`
- Test: `core/tests/test_collections_routes.py` (extension du test de Task 2)

**Interfaces:**
- Consumes: `has_privilege` (Task 1), `can_manage_collections` (variable
  locale introduite par Task 2 dans `list_collections`).
- Produces: `_collection_permissions(..., can_manage_collections: bool)`,
  `collection_permissions_by_id(..., can_manage_collections: bool, ...)` —
  nouveau paramètre obligatoire sur les deux fonctions. `actor_is_admin`
  reste un paramètre séparé et inchangé (verdicts `read`/`write`/`share`,
  hors périmètre).

### Étape A — repository : nouveau paramètre, verdict `delete` recalculé

- [ ] **Step 1: Write the failing tests**

Dans `core/tests/test_collections_repository.py`, mettre à jour les 6 appels
existants à `collection_permissions_by_id` (lignes 325-409) en ajoutant
`can_manage_collections=` à chacun, et ajouter un nouveau test qui prouve la
séparation d'avec `actor_is_admin` :

```python
def test_owner_gets_full_permissions_except_delete(session, tenant, owner):
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=owner.id,
        actor_is_admin=False,
        can_manage_collections=False,
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
        can_manage_collections=True,
        collections=[col],
    )
    assert result[col.id].delete is True


def test_custom_role_gets_delete_without_being_actor_is_admin(session, tenant, owner, other):
    # Le coeur de SP-35 : delete suit can_manage_collections, pas actor_is_admin.
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=other.id,
        actor_is_admin=False,
        can_manage_collections=True,
        collections=[col],
    )
    assert result[col.id].delete is True
    assert result[col.id].read is False  # inchangé : read reste gouverné par decide()/actor_is_admin


def test_non_admin_owner_cannot_delete(session, tenant, owner):
    # Anti-régression : unregister_collection est require_privilege(
    # admin.collections.manage) seul, pas decide() — un propriétaire
    # non-privilégié ne doit JAMAIS voir delete=True,
    # sinon le bouton Supprimer produirait un 403 après clic.
    col = _register(session, tenant, owner)
    result = collection_permissions_by_id(
        session,
        tenant_id=tenant.id,
        current_user_id=owner.id,
        actor_is_admin=False,
        can_manage_collections=False,
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
        can_manage_collections=False,
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
        can_manage_collections=False,
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
        can_manage_collections=False,
        collections=[col],
    )
    assert result[col.id] == CollectionPermissions(
        read=True, write=False, delete=False, share=False
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_collections_repository.py -v -k "delete or permissions or owner or editor or anonymous"`
Expected: FAIL — `TypeError: collection_permissions_by_id() missing 1 required keyword-only argument: 'can_manage_collections'`

- [ ] **Step 3: Write minimal implementation**

Dans `core/app/collections/repository.py`, remplacer `_collection_permissions`
et `collection_permissions_by_id` (lignes 205-264) :

```python
def _collection_permissions(
    col: Collection,
    *,
    current_user_id: str | None,
    roles: frozenset[str],
    actor_is_admin: bool,
    can_manage_collections: bool,
) -> CollectionPermissions:
    is_owner = current_user_id is not None and col.owner_id == current_user_id

    def verdict(action: Action) -> bool:
        if action == "delete":
            return can_manage_collections
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
    can_manage_collections: bool,
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
            can_manage_collections=can_manage_collections,
        )
        for c in collections
    }
```

(la fermeture `for c in collections` et le `}` final reprennent exactement
la fin déjà présente après la ligne 264 — ne pas dupliquer.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_repository.py -v -k "not postgis"`
Expected: PASS (tous, y compris le nouveau `test_custom_role_gets_delete_without_being_actor_is_admin`)

### Étape B — docstring `CollectionPermissions`

- [ ] **Step 5: Corriger le docstring**

Dans `core/app/collections/schemas.py`, remplacer le docstring de
`CollectionPermissions` (lignes 18-34) :

```python
class CollectionPermissions(BaseModel):
    """Miroir d'`ItemPermissions` (`app/items/schemas.py`) pour les
    collections. Calculé depuis `decide()`, jamais recalculé côté client.

    `delete` n'est PAS le verdict générique de `decide()` : `unregister_collection`
    (DELETE /collections/{id}) est gardé par `require_privilege(...,
    "admin.collections.manage")` seul, pas par `can()`/`decide()`. Le calcul de
    `delete` ici (`app/collections/repository.py::_collection_permissions`)
    reflète directement ce même privilège via `has_privilege()`
    (`app/roles/guards.py`), pas `actor_is_admin`/`User.is_admin` — un rôle
    sur mesure qui détiendrait `admin.collections.manage` sans être le rôle
    prédéfini "admin" voit donc `delete: true` ici exactement quand la route
    DELETE le laisserait effectivement passer (SP-35, corrige l'écart
    documenté par SP-31 — l'ancien comportement retournait `actor_is_admin`
    ici).
    """

    read: bool
    write: bool
    delete: bool
    share: bool
```

Pas de test dédié pour un docstring — vérifié par relecture à l'Étape D.

### Étape C — router les 5 sites d'appel

- [ ] **Step 6: Write the failing test (extension du test de Task 2)**

Étendre `test_custom_role_with_collections_manage_sees_a_private_collection`
(ajouté par Task 2 dans `core/tests/test_collections_routes.py`) pour
couvrir aussi `delete`, en remplaçant son corps par :

```python
def test_custom_role_with_collections_manage_sees_and_can_delete_a_private_collection(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # privée, admin owner

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)

        listed = client.get("/collections").json()["collections"]
        assert [c["id"] for c in listed] == ["incidents"]
        assert listed[0]["permissions"]["delete"] is True

        # La route DELETE laisse effectivement passer — le verdict n'est pas
        # un mensonge d'affichage (piège n°5/n°4 : chemin de lecture ET
        # d'écriture doivent être d'accord).
        assert client.delete("/collections/incidents").status_code == 204
```

(renomme le test : l'ancien nom
`test_custom_role_with_collections_manage_sees_a_private_collection` de
Task 2 disparaît, remplacé par celui-ci — un seul test couvre maintenant
les deux sites.)

- [ ] **Step 7: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k custom_role_with_collections_manage`
Expected: FAIL — soit `TypeError` (paramètre manquant) si l'implémentation
n'est pas encore branchée, soit `assert False is True` sur
`permissions["delete"]` (verdict encore basé sur `actor_is_admin`) selon
l'ordre d'exécution des steps — dans les deux cas, échec attendu avant
l'Étape suivante.

- [ ] **Step 8: Write minimal implementation — les 5 sites de `routes.py`**

Dans `core/app/collections/routes.py`, mettre à jour chacun des 5 appels
à `collection_permissions_by_id` :

`register_collection` (après `require_privilege(...)` ligne 172, l'appel
est en fin de fonction, lignes 208-214) :

```python
    can_manage_collections = has_privilege(
        session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

`create_empty_collection_route` (lignes 237-243) :

```python
    can_manage_collections = has_privilege(
        session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

`list_collections` — la variable `can_manage_collections` existe déjà
(introduite par Task 2), seul l'appel à `collection_permissions_by_id`
(lignes 270-276) change :

```python
    permissions_by_id = repo.collection_permissions_by_id(
        session,
        tenant_id=tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        can_manage_collections=can_manage_collections,
        collections=cols,
    )
```

`get_collection` (lignes 330-337) :

```python
    col = get_readable_collection(session, user, collection_id)
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=col.tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
```

`patch_collection` (lignes 419-425) :

```python
    can_manage_collections = has_privilege(
        session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: PASS (tous)

### Étape D — vérification de clôture de la tâche

- [ ] **Step 10: Run the full collections + roles test suites**

Run: `cd core && uv run pytest tests/test_collections_repository.py tests/test_collections_routes.py tests/test_ingestion_importer.py tests/test_roles_guards.py -v -k "not postgis"`
Expected: PASS (tous)

- [ ] **Step 11: mypy informatif (non bloquant) sur collections**

Run: `cd core && uv run mypy app/collections/ || true`
Expected : pas de nouvelle erreur introduite par ce plan (comparer
visuellement à la sortie avant modification si le fichier en avait déjà —
ne pas chercher à corriger des erreurs préexistantes hors périmètre).

- [ ] **Step 12: Commit**

```bash
cd core
git add app/collections/repository.py app/collections/schemas.py app/collections/routes.py \
  tests/test_collections_repository.py tests/test_collections_routes.py
git commit -m "fix(core): le verdict delete de CollectionPermissions reflète admin.collections.manage

Un rôle sur mesure porteur du privilège admin.collections.manage obtient
désormais delete: true, comme le rôle prédéfini admin — au lieu de
dépendre de actor_is_admin/User.is_admin. Corrige l'écart documenté par la
revue finale SP-31 et son docstring dans CollectionPermissions.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Task 4: Extensions — `include_disabled` reflète `admin.extensions.manage`

**Files:**
- Modify: `core/app/extensions/routes.py:97-108` (`list_extensions`)
- Test: `core/tests/test_extensions_routes.py`

**Interfaces:**
- Consumes: `has_privilege` (Task 1).
- Produces : aucun symbole nouveau exposé à d'autres tâches — site
  autonome.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_extensions_routes.py`, après
`test_get_extensions_all_true_ignored_for_anonymous` (fin de fichier) :

```python
def test_get_extensions_all_true_shown_to_custom_role_with_extensions_manage(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, Session, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire d'extensions",
            privileges=[Privilege.ADMIN_EXTENSIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)
        all_listed = client.get("/extensions?all=true").json()["extensions"]
        assert [e["id"] for e in all_listed] == ["acme.gauge"]
```

Ajouter l'import manquant en tête de fichier :

```python
from app.tenants.repository import get_or_create_default_tenant
```

(vérifier d'abord s'il est déjà importé — ce fichier importe déjà
`get_or_create_default_tenant` dans la fixture `env`, ligne 12 du fichier
existant, donc l'import est probablement déjà présent en tête de module ;
ne pas le dupliquer si c'est le cas.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_extensions_routes.py -v -k custom_role_with_extensions_manage`
Expected: FAIL — `assert [] == ["acme.gauge"]` (le rôle sur mesure est
`is_admin=False`, donc `include_disabled` reste `False`)

- [ ] **Step 3: Write minimal implementation**

Dans `core/app/extensions/routes.py`, ligne 9, étendre l'import :

```python
from app.roles.guards import has_privilege, require_privilege
```

Puis remplacer la ligne `include_disabled = ...` (ligne 105) dans
`list_extensions` :

```python
@router.get("/extensions")
def list_extensions(
    all: bool = False,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    include_disabled = bool(
        user and all and has_privilege(session, user, Privilege.ADMIN_EXTENSIONS_MANAGE.value)
    )
    exts = repo.list_extensions(session, tenant_id=tenant_id, include_disabled=include_disabled)
    return {"extensions": [_extension_json(e) for e in exts]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_extensions_routes.py -v`
Expected: PASS (tous, y compris les 3 tests `all_true_*` déjà existants —
`test_get_extensions_all_true_shows_disabled_to_admin` doit rester vert :
le rôle prédéfini `admin` porte `admin.extensions.manage`)

- [ ] **Step 5: Commit**

```bash
cd core
git add app/extensions/routes.py tests/test_extensions_routes.py
git commit -m "fix(core): GET /extensions?all=true reflète admin.extensions.manage

Un rôle sur mesure porteur du privilège admin.extensions.manage voit
désormais les extensions désactivées avec ?all=true, comme le rôle
prédéfini admin — au lieu de dépendre de User.is_admin.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Task 5: Admin tools — `launch_admin_tool` gardé par `settings.instance.manage`

**Files:**
- Modify: `core/app/admin_tools/routes.py:1-50`
- Test: `core/tests/test_admin_tools_routes.py`

**Interfaces:**
- Consumes: `require_privilege` (déjà existant, `app.roles.guards`).
- Produces : aucun symbole nouveau — site autonome. Supprime
  `_require_admin` (fonction privée, aucun autre module ne l'importe —
  vérifié : `grep -rn "_require_admin" core/app` ne retourne que ce
  fichier).

- [ ] **Step 1: Write the failing test**

La fixture `env` existante (`core/tests/test_admin_tools_routes.py`)
capture `session_factory` dans la fermeture `override_session` sans
l'exposer — pour construire un rôle sur mesure dans le nouveau test, il
faut que `env` retourne aussi `session_factory` lui-même. Modifier la
fixture `env`
(remplacer le `return` final) :

```python
    return TestClient(app), use_as, admin_id, member_id, session_factory
```

Puis mettre à jour la signature de **tous** les tests existants de ce
fichier qui déstructurent `env` — chacun passe de
`client, use_as, _admin_id, member_id = env` (ou variante) à la même liste
plus `_session_factory` (ou le nom pertinent). Concrètement, chaque ligne
`client, use_as, X, Y = env` du fichier devient `client, use_as, X, Y, _sf = env`.
Repérer ces lignes avec :

Run: `cd core && grep -n "= env$" tests/test_admin_tools_routes.py`

puis ajouter `, _sf` (ou le nom choisi) à chacune.

Ajouter enfin le nouveau test :

```python
def test_launch_allowed_for_custom_role_with_settings_instance_manage(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import set_user_role

    client, use_as, _admin_id, member_id, session_factory = env

    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Infra",
            privileges=[Privilege.SETTINGS_INSTANCE_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=member_id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()

    use_as(member_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify the new one fails and the others still pass**

Run: `cd core && uv run pytest tests/test_admin_tools_routes.py -v`
Expected: le nouveau test FAIL avec `403` au lieu de `200` (member reste
`is_admin=False`, `_require_admin` refuse) ; tous les autres tests déjà
présents restent PASS (la fixture a changé de forme mais son comportement
observable non).

- [ ] **Step 3: Write minimal implementation**

Remplacer le contenu de `core/app/admin_tools/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes du gate /admin/* — montées uniquement quand
CORE_ADMIN_TOOLS_ENABLED est actif (app.main, même patron que
app.tileset3d/app.export). Trois endpoints : lancement (Bearer, appelé par
le shell), bootstrap de session (jeton de lancement à durée de vie courte
(60s) -> cookie, atteint par navigation directe du navigateur depuis l'URL
renvoyée par le lancement), et vérification (appelée par le forwardAuth de
Traefik, jamais par le shell — cf. plan d'implémentation, Tâche 4)."""

import os
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin_tools.tokens import (
    AdminToolsTokenError,
    decode_launch_token,
    decode_session_token,
    mint_launch_token,
    mint_session_token,
)
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()

ToolName = Literal["martin", "titiler", "grafana"]
_SESSION_COOKIE = "gs_admin_session"
_SESSION_MAX_AGE_SECONDS = 1800


class LaunchAdminToolResponse(BaseModel):
    url: str


@router.post("/admin-tools/launch/{tool}")
def launch_admin_tool(
    tool: ToolName,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LaunchAdminToolResponse:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    base = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    token = mint_launch_token(sub=user.id, tool=tool)
    return LaunchAdminToolResponse(url=f"{base}/admin-tools/session/{tool}?_at={token}")


@router.get("/admin-tools/session/{tool}")
def bootstrap_admin_tool_session(tool: ToolName, _at: str) -> Response:
    try:
        claims = decode_launch_token(_at)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid launch token") from exc
    if claims.tool != tool:
        raise HTTPException(status_code=401, detail="invalid launch token")
    session_token = mint_session_token(sub=claims.sub)
    response = RedirectResponse(url=f"/admin/{tool}/", status_code=302)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=session_token,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/admin",
    )
    return response


@router.get("/admin-tools/verify")
def verify_admin_tool_session(gs_admin_session: str | None = Cookie(default=None)) -> Response:
    if gs_admin_session is None:
        raise HTTPException(status_code=403, detail="no admin session")
    try:
        decode_session_token(gs_admin_session)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=403, detail="invalid admin session") from exc
    return Response(status_code=200)
```

(seul changement fonctionnel : suppression de `_require_admin`, ajout du
paramètre `session` et de l'appel `require_privilege(...)` dans
`launch_admin_tool`. `bootstrap_admin_tool_session` et
`verify_admin_tool_session` sont recopiées à l'identique.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_admin_tools_routes.py tests/test_admin_tools_enabled_flag.py tests/test_admin_tools_tokens.py tests/test_admin_tools_secret_guard.py -v`
Expected: PASS (tous)

- [ ] **Step 5: mypy --strict**

Run: `cd core && uv run mypy --strict app/admin_tools`
Expected: `Success: no issues found`

- [ ] **Step 6: Commit**

```bash
cd core
git add app/admin_tools/routes.py tests/test_admin_tools_routes.py
git commit -m "fix(core): POST /admin-tools/launch garde settings.instance.manage, pas is_admin

Le shell gate déjà /admin/infrastructure sur ce privilège côté route
(shell/src/shell/routes.tsx) — un rôle sur mesure qui le porte voyait le
bouton dans l'UI mais recevait un 403 réel au clic, faute d'une garde
require_privilege équivalente côté serveur. _require_admin (local,
is_admin direct) supprimé ; ce module n'avait pas encore été migré par
SP-31 car livré par une session concurrente (SP-32/Traefik).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Task 6: Vérification finale + clôture

**Files:** aucun changement de code — vérification uniquement.

- [ ] **Step 1: Suite pytest complète**

Run: `cd core && uv run pytest -q`
Expected: aucune régression par rapport à la référence CLAUDE.md avant ce
plan (1912-1915 passed / ~168 skipped / 0 failed, ou l'intermittent connu
`test_scope_preserves_original_sql_error` documenté séparément — ne pas
imputer un nouvel échec à ce plan sans l'avoir isolé).

- [ ] **Step 2: mypy --strict sur les deux modules déjà dans le périmètre CI**

Run: `cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`
Expected: `Success: no issues found`

- [ ] **Step 3: ruff**

Run: `cd core && uv run ruff check . && uv run ruff format --check .`
Expected: propre (aucun fichier de ce plan ne devrait avoir besoin d'un
reformatage — si `ruff format --check` échoue, lancer `uv run ruff format
.` sur les seuls fichiers touchés par ce plan et relire le diff avant de
committer).

- [ ] **Step 4: lint-imports (contrat de couches)**

Run: `cd core && uv run lint-imports`
Expected: propre — aucun nouvel import cross-module introduit par ce plan
(`app/admin_tools` importait déjà `app.roles.guards`/`app.roles.privileges`
ailleurs dans le dépôt sans problème, ex. `app/harvest`).

- [ ] **Step 5: Diff OpenAPI (piège n°1)**

Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py /tmp/openapi-sp35-check.json
diff core/openapi.json /tmp/openapi-sp35-check.json
```
Expected: diff **vide** — aucune route ni schéma de réponse ne change de
forme dans ce plan (seule la logique interne d'un booléen déjà existant
change). Si le diff n'est pas vide, ne pas régénérer aveuglément : lire le
diff pour comprendre pourquoi avant de committer `core/openapi.json`/
`shell/src/api/generated/core-schema.d.ts`.

- [ ] **Step 6: mypy informatif sur l'ensemble**

Run: `cd core && uv run mypy app/ || true`
Expected: aucune nouvelle erreur attribuable aux fichiers de ce plan
(`app/collections/`, `app/extensions/routes.py`) par rapport à une
exécution avant ce plan — comparer par grep sur les chemins de fichiers
touchés plutôt que sur le compte total (le compte total peut déjà contenir
des erreurs préexistantes sans rapport).

- [ ] **Step 7: Mise à jour de CLAUDE.md**

Ajouter une entrée `### Livré` pour SP-35 (suivre le format des entrées
SP-33/SP-34 déjà présentes : motivation en une phrase, les 4 sites corrigés,
compte de tests avant/après, vérifications de clôture). Retirer la mention
« visibilité `is_admin` vs garde `require_privilege` divergentes sur 3
sites » de la liste des suivis non bloquants hérités de SP-31 (elle est
maintenant traitée — le 4e site, `admin_tools`, n'y figurait pas car
découvert par ce plan, donc rien à retirer pour lui).

- [ ] **Step 8: Commit de clôture**

```bash
git add CLAUDE.md
git commit -m "docs: clôt SP-35 — cohérence privilège/is_admin sur 4 sites dans CLAUDE.md

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WGXq3x4yYsrZF1k5FkW3XF"
```

---

## Self-Review (fait par l'auteur du plan avant transmission)

**1. Couverture de la spec** :
- Site 1 (`list_visible_collections`) → Task 2. ✓
- Site 2 (`_collection_permissions`/`collection_permissions_by_id`) → Task 3. ✓
- Site 3 (`extensions.include_disabled`) → Task 4. ✓
- Site 4 (`admin_tools.launch_admin_tool`, trouvé par l'audit étendu) → Task 5. ✓
- Nouveau helper `has_privilege` → Task 1. ✓
- Docstring `CollectionPermissions` corrigé → Task 3, Étape B. ✓
- Renommage `is_admin` → `can_see_all` sur `list_visible_collections`, ~11
  sites de test → Task 2, Étape A (3 dans `test_collections_repository.py`,
  2 dans `test_ingestion_importer.py` — les 5 kwargs `is_admin=` distincts
  identifiés par grep ; le reste des "11 occurrences" du grep initial de la
  spec comptait aussi les lignes de commentaire/contexte, pas seulement les
  kwargs). ✓
- Hors périmètre (decide()/can(), `User.is_admin` colonne, profil Lecteur) —
  aucune tâche n'y touche. ✓
- Correction apportée pendant la planification, à noter : la spec affirmait
  à tort que `app/admin_tools` n'est pas dans le périmètre `mypy --strict`
  de la CI — il l'est déjà (`.github/workflows/ci.yml:60`, avec `app/roles`).
  Task 5/Step 5 et Task 6/Step 2 vérifient donc les deux modules sous
  `--strict`, pas seulement `app/roles`.

**2. Balayage de placeholders** : aucun "TBD"/"TODO" ; chaque step de code
contient le texte complet à écrire, pas une référence à "faire pareil qu'à
la Task N" (les blocs de Task 3/Étape C répètent le code réel de chaque
site plutôt que de renvoyer à Task 2).

**3. Cohérence des types/signatures** :
- `has_privilege(session: Session, user: User, privilege: str) -> bool`
  (Task 1) — même ordre de paramètres que `require_privilege` existant,
  utilisé identiquement dans les Tasks 2/3/4.
- `list_visible_collections(..., can_see_all: bool, ...)` (Task 2) —
  cohérent entre repository et les 2 sites de test qui l'appellent
  directement (`test_collections_repository.py`,
  `test_ingestion_importer.py`).
- `can_manage_collections: bool` — même nom utilisé pour la variable locale
  de `list_collections` (Task 2) et le paramètre de
  `_collection_permissions`/`collection_permissions_by_id` (Task 3) ; pas de
  divergence de nom entre les deux tâches qui partagent ce fil.
- Task 5 a une étape (Step 1) inhabituellement longue parce que la fixture
  `env` existante de `test_admin_tools_routes.py` ne expose pas
  `session_factory` — plutôt que d'improviser un accès fragile aux
  internes de FastAPI, le plan modifie explicitement la fixture (et
  documente qu'il faut retoucher chaque site qui la déstructure). C'est
  intentionnel, pas un oubli : à exécuter tel quel plutôt que chercher un
  raccourci.
