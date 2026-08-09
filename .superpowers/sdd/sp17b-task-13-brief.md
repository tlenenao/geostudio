## Task 13: MCP `explain_report_schedule`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_report.py`

**Interfaces:**
- Consumes: `reports_repo.get_latest_run` (Task 7), `configs_repo`, `items_repo`, `can` (existing, already imported in `tools.py`).
- Produces: MCP tool `explain_report_schedule(reportScheduleId: str) -> dict`, registered unconditionally.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_mcp_tools_alert.py` first for this file's exact `register_tools`/fake-`Context` test-harness pattern, then mirror it:

```python
# core/tests/test_mcp_tools_report.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# Reuse this test file's own imports/fixtures for register_tools/FastMCP/
# fake Context/_resolve_actor monkeypatching — copy the exact harness from
# test_mcp_tools_alert.py (server, session_factory, fake ctx with a token)
# rather than re-deriving it here.


@pytest.mark.asyncio
async def test_explain_report_schedule_returns_bookmark_schedule_and_channels(mcp_server_and_session):  # fixture name from the copied harness
    server, session_factory, ctx = mcp_server_and_session
    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="report", title="Weekly report",
        )
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-1",
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=item.id, export_job_id="job-1")
        s.commit()
        report_id, run_id = item.id, run.id

    result = await server.call_tool("explain_report_schedule", {"reportScheduleId": report_id}, ctx=ctx)

    assert result["title"] == "Weekly report"
    assert result["bookmarkItemId"] == "bookmark-1"
    assert result["channels"] == ["webhook"]
    assert result["lastRunAt"] is not None
```

Adapt the exact call convention (`server.call_tool(...)` vs directly invoking the registered async function) to whatever `test_mcp_tools_alert.py` actually does — that file is the ground truth for this harness, do not guess its shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_tools_report.py -v`
Expected: FAIL — tool `explain_report_schedule` not found / not registered.

- [ ] **Step 3: Add the tool**

In `core/app/mcp/tools.py`, add the import next to the other domain-repository imports:
```python
from app.pipelines import repository as pipelines_repo
from app.reports import repository as reports_repo
```

Add the tool immediately after the existing `explain_alert_rule` block (right before `get_sharing`), at the same top-level indentation (unconditional — no `is_etl_enabled()`/`is_export_enabled()` gate, mirroring `explain_alert_rule`):

```python
    @server.tool()
    async def explain_report_schedule(ctx: Context, reportScheduleId: str) -> dict:
        """Describe a ReportSchedule (target bookmark, cron, channels, last
        run) without triggering it — mirrors explain_alert_rule's shape.
        Registered unconditionally (no capability flag). SP-17b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, reportScheduleId)
            if config is None or config.config.kind != "report":
                raise ValueError("report schedule not found")
            facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=reportScheduleId)
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("report schedule not found")
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=reportScheduleId)
            if item is None:
                raise ValueError("report schedule not found")
            payload = config.config.report
            assert payload is not None
            latest = reports_repo.get_latest_run(
                session, tenant_id=user.tenant_id, report_item_id=reportScheduleId,
            )
            return {
                "title": item.title,
                "bookmarkItemId": payload.bookmarkItemId,
                "refreshPolicy": payload.refreshPolicy.model_dump(),
                "channels": [c.kind for c in payload.channels],
                "lastRunAt": latest.created_at.isoformat() if latest else None,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_report.py tests/test_mcp_tools_alert.py -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/mcp/tools.py core/tests/test_mcp_tools_report.py
git commit -m "feat(core): MCP explain_report_schedule tool (SP-17b)"
```

---

