# Task 4 report — `mcp_loopback.py` + `tools_allowlist.py`

## What was implemented

- `core/app/copilot/tools_allowlist.py` — `ALLOWED_MCP_TOOL_NAMES` frozenset
  (6 tools: `search_catalog`, `list_items`, `explain_dataset`,
  `run_analytics_query`, `create_item`, `create_form_app`), verbatim from the
  brief. Verified all 6 are real `@server.tool()`-registered functions in
  `core/app/mcp/tools.py`.
- `core/app/copilot/mcp_loopback.py` — `McpLoopbackSession`
  (`list_tools()`, `call_tool(name, arguments)`, `aclose()`),
  `McpLoopbackError`, `ToolCallResult`, verbatim from the brief, with two
  fixes (see Deviations): re-exports `ALLOWED_MCP_TOOL_NAMES` from
  `tools_allowlist`, and a corrected comment about what actually triggers a
  JSON-RPC `"error"` field vs. a tool-level `isError` result.
- `core/tests/test_copilot_mcp_loopback.py` — 5 tests (brief specified 4;
  see Deviations for why a 5th was added) driving the real `/mcp` endpoint
  via `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`, no mocks.

## TDD evidence

### RED

```
cd core && uv run pytest tests/test_copilot_mcp_loopback.py -v
```
```
ERROR collecting tests/test_copilot_mcp_loopback.py
E   ModuleNotFoundError: No module named 'app.copilot.mcp_loopback'
=========================== short test summary info ============================
ERROR tests/test_copilot_mcp_loopback.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.16s ===============================
```
Failed for the expected reason (module doesn't exist yet).

### GREEN

```
cd core && uv run pytest tests/test_copilot_mcp_loopback.py -v
```
```
collected 5 items

tests/test_copilot_mcp_loopback.py::test_list_tools_returns_full_catalog PASSED [ 20%]
tests/test_copilot_mcp_loopback.py::test_call_tool_returns_text_result PASSED [ 40%]
tests/test_copilot_mcp_loopback.py::test_call_tool_surfaces_tool_execution_error_without_raising PASSED [ 60%]
tests/test_copilot_mcp_loopback.py::test_call_tool_surfaces_unknown_tool_name_as_tool_error PASSED [ 80%]
tests/test_copilot_mcp_loopback.py::test_call_tool_raises_on_genuine_protocol_level_failure PASSED [100%]

============================== 5 passed in 2.59s ===============================
```

Also re-ran the surrounding MCP/copilot suites for regressions — all pass
(17/17): `test_mcp_routes.py`, `test_mcp_auth.py`, `test_copilot_llm_provider.py`,
`test_copilot_enabled_flag.py`.

Also ran `uv run lint-imports`: "layered architecture KEPT — 1 kept, 0 broken"
(app.copilot doesn't import anything that would violate the layer contract;
it's a pure HTTP client with no dependency on other app.* internals).

## Deviations from the brief (and why)

The brief's Step 1 test file and Step 3 `mcp_loopback.py` code are given
verbatim, but three things in the brief didn't match the real system. All
three were resolved by testing against the real `/mcp` endpoint rather than
guessing, per the task's "ask before proceeding rather than guessing"
instruction interpreted as "resolve by empirical substitution when possible,
escalate only if unresolvable" (the brief itself pre-authorizes exactly this
kind of substitution for the `get_item` test).

1. **`asyncio_mode` / `pytest.mark.asyncio` doesn't apply to this repo.**
   `pytest-asyncio` is not a dependency at all — `pyproject.toml`'s
   `[tool.pytest.ini_options]` has no `asyncio_mode` key, and there's no
   `asyncio` marker registered. The repo's actual convention (confirmed in
   `tests/test_mcp_auth.py`, `tests/test_jobs_observability.py`) is the
   `anyio` pytest plugin: `@pytest.mark.anyio` plus a per-file
   `anyio_backend` fixture returning `"asyncio"`. I used that convention
   instead of `@pytest.mark.asyncio` / `asyncio_mode = "auto"` — did **not**
   touch `pyproject.toml`, since the setting the brief worried about isn't
   applicable here (`anyio`'s plugin is auto-active via `pytest-anyio`
   dependency of `httpx`/`anyio`, no ini config needed).

2. **`base_url="http://test"` is rejected by DNS-rebinding host-header
   protection.** FastMCP auto-enables `TransportSecuritySettings` with
   `allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"]` whenever its
   `host` constructor arg (default `"127.0.0.1"`, never overridden in
   `create_mcp_server`) is a loopback value — which it always is here. A
   client presenting `Host: test` gets a genuine `421 Misdirected Request`
   before the handshake even starts. Changed both the `CORE_BASE_URL` env
   var and the `httpx.AsyncClient(base_url=...)` in every test from
   `http://test` to `http://localhost:8200` (matching the already-working
   pattern in `test_mcp_routes.py`). This is orthogonal to `CORE_BASE_URL`'s
   own value — the allowlist is fixed to loopback hostnames regardless.

3. **An unknown tool name is *not* a JSON-RPC protocol-level error in this
   MCP SDK version.** The brief's 4th test
   (`test_call_tool_raises_on_unknown_tool_name`) assumed
   `session.call_tool("not_a_real_tool", {})` would produce a top-level
   JSON-RPC `"error"` field, causing `McpLoopbackError` to be raised.
   Empirically (confirmed with a standalone repro script hitting the real
   `/mcp` endpoint), the server instead returns `200 OK` with
   `{"result": {"content": [...], "isError": true}}` — the exact same shape
   as a tool that raises internally (e.g. `get_item` on a bad id). So
   `call_tool`'s existing logic (as given in the brief, unchanged) correctly
   does **not** raise for this case — the brief's test expectation, not the
   implementation, was wrong.
   - Renamed/rewrote that test to
     `test_call_tool_surfaces_unknown_tool_name_as_tool_error`, asserting
     `result.is_error is True` instead of `pytest.raises`.
   - Since that removed the only exercised path proving `McpLoopbackError`
     really gets raised for a *genuine* protocol failure, I added a 5th
     test, `test_call_tool_raises_on_genuine_protocol_level_failure`, using
     the real DNS-rebinding 421 from finding #2 above as the trigger (an
     `httpx.AsyncClient` pointed at `http://unrecognized-host`). This keeps
     the interface contract ("raises only on protocol failure, never on
     tool-level errors") actually covered by a real, reproducible case
     instead of an imagined one.
   - Corrected the misleading inline comment in `mcp_loopback.py`'s
     `call_tool` (previously listed "nom d'outil inconnu" as an example of
     a protocol-level error — it isn't) to reflect this.

4. **`ALLOWED_MCP_TOOL_NAMES` re-export.** The brief's own test file (given
   verbatim in Step 1) imports `ALLOWED_MCP_TOOL_NAMES` from
   `app.copilot.mcp_loopback`, but Step 3's `mcp_loopback.py` code doesn't
   import it from `tools_allowlist.py` — an internal inconsistency in the
   brief. Added `from app.copilot.tools_allowlist import
   ALLOWED_MCP_TOOL_NAMES` plus an `__all__` to `mcp_loopback.py` so both
   import paths work, matching what the brief's own test expects.

No changes were needed to `get_item`/Step 4's documented fallback — `get_item`
on a nonexistent id really does raise via `_require_access`
(`core/app/mcp/tools.py:69-79`, `raise ValueError("item not found")`), which
the MCP SDK turns into `isError=true`, exactly as the brief predicted for the
happy case.

## Files changed

- `core/app/copilot/mcp_loopback.py` (new)
- `core/app/copilot/tools_allowlist.py` (new)
- `core/tests/test_copilot_mcp_loopback.py` (new)

Commit: `308e97d` — `feat(core): client de rappel MCP + allowlist d'outils
pour le copilote (SP-20)` (exact message from the brief).

## Self-review findings

- Confirmed via `uv run lint-imports` that `app.copilot` doesn't break the
  layered-architecture import-linter contract.
- Confirmed the 6 allowlisted tool names are all real, currently-registered
  MCP tools (not just plausible-sounding names) by grepping
  `core/app/mcp/tools.py`.
- Confirmed no regression in the 4 directly-related existing test files
  (17/17 pass) plus the new file (5/5 pass).
- `McpLoopbackSession.__init__` raises `KeyError` if `CORE_BASE_URL` is unset
  and no `http_client` is injected — this is deliberate (brief's own code,
  unchanged), consistent with this repo's "fail fast on missing required
  env var" convention (e.g. `CORE_SECRETS_MASTER_KEY`). Flagging only for
  Task 5's awareness: whatever constructs `McpLoopbackSession` in
  `routes.py` must ensure `CORE_BASE_URL` is set in every deployment path
  (it already is per `app/main.py`'s own default-handling, so this should be
  a non-issue in practice).

## Issues or concerns

None blocking. The three empirical corrections above (asyncio/anyio
convention, Host-header allowlist, unknown-tool-name behavior) are the kind
of thing that would have caused Task 5's `routes.py` to be built against a
false mental model of `call_tool`'s failure modes if left uncorrected — worth
a quick read by whoever picks up Task 5, since it consumes exactly this
`McpLoopbackSession`/`McpLoopbackError`/`ToolCallResult` interface.
