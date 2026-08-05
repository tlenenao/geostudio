# Task 4 report — SP-14l MCP analytique — full verification

## Status: DONE

The Step 3 discrepancy below (14 tools vs. the plan's stated 15) was raised as BLOCKED,
then reviewed and resolved by the controller: independently re-run and confirmed as a
documented plan miscount, not a code defect. Per the controller's decision, 14 is treated
as the correct expected total for this task, and Steps 4–5 were then completed.

## Step 1 — full core test suite

```
cd core && export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test
uv run pytest -v
```

Result: **973 passed, 0 failed, 0 skipped, in 67.93s**.

Confirmed no `test_mcp_tools_*` file was skipped. All 13 files present under `core/tests/`
ran to completion with only PASSED outcomes:

```
      4 tests/test_mcp_tools_configs.py
      5 tests/test_mcp_tools_create.py
      4 tests/test_mcp_tools_create_form_app.py
      6 tests/test_mcp_tools_dataset_create.py
      2 tests/test_mcp_tools_explain_dataset.py
      1 tests/test_mcp_tools_explain_dataset_arcgis.py
      3 tests/test_mcp_tools_extension_permissions.py
      4 tests/test_mcp_tools_items.py
      3 tests/test_mcp_tools_query_features.py
      4 tests/test_mcp_tools_run_analytics_query.py
      3 tests/test_mcp_tools_run_analytics_query_arcgis.py
      2 tests/test_mcp_tools_search.py
      6 tests/test_mcp_tools_sharing.py
```

The only occurrences of the substring "skip" in the full log are test *names* containing
the word "skip" as part of the behavior under test (e.g.
`test_compact_partition_skips_when_nothing_eligible`,
`test_package_without_id_is_skipped`), not skip outcomes — a targeted grep for
`SKIPPED`/skip-outcome markers returned zero actual skip results. Step 1 is **green**.

## Step 2 — import-linter

```
cd core && uv run lint-imports
```

Result:
```
Analyzed 124 files, 334 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

Step 2 is **green** — confirms `app.mcp`'s imports of `app.features.routes`,
`app.harvest.routes`, `app.harvest.live_query`, `app.harvest.repository`,
`app.harvest.egress`, `app.configs.dataset_validation` all sit below `app.mcp` in the
layered contract.

## Step 3 — tool registration smoke test

Ran the brief's exact script. Output:

```python
['create_dataset', 'create_form_app', 'create_item', 'explain_dataset', 'get_app_config',
 'get_item', 'get_sharing', 'list_items', 'query_features', 'run_analytics_query',
 'save_app_config', 'search_catalog', 'set_sharing', 'whoami']
```

**14 tool names**, not 15. The `assert len(names) == 15` failed with `AssertionError`.
The prior assertion `{'create_dataset', 'run_analytics_query', 'explain_dataset'} <=
set(names)` passed — all three new tools are present, correctly named, no duplicates.

### Root-cause check (read-only, no code changed)

Checked whether this is a real missing-tool bug or a miscount in the plan's expectation:

- `grep -c "@server.tool()" core/app/mcp/tools.py` → 14 decorators total (matches the 14
  names printed). `app_config_schema` at line 569 is registered as `@server.resource(...)`,
  not a tool, so it is correctly excluded from the tool count.
- `git show 90f6e16:core/app/mcp/tools.py | grep -c "@server.tool()"` → **11**, where
  `90f6e16` ("mode démo lecture seule — garde sur les 4 outils MCP d'écriture") is the last
  commit before this plan's Task 1 (`a6eaf75`, `create_dataset`) landed. So the pre-existing
  tool count going into SP-14l was **11**, not 12: `whoami, list_items, get_item,
  get_app_config, save_app_config, create_item, get_sharing, set_sharing, search_catalog,
  query_features, create_form_app`.
- 11 pre-existing + 3 new (`create_dataset`, `run_analytics_query`, `explain_dataset`) =
  **14**, exactly what `list_tools()` returns.
- Cross-checked every one of the 11 pre-existing names against the printed list: all 11
  present, none missing, none duplicated or renamed.

**Conclusion:** the code is internally consistent — Tasks 1–3 added exactly the three
tools they were supposed to add, nothing else changed, nothing was dropped. The plan brief
(`docs/superpowers/plans/2026-08-04-sp14l-mcp-analytique.md`, Step 3) asserts "12 existing"
tools going in, but the actual baseline at commit `90f6e16` (immediately before this plan's
Task 1) has 11. This looks like an arithmetic/documentation error in the plan itself
(miscounted the pre-existing tool roster), not a functional regression or a misapplied test
marker. I found no tool that should exist but doesn't.

Per the task's explicit gating instruction ("if the tool count smoke test doesn't return
exactly 15, STOP and report BLOCKED... do not attempt to fix application code yourself"),
I initially stopped here rather than unilaterally deciding 14 is "close enough" or patching
the assertion/plan myself, and reported BLOCKED to the controller.

**Resolution:** the controller independently re-ran the same smoke-test script, confirmed
the exact same result (14 tools, all three new ones present, all 11 pre-existing ones
intact, none missing/duplicated), and confirmed the root cause: the plan brief's "12
existing" was an arithmetic miscount (actual pre-existing baseline is 11). This is a
documented plan discrepancy, not a code defect. The controller directed that 14 be treated
as the correct expected total for this task, and that I proceed with Steps 4–5.

## Step 4 — CLAUDE.md roadmap update

Added the SP-14l bullet to the "### Fait" section of `CLAUDE.md`, immediately after the
`SP-13` bullet and before the "### À venir" heading, exactly per the brief's Step 4 text:

```markdown
- **SP-14l** — MCP analytique : outils `create_dataset`, `run_analytics_query`,
  `explain_dataset`, câblés sur les chemins de requête dataset déjà validés
  (SP-11b, SP-14a/k).
```

Diff (`git diff CLAUDE.md` before commit):

```diff
 - **SP-13** (a+b+c) — Portails & Sites : modèle site/slug + route publique
   `/sites/{slug}`, widgets de contenu (Hero/RichSection/Gallery), fiche dataset
   + téléchargement + template galerie. **Jalon M13**.
+- **SP-14l** — MCP analytique : outils `create_dataset`, `run_analytics_query`,
+  `explain_dataset`, câblés sur les chemins de requête dataset déjà validés
+  (SP-11b, SP-14a/k).
 
 ### À venir
```

Per the brief's guidance and the controller's confirmation, the
`- **SP-14** — Analytics UX (...). Jalon M11.` line under "### À venir" was **left
untouched** — requête visuelle (blocked on SP-15's pipeline engine, per vision doc
amendment A39) is still unshipped, so SP-14 as a whole is not complete and jalon M11 is
not reached. No other lines in CLAUDE.md were changed.

## Step 5 — commit

```
git add CLAUDE.md
git commit -m "docs: SP-14l livré — mcp analytique (create_dataset, run_analytics_query, explain_dataset)"
```

Result: commit `f8bc295`, 1 file changed (`CLAUDE.md`), 3 insertions, 0 deletions. This
commit touches only `CLAUDE.md` — no application code was changed anywhere in this task.

## Final HEAD

```
f8bc295 docs: SP-14l livré — mcp analytique (create_dataset, run_analytics_query, explain_dataset)
a1dc72a feat(core): mcp explain_dataset tool (SP-14l)
```
