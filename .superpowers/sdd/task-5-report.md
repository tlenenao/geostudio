# Task 5 report — Shell: `CatalogPage` reuse (`/bookmarks`) + bookmark-aware open navigation

## What I implemented

1. **`shell/src/pages/CatalogPage.tsx`** — added an optional `fixedType?: ResourceType` prop.
   - `type` state now initializes to `fixedType ?? ""`.
   - The "Type" selector `<label>` is now wrapped in `{!fixedType && (...)}`, hiding it entirely
     when `fixedType` is set, while the underlying `useItems` query still filters on `type` (via
     the state initializer), so the list is locked to that type without an escape hatch in the UI.
   - `onOpenItem`'s contract is unchanged.

2. **`shell/src/shell/routes.tsx`**:
   - Added imports: `useItemClient` (`../api/ItemClientProvider`), `encodeAnalyticsContext`
     (`../lib/analyticsContextUrl`), `type { ResourceType }` (`../api/types`).
   - Extracted the old inline open-navigation ternary out of `CatalogRoute` into a new shared
     `useOpenItem()` hook, placed right after the imports (before `CatalogRoute`). Its non-bookmark
     branch (`navigate(type === "map" ? ... : ...)`) is byte-identical to the code it replaced.
   - Added a `bookmark`-specific branch: fetches `client.getBookmarkConfig(pk)`, encodes
     `{ timeRange, extent, crossFilter }` via `encodeAnalyticsContext`, and navigates to
     `/apps/{appId}/{pageId}?ctx={ctx}` (URL-encoding `appId`/`pageId`) instead of an editor route.
   - `CatalogRoute` now just calls `useOpenItem()` and passes it straight through.
   - Added `BookmarksRoute`, using the same `useOpenItem()` and passing `fixedType="bookmark"`.
   - Registered `<Route path="/bookmarks" element={<BookmarksRoute />} />` inside
     `ProtectedLayout`, right after `/items/:pk`.

## What I tested and results

- `shell/src/pages/CatalogPage.test.tsx`: appended "fixedType locks the type filter and hides the
  selector" (asserts the `/items` request has `type=bookmark` and the `Type` selector is absent).
- `shell/src/shell/routes.test.tsx`: appended two tests —
  - "renders the bookmarks catalog at /bookmarks, filtered to type=bookmark"
  - "opening a bookmark navigates to its app+page+ctx URL, not an editor" (mocks
    `GET /configs/by-item/bm-1` returning a bookmark config, clicks "Ouvrir", asserts the mocked
    `AppRuntimePage` renders `app-runtime-42-page-1`).

All new tests pass. Full unit suite: **110 files / 847 tests passed**. `npx tsc --noEmit`: clean,
no errors.

## TDD Evidence

**RED** — `cd shell && npx vitest run src/pages/CatalogPage.test.tsx src/shell/routes.test.tsx`
(run before implementation, only tests appended):
```
FAIL src/pages/CatalogPage.test.tsx > fixedType locks the type filter and hides the selector
  - Expected: "bookmark"
  + Received: null

FAIL src/shell/routes.test.tsx > renders the bookmarks catalog at /bookmarks, filtered to type=bookmark
  TestingLibraryElementError: Unable to find an element with the text: Ma vue.

FAIL src/shell/routes.test.tsx > opening a bookmark navigates to its app+page+ctx URL, not an editor
  TestingLibraryElementError: Unable to find role="button" and name `/ouvrir/i`

 Test Files  2 failed (2)
      Tests  3 failed | 10 passed (13)
```
Expected and matches the brief: no `fixedType` prop yet, no `/bookmarks` route yet.

**GREEN** — after implementing `CatalogPage.tsx` and `routes.tsx`:
```
$ npx vitest run src/pages/CatalogPage.test.tsx
 ✓ src/pages/CatalogPage.test.tsx (4 tests) 291ms

$ npx vitest run src/shell/routes.test.tsx
 ✓ src/shell/routes.test.tsx (9 tests) 352ms
```
The pre-existing "navigates from catalog to app builder on open (app item)" test passed unchanged
(confirmed it's part of the 9 green tests, no modification needed — the non-bookmark branch of
`useOpenItem` is byte-identical to the old inline ternary).

Full suite: `npm run test` → `Test Files 110 passed (110)`, `Tests 847 passed (847)`.

## Files changed

- `shell/src/pages/CatalogPage.tsx`
- `shell/src/shell/routes.tsx`
- `shell/src/pages/CatalogPage.test.tsx`
- `shell/src/shell/routes.test.tsx`

Commit: `04dc6a4 feat(shell): /bookmarks catalog + bookmark-aware open navigation (SP-14m)`

## Self-review findings

- Checked that `client.getBookmarkConfig` (Task 4) and `BookmarkPayload` type already existed and
  matched what the brief assumes (`shell/src/api/itemClient.ts:624-628`, hitting
  `GET /configs/by-item/{pk}`) — no drift found.
- Checked `useItemClient` export shape in `shell/src/api/ItemClientProvider.tsx` (file is `.tsx`,
  not `.ts` as the brief's file reference implied) — import path `../api/ItemClientProvider`
  resolves fine either way (no extension in the import), no issue.
- Confirmed `CatalogPage`'s `onOpenItem` external contract (`(pk, type) => void`) is unchanged —
  `useOpenItem()`'s return value is `async (pk, type) => Promise<void>`, which is call-compatible
  since callers (e.g. `ItemCard`'s `onOpen`) don't await it.
- No other call sites of `CatalogPage` or the old inline ternary in `routes.tsx` needed updates
  (verified via grep — only `CatalogRoute` used it).
- Left `.superpowers/sdd/` files (task-1..4 briefs/reports, progress.md — modified by concurrent
  parallel tasks) unstaged, per the brief's explicit `git add` file list.

## Issues or concerns

None. Implementation matches the brief exactly; no deviations were needed.

---

## Post-review fix: unhandled rejection on failed bookmark-config fetch

**Finding (code review on commit `04dc6a4`):** `useOpenItem()`'s bookmark branch called
`await client.getBookmarkConfig(pk)` with no try/catch. `ItemCard.tsx`'s only caller invokes
`onOpen(item.pk, item.resourceType)` synchronously, without `await` or `.catch()`. A rejection
(deleted config row while the item survived, transient network error) was therefore an unhandled
promise rejection: no navigation, no error surfaced, clicking "Ouvrir" silently did nothing.

**Convention check:** searched the shell for a global toast/notification system — none exists.
The established idiom for surfacing a failed async action outside a form/dialog is local
component state + a `role="alert"` paragraph styled `text-sm text-red-600` (see
`HarvestSourcesAdminPage.tsx`: `deleteSource.isError && <p role="alert" ...>Échec de la
suppression.</p>`). Matched that pattern rather than inventing a new mechanism.

**Fix:** `useOpenItem()` now wraps the bookmark fetch/navigate in try/catch, tracks a local
`openError` boolean (`useState`), and returns `{ onOpenItem, openError }`. `CatalogRoute` and
`BookmarksRoute` each render a `role="alert"` message (`Échec de l'ouverture de l'élément.` /
`Échec de l'ouverture du signet.`) when `openError` is true, alongside the unchanged `CatalogPage`.
No navigation happens on failure; the user stays on the catalog/bookmarks page with a visible error
instead of a silent no-op.

**Regression test** — appended to `shell/src/shell/routes.test.tsx`:
"a failed bookmark config fetch surfaces an error instead of silently doing nothing" — mocks
`GET https://core.test/configs/by-item/bm-1` to return a 500, clicks "Ouvrir" on the bookmarks
catalog, and asserts: a `role="alert"` appears with the expected text, the catalog item ("Ma vue")
is still shown, and no `app-runtime-*` text appears (i.e. no navigation occurred).

**TDD evidence for the fix:**

RED — temporarily removed the try/catch (kept the test as-is) and ran
`npx vitest run src/shell/routes.test.tsx -t "failed bookmark config fetch"`:
```
FAIL  src/shell/routes.test.tsx > a failed bookmark config fetch surfaces an error instead of silently doing nothing
 ❯ src/shell/routes.test.tsx:169:23
   expect(await screen.findByRole("alert")).toHaveTextContent(...)
   (timed out waiting for the alert — it never appears without the catch)

⎯⎯⎯⎯ Unhandled Rejection ⎯⎯⎯⎯⎯
Error: Request failed: 500 GET /configs/by-item/bm-1
 ❯ request src/api/itemClient.ts:191:13
 ❯ Object.getBookmarkConfig src/api/itemClient.ts:625:20
 ❯ onOpenItem src/shell/routes.tsx:41:24

 Test Files  1 failed (1)
      Tests  1 failed | 9 skipped (10)
```
This reproduces exactly the unhandled-promise-rejection failure mode the review flagged.

GREEN — restored the try/catch, reran the full file:
```
$ npx vitest run src/shell/routes.test.tsx src/pages/CatalogPage.test.tsx
 ✓ src/pages/CatalogPage.test.tsx (4 tests) 301ms
 ✓ src/shell/routes.test.tsx (10 tests) 422ms

 Test Files  2 passed (2)
      Tests  14 passed (14)
```

**Full suite + build after the fix:**
```
$ npm run test
 Test Files  110 passed (110)
      Tests  848 passed (848)

$ npm run build
> tsc --noEmit && vite build
✓ 2720 modules transformed.
✓ built in 11.48s
```
(Chunk-size warnings in the build output are pre-existing and unrelated to this change.)

**Files changed (fix):**
- `shell/src/shell/routes.tsx`
- `shell/src/shell/routes.test.tsx`

**Commit:** `29929aa fix(shell): surface a failed bookmark-config fetch instead of silently doing nothing`

**Concerns:** none. The fix is scoped to `useOpenItem()` and its two callers; `ItemDetailPage`'s
separate `onOpenEditor` navigation (which never routes bookmarks — bookmarks have no editor) was
left untouched as out of scope for this finding.
