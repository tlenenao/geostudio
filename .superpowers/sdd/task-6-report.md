# Task 6 Report: E2E — explorer menu and drill panel (SP-14d)

## What was implemented

Appended 2 new Playwright scenarios to `shell/e2e/analytics-context.spec.ts` (after
the last existing scenario, "interactions manual: no indicator, select/slider never
cross-filter"), exercising the real running app end-to-end against the ⋮ Explorer
feature built in Tasks 1-5:

1. **`voir les entités shows cross-filtered rows, even opened from the widget that
   set the filter`** — builds an app with a chart (source 1) and table (source 2)
   sharing a dataset, cross-filters by clicking the "Nord" bar, then:
   - opens the drawer from the table's `⋮ Explorer` menu (a widget different from
     the one that set the filter) → drawer's table shows only "Nord".
   - closes via the "Fermer le panneau" (×) button.
   - opens the drawer again, this time from the chart's own `⋮ Explorer` menu (the
     widget that originated the click) → drawer's table still shows only "Nord",
     proving the drawer's synthetic `"__explorer__"` source id is never excluded by
     cross-filter self-exclusion the way a real widget's own id would be.
   - closes via `Escape` and confirms the underlying app/cross-filter is untouched.

2. **`the explorer menu never appears when interactions is manual`** — an app with
   `interactions: "manual"` (unchecked "Interactions automatiques (cross-filter)")
   never renders any `⋮ Explorer` button, confirming the gating
   (`mode !== "edit" && config.interactions === "auto"`) from Task 5.

## Selector adjustments made and why

The brief's literal test code (copied near-verbatim) had one selector-ambiguity bug,
not a product bug:

- `page.getByRole("cell", { name: "Nord" })` was ambiguous once the drawer was open,
  because the underlying Table widget (bound to the same cross-filtered dataset) also
  renders a `<td>Nord</td>` cell — both the drawer's table and the app's own Table
  widget show "Nord" only, at the same time. Playwright's strict mode correctly
  rejected the 2-element match with a "strict mode violation" error.
- Fix: scoped the two ambiguous assertion pairs to
  `const drawerTable = page.locator("table").first();`. `ExplorerDrawer` is mounted
  in `AppRenderer` (`shell/src/builder/AppRenderer.tsx:185`) *before*
  `DataProvider`/`GridCanvas` in JSX, so its `<table>` is always the first `<table>`
  node in the DOM while the drawer is open — structurally distinct from any widget's
  own table. No product code was touched; only the test's locator scoping changed.

No other adjustments were needed: `getByRole("button", { name: "Explorer" })`,
`"Voir les entités"`, and `"Fermer le panneau"` matched the `aria-label`s in
`shell/src/builder/widgets/ExplorerMenu.tsx` and `shell/src/builder/ExplorerDrawer.tsx`
exactly as written in the brief.

## What was tested and results

- Targeted run: `cd shell && npm run e2e -- analytics-context.spec.ts` →
  **11/11 passed** (9 pre-existing SP-14b/14c scenarios + 2 new SP-14d scenarios).
- Full E2E suite: `cd shell && npm run e2e` → **62/62 passed** (60 previously
  existing across 18 spec files + the 2 new scenarios in `analytics-context.spec.ts`).
- Full final-verification check per the plan:
  - `npm run build` → `tsc --noEmit` clean, `vite build` succeeded.
  - `npm run test` → **706/706 unit tests passed** (99 files).
  - `npm run e2e` → 62/62 passed (confirmed again as part of the combined check).

All runs pristine — no retries needed after the one locator fix, no flaky waits
introduced (reused existing `waitForRequest`/`expect(...).toBeVisible()/toBeHidden()`
patterns already established in this file).

## Files changed

- `shell/e2e/analytics-context.spec.ts` — 120 lines appended (2 new `test(...)`
  blocks), 0 lines of pre-existing scenarios modified. Confirmed via
  `git diff df409f7 HEAD -- shell/e2e/analytics-context.spec.ts`: pure addition.

No product code was changed for this task.

## Self-review findings

- **Completeness**: both new scenarios pass; full E2E suite (62 specs total) green;
  full build+unit+e2e check green.
- **Quality**: French UI copy respected throughout (`getByRole("button", { name:
  "Enregistrer" })`, `"Voir les entités"`, `"Fermer le panneau"`, `"Explorer"`,
  `"Interactions automatiques (cross-filter)"`) matching existing file conventions;
  no arbitrary `waitForTimeout` added; the one adjusted locator
  (`page.locator("table").first()`) is justified by actual DOM structure (JSX mount
  order in `AppRenderer.tsx`), not a hack around a flaky test.
- **Discipline**: `git show --stat HEAD` confirms only `shell/e2e/analytics-context.spec.ts`
  changed, 120 insertions / 0 deletions — no pre-existing test in the file was
  modified, no product code touched.

## Issues or concerns

None. The one selector fix was exactly the kind of adjustment the brief anticipated
("adjust the locator... `.first()`/`.last()` ordering doesn't match actual DOM
order") — not a product bug. All 5 prior tasks' feature code worked as designed on
first real end-to-end exercise, including the specific `"__explorer__"` synthetic-id
behavior that was the whole point of scenario 1 (the drawer never excludes itself
from the cross-filter the way a real widget would).
