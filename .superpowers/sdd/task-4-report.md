# Task 4 Report — `ExplorerDrawer` (drill panel: table + map)

## What was implemented

Wrote `shell/src/builder/ExplorerDrawer.tsx` and `shell/src/builder/ExplorerDrawer.test.tsx` exactly as given in the brief (`.superpowers/sdd/task-4-brief.md`), with **zero deviation** from the literal code — all real module signatures matched the brief's assumptions after verification:

- `derivePatch(source, ctx, datasets)` in `shell/src/lib/analyticsPatch.ts` — signature and cross-filter "don't self-filter" exclusion (`crossFilter.originSourceId !== source.id`) matched exactly. This confirms the design rationale in the brief: since the drawer's synthetic `DataSource.id` is the constant `"__explorer__"` (never a real widget id), the exclusion never triggers for the drawer, so its query always reflects the live cross-filter even when the drawer was opened from the very widget that set it.
- `useAnalyticsContext()` / `AnalyticsContextProvider` / `useSetCrossFilter()` in `shell/src/builder/AnalyticsContext.tsx` — matched.
- `useItemClient()` / `ItemClientProvider` in `shell/src/api/ItemClientProvider.tsx` — matched.
- `useExplorerTarget()` / `useCloseExplorer()` / `useOpenExplorer()` / `ExplorerProvider` in `shell/src/builder/ExplorerContext.tsx` (Task 1) — matched, including the `{ datasetId, dataSourceId }` target shape.
- Types `DataSource`, `DataRecord`, `DatasetConfig`, `MapConfig`, `ItemClient` (incl. `getDatasetConfig`, `queryDataSource`, `featuresUrl`) in `shell/src/api/types.ts` — matched exactly.
- `MapView` / `MapViewHandle` (`flyTo`, `highlight(geometry)`) in `shell/src/map/MapView.tsx` — matched exactly, including the lazy-import pattern already used elsewhere in the codebase for this component.

Cross-checked against the existing analogous consumer `shell/src/builder/DataContext.tsx`, which uses the identical `derivePatch(s, analyticsCtx, datasets)` → merge query → `client.queryDataSource(merged)` pipeline, confirming the brief's pattern is idiomatic for this codebase.

The component:
- Renders `null` when `useExplorerTarget()` is `null`.
- Builds a synthetic `DataSource` with fixed id `"__explorer__"`, `datasetId` from the target, `query: { limit: 200 }`.
- Resolves the `DatasetConfig` via `client.getDatasetConfig`, runs `derivePatch` against the live `useAnalyticsContext()`, merges the patch into the query, and fetches rows via `client.queryDataSource`.
- Renders a small `MapView` (lazy-loaded, wrapped in `Suspense`) showing a `feature` layer built from `client.featuresUrl(merged)`, plus a paginated (20/page) table with dataset-driven column labels (`dataset.columns[c]?.label ?? c`), a 200-row cap message, and row click → `mapHandle.current?.highlight(r.geometry ?? null)`.
- Closes via a "Fermer le panneau" button or Escape key, both calling `useCloseExplorer()`'s `close()` only — no analytics-context writes anywhere.

## Testing

Ran the focused test file first to confirm RED, then implemented, then confirmed GREEN, then ran the full unit suite once.

### TDD Evidence — RED

```
$ cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx
 FAIL  src/builder/ExplorerDrawer.test.tsx [ src/builder/ExplorerDrawer.test.tsx ]
Error: Failed to resolve import "./ExplorerDrawer" from "src/builder/ExplorerDrawer.test.tsx". Does the file exist?
...
 Test Files  1 failed (1)
      Tests  no tests
```

### TDD Evidence — GREEN

```
$ cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx
 ✓ src/builder/ExplorerDrawer.test.tsx (8 tests) 632ms

 Test Files  1 passed (1)
      Tests  8 passed (8)
```

All 8 scenarios pass:
1. renders nothing when no target is open
2. cross-filtered query applied even from own origin widget (proves `__explorer__` never self-excludes)
3. dataset column labels used in table headers
4. 200-row cap message shown
5. pagination (20/page, "Suivant"/"Précédent")
6. row click highlights geometry on drawer's own map, without touching analytics context
7. close via "Fermer le panneau" button
8. close via Escape key

### Typecheck

```
$ cd shell && npx tsc --noEmit
(no output — clean)
```

### Full unit suite (once, before commit)

```
$ cd shell && npm run test
 Test Files  99 passed (99)
      Tests  701 passed (701)
   Duration  37.70s
```

Zero regressions. (Some stderr output from unrelated tests — `exprBindings.test.ts`, `ActionBus.test.ts` — is expected error-path logging from those tests' own assertions, not failures.)

## Files changed

- `shell/src/builder/ExplorerDrawer.tsx` (new, 149 lines)
- `shell/src/builder/ExplorerDrawer.test.tsx` (new, 129 lines)

## Self-review

- **Never writes to analytics context**: `grep -n "setCrossFilter\|setExtent\|setTimeRange" shell/src/builder/ExplorerDrawer.tsx` returns **zero matches** (grep exit code 1). The component only calls `useAnalyticsContext()` (read) and `useCloseExplorer()` (drawer-local state), plus `mapHandle.current?.highlight(...)` (drawer's own map ref). Confirmed read-only with respect to `AnalyticsContextState`.
- **Completeness**: all 8 test scenarios pass, matching the brief's expected 8/8.
- **Discipline**: implementation written verbatim from the brief; no extra helper modules, no extra files beyond the two specified. No gold-plating.
- **Testing hygiene**: RED confirmed before implementation existed; GREEN confirmed after; full suite run once before commit, zero regressions; only the two intended files were staged for commit (`git status` checked before commit — the other unrelated modified/untracked files in the working tree were left alone).

## Commit

`2131705` — `feat(shell): ExplorerDrawer — table+map drill panel for the active analytics context (SP-14d)`
Files: `shell/src/builder/ExplorerDrawer.tsx` (new), `shell/src/builder/ExplorerDrawer.test.tsx` (new).

## Issues or concerns

None. All existing module signatures matched the brief's assumptions exactly — no adaptation was required. Note: this report file previously held stale content from an unrelated Task 4 (`sliderFilter`, SP-14c, from a different/earlier plan iteration) — it has been overwritten with this task's actual report.

---

## Fix report — code review findings (post-commit `2131705`)

Two Important findings from the task review of `ExplorerDrawer.tsx` were fixed.

### Finding 1 — missing `aria-label` / keyboard access on interactive elements

- Added `aria-label="Page précédente"` to the "Précédent" pagination button and `aria-label="Page suivante"` to the "Suivant" button (previously relied on visible text only for their accessible name).
- Made each table row keyboard-accessible: added `role="button"`, `tabIndex={0}`, `aria-label={`Voir ${String(r.properties[columns[0]] ?? r.id)}`}` (derived from the first displayed column, falling back to the row id), and an `onKeyDown` handler that calls `selectRecord(r)` on `Enter` or `" "` (space), with `e.preventDefault()` on space to avoid scrolling the page.

### Finding 2 — dataset-load/error state silently swallowed

Previously the render's loading/error/empty branches only checked `recordsQuery`. Since `recordsQuery` is `enabled` only once `merged && dataset` are both available, a disabled query with no data is not `isLoading` in TanStack Query v5 — so while `datasetQuery` was still in flight (or if `getDatasetConfig` rejected), the UI fell straight through to "Aucune entité", silently.

Fixed by combining both queries' states in the render:
- `Chargement…` now shows when `datasetQuery.isLoading || recordsQuery.isLoading`.
- `Erreur de données` now shows when `datasetQuery.isError || recordsQuery.isError` (guarded so it doesn't flash while either query is still loading).
- `Aucune entité` only renders once both queries have settled successfully with zero records.

No changes were made to the 200-row cap, 20-row pagination logic, the `"__explorer__"` synthetic source id, or the query-merge/`derivePatch` pipeline.

### Tests added (`ExplorerDrawer.test.tsx`, now 12 tests, up from 8)

- Updated the existing pagination test to look up the "Suivant" button by its new accessible name (`"Page suivante"`), since the `aria-label` now overrides the visible text as the accessible name.
- `pagination buttons have explicit aria-labels` — asserts both buttons are queryable by `"Page précédente"` / `"Page suivante"` and reflect correct disabled state.
- `rows are keyboard-accessible: labeled, focusable, and activated by Enter/Space` — finds a row via `getByRole("button", { name: "Voir Parc A" })`, confirms `tabIndex="0"`, and confirms both `Enter` and `Space` call `highlight` with the row's geometry.
- `shows the loading state while the dataset config is still in flight, not the empty state` — mocks `getDatasetConfig` with a manually-resolved promise; asserts "Chargement…" is shown and "Aucune entité" is absent while pending, then asserts "Aucune entité" appears once the promise resolves (records still empty).
- `shows the error state when the dataset config fetch rejects` — mocks `getDatasetConfig` to reject; asserts "Erreur de données" is shown and "Aucune entité" is never shown.

`renderDrawer(opts)` was extended to accept an optional `getDatasetConfig` mock override (previously hard-coded to always resolve).

### Test commands run and results

```
$ cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx
 ✓ src/builder/ExplorerDrawer.test.tsx (12 tests) 911ms
 Test Files  1 passed (1)
      Tests  12 passed (12)
```

```
$ cd shell && npm run test
 Test Files  99 passed (99)
      Tests  705 passed (705)
   Duration  36.66s
```
(The CEL parse-error stack traces in the output are expected stderr logging from `exprBindings.test.ts`'s own throw-assertions, not failures — pre-existing behavior, unrelated to this fix.)

```
$ cd shell && npx tsc --noEmit
(no output — clean)
```

### Invariant confirmation

- **No analytics-context writes**: `grep -nE "setCrossFilter|setExtent|setTimeRange" shell/src/builder/ExplorerDrawer.tsx` → zero matches. The fix only reads `datasetQuery`/`recordsQuery` state and adds DOM attributes/handlers; it introduces no new calls into `AnalyticsContextState` setters.
- **`"__explorer__"` self-exclusion untouched**: the synthetic `DataSource` construction (`{ id: "__explorer__", ... }`) and the `derivePatch(source, analyticsCtx, { [target!.datasetId]: dataset })` call are byte-identical to before this fix; the existing test covering "queries the raw dataset features with the analytics context applied, even from its own origin widget" (cross-filter self-exclusion) still passes unmodified.

### Commit

`fix(shell): ExplorerDrawer accessible pagination/rows + dataset-load state (SP-14d)` — touches `shell/src/builder/ExplorerDrawer.tsx` and `shell/src/builder/ExplorerDrawer.test.tsx` only. Pre-existing unrelated working-tree changes (`.superpowers/sdd/*` ledger/brief files from other in-progress tasks, an untracked plans doc) were left untouched and not staged.
