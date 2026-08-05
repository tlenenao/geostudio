### Task 4: Full verification

**Files:** none modified — verification only.

**Interfaces:** none (terminal task).

- [ ] **Step 1: Run the full core test suite**

Run: `cd core && uv run pytest -v`
Expected: every test PASSES or is explicitly `SKIPPED` for a documented reason (`postgis: nécessite un PostGIS réel` when `CORE_TEST_DATABASE_URL` is unset). If any of the new `test_mcp_tools_*` files show as skipped in an environment where `CORE_TEST_DATABASE_URL` **is** set, stop — that means the `postgis` marker was misapplied (a file that doesn't actually need PostGIS shouldn't carry it, or one that does isn't getting picked up) and needs fixing before this task can be marked done.

- [ ] **Step 2: Run import-linter to confirm no layering violation**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — confirms `app.mcp`'s new imports (`app.features.routes`, `app.harvest.routes`, `app.harvest.live_query`, `app.harvest.repository`, `app.harvest.egress`, `app.configs.dataset_validation`) all sit in layers below `app.mcp`, per the existing `[tool.importlinter]` contract in `core/pyproject.toml` (already verified during planning — this step is the executable confirmation).

- [ ] **Step 3: Smoke-test tool registration count**

Run:
```bash
cd core && uv run python3 -c "
from app.mcp.server import create_mcp_server
import asyncio

async def main():
    server = create_mcp_server('http://localhost:8200', lambda: None)
    tools = await server.list_tools()
    names = sorted(t.name for t in tools)
    print(names)
    assert {'create_dataset', 'run_analytics_query', 'explain_dataset'} <= set(names)
    assert len(names) == 15

asyncio.run(main())
"
```
Expected: prints a sorted list of 15 tool names including the 3 new ones (12 existing + `create_dataset` + `run_analytics_query` + `explain_dataset`), no assertion error. (`session_factory=lambda: None` is safe here — `list_tools()` only reads the registered tool metadata, it never opens a session.)

- [ ] **Step 4: Update CLAUDE.md's roadmap section**

Modify `CLAUDE.md`, in the "### À venir" section under "Feuille de route (état d'avancement)": move the SP-14l line from implied/future into the "### Fait" section, following the exact style of the SP-14k entry already there (`- **SP-14k** — ... **A22 complet...**.` pattern). Add, right after the `SP-13` bullet and before the existing `SP-14` planning note is removed:

```markdown
- **SP-14l** — MCP analytique : outils `create_dataset`, `run_analytics_query`,
  `explain_dataset`, câblés sur les chemins de requête dataset déjà validés
  (SP-11b, SP-14a/k).
```

Remove the now-stale `- **SP-14** — Analytics UX (...). Jalon M11.` line from `### À venir` only if this was the last outstanding SP-14 sub-part — check `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-14 "Contenu" against what's shipped (datasets partagés ✅ SP-14a, contexte analytique ✅ SP-14b, widgets analytiques ✅ SP-14c–j, SQL Lab ✅ SP-14i, source arcgis ✅ SP-14k, MCP ✅ SP-14l) — **requête visuelle is still missing** (blocked on SP-15, per the design doc's non-buts), so SP-14 as a whole is **not** complete yet. Leave the `### À venir` line as-is; do not mark jalon M11 reached.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: SP-14l livré — mcp analytique (create_dataset, run_analytics_query, explain_dataset)"
```

---

## Self-Review

**Spec coverage:** §2 `create_dataset` → Task 1. §3 `run_analytics_query` → Task 2. §4 `explain_dataset` → Task 3. §5 (mirroring, not extraction) → followed throughout (every helper reimplements route logic rather than importing private `_`-prefixed names; only non-underscored "factory" functions — `get_duckdb_connection_factory`, `get_analytics_base_uri`, `get_arcgis_http_client` — are called via module reference). §6 (permissions: dataset read ≠ data read, re-checked independently) → covered by `_resolve_arcgis_external_url`'s independent check + the `test_run_analytics_query_collection_unreadable_by_caller_errors`/`test_run_analytics_query_arcgis_layer_unreadable_errors` tests. §7 (no audit on reads) → `run_analytics_query`/`explain_dataset` write no audit rows, matching `aggregate_features`/`query_features`. §8 risks table → each row maps to a test or an explicit design choice already reflected in the code above.

**Placeholder scan:** no TBD/TODO; every step shows complete code; no "similar to Task N" references (Task 3's tests are fully written out despite structural similarity to Task 2's, since the exact assertions/fixtures differ).

**Type consistency:** `DatasetPayload`/`DatasetColumnMeta` used identically across Tasks 1–3 (as defined in `app.configs.schemas`, unmodified). `_resolve_dataset_payload` (Task 2) and `_resolve_arcgis_external_url` (Task 2) signatures match their Task 3 call sites exactly. `run_analytics_query`'s return shape (`{"categoryKey", "rows"}`) matches what Task 2's tests assert. `explain_dataset`'s return shape matches what Task 3's tests assert.
