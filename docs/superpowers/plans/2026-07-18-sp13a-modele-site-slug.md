# SP-13a — modèle `site`/slug + route publique + résolution shell : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un admin de créer un item de type `site` (slug auto-généré, éditable), de le publier, et à un visiteur anonyme de le consulter à `/sites/{slug}` qui rend `AppRenderer(config, "runtime")` — première sous-phase de SP-13 « Portails & Sites ».

**Architecture:** Extension du module `items` existant (aucun nouveau module cœur) : colonne `items.slug` + unicité partielle par tenant, helpers de slug purs, route publique `GET /public/sites/{slug}` miroir de `GET /public/items/{id}`. Shell : premières méthodes `/public/*` de l'`itemClient` (`getItemBySlug`, `getPublicAppConfig`), route publique `/sites/:slug` hors `ProtectedLayout`, type « Site » dans `NewItemButton`. Aucun widget de contenu (SP-13b/c).

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic / pytest (cœur) ; React / TypeScript / react-query / Vitest / Playwright (shell).

## Global Constraints

- En-tête SPDX sur tout nouveau fichier source : `# SPDX-License-Identifier: Apache-2.0` (Python) ou `// SPDX-License-Identifier: Apache-2.0` (TS). Exclusion : `shell/src/api/generated/`.
- Docs et messages utilisateur en **français** ; code/identifiants en **anglais**.
- Commits **conventional** (`feat(core): …`, `feat(shell): …`, `test(shell): …`), petits, un sujet.
- **Aucun nouveau chemin d'autorisation** : un `site` est un item comme un autre (`can()`, politique de publication SP-1c, `audit_log`).
- Tenant public résolu à `"default"` uniquement (A33 — pas de résolution par host en v1).
- Route publique : **404 jamais 403** pour un site non publié / inexistant / d'un autre tenant (pas de fuite d'existence).
- Format de slug : `^[a-z0-9]+(?:-[a-z0-9]+)*$`, longueur ≤ 100. Collision à la **création implicite** (slug absent) → résolution silencieuse par suffixe ; collision à la **création explicite** ou à l'**édition** d'un slug fourni → 409.
- Toute modif de schéma cœur impose de régénérer `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts` (job CI `api-types-drift`) — Task 9.
- Commandes de test : `cd core && uv run pytest` ; `cd shell && npm run test` (Vitest), `npm run e2e` (Playwright), `npm run build` (tsc + vite). Les tests `postgis` s'exécutent contre un PostGIS réel via `CORE_TEST_DATABASE_URL` (marqueur `@pytest.mark.postgis`).

---

## File Structure

**Cœur (créés) :**
- `core/app/items/slug.py` — helpers purs de slug (`slugify`, `is_valid_slug`, exceptions `InvalidSlugError`/`SlugCollisionError`).
- `core/alembic/versions/0015_items_slug.py` — migration colonne + index unique partiel.
- `core/tests/items/test_slug.py` — tests purs des helpers.

**Cœur (modifiés) :**
- `core/app/items/models.py` — colonne `Item.slug`.
- `core/app/items/repository.py` — `slug_exists`, `ensure_unique_slug`, `get_published_site_by_slug` ; `create_item`/`update_item` gagnent `slug`.
- `core/app/items/schemas.py` — `ItemRead.slug`, `ItemUpdatePatch.slug`.
- `core/app/items/routes.py` — `update_item` passe/valide `slug` (422/409).
- `core/app/configs/schemas.py` — `BuilderConfig.kind` += `"site"` + check layout.
- `core/app/configs/routes.py` — `CreateConfigRequest.slug`, passé à `create_item`.
- `core/app/public/routes.py` — `GET /public/sites/{slug}`.
- `core/tests/items/…`, `core/tests/public/…`, `core/tests/configs/…` — tests DB/route.

**Shell (créés) :**
- `shell/src/lib/slug.ts` — `slugify`, `isValidSlug` (miroir client, écho documenté).
- `shell/src/lib/slug.test.ts`
- `shell/src/pages/SitePublicPage.tsx`
- `shell/src/pages/SitePublicPage.test.tsx`
- `shell/e2e/sites-portal-shell.spec.ts`

**Shell (modifiés) :**
- `shell/src/api/types.ts` — `ResourceType`, `CreateKind`, `Item.slug`, `UpdatePatch.slug`, signatures `ItemClient`.
- `shell/src/api/itemClient.ts` — `createConfigItem` (slug), `getItemBySlug`, `getPublicAppConfig`.
- `shell/src/api/hooks.ts` — hooks `useItemBySlug`, `usePublicAppConfig` (si nécessaire pour la page).
- `shell/src/shell/routes.tsx` — route `/sites/:slug`.
- `shell/src/shell/NewItemButton.tsx` — type « Site » + champ slug.
- `shell/e2e/mocks.ts` — routes `/public/sites/*`, `/public/configs/by-item/*`, création `site`.

---

## Task 1 : helpers de slug purs (cœur)

**Files:**
- Create: `core/app/items/slug.py`
- Test: `core/tests/items/test_slug.py`

**Interfaces:**
- Produces:
  - `slugify(text: str) -> str`
  - `is_valid_slug(slug: str) -> bool`
  - `class InvalidSlugError(ValueError)`
  - `class SlugCollisionError(ValueError)`

- [ ] **Step 1: Écrire les tests qui échouent**

`core/tests/items/test_slug.py` :
```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.items.slug import (
    InvalidSlugError,
    SlugCollisionError,
    is_valid_slug,
    slugify,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mon Portail", "mon-portail"),
        ("Été à Lyon !", "ete-a-lyon"),
        ("  double   espace  ", "double-espace"),
        ("Déjà-Tiret", "deja-tiret"),
        ("C'est / ça", "c-est-ca"),
        ("", "site"),
        ("---", "site"),
        ("!!!", "site"),
    ],
)
def test_slugify_deterministe(text, expected):
    assert slugify(text) == expected
    # idempotence : slugifier un slug déjà propre ne le change pas
    assert slugify(slugify(text)) == slugify(text)


@pytest.mark.parametrize(
    "slug,valid",
    [
        ("mon-portail", True),
        ("a", True),
        ("a1-b2", True),
        ("Mon-Portail", False),   # majuscules
        ("-lead", False),
        ("trail-", False),
        ("double--tiret", False),
        ("avec espace", False),
        ("", False),
        ("a" * 101, False),       # trop long
    ],
)
def test_is_valid_slug(slug, valid):
    assert is_valid_slug(slug) is valid


def test_exceptions_sont_des_value_errors():
    assert issubclass(InvalidSlugError, ValueError)
    assert issubclass(SlugCollisionError, ValueError)
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/items/test_slug.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.items.slug'`).

- [ ] **Step 3: Implémenter `slug.py`**

`core/app/items/slug.py` :
```python
# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_LEN = 100
_FALLBACK = "site"


class InvalidSlugError(ValueError):
    """Slug dont le format est invalide."""


class SlugCollisionError(ValueError):
    """Slug déjà utilisé par un autre item du même tenant."""


def slugify(text: str) -> str:
    """Slug déterministe : ASCII, minuscules, tirets simples, borné. Repli
    sur `site` si le résultat est vide."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    result = dashed[:_MAX_LEN].strip("-")
    return result or _FALLBACK


def is_valid_slug(slug: str) -> bool:
    return len(slug) <= _MAX_LEN and bool(_SLUG_RE.match(slug))
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/items/test_slug.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/items/slug.py core/tests/items/test_slug.py
git commit -m "feat(core): helpers de slug purs (slugify, is_valid_slug, exceptions) — SP-13a"
```

---

## Task 2 : colonne `items.slug` + migration + helpers repo + création de site (cœur)

**Files:**
- Create: `core/alembic/versions/0015_items_slug.py`
- Modify: `core/app/items/models.py`, `core/app/items/repository.py`
- Test: `core/tests/items/test_slug_repository.py` (create)

**Interfaces:**
- Consumes: `slugify`, `is_valid_slug`, `InvalidSlugError`, `SlugCollisionError` (Task 1).
- Produces:
  - `Item.slug: Mapped[str | None]`
  - `slug_exists(session, *, tenant_id: str, slug: str, exclude_item_id: str | None = None) -> bool`
  - `ensure_unique_slug(session, *, tenant_id: str, base: str) -> str`
  - `create_item(..., slug: str | None = None)` — comportement `site` : slug fourni → validé (format `InvalidSlugError`, collision `SlugCollisionError`) ; slug absent → `ensure_unique_slug(slugify(title))`. Non-`site` → `slug` reste `None`.

- [ ] **Step 1: Confirmer la tête Alembic**

Run: `cd core && uv run alembic heads`
Expected: une seule tête `0014_users_is_analyst`. La nouvelle migration en dépend (`down_revision = "0014"`).

- [ ] **Step 2: Écrire la migration**

`core/alembic/versions/0015_items_slug.py` :
```python
# SPDX-License-Identifier: Apache-2.0
"""items.slug + unicité partielle par tenant

Revision ID: 0015_items_slug
Revises: 0014_users_is_analyst
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_items_slug"
down_revision = "0014_users_is_analyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("slug", sa.String(), nullable=True), schema="app")
    op.create_index(
        "uq_items_tenant_slug",
        "items",
        ["tenant_id", "slug"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_items_tenant_slug", table_name="items", schema="app")
    op.drop_column("items", "slug", schema="app")
```

> Note : la table `items` est dans le schéma `app` (cf. migrations existantes) ; vérifier le `schema=` réel dans `0002`/`0013` et l'aligner. Si les autres migrations n'utilisent pas `schema=`, retirer l'argument partout ici.

- [ ] **Step 3: Ajouter la colonne ORM**

Dans `core/app/items/models.py`, après `keywords` (ligne ~25) :
```python
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Écrire le test de création (postgis)**

`core/tests/items/test_slug_repository.py` :
```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.items import repository as repo
from app.items.slug import SlugCollisionError, InvalidSlugError


@pytest.mark.postgis
def test_create_site_genere_slug_depuis_titre(pg_session, seed_tenant_user):
    tenant_id, owner_id = seed_tenant_user
    item = repo.create_item(
        pg_session, tenant_id=tenant_id, owner_id=owner_id,
        resource_type="site", title="Mon Portail",
    )
    assert item.slug == "mon-portail"


@pytest.mark.postgis
def test_create_site_collision_implicite_suffixe(pg_session, seed_tenant_user):
    tenant_id, owner_id = seed_tenant_user
    a = repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                         resource_type="site", title="Portail")
    b = repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                         resource_type="site", title="Portail")
    assert a.slug == "portail"
    assert b.slug == "portail-2"


@pytest.mark.postgis
def test_create_site_slug_fourni_collision_leve(pg_session, seed_tenant_user):
    tenant_id, owner_id = seed_tenant_user
    repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                     resource_type="site", title="X", slug="pris")
    with pytest.raises(SlugCollisionError):
        repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                         resource_type="site", title="Y", slug="pris")


@pytest.mark.postgis
def test_create_site_slug_fourni_invalide_leve(pg_session, seed_tenant_user):
    tenant_id, owner_id = seed_tenant_user
    with pytest.raises(InvalidSlugError):
        repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                         resource_type="site", title="Y", slug="Pas Valide")


@pytest.mark.postgis
def test_create_non_site_slug_reste_null(pg_session, seed_tenant_user):
    tenant_id, owner_id = seed_tenant_user
    item = repo.create_item(pg_session, tenant_id=tenant_id, owner_id=owner_id,
                            resource_type="app", title="Appli")
    assert item.slug is None
```

> Note : réutiliser les fixtures `pg_session`/`seed_tenant_user` déjà présentes dans `core/tests/conftest.py` ou les tests `items` existants. Si elles portent d'autres noms, aligner (chercher un test postgis existant du module `items` comme modèle exact).

- [ ] **Step 5: Lancer, vérifier l'échec**

Run: `cd core && CORE_TEST_DATABASE_URL=... uv run pytest tests/items/test_slug_repository.py -v`
Expected: FAIL (`create_item()` ne connaît pas `slug`).

- [ ] **Step 6: Implémenter les helpers repo + la création**

Dans `core/app/items/repository.py`, ajouter l'import en tête de fichier puis les helpers :
```python
from app.items.slug import InvalidSlugError, SlugCollisionError, is_valid_slug, slugify


def slug_exists(session, *, tenant_id: str, slug: str, exclude_item_id: str | None = None) -> bool:
    stmt = select(Item.id).where(Item.tenant_id == tenant_id, Item.slug == slug)
    if exclude_item_id is not None:
        stmt = stmt.where(Item.id != exclude_item_id)
    return session.execute(stmt).first() is not None


def ensure_unique_slug(session, *, tenant_id: str, base: str) -> str:
    if not slug_exists(session, tenant_id=tenant_id, slug=base):
        return base
    n = 2
    while slug_exists(session, tenant_id=tenant_id, slug=f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def _resolve_site_slug(session, *, tenant_id: str, title: str, slug: str | None) -> str:
    if slug is None:
        return ensure_unique_slug(session, tenant_id=tenant_id, base=slugify(title))
    if not is_valid_slug(slug):
        raise InvalidSlugError(f"slug invalide: {slug!r}")
    if slug_exists(session, tenant_id=tenant_id, slug=slug):
        raise SlugCollisionError(f"slug déjà utilisé: {slug!r}")
    return slug
```

Modifier `create_item` (signature + corps) :
```python
def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str,
    slug: str | None = None,
) -> Item:
    resolved_slug = None
    if resource_type == "site":
        resolved_slug = _resolve_site_slug(session, tenant_id=tenant_id, title=title, slug=slug)
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title, slug=resolved_slug,
    )
    session.add(item)
    session.flush()
    session.refresh(item)
    _enqueue_embedding(item.id, tenant_id)
    _items_created_counter.add(1)
    return item
```

- [ ] **Step 7: Lancer, vérifier le succès**

Run: `cd core && CORE_TEST_DATABASE_URL=... uv run pytest tests/items/test_slug_repository.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Vérifier la migration s'applique réellement**

Run: `cd core && CORE_TEST_DATABASE_URL=... uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: aucune erreur (upgrade + downgrade + upgrade idempotents).

- [ ] **Step 9: Commit**

```bash
git add core/alembic/versions/0015_items_slug.py core/app/items/models.py core/app/items/repository.py core/tests/items/test_slug_repository.py
git commit -m "feat(core): items.slug + unicité partielle par tenant, génération à la création d'un site — SP-13a"
```

---

## Task 3 : création d'un `site` via `POST /configs` (schéma + route cœur)

**Files:**
- Modify: `core/app/configs/schemas.py`, `core/app/configs/routes.py`, `core/app/items/schemas.py`, `core/app/items/repository.py:_to_read`
- Test: `core/tests/configs/test_create_site.py` (create)

**Interfaces:**
- Consumes: `create_item(..., slug=...)` (Task 2).
- Produces:
  - `BuilderConfig.kind: Literal["app", "dashboard", "map", "site"]`
  - `CreateConfigRequest.slug: str | None = None`
  - `ItemRead.slug: str | None = None` (sérialisé dans `_to_read`)
  - `POST /configs` : un site collisionné explicitement → 409.

- [ ] **Step 1: Écrire le test qui échoue**

`core/tests/configs/test_create_site.py` :
```python
# SPDX-License-Identifier: Apache-2.0
import pytest


def _site_body(title: str, slug: str | None = None):
    body = {
        "title": title,
        "config": {
            "version": 1,
            "kind": "site",
            "theme": {},
            "dataSources": [],
            "layout": {"type": "grid", "breakpoints": {}, "items": []},
            "messages": [],
            "pages": [],
        },
    }
    if slug is not None:
        body["slug"] = slug
    return body


def test_create_site_genere_slug(client_admin):
    res = client_admin.post("/configs", json=_site_body("Mon Portail"))
    assert res.status_code == 201
    item_id = res.json()["itemId"]
    item = client_admin.get(f"/items/{item_id}").json()
    assert item["resourceType"] == "site"
    assert item["slug"] == "mon-portail"


def test_create_site_slug_explicite_collision_409(client_admin):
    assert client_admin.post("/configs", json=_site_body("A", slug="pris")).status_code == 201
    res = client_admin.post("/configs", json=_site_body("B", slug="pris"))
    assert res.status_code == 409
```

> Note : `client_admin` = fixture TestClient authentifiée admin déjà utilisée par les tests `configs` existants (vérifier son nom réel dans `core/tests/configs/`). Ces tests tournent sans DB Postgres si les tests `configs` existants le font (SQLite via `create_all`) ; sinon les marquer `@pytest.mark.postgis` comme leurs voisins.

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/configs/test_create_site.py -v`
Expected: FAIL (`kind` "site" rejeté par le `Literal`, 422).

- [ ] **Step 3: Élargir `BuilderConfig.kind` + le check layout**

Dans `core/app/configs/schemas.py` (BuilderConfig) :
```python
    kind: Literal["app", "dashboard", "map", "site"]
```
et le validateur :
```python
    @model_validator(mode="after")
    def _require_kind_payload(self) -> "BuilderConfig":
        if self.kind in ("app", "dashboard", "site") and self.layout is None:
            raise ValueError(f"{self.kind} config requires a layout")
        if self.kind == "map" and self.map is None:
            raise ValueError("map config requires a map")
        return self
```

- [ ] **Step 4: Ajouter `slug` à `CreateConfigRequest` + le passer à `create_item`**

Dans `core/app/configs/routes.py`, la classe :
```python
class CreateConfigRequest(BaseModel):
    title: str
    config: BuilderConfig
    slug: str | None = None
```
et dans `create_config`, envelopper la création pour traduire les erreurs de slug :
```python
    from app.items.slug import InvalidSlugError, SlugCollisionError
    try:
        item = items_repo.create_item(
            session, tenant_id=user.tenant_id, owner_id=user.id,
            resource_type=request.config.kind, title=request.title,
            slug=request.slug,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
```

- [ ] **Step 5: Exposer `slug` dans `ItemRead`**

Dans `core/app/items/schemas.py` (ItemRead), ajouter après `resourceType` :
```python
    slug: str | None = None
```
Dans `core/app/items/repository.py` `_to_read`, ajouter le champ :
```python
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        slug=item.slug,
        title=item.title,
        ...
    )
```

- [ ] **Step 6: Lancer, vérifier le succès**

Run: `cd core && uv run pytest tests/configs/test_create_site.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Non-régression du module configs/items**

Run: `cd core && uv run pytest tests/configs tests/items -q`
Expected: PASS (aucune régression sur les créations app/dashboard/map existantes).

- [ ] **Step 8: Commit**

```bash
git add core/app/configs/schemas.py core/app/configs/routes.py core/app/items/schemas.py core/app/items/repository.py core/tests/configs/test_create_site.py
git commit -m "feat(core): créer un item type site via POST /configs (kind=site, slug), ItemRead.slug — SP-13a"
```

---

## Task 4 : édition du slug via `PATCH /items/{id}` (cœur)

**Files:**
- Modify: `core/app/items/schemas.py`, `core/app/items/repository.py:update_item`, `core/app/items/routes.py:update_item`
- Test: `core/tests/items/test_patch_slug.py` (create)

**Interfaces:**
- Consumes: `is_valid_slug`, `slug_exists`, `InvalidSlugError`, `SlugCollisionError` (Tasks 1-2).
- Produces:
  - `ItemUpdatePatch.slug: str | None = None`
  - `update_item(..., slug: str | None = None)` — si `slug` fourni : format invalide → `InvalidSlugError`, collision (hors self) → `SlugCollisionError`, sinon set.
  - `PATCH /items/{id}` : slug invalide → 422, collision → 409.

- [ ] **Step 1: Écrire le test qui échoue**

`core/tests/items/test_patch_slug.py` :
```python
# SPDX-License-Identifier: Apache-2.0
def _create_site(client_admin, title, slug=None):
    body = {"title": title, "config": {"version": 1, "kind": "site", "theme": {},
            "dataSources": [], "layout": {"type": "grid", "breakpoints": {}, "items": []},
            "messages": [], "pages": []}}
    if slug:
        body["slug"] = slug
    return client_admin.post("/configs", json=body).json()["itemId"]


def test_patch_slug_valide(client_admin):
    item_id = _create_site(client_admin, "Portail")
    res = client_admin.patch(f"/items/{item_id}", json={"slug": "nouveau-slug"})
    assert res.status_code == 200
    assert res.json()["slug"] == "nouveau-slug"


def test_patch_slug_invalide_422(client_admin):
    item_id = _create_site(client_admin, "Portail")
    res = client_admin.patch(f"/items/{item_id}", json={"slug": "Pas Valide"})
    assert res.status_code == 422


def test_patch_slug_collision_409(client_admin):
    _create_site(client_admin, "A", slug="pris")
    item_id = _create_site(client_admin, "B")
    res = client_admin.patch(f"/items/{item_id}", json={"slug": "pris"})
    assert res.status_code == 409


def test_patch_meme_slug_sur_soi_ok(client_admin):
    item_id = _create_site(client_admin, "A", slug="stable")
    res = client_admin.patch(f"/items/{item_id}", json={"slug": "stable"})
    assert res.status_code == 200
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/items/test_patch_slug.py -v`
Expected: FAIL (le patch ignore `slug`, `test_patch_slug_valide` renvoie l'ancien slug).

- [ ] **Step 3: Ajouter `slug` au schéma de patch**

Dans `core/app/items/schemas.py` (ItemUpdatePatch) :
```python
    slug: str | None = None
```

- [ ] **Step 4: Gérer `slug` dans `update_item` (repo)**

Dans `core/app/items/repository.py` `update_item`, ajouter le paramètre et la logique (après le bloc `keywords`) :
```python
def update_item(
    session: Session, *, tenant_id: str, item_id: str,
    title: str | None, abstract: str | None, keywords: list[str] | None,
    is_published: bool | None, slug: str | None = None,
) -> ItemRead | None:
    ...
    if slug is not None:
        if not is_valid_slug(slug):
            raise InvalidSlugError(f"slug invalide: {slug!r}")
        if slug_exists(session, tenant_id=tenant_id, slug=slug, exclude_item_id=item_id):
            raise SlugCollisionError(f"slug déjà utilisé: {slug!r}")
        item.slug = slug
    ...
```

- [ ] **Step 5: Traduire les erreurs en 422/409 dans la route**

Dans `core/app/items/routes.py` `update_item`, envelopper l'appel repo :
```python
    from app.items.slug import InvalidSlugError, SlugCollisionError
    try:
        result = repo.update_item(
            session, tenant_id=user.tenant_id, item_id=item_id,
            title=patch.title, abstract=patch.abstract, keywords=patch.keywords,
            is_published=patch.isPublished, slug=patch.slug,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
```

- [ ] **Step 6: Lancer, vérifier le succès**

Run: `cd core && uv run pytest tests/items/test_patch_slug.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/items/schemas.py core/app/items/repository.py core/app/items/routes.py core/tests/items/test_patch_slug.py
git commit -m "feat(core): éditer le slug via PATCH /items (422 format, 409 collision) — SP-13a"
```

---

## Task 5 : route publique `GET /public/sites/{slug}` (cœur)

**Files:**
- Modify: `core/app/public/routes.py`, `core/app/items/repository.py`
- Test: `core/tests/public/test_public_sites.py` (create)

**Interfaces:**
- Consumes: `_to_read`, `get_published_item` comme modèle (Task 3).
- Produces:
  - `get_published_site_by_slug(session, *, slug: str, tenant_id: str = "default") -> ItemRead | None`
  - `GET /public/sites/{slug}` → 200 / 404.

- [ ] **Step 1: Écrire le test qui échoue**

`core/tests/public/test_public_sites.py` :
```python
# SPDX-License-Identifier: Apache-2.0
import pytest

# Helpers de publication : réutiliser exactement le patron des tests
# tests/public/test_public_items.py existants (création + set is_published).


def test_site_publie_200(client_admin, client_anon):
    item_id = _create_and_publish_site(client_admin, "Portail", slug="mon-portail")
    res = client_anon.get("/public/sites/mon-portail")
    assert res.status_code == 200
    assert res.json()["pk"] == item_id
    assert res.json()["slug"] == "mon-portail"


def test_site_non_publie_404_jamais_403(client_admin, client_anon):
    _create_site_unpublished(client_admin, "Brouillon", slug="brouillon")
    res = client_anon.get("/public/sites/brouillon")
    assert res.status_code == 404


def test_slug_inexistant_404(client_anon):
    assert client_anon.get("/public/sites/nexiste-pas").status_code == 404


def test_non_site_meme_publie_404(client_admin, client_anon):
    # un item app publié n'est pas exposé par /public/sites/{slug}
    _create_and_publish_app(client_admin, "Appli")
    assert client_anon.get("/public/sites/appli").status_code == 404


@pytest.mark.postgis
def test_isolation_tenant_meme_slug(pg_session, ...):
    # deux tenants, même slug 'shared' ; la route (tenant=default) ne sert que
    # le site du tenant 'default', l'homonyme de l'autre tenant reste 404.
    ...
```

> Note : compléter les helpers `_create_and_publish_site`, `_create_site_unpublished`, `_create_and_publish_app`, `client_anon` (TestClient sans header) d'après les tests `tests/public/` existants — ne pas inventer de nouveau mécanisme de publication. Le test d'isolation tenant `postgis` insère deux items sur deux tenants directement via `repo.create_item` + publication, puis interroge la route ; s'inspirer d'un test d'isolation tenant existant (SP-3/SP-7) pour la fixture multi-tenant.

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/public/test_public_sites.py -v`
Expected: FAIL (404 sur tout — route absente).

- [ ] **Step 3: Ajouter le resolver repo**

Dans `core/app/items/repository.py`, à côté de `get_published_item` :
```python
def get_published_site_by_slug(
    session: Session, *, slug: str, tenant_id: str = "default"
) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(
            Item.resource_type == "site",
            Item.slug == slug,
            Item.tenant_id == tenant_id,
            Item.is_published.is_(True),
        )
    ).first()
    if row is None:
        return None
    item, owner_username = row
    return _to_read(item, owner_username)
```

- [ ] **Step 4: Ajouter la route publique**

Dans `core/app/public/routes.py`, après `get_public_item` :
```python
@router.get("/sites/{slug}", response_model=ItemRead)
def get_public_site(slug: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_site_by_slug(session, slug=slug)
    if result is None:
        raise HTTPException(status_code=404, detail="site not found")
    return result
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `cd core && uv run pytest tests/public/test_public_sites.py -v`
Expected: PASS (le test `postgis` skippé sans DB, exécuté avec `CORE_TEST_DATABASE_URL`).

- [ ] **Step 6: Suite cœur complète**

Run: `cd core && uv run pytest -q`
Expected: PASS (aucune régression) ; avec `CORE_TEST_DATABASE_URL` les tests `postgis` de slug/isolation passent aussi.

- [ ] **Step 7: Commit**

```bash
git add core/app/public/routes.py core/app/items/repository.py core/tests/public/test_public_sites.py
git commit -m "feat(core): GET /public/sites/{slug} (404 jamais 403, tenant default, isolation) — SP-13a"
```

---

## Task 6 : types + méthodes `itemClient` (shell)

**Files:**
- Modify: `shell/src/api/types.ts`, `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (ajout ; créer si absent)

**Interfaces:**
- Consumes: routes cœur `GET /public/sites/{slug}`, `GET /public/configs/by-item/{id}`, `POST /configs` (slug), `PATCH /items/{id}` (slug).
- Produces:
  - `ResourceType = "app" | "dashboard" | "map" | "site"`
  - `CreateKind = "app" | "dashboard" | "site"`
  - `Item.slug?: string`
  - `UpdatePatch` gagne `slug?: string`
  - `getItemBySlug(slug: string): Promise<Item>`
  - `getPublicAppConfig(pk: string): Promise<AppConfig>`
  - `createConfigItem` input gagne `slug?: string`

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts` (ajouter, en mockant `fetch`) :
```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createItemClient } from "./itemClient";

function client() {
  return createItemClient({ coreUrl: "http://core", getToken: () => undefined });
}

describe("itemClient sites", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("getItemBySlug appelle /public/sites/{slug} et renvoie l'item", async () => {
    const item = { pk: "s1", resourceType: "site", slug: "mon-portail", title: "P",
      abstract: "", owner: "a", thumbnailUrl: null, date: "", configId: null, isPublished: true };
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(item), { status: 200 }));
    const res = await client().getItemBySlug("mon-portail");
    expect(spy).toHaveBeenCalledWith("http://core/public/sites/mon-portail", expect.anything());
    expect(res.slug).toBe("mon-portail");
  });

  it("getItemBySlug propage l'échec 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));
    await expect(client().getItemBySlug("x")).rejects.toThrow();
  });

  it("getPublicAppConfig appelle /public/configs/by-item/{pk}", async () => {
    const cfg = { version: 1, kind: "site", theme: {}, dataSources: [],
      layout: { type: "grid", breakpoints: {}, items: [] }, messages: [], pages: [] };
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(cfg), { status: 200 }));
    const res = await client().getPublicAppConfig("s1");
    expect(spy).toHaveBeenCalledWith("http://core/public/configs/by-item/s1", expect.anything());
    expect(res.layout).toBeDefined();
  });

  it("createConfigItem transmet le slug dans le corps POST", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "1", kind: "site", itemId: "s1" }), { status: 201 }));
    await client().createConfigItem({ kind: "site", title: "P", owner: "a", slug: "mon-portail" });
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.slug).toBe("mon-portail");
    expect(body.config.kind).toBe("site");
  });
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npm run test -- itemClient`
Expected: FAIL (`getItemBySlug`/`getPublicAppConfig` inexistants ; `createConfigItem` ignore `slug`).

- [ ] **Step 3: Élargir les types**

Dans `shell/src/api/types.ts` :
```ts
export type ResourceType = "app" | "dashboard" | "map" | "site";
export type CreateKind = "app" | "dashboard" | "site";
```
Dans l'interface `Item`, ajouter :
```ts
  slug?: string;
```
`UpdatePatch` :
```ts
export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[]; isPublished?: boolean; slug?: string };
```
Dans l'interface `ItemClient`, ajouter les signatures :
```ts
  getItemBySlug(slug: string): Promise<Item>;
  getPublicAppConfig(pk: string): Promise<AppConfig>;
```
et élargir `createConfigItem` :
```ts
  createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string; slug?: string }): Promise<Item>;
```

- [ ] **Step 4: Implémenter dans `itemClient.ts`**

Élargir la signature et le corps de `createConfigItem` (transmettre `slug`) :
```ts
    async createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string; slug?: string }): Promise<Item> {
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const firstPageLayout = template?.pages?.[0]?.layout;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: template?.dataSources ?? [],
        layout: firstPageLayout ?? template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: template?.messages ?? [],
        pages: template?.pages ?? [],
        navigationMode: template?.navigationMode ?? "tabs",
      };
      const payload: Record<string, unknown> = { title: input.title, config };
      if (input.slug) payload.slug = input.slug;
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, payload,
      );
      if (!data.itemId) throw new Error("createConfigItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: data.kind as ResourceType,
        slug: input.slug,
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: "",
        configId: null,
        isPublished: false,
      };
    },
```
Ajouter les deux méthodes publiques (à côté de `getItem`) :
```ts
    async getItemBySlug(slug: string): Promise<Item> {
      return request<Item>("GET", `/public/sites/${encodeURIComponent(slug)}`);
    },

    async getPublicAppConfig(pk: string): Promise<AppConfig> {
      const c = await request<{ layout?: unknown } & Record<string, unknown>>(
        "GET", `/public/configs/by-item/${encodeURIComponent(pk)}`);
      if (!c?.layout) throw new Error("getPublicAppConfig: config has no layout");
      return c as unknown as AppConfig;
    },
```

> Note : aligner le retour de `getPublicAppConfig` sur la forme exacte que `getAppConfig` (ligne ~413) renvoie déjà — reprendre son mapping (mêmes champs extraits) pour garantir la parité runtime.

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `cd shell && npm run test -- itemClient`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): types site/slug + getItemBySlug/getPublicAppConfig, slug dans createConfigItem — SP-13a"
```

---

## Task 7 : slugify client + page publique `/sites/:slug` (shell)

**Files:**
- Create: `shell/src/lib/slug.ts`, `shell/src/lib/slug.test.ts`, `shell/src/pages/SitePublicPage.tsx`, `shell/src/pages/SitePublicPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`, `shell/src/api/hooks.ts`

**Interfaces:**
- Consumes: `getItemBySlug`, `getPublicAppConfig` (Task 6), `AppRenderer`.
- Produces:
  - `slugify(text: string): string`, `isValidSlug(slug: string): boolean` (miroir client).
  - `SitePublicPage({ slug })` : 200 → `AppRenderer` runtime ; 404 → page « Introuvable ».
  - Route `/sites/:slug` hors `ProtectedLayout`.

- [ ] **Step 1: Écrire les tests slugify + page (échec)**

`shell/src/lib/slug.test.ts` :
```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from "vitest";
import { slugify, isValidSlug } from "./slug";

describe("slugify (client)", () => {
  it.each([
    ["Mon Portail", "mon-portail"],
    ["Été à Lyon !", "ete-a-lyon"],
    ["  double   espace  ", "double-espace"],
    ["", "site"],
  ])("slugify(%s) = %s", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });
});

describe("isValidSlug", () => {
  it.each([
    ["mon-portail", true],
    ["Mon-Portail", false],
    ["-x", false],
    ["a--b", false],
    ["", false],
  ])("isValidSlug(%s) = %s", (slug, valid) => {
    expect(isValidSlug(slug)).toBe(valid);
  });
});
```

`shell/src/pages/SitePublicPage.test.tsx` : rendre le composant avec un `ItemClient` mocké via le provider/contexte utilisé par les autres tests de page (reprendre le harness de `AppRuntimePage.test.tsx` — `QueryClientProvider` + `ItemClientProvider` mock). Deux cas :
```tsx
// SPDX-License-Identifier: Apache-2.0
// cas 200 : getItemBySlug résout un site, getPublicAppConfig renvoie un layout
//           → un conteneur runtime est rendu (role/testid stable de AppRenderer).
// cas 404 : getItemBySlug rejette (404) → texte « introuvable » rendu, aucun
//           détail sur l'existence du slug.
```

> Note : calquer exactement le montage (providers, mock d'`ItemClient`) sur `AppRuntimePage.test.tsx` pour éviter le piège « WidgetHost sans QueryClientProvider » déjà documenté au projet.

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npm run test -- slug SitePublicPage`
Expected: FAIL (modules absents).

- [ ] **Step 3: Implémenter `slug.ts` (client)**

`shell/src/lib/slug.ts` :
```ts
// SPDX-License-Identifier: Apache-2.0
// Miroir client du slugify serveur (core/app/items/slug.py) — écho documenté,
// PAS une frontière : le serveur reste l'autorité (409/422). Voir SP-13a.
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_LEN = 100;

export function slugify(text: string): string {
  const ascii = text.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  const dashed = ascii.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const result = dashed.slice(0, MAX_LEN).replace(/^-+|-+$/g, "");
  return result || "site";
}

export function isValidSlug(slug: string): boolean {
  return slug.length <= MAX_LEN && SLUG_RE.test(slug);
}
```

- [ ] **Step 4: Implémenter `SitePublicPage.tsx`**

`shell/src/pages/SitePublicPage.tsx` :
```tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function SitePublicPage({ slug }: { slug: string }) {
  const client = useItemClient();
  const itemQuery = useQuery({
    queryKey: ["public-site", slug],
    queryFn: () => client.getItemBySlug(slug),
    retry: false,
  });
  const configQuery = useQuery({
    queryKey: ["public-site-config", itemQuery.data?.pk],
    queryFn: () => client.getPublicAppConfig(itemQuery.data!.pk),
    enabled: itemQuery.isSuccess,
    retry: false,
  });

  if (itemQuery.isLoading || (itemQuery.isSuccess && configQuery.isLoading)) {
    return <p role="status">Chargement…</p>;
  }
  if (itemQuery.isError || configQuery.isError || !configQuery.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-slate-600">Page introuvable.</p>
      </div>
    );
  }
  return (
    <div className="h-full w-full">
      <AppRenderer config={configQuery.data} mode="runtime" />
    </div>
  );
}
```

> Note : vérifier le nom réel du hook/provider d'`ItemClient` (`useItemClient`/`ItemClientProvider`) dans le shell et l'aligner. Ne PAS charger les extensions ici (décision 16a : sites v1 = widgets builtin b/c ; évite le délai fail-open ~5-7s de `useActiveExtensions`).

- [ ] **Step 5: Déclarer la route publique**

Dans `shell/src/shell/routes.tsx`, ajouter un composant + la route **hors** `ProtectedLayout`, à côté de `/apps/:pk/:pageId?` :
```tsx
function SitePublicRoute() {
  const { slug } = useParams();
  return <SitePublicPage slug={slug!} />;
}
```
et dans `<Routes>`, après la route runtime :
```tsx
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
```
(importer `SitePublicPage` en tête de fichier.)

- [ ] **Step 6: Lancer, vérifier le succès**

Run: `cd shell && npm run test -- slug SitePublicPage`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/lib/slug.ts shell/src/lib/slug.test.ts shell/src/pages/SitePublicPage.tsx shell/src/pages/SitePublicPage.test.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): slugify client + page publique /sites/:slug (AppRenderer runtime) — SP-13a"
```

---

## Task 8 : type « Site » dans `NewItemButton` (shell)

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx` (ajout ; créer si absent)

**Interfaces:**
- Consumes: `slugify`, `isValidSlug` (Task 7), `createConfigItem` (slug) (Task 6).
- Produces: option « Site » avec champ slug (auto depuis titre, éditable, validé), création → navigation builder.

- [ ] **Step 1: Écrire le test qui échoue**

`shell/src/shell/NewItemButton.test.tsx` (ajouter les cas ; reprendre le harness du test existant s'il y en a un) :
```tsx
// SPDX-License-Identifier: Apache-2.0
// cas 1 : ouvrir le dialogue, choisir type « Site », taper le titre « Mon Portail »
//         → le champ slug affiche « mon-portail » (auto-généré).
// cas 2 : éditer le slug en « Pas Valide » → le bouton Créer est désactivé
//         (isValidSlug faux).
// cas 3 : soumettre un slug valide → createConfigItem appelé avec
//         { kind: "site", slug: "mon-portail" }.
```

> Écrire ces cas avec `@testing-library/react` + `userEvent`, en mockant le hook de création (`useCreateItem`) comme le fait le test existant du bouton. Envelopper dans un composant à état si le test édite un champ contrôlé (piège `clear()+type()` déjà documenté au projet).

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npm run test -- NewItemButton`
Expected: FAIL (pas d'option Site, pas de champ slug).

- [ ] **Step 3: Implémenter l'option Site + le champ slug**

Dans `shell/src/shell/NewItemButton.tsx` :
- élargir l'état `kind` : `useState<"app" | "dashboard" | "map" | "site">("app")` ;
- ajouter un état slug + suivi auto :
```tsx
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  // slug auto-suivi du titre tant que l'utilisateur ne l'a pas édité
  useEffect(() => {
    if (kind === "site" && !slugTouched) setSlug(slugify(title));
  }, [title, kind, slugTouched]);
```
- ajouter `<option value="site">Site</option>` au `<select>` de type ;
- rendre le champ slug quand `kind === "site"` :
```tsx
  {kind === "site" && (
    <label className="flex flex-col gap-1 text-sm">
      Slug
      <Input
        aria-label="Slug"
        value={slug}
        onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); }}
      />
      {slug && !isValidSlug(slug) && (
        <span className="text-xs text-red-600">Slug invalide (minuscules, chiffres, tirets).</span>
      )}
    </label>
  )}
```
- dans `submit`, brancher la création `site` (kind !== "map"), en passant `slug`, et désactiver le bouton si slug invalide :
```tsx
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : await create.mutateAsync({
              kind, title: clean, owner: username ?? "",
              templateId: templateId || undefined,
              slug: kind === "site" ? slug : undefined,
            });
```
Bouton Créer : `disabled={kind === "site" && !isValidSlug(slug)}`.
- surface l'erreur serveur 409 (collision) : le `create.isError` existant affiche déjà un message ; s'assurer qu'il est visible pour le cas site.

> Note : `useCreateItem`/`useCreateMap` (hooks.ts) doivent accepter `slug?` dans leur input — l'ajouter à la signature du hook `useCreateItem` (mutationFn qui appelle `createConfigItem`). Aligner `hooks.ts:48`.

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `cd shell && npm run test -- NewItemButton`
Expected: PASS.

- [ ] **Step 5: tsc + build**

Run: `cd shell && npm run build`
Expected: PASS (aucune erreur de type — unions élargies cohérentes).

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx shell/src/api/hooks.ts
git commit -m "feat(shell): type Site dans NewItemButton (slug auto-généré, éditable, validé) — SP-13a"
```

---

## Task 9 : régénération des types OpenAPI (drift)

**Files:**
- Modify: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: toutes les modifs de schéma cœur (Tasks 3-5 : `ItemRead.slug`, `ItemUpdatePatch.slug`, `CreateConfigRequest.slug`, `BuilderConfig.kind`, route `/public/sites/{slug}`).

- [ ] **Step 1: Régénérer `openapi.json`**

Run: la commande de génération du dépôt (chercher le script exact ; en général `cd core && uv run python -m app.export_openapi > openapi.json` ou l'équivalent utilisé par le job CI `api-types-drift`). Reprendre la commande exacte du workflow `.github/workflows/ci.yml`.

- [ ] **Step 2: Régénérer les types shell**

Run: la commande `openapi-typescript` du dépôt (cf. `.github/workflows/ci.yml` job `api-types-drift`), qui écrit `shell/src/api/generated/core-schema.d.ts`.

- [ ] **Step 3: Vérifier l'absence de drift**

Run: reproduire localement le check du job `api-types-drift` (souvent `git diff --exit-code` après régénération). Après commit, il ne doit plus rien y avoir à régénérer.

- [ ] **Step 4: Vérifier build shell**

Run: `cd shell && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(api): régénère openapi.json + core-schema.d.ts (slug, kind=site, /public/sites) — SP-13a"
```

---

## Task 10 : spec E2E `sites-portal-shell.spec.ts`

**Files:**
- Create: `shell/e2e/sites-portal-shell.spec.ts`
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: tout le flux (Tasks 1-9).
- Produces: preuve bout-en-bout créer → publier → consulter anonyme + 404.

- [ ] **Step 1: Étendre les mocks E2E**

Dans `shell/e2e/mocks.ts` (`mockCore`), ajouter un état de site et les routes :
```ts
  // état du site créé
  let siteSlug: string | null = null;
  let sitePublished = false;
  const SITE_APP_CONFIG = { version: 1, kind: "site", theme: {}, dataSources: [],
    layout: { type: "grid", breakpoints: {}, items: [] }, messages: [], pages: [] };

  // POST /configs : capturer un site créé
  await page.route("**/configs", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      if (body?.config?.kind === "site") {
        siteSlug = body.slug ?? "mon-portail";
        await route.fulfill({ status: 201, json: { id: "cfg-site", kind: "site", itemId: "site-1" } });
        return;
      }
    }
    await route.fallback();
  });

  // PATCH publish du site
  await page.route("**/items/site-1", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON();
      if (body?.isPublished === true) sitePublished = true;
      await route.fulfill({ json: { pk: "site-1", resourceType: "site", slug: siteSlug,
        title: "Mon Portail", abstract: "", owner: "mockuser", thumbnailUrl: null,
        date: "", configId: null, isPublished: sitePublished } });
      return;
    }
    await route.fallback();
  });

  // route publique par slug
  await page.route("**/public/sites/**", async (route) => {
    const url = new URL(route.request().url());
    const wanted = decodeURIComponent(url.pathname.split("/").pop() ?? "");
    if (sitePublished && wanted === siteSlug) {
      await route.fulfill({ json: { pk: "site-1", resourceType: "site", slug: siteSlug,
        title: "Mon Portail", abstract: "", owner: "mockuser", thumbnailUrl: null,
        date: "", configId: null, isPublished: true } });
    } else {
      await route.fulfill({ status: 404, json: { detail: "site not found" } });
    }
  });

  // config publique du site
  await page.route("**/public/configs/by-item/site-1", async (route) => {
    await route.fulfill({ json: SITE_APP_CONFIG });
  });
```

> Note : placer ces `page.route` **avant** les routes génériques `**/items*` / `**/configs*` existantes (Playwright applique le dernier handler enregistré en premier — vérifier l'ordre réel de `mocks.ts` et, si besoin, rendre les handlers génériques tolérants via `route.fallback()`). Le piège glob `**/items/site-1` vs navigation SPA est déjà documenté au projet — utiliser des motifs précis.

- [ ] **Step 2: Écrire la spec E2E**

`shell/e2e/sites-portal-shell.spec.ts` :
```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, le publier, le consulter en anonyme, 404 si non publié", async ({ page }) => {
  await mockCore(page);

  // 1. Créer un Site depuis le catalogue
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Type").selectOption("site");
  await page.getByLabel(/titre|nom/i).fill("Mon Portail");
  await expect(page.getByLabel("Slug")).toHaveValue("mon-portail");
  await page.getByRole("button", { name: /créer|nouveau/i }).click();

  // 2. (depuis le builder) publier — via le mécanisme de partage/publication existant.
  //    Reprendre les sélecteurs exacts d'un spec de publication existant
  //    (share/publish) pour déclencher le PATCH isPublished:true sur /items/site-1.

  // 3. Consultation publique anonyme
  await page.goto("/sites/mon-portail");
  await expect(page.locator("[data-app-runtime], .h-full.w-full").first()).toBeVisible();
  await expect(page.getByText("introuvable")).toHaveCount(0);
});

test("un site non publié rend une page introuvable sans fuite", async ({ page }) => {
  await mockCore(page);
  await page.goto("/sites/inexistant");
  await expect(page.getByText(/introuvable/i)).toBeVisible();
});
```

> Note : l'étape 2 (publication) doit réutiliser le parcours de publication réel du shell — s'inspirer du spec E2E de partage/publication existant (`sharing`/`publish`) pour les sélecteurs exacts, ne pas inventer d'UI. Choisir un sélecteur runtime stable pour l'assertion de rendu (ajouter au besoin un `data-testid` sur le conteneur d'`AppRenderer` runtime si aucun n'existe).

- [ ] **Step 3: Lancer la nouvelle spec**

Run: `cd shell && npm run e2e -- sites-portal-shell`
Expected: PASS (2 tests).

- [ ] **Step 4: Lancer toute la suite E2E (non-régression)**

Run: `cd shell && npm run e2e`
Expected: PASS — 38 specs existantes + `sites-portal-shell` = **39 specs vertes**.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/sites-portal-shell.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): E2E sites — créer/publier/consulter un site par slug + 404 — SP-13a"
```

---

## Vérification finale de branche

- [ ] `cd core && uv run pytest -q` (avec `CORE_TEST_DATABASE_URL` pour les tests `postgis` de slug/isolation) — vert.
- [ ] `cd shell && npm run test` — vert.
- [ ] `cd shell && npm run build` — vert (tsc + vite).
- [ ] `cd shell && npm run e2e` — 39 specs vertes.
- [ ] `cd core && uv run lint-imports` (frontières de modules) — clean.
- [ ] Demander une revue finale de branche (modèle opus) avec l'exigence explicite de sécurité : **aucun chemin (notamment `GET /public/sites/{slug}`) ne contourne `can()`/la politique de publication ; l'isolation tenant×slug est testée** (cf. spec §8/§9).
- [ ] Mettre à jour la section « État » de `CLAUDE.md` (entrée SP-13a) en commit séparé après la revue.

---

## Self-Review (couverture spec → plan)

- Migration `items.slug` + unicité partielle par tenant → Task 2. ✅
- Génération de slug déterministe + collision → Tasks 1-2. ✅
- `GET /public/sites/{slug}` 200/404 (jamais 403) + isolation tenant → Task 5. ✅
- Garde d'unicité à l'édition (409) + format (422) → Task 4. ✅
- `resource_type == "site"` + création via `POST /configs` → Task 3. ✅
- Shell : `Item.slug`, `getItemBySlug`, `getPublicAppConfig`, route `/sites/:slug`, `SitePublicPage`, type Site dans `NewItemButton` → Tasks 6-8. ✅
- Tests Vitest (widgets hors périmètre 16a ; SitePublicPage 200/404, création slug, round-trip itemClient) → Tasks 6-8. ✅
- E2E `sites-portal-shell.spec.ts` (créer/publier/consulter + 404) → Task 10. ✅
- Dérive OpenAPI → Task 9. ✅
- Round-trip `slug` (classe de bug `visibleWhen`/`navigationMode`) → Task 6 (test dédié + passthrough `request<Item>`). ✅
