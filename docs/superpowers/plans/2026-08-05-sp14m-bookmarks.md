# SP-14m — Bookmarks (vues analytiques enregistrées) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user on an `interactions: "auto"` dashboard name and save the current analytics context (time range / extent / cross-filter) as a new platform item — a "bookmark" — catalogued and shareable like any other item, retrievable from a dedicated "Mes vues" page and reopened in one click to replay the exact same context.

**Architecture:** `bookmark` becomes a fifth `BuilderConfig.kind` alongside `app`/`dashboard`/`map`/`site`/`dataset` — no new REST route, no DB migration (`configs.kind` and `items.resource_type` are bare `String` columns). Core validation (`appId` must reference a readable `app`/`dashboard` item) is direct in `app.configs`, not routed through the `dataset_validation.py` registry, because `app.configs` already imports `app.items` — no forbidden-layer situation exists here. The shell's `BookmarkPayload` type is a byte-for-byte mirror of `AnalyticsContextState` (`shell/src/builder/AnalyticsContext.tsx`), so no client-side translation is ever needed between "the context currently active" and "the payload sent to the server."

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy (`core/`), React/TypeScript/React Query/React Router (`shell/`), Playwright E2E, MCP (`mcp.server.fastmcp`).

## Global Constraints

- No Alembic migration — `configs.kind` and `items.resource_type` are plain `String` columns, verified in `core/app/configs/models.py` and `core/app/items/models.py`.
- Additive only: existing configs/specs must remain valid and green; no config in the fixtures or E2E specs currently has `kind="bookmark"`.
- Docs and commit messages in French; code/identifiers in English (per `CLAUDE.md`).
- Conventional commits (`feat(core): …`, `feat(shell): …`), one subject each, small.
- TDD: write the failing test before the implementation, for every step below.
- Out of scope (do not implement): cross-dataset cross-filter, visual query builder, a bookmark edit flow, a data snapshot/cache, a dedicated `list_bookmarks` MCP tool (generic `list_items(type="bookmark")` already covers it), and validation of `pageId`/context freshness against the target app.

---

## Task 1: Core — `BookmarkPayload` schema (Pydantic)

**Files:**
- Modify: `core/app/configs/schemas.py:88-142` (insert new models before `BuilderConfig`, extend `BuilderConfig.kind`/fields/validator)
- Test: `core/tests/test_bookmark_config_schema.py` (new)

**Interfaces:**
- Produces: `BookmarkCrossFilterEntry(field: str, value: str | list[str], originSourceId: str)`, `BookmarkTimeRange(from_: str [alias "from"], to: str)`, `BookmarkPayload(appId: str, pageId: str, timeRange: BookmarkTimeRange | None, extent: tuple[float,float,float,float] | None, crossFilter: dict[str, BookmarkCrossFilterEntry])`. `BuilderConfig.kind` gains the literal `"bookmark"` and a new field `bookmark: BookmarkPayload | None = None`. These are the exact names Task 2 (validation) and Task 3 (MCP tool) import.

- [ ] **Step 1: Write the failing schema tests**

Create `core/tests/test_bookmark_config_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _bookmark_body(**overrides) -> dict:
    body = {
        "version": 1,
        "kind": "bookmark",
        "bookmark": {
            "appId": "app-1",
            "pageId": "page-1",
            "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
            "extent": [2.0, 46.0, 3.0, 47.0],
            "crossFilter": {
                "dataset-1": {"field": "region", "value": "Nord", "originSourceId": "src-1"},
            },
        },
    }
    body["bookmark"].update(overrides)
    return body


def test_bookmark_config_valide():
    config = BuilderConfig.model_validate(_bookmark_body())
    assert config.kind == "bookmark"
    assert config.bookmark.appId == "app-1"
    assert config.bookmark.pageId == "page-1"
    assert config.bookmark.timeRange.from_ == "2026-01-01"
    assert config.bookmark.timeRange.to == "2026-02-01"
    assert config.bookmark.extent == (2.0, 46.0, 3.0, 47.0)
    assert config.bookmark.crossFilter["dataset-1"].field == "region"
    assert config.bookmark.crossFilter["dataset-1"].originSourceId == "src-1"


def test_bookmark_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "bookmark"})


def test_bookmark_config_time_range_extent_cross_filter_optionnels():
    body = _bookmark_body()
    del body["bookmark"]["timeRange"]
    del body["bookmark"]["extent"]
    del body["bookmark"]["crossFilter"]
    config = BuilderConfig.model_validate(body)
    assert config.bookmark.timeRange is None
    assert config.bookmark.extent is None
    assert config.bookmark.crossFilter == {}


def test_bookmark_config_page_id_vide_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId=""))


def test_bookmark_config_page_id_blanc_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId="   "))


def test_bookmark_config_round_trips_through_dump_and_validate():
    # by_alias=True is what configs_repo.create_config persists with — this
    # is the exact round trip a saved-then-reloaded bookmark goes through.
    config = BuilderConfig.model_validate(_bookmark_body())
    dumped = config.model_dump(by_alias=True)
    assert dumped["bookmark"]["timeRange"]["from"] == "2026-01-01"
    reloaded = BuilderConfig.model_validate(dumped)
    assert reloaded.bookmark.timeRange.from_ == "2026-01-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_bookmark_config_schema.py -v`
Expected: FAIL — `kind` literal doesn't accept `"bookmark"` / `BuilderConfig` has no field `bookmark` (Pydantic `ValidationError` raised where the test expects success, or `AttributeError`).

- [ ] **Step 3: Implement the schema**

In `core/app/configs/schemas.py`, insert immediately after the `DatasetPayload` class (after its closing `_require_source_id` validator, before `class BuilderConfig`):

```python
class BookmarkCrossFilterEntry(BaseModel):
    field: str
    value: str | list[str]
    originSourceId: str


class BookmarkTimeRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class BookmarkPayload(BaseModel):
    appId: str
    pageId: str
    timeRange: BookmarkTimeRange | None = None
    extent: tuple[float, float, float, float] | None = None
    crossFilter: dict[str, BookmarkCrossFilterEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_non_empty_page_id(self) -> "BookmarkPayload":
        if not self.pageId.strip():
            raise ValueError("bookmark pageId must not be empty")
        return self
```

Then edit `BuilderConfig` (same file):

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark"]
```

and add the field alongside `dataset`:

```python
    dataset: DatasetPayload | None = None
    bookmark: BookmarkPayload | None = None
```

and extend `_require_kind_payload`:

```python
        if self.kind == "dataset" and self.dataset is None:
            raise ValueError("dataset config requires a dataset payload")
        if self.kind == "bookmark" and self.bookmark is None:
            raise ValueError("bookmark config requires a bookmark payload")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_bookmark_config_schema.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: same pass/skip counts as before, plus the 6 new tests (no existing test references an exhaustive `kind` literal list, per the earlier grep sweep of `core/app`).

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_bookmark_config_schema.py
git commit -m "feat(core): bookmark config schema (SP-14m)"
```

---

## Task 2: Core — direct validation + REST wiring (`POST /configs`, `PUT /configs/by-item/{id}`)

**Files:**
- Create: `core/app/configs/bookmark_validation.py`
- Modify: `core/app/configs/routes.py:1-20` (import), `:68-92` (create_config), `:211-229` (update_config_by_item)
- Test: `core/tests/test_create_bookmark.py` (new)

**Interfaces:**
- Consumes: `BuilderConfig`/`BookmarkPayload` (Task 1), `items_repo.get_access_facts`/`items_repo.get_item` (`core/app/items/repository.py:129,141`), `can()` (`core/app/sharing/authorization.py:29`).
- Produces: `validate_bookmark_payload(session: Session, config: BuilderConfig, *, user: User) -> None` — raises `HTTPException(422, "app not found")` for both a non-existent `appId` and one the caller can't read (same message, to not leak existence — same convention as `app.collections.dataset_validation`), and for an `appId` that resolves to an item whose `resourceType` isn't `"app"`/`"dashboard"`. This is the exact name Task 3 wraps for the MCP tool.

- [ ] **Step 1: Write the failing REST tests**

Create `core/tests/test_create_bookmark.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="alice@example.com", first_name="Alice", last_name="Doe",
        )
        bob = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-2",
            username="bob", email="bob@example.com", first_name="Bob", last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.user = user  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.bob = bob  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _app_body(title: str = "Cible") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1, "kind": "app",
            "layout": {"type": "grid", "breakpoints": {}, "items": []},
        },
    }


def _bookmark_body(app_id: str, title: str = "Ma vue") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1, "kind": "bookmark",
            "bookmark": {
                "appId": app_id, "pageId": "page-1",
                "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
                "extent": None, "crossFilter": {},
            },
        },
    }


def test_create_bookmark_avec_app_existante_et_lisible(client):
    app_item_id = client.post("/configs", json=_app_body()).json()["itemId"]
    res = client.post("/configs", json=_bookmark_body(app_item_id))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/items/{item_id}").json()
    assert item["resourceType"] == "bookmark"


def test_create_bookmark_app_inexistante_rejetee(client):
    res = client.post("/configs", json=_bookmark_body("inexistante"))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_app_non_lisible_rejetee_avec_meme_message(client):
    # Bob's app is private by default (Item.is_public defaults to False) —
    # alice (the caller) is neither its owner nor a group member.
    with client.session_factory() as session:
        from app.configs import repository as configs_repo
        from app.configs.schemas import BuilderConfig
        from app.items import repository as items_repo

        bob_app = items_repo.create_item(
            session, tenant_id=client.user.tenant_id, owner_id=client.bob.id,
            resource_type="app", title="App de Bob",
        )
        configs_repo.create_config(
            session,
            BuilderConfig(version=1, kind="app", layout={"type": "grid", "breakpoints": {}, "items": []}),
            bob_app.id, tenant_id=client.user.tenant_id,
        )
        session.commit()
        bob_app_id = bob_app.id

    res = client.post("/configs", json=_bookmark_body(bob_app_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_cible_un_kind_non_app_rejetee(client):
    with client.session_factory() as session:
        from app.items import repository as items_repo

        map_item = items_repo.create_item(
            session, tenant_id=client.user.tenant_id, owner_id=client.user.id,
            resource_type="map", title="Une carte",
        )
        session.commit()
        map_item_id = map_item.id

    res = client.post("/configs", json=_bookmark_body(map_item_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_update_bookmark_app_inexistante_rejetee(client):
    app_item_id = client.post("/configs", json=_app_body()).json()["itemId"]
    created = client.post("/configs", json=_bookmark_body(app_item_id))
    item_id = created.json()["itemId"]
    bad_config = {
        "version": 1, "kind": "bookmark",
        "bookmark": {"appId": "inexistante", "pageId": "page-1"},
    }
    res = client.put(f"/configs/by-item/{item_id}", json=bad_config)
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_create_bookmark.py -v`
Expected: FAIL — `POST /configs` with `kind="bookmark"` currently returns 201 unconditionally (no validation runs yet), so `test_create_bookmark_app_inexistante_rejetee` and the two "rejected" tests fail (they expect 422 but get 201).

- [ ] **Step 3: Implement `bookmark_validation.py`**

Create `core/app/configs/bookmark_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Direct kind="bookmark" validation for app.configs. Unlike dataset_validation.py,
no registry indirection is needed here: appId always refers to an app/dashboard
item, and app.configs already imports app.items (see routes.py's _require_access),
so there is no forbidden cross-module dependency to route around (SP-14m §3).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_bookmark_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "bookmark":
        return
    payload = config.bookmark
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.appId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak app
        # existence, same convention as app.collections.dataset_validation.
        raise HTTPException(status_code=422, detail="app not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.appId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType not in ("app", "dashboard"):
        raise HTTPException(status_code=422, detail="app not found")
```

- [ ] **Step 4: Wire it into `core/app/configs/routes.py`**

Add the import next to the existing dataset one (near line 10):

```python
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
```

In `create_config` (around line 71), add the call right after the dataset one:

```python
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
```

In `update_config_by_item` (around line 224), same pattern:

```python
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_create_bookmark.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: same baseline plus the 6 (Task 1) + 5 (Task 2) new tests, no regressions — `validate_bookmark_payload` is a no-op for every other `kind`, so existing `app`/`dashboard`/`map`/`site`/`dataset` configs are unaffected.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/bookmark_validation.py core/app/configs/routes.py core/tests/test_create_bookmark.py
git commit -m "feat(core): validate bookmark appId readability on create/update (SP-14m)"
```

---

## Task 3: Core — MCP tool `create_bookmark`

**Files:**
- Modify: `core/app/mcp/tools.py:17` (import), `:39` (READ_ONLY_TOOLS), `:97-107` (add `_validate_bookmark` next to `_validate_dataset`), `:375-419` (add `create_bookmark` tool after `create_dataset`)
- Modify: `core/tests/test_mcp_read_only_mode.py:112-115,147-154` (extend the read-only-tools set test + add a bookmark-specific refuse test)
- Test: `core/tests/test_mcp_tools_bookmark_create.py` (new)

**Interfaces:**
- Consumes: `BookmarkPayload`/`BookmarkTimeRange`/`BookmarkCrossFilterEntry` (Task 1), `validate_bookmark_payload` (Task 2), `_resolve_actor`/`is_read_only_mode`/`items_repo`/`configs_repo`/`write_audit` (all already imported in `mcp/tools.py`).
- Produces: MCP tool `create_bookmark(ctx, title, appId, pageId, timeRange=None, extent=None, crossFilter=None) -> ItemRead`, registered in `READ_ONLY_TOOLS`.

- [ ] **Step 1: Write the failing MCP tool tests**

Create `core/tests/test_mcp_tools_bookmark_create.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""create_bookmark (SP-14m) — mirrors POST /configs with kind="bookmark":
same BookmarkPayload construction, same appId readability validation
(app.configs.bookmark_validation) as the REST route."""
from sqlalchemy import select

from app.audit.models import AuditLog
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401


def _register_app(app_client, *, owner=None) -> str:
    with app_client.session_factory() as session:
        item_owner = owner or app_client.mock_user
        item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=item_owner.id,
            resource_type="app", title="Cible",
        )
        configs_repo.create_config(
            session,
            BuilderConfig(version=1, kind="app", layout={"type": "grid", "breakpoints": {}, "items": []}),
            item.id, tenant_id=app_client.tenant.id,
        )
        session.commit()
        return item.id


def test_create_bookmark_creates_item_and_config(app_client):
    with app_client:
        app_id = _register_app(app_client)
        result = call_tool(app_client, "create_bookmark", {
            "title": "Ma vue", "appId": app_id, "pageId": "page-1",
            "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
        })

    assert result["resourceType"] == "bookmark"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.kind == "bookmark"
        assert config.config.bookmark.appId == app_id
        assert config.config.bookmark.pageId == "page-1"
        assert config.config.bookmark.timeRange.from_ == "2026-01-01"


def test_create_bookmark_accepts_extent_and_cross_filter(app_client):
    with app_client:
        app_id = _register_app(app_client)
        result = call_tool(app_client, "create_bookmark", {
            "title": "Ma vue", "appId": app_id, "pageId": "page-1",
            "extent": [2.0, 46.0, 3.0, 47.0],
            "crossFilter": {"dataset-1": {"field": "region", "value": "Nord", "originSourceId": "src-1"}},
        })

    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.bookmark.extent == (2.0, 46.0, 3.0, 47.0)
        assert config.config.bookmark.crossFilter["dataset-1"].field == "region"


def test_create_bookmark_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        app_id = _register_app(app_client)
        call_tool(app_client, "create_bookmark", {"title": "Ma vue", "appId": app_id, "pageId": "page-1"})

    with app_client.session_factory() as session:
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)


def test_create_bookmark_unreadable_app_errors_without_leaking_existence(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cb-sub",
            username="otherowner-cb", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        app_id = _register_app(app_client, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_bookmark", {
            "title": "Ma vue", "appId": app_id, "pageId": "page-1",
        })
    assert "app not found" in error_text


def test_create_bookmark_empty_page_id_errors(app_client):
    with app_client:
        app_id = _register_app(app_client)
        error_text = call_tool_expecting_error(app_client, "create_bookmark", {
            "title": "Ma vue", "appId": app_id, "pageId": "  ",
        })
    assert error_text  # Pydantic ValidationError surfaced as a tool error
```

Add the read-only-mode tests to `core/tests/test_mcp_read_only_mode.py`. Replace the existing:

```python
def test_read_only_tools_constant_matches_the_five_write_tools():
    assert READ_ONLY_TOOLS == {
        "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
    }
```

with:

```python
def test_read_only_tools_constant_matches_the_six_write_tools():
    assert READ_ONLY_TOOLS == {
        "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
        "create_bookmark",
    }
```

and add, right after `test_create_dataset_refuses_in_read_only_mode`:

```python
def test_create_bookmark_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_bookmark",
            {"title": "X", "appId": "does-not-exist", "pageId": "page-1"},
        )
    assert READ_ONLY_MESSAGE in error_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_bookmark_create.py tests/test_mcp_read_only_mode.py -v`
Expected: FAIL — `create_bookmark` tool doesn't exist yet (`call_tool` raises because the MCP server has no such tool registered); the read-only-tools set test fails (still 5 entries).

- [ ] **Step 3: Implement the tool**

In `core/app/mcp/tools.py`, extend the schemas import (line 17):

```python
from app.configs.schemas import (
    BookmarkCrossFilterEntry, BookmarkPayload, BookmarkTimeRange, BuilderConfig,
    DatasetColumnMeta, DatasetPayload,
)
```

Add the validation import next to the dataset one:

```python
from app.configs.bookmark_validation import validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload
```

Extend `READ_ONLY_TOOLS` (line 39):

```python
READ_ONLY_TOOLS = {
    "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
    "create_bookmark",
}
```

Add `_validate_bookmark` right after `_validate_dataset` (around line 106):

```python
def _validate_bookmark(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors _validate_dataset above — same rationale (ValueError instead
    of HTTPException, no HTTP status channel in an MCP tool body)."""
    try:
        validate_bookmark_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
```

Add the tool itself right after `create_dataset` (around line 419):

```python
    @server.tool()
    async def create_bookmark(
        ctx: Context,
        title: str,
        appId: str,
        pageId: str,
        timeRange: BookmarkTimeRange | None = None,
        extent: tuple[float, float, float, float] | None = None,
        crossFilter: dict[str, BookmarkCrossFilterEntry] | None = None,
    ) -> ItemRead:
        """Save a named analytics view (time range/extent/cross-filter) on an
        app page — mirrors POST /configs with kind="bookmark". SP-14m."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = BookmarkPayload(
                appId=appId, pageId=pageId, timeRange=timeRange,
                extent=extent, crossFilter=crossFilter or {},
            )
            config = BuilderConfig(version=1, kind="bookmark", bookmark=payload)
            _validate_bookmark(session, config, user=user)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="bookmark", title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": "bookmark"},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None  # just created it, in the same transaction
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_bookmark_create.py tests/test_mcp_read_only_mode.py -v`
Expected: PASS (5 + 2 tests)

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: same baseline plus all new tests from Tasks 1-3, no regressions.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_bookmark_create.py core/tests/test_mcp_read_only_mode.py
git commit -m "feat(core): mcp create_bookmark tool (SP-14m)"
```

---

## Task 4: Shell — types, `itemClient`, hooks

**Files:**
- Modify: `shell/src/api/types.ts:2` (`ResourceType`), insert near `:215-241` (new `Bookmark*` types + `CreateBookmarkInput`), `:103-...` (`ItemClient` interface — add `createBookmarkItem`/`getBookmarkConfig`)
- Modify: `shell/src/api/itemClient.ts:1-2` (imports), insert near `:605-619` (`createBookmarkItem`/`getBookmarkConfig` implementations)
- Modify: `shell/src/api/hooks.ts` (add `useCreateBookmark`, near `:208-217`)
- Test: `shell/src/api/itemClient.test.ts` (append), `shell/src/api/hooks.test.tsx` (append, if it covers `useCreateDataset` — mirror that pattern)

**Interfaces:**
- Consumes: `AnalyticsContextState` shape (`shell/src/builder/AnalyticsContext.tsx:1-13`) — `BookmarkPayload`'s `timeRange`/`extent`/`crossFilter` fields are a byte-for-byte copy of that type's fields, plus `appId`/`pageId`.
- Produces: `CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload` (`BookmarkPayload` itself already carries `appId`/`pageId`/`timeRange`/`extent`/`crossFilter`), `client.createBookmarkItem(input): Promise<Item>`, `client.getBookmarkConfig(pk): Promise<BookmarkPayload>`, `useCreateBookmark()` mutation hook. Task 5 and Task 6 both import these.

- [ ] **Step 1: Write the failing itemClient tests**

Append to `shell/src/api/itemClient.test.ts` (after the `createDatasetItem`/`getDatasetConfig` tests, following the exact same style — check an existing `createMapItem`/`createDatasetItem` test above for the `makeClient()`/`server.use(...)` harness already in this file and reuse it verbatim):

```typescript
test("createBookmarkItem posts a bookmark payload and returns a bookmark Item", async () => {
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      const body = (await request.json()) as { title: string; config: unknown };
      expect(body.config).toEqual({
        version: 1,
        kind: "bookmark",
        bookmark: {
          appId: "app-1", pageId: "page-1",
          timeRange: { from: "2026-01-01", to: "2026-02-01" },
          extent: null, crossFilter: {},
        },
      });
      return HttpResponse.json({ id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" }, { status: 201 });
    }),
  );
  const item = await makeClient().createBookmarkItem({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
  });
  expect(item).toEqual({
    pk: "bookmark-1", resourceType: "bookmark", title: "Ma vue", abstract: "",
    owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-bookmark", isPublished: false,
  });
});

test("getBookmarkConfig reads the bookmark payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-1", () =>
      HttpResponse.json({
        id: "cfg-bookmark", itemId: "bookmark-1", kind: "bookmark",
        config: {
          version: 1, kind: "bookmark",
          bookmark: {
            appId: "app-1", pageId: "page-1",
            timeRange: { from: "2026-01-01", to: "2026-02-01" },
            extent: null, crossFilter: {},
          },
        },
      }),
    ),
  );
  const payload = await makeClient().getBookmarkConfig("bookmark-1");
  expect(payload).toEqual({
    appId: "app-1", pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
  });
});

test("getBookmarkConfig throws when the config has no bookmark payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-2", () =>
      HttpResponse.json({ id: "cfg-x", itemId: "bookmark-2", kind: "bookmark", config: { version: 1, kind: "bookmark" } }),
    ),
  );
  await expect(makeClient().getBookmarkConfig("bookmark-2")).rejects.toThrow();
});
```

(`server`/`http`/`HttpResponse` are already imported at the top of `itemClient.test.ts:2-3`, and `makeClient` is already defined at `:6` — the same harness the existing `createDatasetItem` tests use. Nothing new to import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `createBookmarkItem`/`getBookmarkConfig` don't exist on the client yet (TypeScript compile error / `undefined is not a function`).

- [ ] **Step 3: Add the types**

In `shell/src/api/types.ts`, extend `ResourceType` (line 2):

```typescript
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark";
```

Insert near the `DatasetConfig`/`CreateDatasetInput` block (after line 241, before `export type FeatureLayerSource`):

```typescript
export type BookmarkCrossFilterValue = string | string[] | { from: string; to: string };
export type BookmarkCrossFilterEntry = { field: string; value: BookmarkCrossFilterValue; originSourceId: string };

export type BookmarkPayload = {
  appId: string;
  pageId: string;
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, BookmarkCrossFilterEntry>;
};

export type CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload;
```

Add to the `ItemClient` interface (after `createDatasetItem`, around line 136):

```typescript
  createDatasetItem(input: CreateDatasetInput): Promise<Item>;
  createBookmarkItem(input: CreateBookmarkInput): Promise<Item>;
  getBookmarkConfig(pk: string): Promise<BookmarkPayload>;
```

- [ ] **Step 4: Implement `itemClient.ts`**

Extend the type import at the top of `shell/src/api/itemClient.ts` (line 2) with `BookmarkPayload, CreateBookmarkInput`.

Insert after `createDatasetItem` (after line 605, before `getDatasetConfig`):

```typescript
    async createBookmarkItem(input: CreateBookmarkInput): Promise<Item> {
      const bookmark: BookmarkPayload = {
        appId: input.appId, pageId: input.pageId,
        timeRange: input.timeRange, extent: input.extent, crossFilter: input.crossFilter,
      };
      const config = { version: 1, kind: "bookmark", bookmark };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createBookmarkItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "bookmark", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getBookmarkConfig(pk: string): Promise<BookmarkPayload> {
      const data = await request<{ config?: { bookmark?: BookmarkPayload } }>(
        "GET", `/configs/by-item/${pk}`,
      );
      if (!data.config?.bookmark) throw new Error("getBookmarkConfig: config has no bookmark payload");
      return data.config.bookmark;
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: Write the failing hook test**

`hooks.test.tsx` has no dedicated test for `useCreateDataset`, but it does have one for `useCreateMap` (`shell/src/api/hooks.test.tsx:140-147`), using its own `makeWrapper(client: ItemClient)` helper (`:129-138`, distinct from the file's other `wrapper` function used by hooks that don't need a custom per-test client). Add the mirror for `useCreateBookmark` right after the `useCreateMap` test:

```typescript
test("useCreateBookmark creates a bookmark and invalidates items", async () => {
  const client = {
    createBookmarkItem: vi.fn().mockResolvedValue({ pk: "bookmark-1", resourceType: "bookmark", title: "Ma vue" }),
  } as unknown as ItemClient;
  const { result } = renderHook(() => useCreateBookmark(), { wrapper: makeWrapper(client) });
  await result.current.mutateAsync({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: null, extent: null, crossFilter: {},
  });
  expect(client.createBookmarkItem).toHaveBeenCalledWith({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: null, extent: null, crossFilter: {},
  });
});
```

Add `useCreateBookmark` to this file's import from `./hooks` (line 10).

- [ ] **Step 7: Implement `useCreateBookmark`**

In `shell/src/api/hooks.ts`, add after `useCreateDataset` (after line 217):

```typescript
export function useCreateBookmark() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookmarkInput) => client.createBookmarkItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
```

Add `CreateBookmarkInput` to this file's type import from `./types`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx`
Expected: PASS

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: 398+ tests, all green (no regressions — every change so far is additive: a new `ResourceType` member, new types, new interface methods, new client methods, new hook).

- [ ] **Step 10: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): bookmark item client + hook (SP-14m)"
```

---

## Task 5: Shell — `CatalogPage` reuse (`/bookmarks`) + bookmark-aware open navigation

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx:12,14,50-66` (add `fixedType` prop, hide the selector when set)
- Modify: `shell/src/shell/routes.tsx` (add `BookmarksRoute` + `/bookmarks` route; add a shared async open-navigation helper used by both `CatalogRoute` and `BookmarksRoute`)
- Test: `shell/src/pages/CatalogPage.test.tsx` (append), `shell/src/shell/routes.test.tsx` (append)

**Interfaces:**
- Consumes: `client.getBookmarkConfig(pk)` (Task 4), `encodeAnalyticsContext` (`shell/src/lib/analyticsContextUrl.ts:3-6`), `useItemClient` (`shell/src/api/ItemClientProvider.ts`).
- Produces: `CatalogPage({ onOpenItem, fixedType? }: { onOpenItem: ...; fixedType?: ResourceType })`; route `/bookmarks`. No change to `CatalogPage`'s existing `onOpenItem` contract, so Task 6 and E2E (Task 7) can rely on it unchanged.

- [ ] **Step 1: Write the failing `CatalogPage` test**

Append to `shell/src/pages/CatalogPage.test.tsx`:

```typescript
test("fixedType locks the type filter and hides the selector", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} fixedType="bookmark" />, { wrapper });
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark"));
  expect(screen.queryByLabelText("Type")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: FAIL — `CatalogPage` has no `fixedType` prop; `type` stays `""`/unlocked and the `Type` selector is still rendered.

- [ ] **Step 3: Implement `fixedType` in `CatalogPage.tsx`**

Change the signature (line 12):

```typescript
export function CatalogPage({
  onOpenItem, fixedType,
}: {
  onOpenItem: (pk: string, type: ResourceType) => void;
  fixedType?: ResourceType;
}) {
```

Change the `type` state initializer (line 14):

```typescript
  const [type, setType] = useState<ResourceType | "">(fixedType ?? "");
```

Wrap the `Type` selector label (lines 50-66) in a guard:

```typescript
        {!fixedType && (
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={type}
              onChange={(e) => {
                setType(e.target.value as ResourceType | "");
                setPage(1);
              }}
            >
              <option value="">Tous</option>
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
            </select>
          </label>
        )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: PASS (4 tests total)

- [ ] **Step 5: Write the failing routes test**

Append to `shell/src/shell/routes.test.tsx`. First add a mock for the bookmark-config fetch route, mirroring the file's existing `http.get("https://core.test/items", ...)` mock style:

```typescript
test("renders the bookmarks catalog at /bookmarks, filtered to type=bookmark", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({
        items: [
          { pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      });
    }),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await screen.findByText("Ma vue");
  expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark");
});

test("opening a bookmark navigates to its app+page+ctx URL, not an editor", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          { pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      }),
    ),
    http.get("https://core.test/configs/by-item/bm-1", () =>
      HttpResponse.json({
        id: "cfg-bm-1", itemId: "bm-1", kind: "bookmark",
        config: {
          version: 1, kind: "bookmark",
          bookmark: { appId: "42", pageId: "page-1", timeRange: null, extent: null, crossFilter: {} },
        },
      }),
    ),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText(/^app-runtime-42-page-1$/)).toBeInTheDocument();
});
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: FAIL — no `/bookmarks` route exists (blank render / no "Ma vue" text found).

- [ ] **Step 7: Implement the route + bookmark-aware open navigation**

In `shell/src/shell/routes.tsx`, add the import:

```typescript
import { useItemClient } from "../api/ItemClientProvider";
import { encodeAnalyticsContext } from "../lib/analyticsContextUrl";
```

Add a shared navigation helper, right after the imports (before `CatalogRoute`):

```typescript
// Shared by CatalogRoute (general catalog) and BookmarksRoute ("Mes vues"):
// a bookmark has no editor (SP-14m — no edit flow for this kind), so opening
// one fetches its saved app/page/context and replays it via ?ctx=, instead
// of navigating to an editor route like every other kind below.
function useOpenItem() {
  const navigate = useNavigate();
  const client = useItemClient();
  return async (pk: string, type: ResourceType) => {
    if (type === "bookmark") {
      const bookmark = await client.getBookmarkConfig(pk);
      const ctx = encodeAnalyticsContext({
        timeRange: bookmark.timeRange, extent: bookmark.extent, crossFilter: bookmark.crossFilter,
      });
      navigate(`/apps/${encodeURIComponent(bookmark.appId)}/${encodeURIComponent(bookmark.pageId)}?ctx=${ctx}`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
  };
}
```

Add the `ResourceType` import to the existing `import type` (or add a new `import type { ResourceType } from "../api/types";` line).

Replace `CatalogRoute` to use the shared helper:

```typescript
function CatalogRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} />;
}
```

Add `BookmarksRoute` right after it:

```typescript
function BookmarksRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} fixedType="bookmark" />;
}
```

Register the route in `AppRoutes` (inside `<Route element={<ProtectedLayout />}>`, after `/items/:pk`):

```typescript
        <Route path="/bookmarks" element={<BookmarksRoute />} />
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: PASS (all routes.test.tsx tests, including the two new ones — the pre-existing `"navigates from catalog to app builder on open (app item)"` test must still pass unchanged, since `useOpenItem`'s non-bookmark branch is byte-identical to the old inline ternary)

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/shell/routes.tsx shell/src/pages/CatalogPage.test.tsx shell/src/shell/routes.test.tsx
git commit -m "feat(shell): /bookmarks catalog + bookmark-aware open navigation (SP-14m)"
```

---

## Task 6: Shell — "Enregistrer la vue" button on `AppRuntimePage`

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx` (add local analytics-context state, a toolbar, the save button + dialog)
- Test: `shell/src/pages/AppRuntimePage.test.tsx` (append)

**Interfaces:**
- Consumes: `useCreateBookmark` (Task 4), `AnalyticsContextState` (`shell/src/builder/AnalyticsContext.tsx`), `Dialog` (`shell/src/ui/dialog.tsx`), `useAuth` (`shell/src/auth/useAuth.ts`, for `username` as the bookmark's `owner`).
- Produces: a button labeled "Enregistrer la vue", visible only when `query.data?.interactions === "auto"`; clicking it opens a dialog (label input, "Enregistrer"/"Annuler" buttons) that calls `useCreateBookmark().mutateAsync(...)` with the page's current `AnalyticsContextState`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/pages/AppRuntimePage.test.tsx`. First extend the top-of-file mocks: add `vi.mock("../auth/useAuth", ...)` already exists (it mocks `username: "tanguy"`), and add a `createBookmarkItem` spy to the client passed into `renderRuntime`.

```typescript
test("the save-view button is absent when interactions is manual", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(manualDateFilterConfig) });
  await screen.findByLabelText("Date de début");
  expect(screen.queryByRole("button", { name: "Enregistrer la vue" })).not.toBeInTheDocument();
});

test("the save-view button is present when interactions is auto", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig) });
  expect(await screen.findByRole("button", { name: "Enregistrer la vue" })).toBeInTheDocument();
});

test("saving a view captures the current analytics context and posts a bookmark", async () => {
  const createBookmarkItem = vi.fn().mockResolvedValue({
    pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "",
    owner: "tanguy", thumbnailUrl: null, date: "", configId: "cfg-bm-1", isPublished: false,
  });
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
    createBookmarkItem,
  });
  const fromInput = await screen.findByLabelText("Date de début");
  const toInput = await screen.findByLabelText("Date de fin");
  await userEvent.type(fromInput, "2026-01-01");
  await userEvent.type(toInput, "2026-02-01");

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer la vue" }));
  await userEvent.type(screen.getByLabelText("Nom de la vue"), "Ma vue");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(createBookmarkItem).toHaveBeenCalledWith({
      title: "Ma vue", owner: "tanguy", appId: "9", pageId: "page-1",
      timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
    }),
  );
});
```

Note: `dateFilterConfig` (already defined in this file, `interactions: "auto"` with a `dateRangeFilter` widget on `page-1`) is the config to use — reuse it, don't redefine it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: FAIL — no such button exists yet.

- [ ] **Step 3: Implement the button + dialog in `AppRuntimePage.tsx`**

Add imports:

```typescript
import { useState } from "react";
import { useAuth } from "../auth/useAuth";
import { useCreateBookmark } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";
```

(merge the `useState` import into the existing `useEffect, useMemo, useRef, useState` import on line 10 if `useState` isn't already there — it is: line 10 already imports `useState`. Only add the new named imports listed above.)

Add local state to retain the latest analytics context (currently only captured in the debounce-timer closure) and the save-dialog state, inside the component body, right after the `handleAnalyticsContextChange` function:

```typescript
  const [currentAnalyticsContext, setCurrentAnalyticsContext] = useState<AnalyticsContextState>(initialAnalyticsContext);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [viewTitle, setViewTitle] = useState("");
  const { username } = useAuth();
  const createBookmark = useCreateBookmark();

  function handleAnalyticsContextChangeAndTrack(state: AnalyticsContextState) {
    setCurrentAnalyticsContext(state);
    handleAnalyticsContextChange(state);
  }

  async function saveView() {
    const title = viewTitle.trim();
    if (!title) return;
    try {
      await createBookmark.mutateAsync({
        title, owner: username ?? "",
        appId: pk, pageId: pageId ?? query.data?.pages?.[0]?.id ?? "",
        ...currentAnalyticsContext,
      });
      setSaveDialogOpen(false);
      setViewTitle("");
      createBookmark.reset();
    } catch {
      // surfaced via createBookmark.isError
    }
  }
```

Replace the `onAnalyticsContextChange={handleAnalyticsContextChange}` prop on `<AppRenderer>` with `onAnalyticsContextChange={handleAnalyticsContextChangeAndTrack}`.

Replace the render body (the current bare `<div className="h-full w-full">…</div>`) with a toolbar wrapper:

```typescript
  return (
    <div className="flex h-full w-full flex-col">
      {query.data.interactions === "auto" && (
        <div className="flex justify-end border-b border-slate-200 p-2">
          <Button size="sm" variant="outline" onClick={() => setSaveDialogOpen(true)}>
            Enregistrer la vue
          </Button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <AppRenderer
          config={query.data}
          mode="runtime"
          pageId={pageId}
          onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
          initialAnalyticsContext={initialAnalyticsContext}
          onAnalyticsContextChange={handleAnalyticsContextChangeAndTrack}
        />
      </div>
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} title="Enregistrer la vue">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Nom de la vue
            <Input aria-label="Nom de la vue" value={viewTitle} onChange={(e) => setViewTitle(e.target.value)} />
          </label>
          {createBookmark.isError && (
            <p role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setSaveDialogOpen(false)}>
              Annuler
            </Button>
            <Button type="button" size="sm" disabled={createBookmark.isPending || !viewTitle.trim()} onClick={saveView}>
              Enregistrer
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS (all tests in the file, including the 5 pre-existing ones — `handleAnalyticsContextChangeAndTrack` calls the original `handleAnalyticsContextChange` unchanged, so the debounced-URL-write behavior is untouched)

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green.

- [ ] **Step 6: Run the shell build (type-check)**

Run: `cd shell && npm run build`
Expected: succeeds — `tsc --noEmit` catches any type mismatch between `CreateBookmarkInput` and the `mutateAsync` call shape.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "feat(shell): enregistrer la vue button on AppRuntimePage (SP-14m)"
```

---

## Task 7: E2E — save, list, and reopen a bookmark

**Files:**
- Create: `shell/e2e/bookmarks.spec.ts`

**Interfaces:**
- Consumes: `mockCore(page)` (`shell/e2e/mocks.ts`), the same per-test `page.route(...)` override convention as `shell/e2e/datasets-shared.spec.ts` and `shell/e2e/analytics-context.spec.ts`.

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/bookmarks.spec.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-14m — enregistrer le contexte analytique courant comme une vue nommée,
// la retrouver dans "Mes vues", la rouvrir restaure exactement le même
// contexte ; une vue non partagée reste invisible pour un autre utilisateur.
test("save a view with a cross-filter and a time range, find it in Mes vues, reopen restores the context", async ({ page }) => {
  await mockCore(page);

  let bookmarkCreated = false;
  let bookmarkConfigBody: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          { id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" },
        ],
      },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01" } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01" } },
    ];
    const features = gte && lte ? all.filter((f) => f.properties.date >= gte && f.properties.date <= lte) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, timeField: "date" } },
      },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  // App "9" : builder crée un dataset partagé, un widget de plage de dates lié
  // à son timeField, et active interactions="auto".
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    if (body?.config?.kind === "bookmark") {
      bookmarkCreated = true;
      bookmarkConfigBody = body.config;
      await route.fulfill({ status: 201, json: { id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" } });
      return;
    }
    return route.fallback();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Dashboard analytique");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("events");
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).click();
  await expect(page.getByText("Dataset partagé actif")).toBeVisible();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();

  await page.getByRole("button", { name: "Ajouter un widget" }).click();
  await page.getByRole("button", { name: /Plage de dates/ }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 1. Ouvrir le runtime, poser une plage temporelle.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-12-31");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();

  // 2. Enregistrer la vue.
  await page.getByRole("button", { name: "Enregistrer la vue" }).click();
  await page.getByLabel("Nom de la vue").fill("Récents 2026");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => bookmarkCreated).toBe(true);
  expect(bookmarkConfigBody).toMatchObject({
    kind: "bookmark",
    bookmark: { appId: "9", pageId: expect.any(String), timeRange: { from: "2026-01-01", to: "2026-12-31" } },
  });

  // 3. La vue apparaît dans /bookmarks.
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          { pk: "bookmark-1", resourceType: "bookmark", title: "Récents 2026", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-bookmark", isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      },
    });
  });
  await page.route("https://core.test/configs/by-item/bookmark-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-bookmark", itemId: "bookmark-1", kind: "bookmark",
        config: { version: 1, kind: "bookmark", bookmark: bookmarkConfigBody.bookmark },
      },
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  // 4. L'ouvrir restaure exactement le même contexte.
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/.*\?ctx=/);
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
});

test("a non-shared view is invisible to a second user of the same tenant", async ({ page }) => {
  await mockCore(page);

  // "mockuser" (the fixture's authenticated identity, per mocks.ts) owns the
  // bookmark; scope=mine already returns [] for every non-owned fixture item
  // (see mocks.ts's "**/items*" comment) — reused here unmodified to prove a
  // bookmark obeys the exact same generic sharing default as any other kind.
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark" || url.searchParams.get("scope") !== "mine") {
      return route.fallback();
    }
    await route.fulfill({ json: { items: [], total: 0, page: 1, pageSize: 12 } });
  });

  await page.goto("/bookmarks");
  await page.getByLabel("Portée").selectOption("mine");
  await expect(page.getByText("Aucun élément.")).toBeVisible();
});
```

- [ ] **Step 2: Run the new spec to verify it fails**

Run: `cd shell && npx playwright test bookmarks.spec.ts`
Expected: FAIL at the "Enregistrer la vue" button click (button doesn't exist without Task 6) if run before Tasks 4-6 land; once all prior tasks are committed, run again — it should FAIL only on any typo/route-mismatch, not on missing features.

- [ ] **Step 3: Fix any mock/route mismatches found, then run to green**

Run: `cd shell && npx playwright test bookmarks.spec.ts`
Expected: PASS (2 tests)

- [ ] **Step 4: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: all 18+ existing specs plus `bookmarks.spec.ts` green, `VITE_AUTH_MODE=mock`.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/bookmarks.spec.ts
git commit -m "test(e2e): save, list and reopen a bookmark view (SP-14m)"
```

---

## Final check

- [ ] **Run the complete core + shell test matrix one more time**

```bash
cd core && uv run pytest -q
cd ../shell && npm run test && npm run build && npm run e2e
```

Expected: all green — core baseline (606 executed + 87 skipped) plus ~17 new core tests; shell baseline (398 tests) plus ~10 new unit tests; E2E baseline (18 specs) plus 1 new spec (2 tests).

- [ ] **Update `CLAUDE.md`'s "Fait" list**

Add a line under SP-14l in the roadmap section once this branch is merged, following the existing style (one bullet per delivered sub-part, French, with the concrete artifact named) — leave this to the finishing-a-development-branch workflow, not a plan step to execute now.
