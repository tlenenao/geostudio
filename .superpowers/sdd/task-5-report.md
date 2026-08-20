# Task 5 report — `POST /copilot/turn` + wiring (SP-20)

## What was implemented

- `core/app/copilot/routes.py` (new): `POST /copilot/turn` — a tool-calling
  loop (`MAX_TOOL_ITERATIONS = 6`, `TURN_TIMEOUT_SECONDS = 30.0`) that:
  - builds a system message from `itemId`/`currentConfig`, appends `history`
    then the user `message`;
  - fetches the MCP tool catalog via `McpLoopbackSession.list_tools()`,
    filters it to `ALLOWED_MCP_TOOL_NAMES`, and merges it with the caller's
    `clientTools`;
  - calls `get_llm_provider().chat(messages, all_tools)` each iteration;
  - if the LLM returns no tool calls, returns `{reply, clientOps: []}`;
  - for each tool call: if the name is in `ALLOWED_MCP_TOOL_NAMES`, executes
    it via `mcp_session.call_tool()` (real loopback to `/mcp`) and appends
    the result as a `tool` message for the next LLM turn; otherwise (client
    op or hallucinated name) it is collected into `clientOps` and never
    executed server-side;
  - if any `clientOps` were collected in an iteration, returns immediately
    with `{reply: turn.text, clientOps}` (does not keep looping);
  - after `MAX_TOOL_ITERATIONS` iterations with no resolution, returns a
    French fallback message with empty `clientOps`;
  - `McpLoopbackError` from the loopback session is surfaced as `502`;
    `asyncio.TimeoutError` from the overall turn budget as `504`; the
    session is always closed in a `finally`.
  - Code transcribed exactly as given in the brief (Step 3), verified
    against Task 4's actual delivered `McpLoopbackSession`/
    `ALLOWED_MCP_TOOL_NAMES` interface (`core/app/copilot/mcp_loopback.py`,
    `core/app/copilot/tools_allowlist.py`) — no interface mismatch found,
    the brief's assumptions about Task 4 held exactly.

- `core/app/main.py` — wired exactly as the brief's Step 4 diffs:
  - import `app.copilot.routes as copilot_routes` (alphabetical, between
    `app.configs` and `app.dcat`);
  - `is_copilot_enabled` added to the `app.auth.dependency` import
    (alphabetical, after `is_appexport_enabled`);
  - `/copilot/turn` added to the `read_only_guard` middleware's exemption
    list (alongside `/mcp` and `/analytics/sql`);
  - `if is_copilot_enabled(): app.include_router(copilot_routes.router)`
    added right after the `is_terrain3d_enabled()` block.

- `core/pyproject.toml` — `app.copilot` inserted into the import-linter
  `layers` list right after `"app.mcp"` (Step 5), per the brief's
  reasoning: `app.copilot` needs only `app.auth.dependency` and
  `app.users.models`, and never imports `app.mcp` (it talks to it over a
  real HTTP loopback, invisible to import-linter).

- `core/tests/test_copilot_routes.py` (new) — 6 tests, using the brief's
  **corrected** final version of
  `test_allowlisted_mcp_tool_call_is_executed_via_loopback` (the one using
  `list_items` + a real `{"reply": "Voici tes items.", "clientOps": []}`
  assertion), not the placeholder shown mid-document in the brief.

## Deviation from the brief (test fixture only — no production code changed)

The brief's Step 1 `client` fixture sets `CORE_BASE_URL=http://test` and
lets `routes.py` construct `McpLoopbackSession(body.mcpToken)` with no
injected `http_client`. Running this literally, the 4 tests that reach
`_run_turn` (i.e. everything past auth) all failed with
`httpx.ConnectError: [Errno -3] Temporary failure in name resolution` —
`McpLoopbackSession` makes a **real** network call to `CORE_BASE_URL` when
no `http_client` is injected (this is the intended production design, per
`mcp_loopback.py`'s own module docstring: "un vrai appel réseau (HTTP), pas
une logique d'outil dupliquée"), and `http://test` doesn't resolve on any
network, sandboxed or not — this is a genuine gap in the brief's test code,
not a flag/interface issue.

Fix applied, following the exact pattern Task 4 already established in
`core/tests/test_copilot_mcp_loopback.py` (own fixture there wires
`httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200")`
into `McpLoopbackSession(..., http_client=...)`):
- Changed `CORE_BASE_URL` to `http://localhost:8200` (matches the host the
  MCP server's DNS-rebinding guard already accepts — verified against
  `test_call_tool_raises_on_genuine_protocol_level_failure`, which shows
  `http://unrecognized-host` gets rejected with 421 while
  `http://localhost:8200` is accepted elsewhere in the suite).
- In the `client` fixture, monkeypatched `app.copilot.routes.McpLoopbackSession`
  to a factory that constructs the real `McpLoopbackSession` with an
  `http_client` wired via `httpx.ASGITransport(app=app)` pointed at the same
  `app` instance the test is exercising — so the loopback call really
  executes the real `/mcp` JSON-RPC handshake and tool dispatch in-process,
  rather than doing a real network hop or being stubbed away.
- Changed the fixture to `with TestClient(app) as test_client: yield ...`
  (context manager) instead of a bare `TestClient(app)` return — per the
  precedent/comment in `tests/test_mcp_routes.py`
  ("TestClient only runs startup/shutdown when used as a context manager"),
  the MCP session manager only starts under `app`'s lifespan, which the
  loopback's ASGI-transport call depends on.
- Mock auth mode (`CORE_AUTH_MODE=mock`) ignores the actual bearer token
  value and always resolves a fixed mock identity (verified in
  `app/auth/dependency.py`/`app/mcp/auth.py`), so the literal
  `"mcpToken": "x"` used by every test body works unmodified through the
  loopback — no change needed there.

No production code (`routes.py`, `mcp_loopback.py`, `main.py`) was changed
to work around this — the fix is entirely test-fixture plumbing, consistent
with `McpLoopbackSession`'s existing `http_client` injection seam that Task
4 built specifically for testability.

## TDD evidence

RED — `cd core && uv run pytest tests/test_copilot_routes.py -v`
(before `routes.py` existed):
```
E       ModuleNotFoundError: No module named 'app.copilot.routes'
...
5 failed, 1 passed in 2.44s
```
(the 1 pass was `test_route_is_not_mounted_when_copilot_disabled`, which
correctly expects 404 and doesn't need the module to exist yet.)

GREEN — `cd core && uv run pytest tests/test_copilot_routes.py -v`
(after implementation + fixture fix):
```
tests/test_copilot_routes.py::test_route_is_not_mounted_when_copilot_disabled PASSED
tests/test_copilot_routes.py::test_rejects_unauthenticated_request PASSED
tests/test_copilot_routes.py::test_plain_text_reply_with_no_tool_calls PASSED
tests/test_copilot_routes.py::test_unallowlisted_tool_call_is_returned_as_client_op_not_executed PASSED
tests/test_copilot_routes.py::test_allowlisted_mcp_tool_call_is_executed_via_loopback PASSED
tests/test_copilot_routes.py::test_hits_max_iterations_gracefully PASSED

6 passed in 2.77s
```

Full backend suite — `cd core && uv run pytest -q`:
```
1583 passed, 153 skipped in 115.77s (0:01:55)
```

Import-linter — `cd core && uv run lint-imports`:
```
Analyzed 206 files, 648 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

## OpenAPI regen check

```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=<test key> \
  uv run python scripts/export_openapi.py openapi.json
git diff --stat openapi.json
```
No output — **empty diff**, as expected. `is_copilot_enabled()` reads
`CORE_LLM_PROVIDER` at call time and is false in this environment (unset),
so the router is never mounted during the export, same precedent as
`CORE_ETL_ENABLED`/pipelines. No `shell/` regen needed.

(Note: `uv run python scripts/export_openapi.py` alone fails with
`ModuleNotFoundError: No module named 'app'` — the script needs
`PYTHONPATH=.`, matching exactly how `.github/workflows/ci.yml`'s
`api-types-drift` job invokes it. Documented here since the brief's Step 7
command as literally written doesn't set `PYTHONPATH`.)

## Files changed (committed in 796b2fc)

- `core/app/copilot/routes.py` (new)
- `core/app/main.py`
- `core/pyproject.toml`
- `core/tests/test_copilot_routes.py` (new)

Commit: `796b2fc feat(core): POST /copilot/turn — boucle d'outils du copilote (SP-20)`

## Self-review findings

- `routes.py`, `main.py`, `pyproject.toml` diffs match the brief's Step
  3/4/5 code verbatim — re-diffed against the brief text line by line, no
  discrepancies.
- Confirmed Task 4's actual `McpLoopbackSession`/`McpLoopbackError`/
  `ALLOWED_MCP_TOOL_NAMES` interface (read directly from
  `mcp_loopback.py`/`tools_allowlist.py`) matches exactly what `routes.py`
  imports and calls — `list_tools()`, `call_tool(name, arguments) ->
  ToolCallResult(text, is_error)`, `aclose()`, constructor
  `(mcp_token, *, http_client=None)`. No adjustment to `routes.py` needed.
  The brief's own note about the bare `KeyError` on missing `CORE_BASE_URL`
  and the `isError`-not-`McpLoopbackError` semantics for unknown tools are
  both correctly accounted for by the existing `try/except McpLoopbackError`
  scoping and the allowlist-gated `call_tool` invocation in `_run_turn` —
  neither path is reachable in a way that would need a bare `except
  KeyError` or extra handling.
- Only deviation is the test fixture's loopback wiring, documented above
  and inline in the test file's own comment block for future readers.
- `git status` before staging showed several unrelated pre-existing dirty
  files (`.superpowers/sdd/progress.md`, `task-1..4-*.md`,
  `deploy/postgis/Dockerfile`, `deploy/postgis/pg_hba.conf`) — none of
  these were touched by this task and none were staged or committed; the
  commit contains exactly the 4 files listed in the brief's Step 8.

## Issues or concerns

None blocking. One thing worth flagging for the branch-level final review
(not fixed here, out of this task's scope): the brief's Step 1 test code as
literally written would not pass as-is in this environment or in CI — the
`client` fixture needed the ASGITransport/lifespan fix described above.
Worth checking whether other already-merged SP-20 tasks' briefs assumed a
similarly naive `CORE_BASE_URL=http://test` pattern anywhere else.
