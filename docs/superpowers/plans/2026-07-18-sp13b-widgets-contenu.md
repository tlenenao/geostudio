# SP-13b — widgets de contenu (Hero/RichSection/Gallery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three content widgets (`Hero`, `RichSection`, `Gallery`) to the existing widget registry, plus the minimal core+shell plumbing (`GET /public/items`, `ItemRead.keywords`, `PublicItemPage`) needed for `Gallery` to list and link to published items for an anonymous visitor.

**Architecture:** Extension of the existing `items` core module (one new repository function + one new anonymous route, no new module, no migration — `Item.keywords` already exists on the model). Shell side: three new `registerWidget()` entries following the exact conventions already used by `chart.tsx`/`form.tsx`/`button` (in `index.tsx`), one new page (`PublicItemPage`, a simplification of the existing `SitePublicPage`), one new `ItemClient` method, and one new E2E spec extending the SP-13a fixture flow.

**Tech Stack:** FastAPI + SQLAlchemy (core), React + TypeScript + `@tanstack/react-query` (shell), `marked` + `dompurify` (new shell deps, Markdown→sanitized HTML), Vitest + Playwright (tests).

## Global Constraints

- **A31** (inherited): the portal config is a sub-template of `AppConfig`, rendered by the single `AppRenderer` runtime — no second engine.
- **A33** (inherited): no custom domain / host-based resolution. Public routes only ever serve the `default` tenant.
- **A38** (inherited): no community features (comments/follow/discussions) — out of scope.
- **Scope = Hero + RichSection + Gallery only.** `DatasetCard`/`DatasetPage`, multi-format download, and the "Portail de données" gallery template are SP-13c — do not build them here.
- **RichSection renders Markdown via `marked` + `DOMPurify`.** Sanitization is mandatory and non-bypassable — always go through the single `sanitizeMarkdown()` helper, never call `marked.parse` directly elsewhere.
- **Gallery thumbnails link to the existing anonymous route `GET /public/configs/by-item/{pk}`** (already implemented, used by SP-13a's `SitePublicPage`) — no new config route.
- **Gallery's filter is fixed by the widget's author** (`type`/`tag`/`limit` props) — no interactive filter controls for the visitor.
- **No migration needed**: `Item.keywords` (JSON column, default `[]`) already exists on the ORM model (`core/app/items/models.py:25`) and is already written by `update_item`/`PATCH /items/{id}`. The only gap is that `ItemRead` never serializes it.
- **`GET /public/items` must use a dedicated published-only repository function** (`list_published_items`), never the authenticated `list_items` path — this is the security boundary this plan must prove with a leakage matrix (unpublished item, other-tenant item, own-tenant published item).
- **Shell `Item.keywords` is optional** (`keywords?: string[]`), not required — several existing test files construct typed `Item` literals without it (`ItemActions.test.tsx`, `ShareDialog.test.tsx`, `AppRuntimePage.test.tsx`, `ItemCard.test.tsx`, `SitePublicPage.test.tsx`); making the field required would force unrelated edits to all of them. Consumers read it defensively (`item.keywords ?? []`).
- **Regenerate `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts`** after the core changes (Task 3) — the CI job `api-types-drift` fails otherwise (recurring pattern, see CLAUDE.md).
- All new shell test/UI copy is in **French** (project convention); identifiers/code stay in English.

---

## File Structure

**Core (new/modified):**
- Modify `core/app/items/schemas.py` — add `ItemRead.keywords`.
- Modify `core/app/items/repository.py` — add `keywords` to `_to_read()`, add `list_published_items()`.
- Modify `core/app/public/routes.py` — add `GET /public/items` (list) handler.
- New `core/tests/test_public_items_list.py` — route-level tests (anonymity, filters, pagination, leakage matrix).
- Modify `core/tests/test_items_repository.py` — repo-level tests for `keywords` round-trip and `list_published_items`.
- Modify `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` — regenerated, not hand-edited.

**Shell (new/modified):**
- Modify `shell/src/api/types.ts` — `Item.keywords?`, `ItemClient.listPublicItems`.
- Modify `shell/src/api/itemClient.ts` — implement `listPublicItems`.
- New `shell/src/pages/PublicItemPage.tsx` + `PublicItemPage.test.tsx`.
- Modify `shell/src/shell/routes.tsx` — new route `/public/items/:pk`.
- New `shell/src/builder/widgets/hero.tsx` + `hero.test.tsx`.
- New `shell/src/builder/widgets/sanitizeMarkdown.ts` + `sanitizeMarkdown.test.ts`.
- New `shell/src/builder/widgets/richSection.tsx` + `richSection.test.tsx`.
- New `shell/src/builder/widgets/gallery.tsx` + `gallery.test.tsx`.
- Modify `shell/src/builder/widgets/index.tsx` — register the three new widgets.
- Modify `shell/package.json` — add `marked`, `dompurify` dependencies.
- New `shell/e2e/sites-portal-content.spec.ts`.
- Modify `shell/e2e/mocks.ts` — public items list mock, second published item + config fixture, make the site's public config mock reflect what was actually saved.

---

### Task 1: Core — expose `Item.keywords` on `ItemRead`

**Files:**
- Modify: `core/app/items/schemas.py:7-17` (the `ItemRead` class)
- Modify: `core/app/items/repository.py:58-75` (the `_to_read` function)
- Test: `core/tests/test_items_repository.py` (add near line 213, after `test_list_items_search_and_type_filter`)

**Interfaces:**
- Consumes: nothing new (uses `Item.keywords`, already on the ORM model).
- Produces: `ItemRead.keywords: list[str]` (default `[]`), consumed by Task 2/3's list route and by the shell (Task 4).

- [ ] **Step 1: Write the failing tests**

In `core/tests/test_items_repository.py`, insert after the existing `test_list_items_search_and_type_filter` function (currently ending around line 213):

```python
def test_update_item_patches_keywords_and_get_item_returns_them(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")

    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title=None, abstract=None, keywords=["geo", "risques"], is_published=None,
    )

    result = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert result.keywords == ["geo", "risques"]


def test_get_item_defaults_keywords_to_empty_list(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")

    result = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert result.keywords == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_repository.py -k keywords -v`
Expected: FAIL — `AttributeError: 'ItemRead' object has no attribute 'keywords'` (or a Pydantic validation-adjacent error), since `ItemRead` doesn't declare the field yet.

- [ ] **Step 3: Add the field to `ItemRead`**

In `core/app/items/schemas.py`, the current class is:

```python
class ItemRead(BaseModel):
    pk: str
    resourceType: str
    slug: str | None = None
    title: str
    abstract: str
    owner: str
    thumbnailUrl: str | None
    date: str
    configId: str | None
    isPublished: bool
```

Add `keywords` at the end:

```python
class ItemRead(BaseModel):
    pk: str
    resourceType: str
    slug: str | None = None
    title: str
    abstract: str
    owner: str
    thumbnailUrl: str | None
    date: str
    configId: str | None
    isPublished: bool
    keywords: list[str] = []
```

- [ ] **Step 4: Populate it in `_to_read`**

In `core/app/items/repository.py`, the current function is:

```python
def _to_read(item: Item, owner_username: str) -> ItemRead:
    # configId is always None: app.items must never import app.configs (see
    # plan Architecture — items sits below configs in the layering), and the
    # shell's own Item.configId is already hardcoded to null everywhere today
    # (itemClient.ts's toItem()), so this isn't a behavior regression for any
    # current consumer. Real wiring, if ever needed, belongs in app.configs.
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        slug=item.slug,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
    )
```

Add `keywords=item.keywords or [],` before the closing parenthesis:

```python
def _to_read(item: Item, owner_username: str) -> ItemRead:
    # configId is always None: app.items must never import app.configs (see
    # plan Architecture — items sits below configs in the layering), and the
    # shell's own Item.configId is already hardcoded to null everywhere today
    # (itemClient.ts's toItem()), so this isn't a behavior regression for any
    # current consumer. Real wiring, if ever needed, belongs in app.configs.
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        slug=item.slug,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
        keywords=item.keywords or [],
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_repository.py -k keywords -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full core test suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: PASS, same count as before + 2 (no `postgis`-marked test touches `ItemRead`, so no skip-count change)

- [ ] **Step 7: Commit**

```bash
git add core/app/items/schemas.py core/app/items/repository.py core/tests/test_items_repository.py
git commit -m "feat(core): expose Item.keywords on ItemRead"
```

---

### Task 2: Core — `list_published_items` repository function

**Files:**
- Modify: `core/app/items/repository.py` (add imports + new function, after `list_items`, i.e. after line 224 in the pre-Task-1 file — insert immediately after the `list_items` function body and before `set_thumbnail_key`)
- Test: `core/tests/test_items_repository.py` (add after the Task 1 tests)

**Interfaces:**
- Consumes: `ItemPage`, `ItemRead`, `_to_read` (all already in this file); `DEFAULT_TENANT_SLUG` from `app.tenants.repository` (new import — allowed by the layers contract: `app.items` sits above `app.tenants` in `core/pyproject.toml`'s `[tool.importlinter]` layers list).
- Produces: `list_published_items(session, *, tenant_id="default", resource_type=None, tag=None, page=1, page_size=12) -> ItemPage`, consumed by Task 3's route.

- [ ] **Step 1: Write the failing tests**

In `core/tests/test_items_repository.py`, insert after the two tests added in Task 1:

```python
def test_list_published_items_returns_only_published(session, tenant_and_user):
    tenant, user = tenant_and_user
    published = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Publie")
    published.is_published = True
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Brouillon")
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, page=1, page_size=12)
    assert [i.title for i in page.items] == ["Publie"]


def test_list_published_items_filters_by_resource_type(session, tenant_and_user):
    tenant, user = tenant_and_user
    app_item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="App")
    app_item.is_published = True
    dash_item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="dashboard", title="Dashboard")
    dash_item.is_published = True
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, resource_type="dashboard", page=1, page_size=12)
    assert [i.title for i in page.items] == ["Dashboard"]


def test_list_published_items_filters_by_tag(session, tenant_and_user):
    tenant, user = tenant_and_user
    tagged = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Avec tag")
    tagged.is_published = True
    tagged.keywords = ["risques"]
    untagged = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Sans tag")
    untagged.is_published = True
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, tag="risques", page=1, page_size=12)
    assert [i.title for i in page.items] == ["Avec tag"]


def test_list_published_items_paginates(session, tenant_and_user):
    tenant, user = tenant_and_user
    for i in range(3):
        item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title=f"Item {i}")
        item.is_published = True
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, page=1, page_size=2)
    assert page.total == 3
    assert len(page.items) == 2
    assert page.page == 1
    assert page.pageSize == 2


def test_list_published_items_defaults_to_default_tenant(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Publie")
    item.is_published = True
    session.commit()

    page = repo.list_published_items(session, page=1, page_size=12)
    assert [i.title for i in page.items] == ["Publie"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_repository.py -k list_published_items -v`
Expected: FAIL — `AttributeError: module 'app.items.repository' has no attribute 'list_published_items'`

- [ ] **Step 3: Add the `DEFAULT_TENANT_SLUG` import**

In `core/app/items/repository.py`, the current import block (lines 1-18) ends with:

```python
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
from app.users.models import User
```

Add one import line:

```python
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
from app.tenants.repository import DEFAULT_TENANT_SLUG
from app.users.models import User
```

- [ ] **Step 4: Implement `list_published_items`**

In `core/app/items/repository.py`, insert this new function immediately after the `list_items` function (which currently ends with `return ItemPage(items=items, total=total, page=page, pageSize=page_size)` right before `def set_thumbnail_key`):

```python
def list_published_items(
    session: Session,
    *,
    tenant_id: str = DEFAULT_TENANT_SLUG,
    resource_type: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> ItemPage:
    # Published-only, tenant-scoped, anonymous-safe: deliberately NOT a
    # variant of list_items() (which is gated by current_user_id/scope) —
    # this is the sole entry point for GET /public/items, so it must never
    # accidentally regain access to unpublished or cross-tenant rows.
    query = (
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.tenant_id == tenant_id, Item.is_published.is_(True))
    )
    if resource_type:
        query = query.where(Item.resource_type == resource_type)

    rows = session.execute(query.order_by(Item.created_at.desc())).all()
    # Tag filter done in Python, not as a DB-side JSON-contains predicate:
    # portable across SQLite (tests) and Postgres (prod) without a
    # dialect-specific operator. Small scale (published items of one
    # tenant), so recomputing `total` post-filter is cheap.
    if tag:
        rows = [row for row in rows if tag in (row[0].keywords or [])]

    total = len(rows)
    page_rows = rows[(page - 1) * page_size : (page - 1) * page_size + page_size]
    items = [_to_read(item, owner_username) for item, owner_username in page_rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_repository.py -k list_published_items -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run `import-linter` to confirm the new import doesn't violate the layers contract**

Run: `cd core && uv run lint-imports`
Expected: no violations reported (the layers contract lists `app.items` above `app.tenants`, so `app.items -> app.tenants` is an allowed downward import)

- [ ] **Step 7: Run the full core test suite**

Run: `cd core && uv run pytest -q`
Expected: PASS, +5 tests vs. Task 1's count

- [ ] **Step 8: Commit**

```bash
git add core/app/items/repository.py core/tests/test_items_repository.py
git commit -m "feat(core): add list_published_items — published-only, tenant-scoped item listing"
```

---

### Task 3: Core — `GET /public/items` route

**Files:**
- Modify: `core/app/public/routes.py`
- Test: New `core/tests/test_public_items_list.py`

**Interfaces:**
- Consumes: `items_repo.list_published_items` (Task 2).
- Produces: `GET /public/items?type=&tag=&page=&pageSize=` → `ItemPage`, consumed by the shell's `listPublicItems` (Task 4).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_public_items_list.py`:

```python
# SPDX-License-Identifier: Apache-2.0
# Fixture pattern copied from test_public_sites.py / test_public_routes.py —
# entirely SQLite, including the tenant-isolation leakage test (it only needs
# a second Tenant/User row, no Postgres-specific feature).
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.auth.dependency import get_current_user
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from app.items import repository as repo


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_item(client, title: str, kind: str = "app") -> str:
    response = client.post(
        "/configs",
        json={"title": title, "config": {"kind": kind, "layout": {"type": "grid", "items": []}}},
    )
    assert response.status_code == 201, response.text
    return response.json()["itemId"]


def _publish(client, item_id: str) -> None:
    response = client.patch(f"/items/{item_id}", json={"isPublished": True})
    assert response.status_code == 200, response.text


def test_anonymous_can_list_published_items(client):
    item_id = _create_item(client, "Publie")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Publie"]


def test_unpublished_item_is_absent(client):
    _create_item(client, "Brouillon")

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_filters_by_type(client):
    app_id = _create_item(client, "Une app", kind="app")
    _publish(client, app_id)
    dash_id = _create_item(client, "Un dashboard", kind="dashboard")
    _publish(client, dash_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?type=dashboard")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Un dashboard"]


def test_filters_by_tag(client):
    tagged_id = _create_item(client, "Avec tag")
    client.patch(f"/items/{tagged_id}", json={"keywords": ["risques"]})
    _publish(client, tagged_id)
    untagged_id = _create_item(client, "Sans tag")
    _publish(client, untagged_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?tag=risques")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Avec tag"]


def test_paginates(client):
    for i in range(3):
        item_id = _create_item(client, f"Item {i}")
        _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?page=1&pageSize=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["pageSize"] == 2


def test_leakage_matrix_unpublished_other_tenant_and_default_published(client):
    # (1) Item non publié → absent.
    _create_item(client, "Non publie")

    # (2) Item publie d'un autre tenant → absent (aucun header/parametre de
    # tenant n'existe cote route publique ; seul le tenant "default" est
    # jamais servi).
    with client.session_factory() as session:
        other_tenant = Tenant(id="other", slug="other", name="Other")
        session.add(other_tenant)
        session.flush()
        bob = get_or_create_user(
            session, tenant_id="other", oidc_sub="sub-other",
            username="bob", email=None, first_name="", last_name="",
        )
        other_item = repo.create_item(
            session, tenant_id="other", owner_id=bob.id,
            resource_type="app", title="Autre tenant",
        )
        other_item.is_published = True
        session.commit()

    # (3) Item publie du tenant default → present.
    published_id = _create_item(client, "Publie default")
    _publish(client, published_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Publie default"]


def test_never_exposes_a_sensitive_field(client):
    item_id = _create_item(client, "Publie")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    body = response.json()["items"][0]
    assert set(body.keys()) == {
        "pk", "resourceType", "slug", "title", "abstract", "owner",
        "thumbnailUrl", "date", "configId", "isPublished", "keywords",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_public_items_list.py -v`
Expected: FAIL — `404 Not Found` on `GET /public/items` (route doesn't exist yet)

- [ ] **Step 3: Add the route**

In `core/app/public/routes.py`, the current file is:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.schemas import ItemRead

router = APIRouter(prefix="/public")


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result
```

Add the import for `ItemPage` and a new `list_public_items` handler, placed **before** `get_public_item` (list-before-detail, matching the convention in `app/items/routes.py`):

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead

router = APIRouter(prefix="/public")


@router.get("/items", response_model=ItemPage)
def list_public_items(
    type: str | None = None,
    tag: str | None = None,
    page: int = 1,
    pageSize: int = 12,
    session: Session = Depends(get_session),
) -> ItemPage:
    return items_repo.list_published_items(
        session, resource_type=type, tag=tag, page=page, page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result
```

(The rest of the file — `get_public_site`, `get_public_config_by_item` — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_public_items_list.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full core test suite**

Run: `cd core && uv run pytest -q`
Expected: PASS, +8 tests vs. Task 2's count

- [ ] **Step 6: Regenerate OpenAPI + shell generated types**

Run:
```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` gains the `GET /public/items` path and `ItemRead.keywords`/`ItemPage` reflect the new field; `shell/src/api/generated/core-schema.d.ts` is regenerated to match.

- [ ] **Step 7: Commit**

```bash
git add core/app/public/routes.py core/tests/test_public_items_list.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): add anonymous GET /public/items — published items of the default tenant"
```

---

### Task 4: Shell — `Item.keywords` type + `ItemClient.listPublicItems`

**Files:**
- Modify: `shell/src/api/types.ts:6-17` (`Item` type), `:102-154` (`ItemClient` interface)
- Modify: `shell/src/api/itemClient.ts` (implementation, near `getItemBySlug` at line 193)
- Test: New `shell/src/api/itemClient.test.ts` additions (check if this file exists; if not, add inline near existing `itemClient` tests — see Step 1 for the exact assertion, which only needs a `fetch` spy, no new test file required if one already covers `itemClient.ts`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Item.keywords?: string[]`; `ItemClient.listPublicItems(params?: { type?: ResourceType; tag?: string; page?: number; pageSize?: number }): Promise<ItemPage>`, consumed by `Gallery` (Task 8).

- [ ] **Step 1: Write the failing test**

Check whether `shell/src/api/itemClient.test.ts` exists:

Run: `ls shell/src/api/*.test.ts`

If it exists, add this test to it (adjust the `fetch` mocking to match that file's existing pattern for other `GET` methods, e.g. `listItems`). If it does not exist, create `shell/src/api/itemClient.test.ts` with:

```ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createCoreItemClient } from "./itemClient";

const originalFetch = global.fetch;

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  global.fetch = originalFetch;
});

test("listPublicItems calls GET /public/items with type/tag/page/pageSize", async () => {
  const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ items: [], total: 0, page: 1, pageSize: 6 }),
  });

  const client = createCoreItemClient({ coreUrl: "https://core.test", getToken: () => undefined });
  await client.listPublicItems({ type: "app", tag: "risques", page: 1, pageSize: 6 });

  const calledUrl = fetchMock.mock.calls[0][0] as string;
  expect(calledUrl).toContain("https://core.test/public/items?");
  expect(calledUrl).toContain("type=app");
  expect(calledUrl).toContain("tag=risques");
  expect(calledUrl).toContain("page=1");
  expect(calledUrl).toContain("pageSize=6");
});

test("listPublicItems round-trips keywords from the response", async () => {
  const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      items: [{
        pk: "8", resourceType: "app", title: "Carte des risques", abstract: "", owner: "alice",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: true, keywords: ["risques"],
      }],
      total: 1, page: 1, pageSize: 12,
    }),
  });

  const client = createCoreItemClient({ coreUrl: "https://core.test", getToken: () => undefined });
  const page = await client.listPublicItems();
  expect(page.items[0].keywords).toEqual(["risques"]);
});
```

**Note:** check the exact exported factory function name and its options shape by reading the bottom of `shell/src/api/itemClient.ts` (the file exports a function that builds the `ItemClient` object — confirm its exact name, e.g. `createCoreItemClient`, and constructor options, e.g. `{ coreUrl, getToken }`, before finalizing this test; adjust the two calls above to match exactly what's already used by any other existing test of this file, or by `shell/src/App.tsx`'s instantiation call).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `client.listPublicItems is not a function`

- [ ] **Step 3: Add `keywords` to the `Item` type and declare `listPublicItems`**

In `shell/src/api/types.ts`, the current `Item` type is:

```ts
export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
  isPublished: boolean;
  slug?: string;
};
```

Add `keywords?: string[];`:

```ts
export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
  isPublished: boolean;
  slug?: string;
  keywords?: string[];
};
```

In the same file, the `ItemClient` interface currently has (around line 105):

```ts
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getItemBySlug(slug: string): Promise<Item>;
```

Add `listPublicItems` right after `getItemBySlug`:

```ts
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getItemBySlug(slug: string): Promise<Item>;
  listPublicItems(params?: { type?: ResourceType; tag?: string; page?: number; pageSize?: number }): Promise<ItemPage>;
```

- [ ] **Step 4: Implement `listPublicItems` in `itemClient.ts`**

In `shell/src/api/itemClient.ts`, the current code around `getItemBySlug` is:

```ts
    async getItemBySlug(slug: string): Promise<Item> {
      return request<Item>("GET", `/public/sites/${encodeURIComponent(slug)}`);
    },

    async getMe(): Promise<Me> {
```

Add `listPublicItems` between them:

```ts
    async getItemBySlug(slug: string): Promise<Item> {
      return request<Item>("GET", `/public/sites/${encodeURIComponent(slug)}`);
    },

    async listPublicItems(params: { type?: ResourceType; tag?: string; page?: number; pageSize?: number } = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.type) q.set("type", params.type);
      if (params.tag) q.set("tag", params.tag);
      q.set("page", String(params.page ?? 1));
      q.set("pageSize", String(params.pageSize ?? 12));
      return request<ItemPage>("GET", `/public/items?${q.toString()}`);
    },

    async getMe(): Promise<Me> {
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 6: Run `tsc --noEmit` to confirm the optional `keywords` field doesn't break existing typed `Item` literals**

Run: `cd shell && npx tsc --noEmit`
Expected: no new errors (making `keywords` optional means `ItemActions.test.tsx`/`ShareDialog.test.tsx`/`AppRuntimePage.test.tsx`/`ItemCard.test.tsx`/`SitePublicPage.test.tsx` compile unchanged)

- [ ] **Step 7: Run the full shell test suite**

Run: `cd shell && npm run test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add ItemClient.listPublicItems and Item.keywords"
```

---

### Task 5: Shell — `PublicItemPage` + route `/public/items/:pk`

**Files:**
- Create: `shell/src/pages/PublicItemPage.tsx`
- Create: `shell/src/pages/PublicItemPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `client.getPublicAppConfig(pk)` (existing, unchanged).
- Produces: `<PublicItemPage pk={string} />`, mounted at `/public/items/:pk`; consumed by `Gallery`'s vignette links (Task 8) and the new E2E spec (Task 9).

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/PublicItemPage.test.tsx` (mirrors `SitePublicPage.test.tsx`, simplified to a single query since the pk is already known — no slug-to-pk resolution needed):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { PublicItemPage } from "./PublicItemPage";

function renderPage(client: Partial<ItemClient>, pk = "8") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/public/items/${pk}`]}>
          <PublicItemPage pk={pk} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 1, props: { text: "Detail de l'article" } },
  ] },
};

test("200: renders the published item's runtime layout via AppRenderer", async () => {
  renderPage({ getPublicAppConfig: vi.fn().mockResolvedValue(config) });
  expect(await screen.findByText("Detail de l'article")).toBeInTheDocument();
  expect(screen.queryByText(/introuvable/i)).not.toBeInTheDocument();
});

test("404: shows a not-found message without leaking whether the item exists", async () => {
  renderPage({ getPublicAppConfig: vi.fn().mockRejectedValue(new Error("404")) }, "does-not-exist");
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/does-not-exist/i);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/PublicItemPage.test.tsx`
Expected: FAIL — cannot find module `./PublicItemPage`

- [ ] **Step 3: Implement `PublicItemPage.tsx`**

Create `shell/src/pages/PublicItemPage.tsx` (simplification of `SitePublicPage.tsx` — one query, not two, since `pk` is already known):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function PublicItemPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const configQuery = useQuery({
    queryKey: ["public-item-config", pk],
    queryFn: () => client.getPublicAppConfig(pk),
    retry: false,
  });

  if (configQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (configQuery.isError || !configQuery.data) {
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/pages/PublicItemPage.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire the route**

In `shell/src/shell/routes.tsx`, add the import (after the `SitePublicPage` import at line 8):

```tsx
import { SitePublicPage } from "../pages/SitePublicPage";
import { PublicItemPage } from "../pages/PublicItemPage";
```

Add a route component (after `SitePublicRoute`, around line 55):

```tsx
function SitePublicRoute() {
  const { slug } = useParams();
  return <SitePublicPage slug={slug!} />;
}

function PublicItemRoute() {
  const { pk } = useParams();
  return <PublicItemPage pk={pk!} />;
}
```

And add the `<Route>`, as a sibling **outside** `ProtectedLayout` (same pattern as `/sites/:slug`):

```tsx
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<CatalogRoute />} />
        <Route path="/items/:pk" element={<ItemDetailRoute />} />
        <Route path="/maps/:pk" element={<MapEditorRoute />} />
        <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
      </Route>
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
      <Route path="/public/items/:pk" element={<PublicItemRoute />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Run the full shell test suite**

Run: `cd shell && npm run test`
Expected: PASS

- [ ] **Step 7: Run `tsc --noEmit`**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/PublicItemPage.tsx shell/src/pages/PublicItemPage.test.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): add PublicItemPage at /public/items/:pk"
```

---

### Task 6: Shell widget — `Hero`

**Files:**
- Create: `shell/src/builder/widgets/hero.tsx`
- Create: `shell/src/builder/widgets/hero.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`

**Interfaces:**
- Consumes: `registerWidget`, `WidgetContext` from `../registry` (existing).
- Produces: widget type `"hero"` registered in the global widget registry, available to the E2E spec (Task 9).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/hero.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("hero declares a cta event", () => {
  expect(getWidget("hero")!.events).toContain("cta");
});

test("hero renders title and subtitle", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue", subtitle: "Un sous-titre" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Bienvenue")).toBeInTheDocument();
  expect(screen.getByText("Un sous-titre")).toBeInTheDocument();
});

test("hero without ctaLabel renders no button", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("hero without backgroundImageUrl falls back to a theme color flat background", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  const container = screen.getByText("Bienvenue").parentElement!;
  expect(container).toHaveStyle({ backgroundColor: "var(--gs-color-primary)" });
});

test("hero with backgroundImageUrl renders it as a CSS background-image", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue", backgroundImageUrl: "https://example.com/bg.png" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  const container = screen.getByText("Bienvenue").parentElement!;
  expect(container.style.backgroundImage).toContain("https://example.com/bg.png");
});

test("hero cta click emits the wired action and opens ctaHref in a new tab", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "run", handler);
  bus.configure([{ id: "m", from: "hero1", event: "cta", to: "sink", action: "run" }]);
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", ctaLabel: "Voir", ctaHref: "https://example.com" }}
      ctx={{ mode: "runtime", bus, widgetId: "hero1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Voir" }));
  expect(handler).toHaveBeenCalled();
  expect(openSpy).toHaveBeenCalledWith("https://example.com", "_blank", "noopener");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/hero.test.tsx`
Expected: FAIL — `getWidget("hero")` returns `undefined` (widget type "hero" not registered)

- [ ] **Step 3: Implement `hero.tsx`**

Create `shell/src/builder/widgets/hero.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

export function registerHeroWidget(): void {
  registerWidget({
    type: "hero",
    label: "Hero",
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
    events: ["cta"],
    PropsPanel: ({ props, onChange }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className={labelCls}>Titre du bandeau
            <input aria-label="Titre du bandeau" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className={labelCls}>Sous-titre
            <input aria-label="Sous-titre" className={inputCls}
              value={String(props.subtitle ?? "")} onChange={(e) => set({ subtitle: e.target.value })} />
          </label>
          <label className={labelCls}>URL de l'image de fond
            <input aria-label="URL de l'image de fond" className={inputCls}
              value={String(props.backgroundImageUrl ?? "")} onChange={(e) => set({ backgroundImageUrl: e.target.value })} />
          </label>
          <label className={labelCls}>Libellé du CTA
            <input aria-label="Libellé du CTA" className={inputCls}
              value={String(props.ctaLabel ?? "")} onChange={(e) => set({ ctaLabel: e.target.value })} />
          </label>
          <label className={labelCls}>Lien du CTA
            <input aria-label="Lien du CTA" className={inputCls}
              value={String(props.ctaHref ?? "")} onChange={(e) => set({ ctaHref: e.target.value })} />
          </label>
          <label className={labelCls}>Alignement
            <select aria-label="Alignement" className={inputCls}
              value={String(props.align ?? "left")} onChange={(e) => set({ align: e.target.value })}>
              <option value="left">Gauche</option>
              <option value="center">Centre</option>
            </select>
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const align = props.align === "center" ? "items-center text-center" : "items-start text-left";
      const backgroundImageUrl = props.backgroundImageUrl ? String(props.backgroundImageUrl) : "";
      return (
        <div
          className={`flex h-full w-full flex-col justify-center gap-3 rounded-[var(--gs-radius)] p-8 text-white ${align}`}
          style={
            backgroundImageUrl
              ? { backgroundImage: `url(${backgroundImageUrl})`, backgroundSize: "cover", backgroundPosition: "center" }
              : { backgroundColor: "var(--gs-color-primary)" }
          }
        >
          <h1 className="text-3xl font-bold">{String(props.title ?? "")}</h1>
          {props.subtitle ? <p className="text-lg">{String(props.subtitle)}</p> : null}
          {props.ctaLabel ? (
            <button
              type="button"
              className="mt-2 w-fit rounded-[var(--gs-radius)] bg-white px-4 py-2 text-sm font-medium text-[var(--gs-color-primary)]"
              onClick={() => {
                ctx.bus?.emit(ctx.widgetId ?? "", "cta", { widgetId: ctx.widgetId });
                const href = String(props.ctaHref ?? "");
                if (href) window.open(href, "_blank", "noopener");
              }}
            >
              {String(props.ctaLabel)}
            </button>
          ) : null}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `index.tsx`**

In `shell/src/builder/widgets/index.tsx`, add the import (after the `registerFormWidget` import at line 11):

```tsx
import { registerFormWidget } from "./form";
import { registerHeroWidget } from "./hero";
```

And add the call at the end of `registerBuiltinWidgets()` (after `registerFormWidget();` at line 152):

```tsx
  registerFormWidget();
  registerHeroWidget();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/hero.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full shell test suite**

Run: `cd shell && npm run test`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/widgets/hero.tsx shell/src/builder/widgets/hero.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add Hero content widget"
```

---

### Task 7: Shell widget — `RichSection` + `sanitizeMarkdown`

**Files:**
- Create: `shell/src/builder/widgets/sanitizeMarkdown.ts`
- Create: `shell/src/builder/widgets/sanitizeMarkdown.test.ts`
- Create: `shell/src/builder/widgets/richSection.tsx`
- Create: `shell/src/builder/widgets/richSection.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Modify: `shell/package.json` (new deps)

**Interfaces:**
- Consumes: `marked`, `dompurify` (new npm deps).
- Produces: `sanitizeMarkdown(markdown: string): string`; widget type `"richSection"` registered.

- [ ] **Step 1: Install the new dependencies**

Run:
```bash
cd shell && npm install marked dompurify
```
Expected: `shell/package.json`'s `dependencies` gains `marked` and `dompurify`; `package-lock.json` updated. (DOMPurify ships its own TypeScript types since v3 — no separate `@types/dompurify` needed; confirm by checking `node_modules/dompurify/dist/purify.d.ts` exists after install. Same for `marked`'s bundled types.)

- [ ] **Step 2: Write the failing test for `sanitizeMarkdown`**

Create `shell/src/builder/widgets/sanitizeMarkdown.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { sanitizeMarkdown } from "./sanitizeMarkdown";

test("renders CommonMark: headings, bold/italic, links, lists", () => {
  const html = sanitizeMarkdown("# Titre\n\n**gras** et *italique*\n\n- un\n- deux\n\n[lien](https://example.com)");
  expect(html).toContain("<h1>Titre</h1>");
  expect(html).toContain("<strong>gras</strong>");
  expect(html).toContain("<em>italique</em>");
  expect(html).toContain("<li>un</li>");
  expect(html).toContain('href="https://example.com"');
});

test("strips <script> tags", () => {
  const html = sanitizeMarkdown("# Titre\n\n<script>alert(1)</script>");
  expect(html).not.toContain("<script");
  expect(html).not.toContain("alert(1)");
});

test("strips onerror/on* event handler attributes", () => {
  const html = sanitizeMarkdown('<img src="x" onerror="alert(2)">');
  expect(html).not.toContain("onerror");
});

test("strips javascript: hrefs", () => {
  const html = sanitizeMarkdown("[lien](javascript:alert(3))");
  expect(html).not.toContain("javascript:");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/sanitizeMarkdown.test.ts`
Expected: FAIL — cannot find module `./sanitizeMarkdown`

- [ ] **Step 4: Implement `sanitizeMarkdown.ts`**

Create `shell/src/builder/widgets/sanitizeMarkdown.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { marked } from "marked";
import DOMPurify from "dompurify";

// Single, non-bypassable path from author-supplied Markdown to inserted DOM:
// every RichSection render must go through this function, never call
// marked.parse directly — DOMPurify.sanitize is what makes the XSS risk
// (dangerouslySetInnerHTML downstream) acceptable.
export function sanitizeMarkdown(markdown: string): string {
  const html = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(html);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/sanitizeMarkdown.test.ts`
Expected: PASS (4 tests). If `marked.parse` reports a type error on the `{ async: false }` option in the installed version, check `node_modules/marked/lib/marked.d.ts` for the exact synchronous overload and adjust the call accordingly (the contract that must hold is: `sanitizeMarkdown` returns a `string`, synchronously, never a `Promise`).

- [ ] **Step 6: Write the failing tests for the `RichSection` widget**

Create `shell/src/builder/widgets/richSection.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("richSection renders sanitized Markdown", () => {
  const RichSection = getWidget("richSection")!.Component;
  render(<RichSection props={{ markdown: "# Titre\n\n**gras**" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByRole("heading", { level: 1, name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("gras").tagName).toBe("STRONG");
});

test("richSection strips a script tag (adversarial)", () => {
  const RichSection = getWidget("richSection")!.Component;
  const { container } = render(
    <RichSection props={{ markdown: "# Titre\n\n<script>window.__pwned = true;</script>" }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  expect(container.querySelector("script")).toBeNull();
});

test("richSection shows a discreet placeholder in edit mode when markdown is empty", () => {
  const RichSection = getWidget("richSection")!.Component;
  render(<RichSection props={{ markdown: "" }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText(/vide/i)).toBeInTheDocument();
});

test("richSection renders nothing when markdown is empty outside edit mode", () => {
  const RichSection = getWidget("richSection")!.Component;
  const { container } = render(<RichSection props={{ markdown: "" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(container).toBeEmptyDOMElement();
});
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/richSection.test.tsx`
Expected: FAIL — `getWidget("richSection")` is `undefined`

- [ ] **Step 8: Implement `richSection.tsx`**

Create `shell/src/builder/widgets/richSection.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { sanitizeMarkdown } from "./sanitizeMarkdown";

export function registerRichSectionWidget(): void {
  registerWidget({
    type: "richSection",
    label: "Section riche",
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Markdown
          <textarea
            aria-label="Markdown"
            className="rounded-md border border-slate-300 p-2 font-mono text-xs"
            rows={8}
            value={String(props.markdown ?? "")}
            onChange={(e) => onChange({ ...props, markdown: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const markdown = String(props.markdown ?? "");
      if (!markdown.trim()) {
        return ctx.mode === "edit" ? (
          <p className="text-xs text-[var(--gs-color-muted)]">
            Section de texte vide — ajoutez du Markdown dans le panneau de propriétés.
          </p>
        ) : null;
      }
      const html = sanitizeMarkdown(markdown);
      return <div className="prose max-w-none text-[var(--gs-color-text)]" dangerouslySetInnerHTML={{ __html: html }} />;
    },
  });
}
```

- [ ] **Step 9: Register it in `index.tsx`**

In `shell/src/builder/widgets/index.tsx`, extend the import line added in Task 6:

```tsx
import { registerHeroWidget } from "./hero";
import { registerRichSectionWidget } from "./richSection";
```

And the call:

```tsx
  registerHeroWidget();
  registerRichSectionWidget();
}
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/richSection.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 11: Run the full shell test suite**

Run: `cd shell && npm run test`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/builder/widgets/sanitizeMarkdown.ts shell/src/builder/widgets/sanitizeMarkdown.test.ts shell/src/builder/widgets/richSection.tsx shell/src/builder/widgets/richSection.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add RichSection content widget (Markdown via marked+DOMPurify)"
```

---

### Task 8: Shell widget — `Gallery`

**Files:**
- Create: `shell/src/builder/widgets/gallery.tsx`
- Create: `shell/src/builder/widgets/gallery.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`

**Interfaces:**
- Consumes: `client.listPublicItems` (Task 4), `useItemClient` from `../../api/ItemClientProvider`.
- Produces: widget type `"gallery"` registered, linking each vignette to `/public/items/{pk}` (Task 5's route).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/gallery.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { Item, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

function renderGallery(props: Record<string, unknown>, clientOverrides: Partial<ItemClient> = {}) {
  const client = {
    listPublicItems: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 }),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Gallery = getWidget("gallery")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Gallery props={props} ctx={{ mode: "runtime" } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

const publishedItem: Item = {
  pk: "8", resourceType: "app", title: "Carte des risques", abstract: "Resume", owner: "alice",
  thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: true, keywords: ["risques"],
};

test("gallery calls listPublicItems with the author's fixed filter props", () => {
  const client = renderGallery({ type: "app", tag: "risques", limit: 6, columns: 2 });
  expect(client.listPublicItems).toHaveBeenCalledWith({ type: "app", tag: "risques", page: 1, pageSize: 6 });
});

test("gallery renders a grid of published items, each linking to its public page", async () => {
  renderGallery({}, { listPublicItems: vi.fn().mockResolvedValue({ items: [publishedItem], total: 1, page: 1, pageSize: 12 }) });
  expect(await screen.findByText("Carte des risques")).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /Carte des risques/ });
  expect(link).toHaveAttribute("href", "/public/items/8");
});

test("gallery shows an empty state when there are no published items", async () => {
  renderGallery({});
  expect(await screen.findByText("Aucun élément publié")).toBeInTheDocument();
});

test("gallery shows an error state when the fetch fails", async () => {
  renderGallery({}, { listPublicItems: vi.fn().mockRejectedValue(new Error("fail")) });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/gallery.test.tsx`
Expected: FAIL — `getWidget("gallery")` is `undefined`

- [ ] **Step 3: Implement `gallery.tsx`**

Create `shell/src/builder/widgets/gallery.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ResourceType } from "../../api/types";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

const RESOURCE_TYPES: [string, string][] = [
  ["", "Tous"], ["app", "Application"], ["dashboard", "Tableau de bord"], ["map", "Carte"], ["site", "Site"],
];

export function registerGalleryWidget(): void {
  registerWidget({
    type: "gallery",
    label: "Galerie",
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
    PropsPanel: ({ props, onChange }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className={labelCls}>Type d'élément
            <select aria-label="Type d'élément" className={inputCls}
              value={String(props.type ?? "")} onChange={(e) => set({ type: e.target.value })}>
              {RESOURCE_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Tag
            <input aria-label="Tag" className={inputCls}
              value={String(props.tag ?? "")} onChange={(e) => set({ tag: e.target.value })} />
          </label>
          <label className={labelCls}>Limite
            <input aria-label="Limite" type="number" className={inputCls}
              value={String(props.limit ?? 12)} onChange={(e) => set({ limit: Number(e.target.value) })} />
          </label>
          <label className={labelCls}>Colonnes
            <input aria-label="Colonnes" type="number" className={inputCls}
              value={String(props.columns ?? 3)} onChange={(e) => set({ columns: Number(e.target.value) })} />
          </label>
        </div>
      );
    },
    Component: ({ props }) => {
      const client = useItemClient();
      const type = props.type ? String(props.type) : undefined;
      const tag = props.tag ? String(props.tag) : undefined;
      const limit = Number(props.limit ?? 12);
      const columns = Number(props.columns ?? 3);
      const query = useQuery({
        queryKey: ["public-gallery", type, tag, limit],
        queryFn: () => client.listPublicItems({ type: type as ResourceType | undefined, tag, page: 1, pageSize: limit }),
      });

      if (query.isLoading) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      }
      if (query.isError) {
        return <p role="alert" className="text-xs text-red-600">Erreur de chargement</p>;
      }
      const items = query.data?.items ?? [];
      if (items.length === 0) {
        return <p className="text-sm text-[var(--gs-color-muted)]">Aucun élément publié</p>;
      }
      return (
        <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
          {items.map((item) => (
            <a
              key={item.pk}
              href={`/public/items/${item.pk}`}
              className="flex flex-col overflow-hidden rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] text-inherit no-underline"
            >
              {item.thumbnailUrl ? (
                <img src={item.thumbnailUrl} alt="" className="h-32 w-full object-cover" />
              ) : (
                <div className="h-32 w-full bg-[var(--gs-color-background)]" />
              )}
              <div className="flex flex-col gap-1 p-3">
                <h3 className="text-sm font-semibold text-[var(--gs-color-text)]">{item.title}</h3>
                <p className="text-xs text-[var(--gs-color-muted)]">{item.abstract}</p>
                {(item.keywords ?? []).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {(item.keywords ?? []).map((k) => (
                      <span key={k} className="rounded-full bg-[var(--gs-color-background)] px-2 py-0.5 text-[10px] text-[var(--gs-color-muted)]">
                        {k}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </a>
          ))}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `index.tsx`**

In `shell/src/builder/widgets/index.tsx`, extend the import block from Tasks 6/7:

```tsx
import { registerRichSectionWidget } from "./richSection";
import { registerGalleryWidget } from "./gallery";
```

And the call:

```tsx
  registerRichSectionWidget();
  registerGalleryWidget();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/gallery.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full shell test suite**

Run: `cd shell && npm run test`
Expected: PASS

- [ ] **Step 7: Run `tsc --noEmit`**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgets/gallery.tsx shell/src/builder/widgets/gallery.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add Gallery content widget"
```

---

### Task 9: E2E — `sites-portal-content.spec.ts` + verification pass

**Files:**
- Modify: `shell/e2e/mocks.ts`
- Create: `shell/e2e/sites-portal-content.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: the 41st green E2E spec (per spec §8's acceptance criterion).

- [ ] **Step 1: Extend `mocks.ts` — public items list + a second published item + stateful site public config**

In `shell/e2e/mocks.ts`, the current `mockCore` function declares its site-portal state near the top (lines 31-40):

```ts
  // Site portal (SP-13a) — state for the created-then-published site.
  let siteSlug: string | null = null;
  let sitePublished = false;
  const SITE_APP_CONFIG = {
    version: 1, kind: "site", theme: {}, dataSources: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bienvenue sur le portail" } },
    ] },
    messages: [], pages: [],
  } as const;
```

Leave this as the fallback default, but the E2E in this task will overwrite the site's config via a real builder save (see Step 3), so the actual served config must reflect what was saved. Add a second published item fixture right after it:

```ts
  // Site portal (SP-13a) — state for the created-then-published site.
  let siteSlug: string | null = null;
  let sitePublished = false;
  const SITE_APP_CONFIG = {
    version: 1, kind: "site", theme: {}, dataSources: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bienvenue sur le portail" } },
    ] },
    messages: [], pages: [],
  } as const;

  // Content widgets (SP-13b) — a second published item, distinct from the
  // site itself, for the Gallery to list and link to.
  const GALLERY_ITEM = {
    pk: "8", resourceType: "app", title: "Carte des risques", abstract: "Resume des risques",
    owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: null,
    isPublished: true, keywords: ["risques"],
  } as const;
  const GALLERY_ITEM_CONFIG = {
    version: 1, kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Detail de l'article" } },
    ] },
  } as const;
```

Then find the existing block at the end of the file (the one starting with the comment `// Site portal (SP-13a) — appended last so...`, currently ~lines 335-381) and:

(a) replace the static public-config-by-item mock for `site-1` so it reflects whatever was actually saved through the builder (falls back to `SITE_APP_CONFIG` only if nothing was ever saved):

```ts
  // Public config for the site item — getPublicAppConfig unwraps `data.config`.
  // Serves whatever was actually PUT through the builder (savedConfigs, set by
  // the generic "**/configs/by-item/**" handler above) so that content widgets
  // added via the palette in a test genuinely round-trip to the public view —
  // not a fixture disconnected from what the test actually saved.
  await page.route("https://core.test/public/configs/by-item/site-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-site", itemId: "site-1", kind: "site", version: 1, config: savedConfigs.get("site-1") ?? SITE_APP_CONFIG },
    });
  });
```

(b) add, right after that block, the new public items list route and the gallery item's own public config route:

```ts
  // Public items list (SP-13b) — Gallery's data source. Always returns the
  // one fixed published item; the site itself is not included (the fixture
  // only needs to prove the Gallery→vignette→PublicItemPage path).
  await page.route("https://core.test/public/items*", async (route) => {
    await route.fulfill({ json: { items: [GALLERY_ITEM], total: 1, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/public/configs/by-item/8", async (route) => {
    await route.fulfill({
      json: { id: "cfg-8", itemId: "8", kind: "app", version: 1, config: GALLERY_ITEM_CONFIG },
    });
  });
```

- [ ] **Step 2: Run the existing SP-13a spec to confirm the `mocks.ts` change doesn't regress it**

Run: `cd shell && npx playwright test sites-portal-shell.spec.ts`
Expected: PASS (2 tests, unchanged) — since the site's builder step in that spec never saves any widget, `savedConfigs.get("site-1")` stays `undefined` there and the mock still falls back to `SITE_APP_CONFIG`.

- [ ] **Step 3: Write the new E2E spec**

Create `shell/e2e/sites-portal-content.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, y ajouter Hero+RichSection+Gallery, publier, consulter en anonyme", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // 1. Créer un Site depuis le catalogue.
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("site");
  await page.getByLabel("Titre").fill("Mon Portail");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/site-1\/edit$/);

  // 2. Ajouter Hero + RichSection + Gallery depuis la palette, puis Enregistrer.
  await page.getByRole("button", { name: "Hero" }).click();
  await page.getByLabel("Titre du bandeau").fill("Bienvenue sur mon portail");

  await page.getByRole("button", { name: "Section riche" }).click();
  await page.getByLabel("Markdown").fill("## À propos\n\nTexte **important**.");

  await page.getByRole("button", { name: "Galerie" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 3. Publier.
  await page.goto("/items/site-1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 4. Consultation publique anonyme : Hero, Markdown rendu, galerie des items publiés.
  await page.goto("/sites/mon-portail");
  await expect(page.getByText("Bienvenue sur mon portail")).toBeVisible();
  await expect(page.getByRole("heading", { name: "À propos" })).toBeVisible();
  await expect(page.getByText("important")).toBeVisible();
  await expect(page.getByText("Carte des risques")).toBeVisible();
  // Aucun item non publié ("Alpha", fixture du mock générique, n'est jamais servi par /public/items).
  await expect(page.getByText("Alpha")).toHaveCount(0);

  // 5. Cliquer la vignette → vue publique per-item, rendue par AppRenderer runtime.
  await page.getByRole("link", { name: /Carte des risques/ }).click();
  await expect(page).toHaveURL(/\/public\/items\/8$/);
  await expect(page.getByText("Detail de l'article")).toBeVisible();
});
```

- [ ] **Step 4: Run the new spec**

Run: `cd shell && npx playwright test sites-portal-content.spec.ts`
Expected: PASS (1 test). If the palette button names don't match ("Hero"/"Section riche"/"Galerie" — these come straight from each widget's `label` field set in Tasks 6-8), adjust the spec to the exact label strings actually registered; do not change the widget labels to fit a wrong guess in the spec.

- [ ] **Step 5: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: 41/41 specs green (40 existing + this new one)

- [ ] **Step 6: Run the full verification pass**

Run:
```bash
cd shell && npm run build
cd ../core && uv run pytest -q
cd ../core && uv run lint-imports
```
Expected: `tsc --noEmit` + `vite build` clean; core tests green; import-linter clean.

- [ ] **Step 7: Check the `npm audit` gate for the two new dependencies**

Run: `cd shell && npm audit --audit-level=high`
Expected: no new High/Critical vulnerability. If one surfaces on a transitive dependency of `marked`/`dompurify` with no upstream fix, follow the existing allowlist mechanism in `shell/scripts/check-npm-audit.mjs` (SP-9 sécurité minimale) rather than downgrading or ignoring the audit — add the package to `ALLOWLIST` with a comment explaining why, matching the existing `lodash-es`/`cel-js` precedent.

- [ ] **Step 8: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/sites-portal-content.spec.ts
git commit -m "test(e2e): sites-portal-content — Hero/RichSection/Gallery end to end"
```

---

## Self-Review Notes (for the plan author, already applied above)

- **Spec coverage:** §4.1 (route + repo function) → Tasks 2-3. §4.2 (`keywords` exposure) → Task 1. §4.3 (no new config route) → Task 5 reuses `getPublicAppConfig` unchanged. §5.1 (public per-item page/route) → Task 5. §5.2 (`ItemClient`) → Task 4. §5.3 (three widgets) → Tasks 6-8. §6 (leakage matrix, XSS) → Task 3's `test_leakage_matrix_...`, Task 7's adversarial `sanitizeMarkdown` tests. §7 (all listed test cases) → covered across Tasks 1-9. §8 (acceptance criteria) → Task 9's E2E spec + full verification pass. §9 (OpenAPI drift, npm audit, tag portability) → Task 3 Step 6, Task 9 Step 7, Task 2's Python-side tag filter.
- **Placeholder scan:** no TBD/"add error handling"/"similar to Task N" left in any step; every step has literal, runnable code.
- **Type consistency:** `list_published_items(session, *, tenant_id=DEFAULT_TENANT_SLUG, resource_type=None, tag=None, page=1, page_size=12) -> ItemPage` (Task 2) matches its call in the route (Task 3) and its 5 repo-level tests. `ItemClient.listPublicItems(params?: {...}): Promise<ItemPage>` (Task 4) matches its use in `Gallery` (Task 8) exactly (`{ type, tag, page: 1, pageSize: limit }`). Widget labels declared in Tasks 6-8 (`"Hero"`, `"Section riche"`, `"Galerie"`) match the button names clicked in Task 9's E2E spec.
