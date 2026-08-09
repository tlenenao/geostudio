# Task 19 Report — E2E `report-schedule.spec.ts`

## What was implemented

Created `shell/e2e/report-schedule.spec.ts` exactly as specified in the task
brief's Step 1 code block, with no adjustments needed. Before writing it, I
verified the following against the actual source, per the brief's own
warning:

- **`shell/e2e/mocks.ts`**: `mockCore` registers a generic `**/items*`
  handler (line 56) and a generic `**/configs/by-item/**` handler (line 149)
  early in the function. Because Playwright matches routes in
  most-recently-registered-first order, and the spec's own `**/items*` /
  `**/configs/by-item/report-1` overrides are registered *after*
  `await mockCore(page)` returns, the spec's overrides correctly win — this
  is the exact same pattern already used by `bookmarks.spec.ts` (its own
  `**/items*` override for the bookmark list, registered after `mockCore`).
  No route-order adjustment was needed.
- **`shell/src/shell/ItemActions.tsx`**: confirmed the "Actions" button has
  `aria-label="Actions"` and that a bookmark-typed item shows a "Programmer
  un rapport" button that navigates to `/reports/new` with
  `state: { bookmarkItemId: item.pk }` — matches the spec's click sequence.
- **`shell/src/shell/routes.tsx`**: confirmed `/bookmarks` renders
  `<CatalogPage fixedType="bookmark" />` and `/reports/new` reads
  `location.state.bookmarkItemId` into `ReportEditPage`.
- **`shell/src/api/itemClient.ts`**: confirmed `createReportScheduleItem`
  POSTs to `/configs` with `{ title, config: { version, kind: "report",
  report } }` (matches the mock's `body?.config?.kind === "report"` check)
  and returns `pk: String(data.itemId)` — so the mocked `itemId: "report-1"`
  correctly drives the post-create redirect to `/reports/report-1/edit`.
  `getReportScheduleConfig`/`saveReportScheduleConfig` hit
  `/configs/by-item/{pk}` with no extra query params, so the plain
  `**/configs/by-item/report-1` route (no `**/` id-splitting needed) is
  sufficient.
- **`shell/src/builder/report/ReportScheduleEditor.tsx`**: confirmed the
  "URL du webhook" label exists for the webhook channel.
- **`shell/src/builder/report/ReportRunPanel.tsx`**: confirmed
  `STATUS_LABEL.done === "Terminé"` and that a run with `resultUrl` renders
  an `<a>` with text "Télécharger" and `href={run.resultUrl}` — matches the
  spec's final assertions. Also noted this panel polls
  `GET /reports/{id}/runs` on a 1500ms loop (no button trigger), consistent
  with the mock being a static `route.fulfill` (repeated polls just get the
  same fixture back, harmless).
- Cross-checked `alert-rule.spec.ts` and `bookmarks.spec.ts` as siblings —
  both confirm the same `**/configs` POST-body-kind-branching mock idiom and
  the same "register override after `mockCore(page)`" convention.

No adjustments to the brief's illustrative code were necessary — it matched
the actual shell implementation and established E2E conventions exactly.

## Testing

1. New spec alone:
   `cd shell && VITE_AUTH_MODE=mock npx playwright test report-schedule.spec.ts`
   → **1 passed** (849ms), clean run, no retries.

2. Full E2E suite: `cd shell && npm run e2e`
   → **96 passed** (1.2m), 0 failed, 0 flaked/retried. The new spec is one
   test among 56 spec files (this codebase groups many scenarios per file
   via multiple `test(...)` blocks, so the total test count is 96, not one
   per file — the brief's "18 previous + 1 = 19" referred to spec *files*;
   file count check: `ls shell/e2e/*.spec.ts | wc -l` → 56 files including
   the new one, consistent with growth since the brief was written across
   SP-12 through SP-17). No regressions to any pre-existing spec.

## Files changed

- Created: `/home/lenen/projets/geostudio/shell/e2e/report-schedule.spec.ts`

## Self-review

- **Create flow exercised**: yes — the spec asserts `createdReportConfig`
  is non-null and matches the expected `POST /configs` body shape
  (`kind: "report"`, `bookmarkItemId: "bookmark-1"`, webhook channel).
- **Run-history display exercised**: yes — asserts "Terminé" status text
  and a "Télécharger" link with the exact `resultUrl` href, sourced from
  the mocked `GET /reports/report-1/runs`.
- **Route-matching order verified**: yes, both by reading `mocks.ts`'s
  registration order and by the spec actually passing (if the generic
  `mockCore` handlers had won, the bookmark row / created report config /
  run list would never have appeared and every assertion below the
  `page.goto("/bookmarks")` line would have failed).
- **Full suite**: 96/96 passing, no regressions.
- **Output cleanliness**: single worker run and full 8-worker run both
  produced no retries, no flakes, no stray console-error output in the
  reporter for this spec.

No issues or concerns found.
