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

