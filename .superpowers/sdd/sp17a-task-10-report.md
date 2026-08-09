# Task 10 Report — mode `exportRender` (chrome d'impression + signal de disponibilité)

## Status: DONE

## What was implemented

1. `shell/src/shell/useIsExportRender.ts` — `useIsExportRender(): boolean`, reads
   `useSearchParams().get("exportRender") === "1"` (exact-literal match, not
   truthy-ish).
2. `shell/src/shell/exportReady.ts` — `markExportReady(): void`, sets
   `document.body.dataset.exportReady = "true"`. Idempotent by construction
   (property assignment, not append).
3. `MapView.tsx` — new `onReady?: () => void` prop, wired via a stable ref
   pattern (matching `onViewChange`/`onFeatureClick`) and called from
   `map.once("idle", () => onReadyRef.current?.())` inside the existing
   `"load"` handler. Also added `hideLegend?: boolean` (see "Deviation/bug
   found" below).
4. `MapEditorPage.tsx` — `isExportRender` early-return renders a nude chrome:
   `<MapView config={draft} onReady={markExportReady} hideLegend />` plus
   absolutely-positioned overlays for `printLayout.title` /`showLegend`/
   `cartouche`. Placed after the loading/error guards, before the normal
   aside+MapView layout.
5. `AppRuntimePage.tsx` — `isExportRender` computed via the hook; an effect
   calls `markExportReady()` (via `requestAnimationFrame`) once
   `query.isSuccess` — "config request succeeded + one paint frame" is the
   best real signal available for non-map apps in SP-17a's scope (no
   per-widget instrumentation). The "Enregistrer la vue" action bar is now
   guarded by `!isExportRender`.

## Deviation from the plan's literal code (bug found and fixed)

The plan's Step 9 code (and the brief verbatim) renders `MapView` unconditionally
inside the exportRender branch, and separately renders a `showLegend`-gated
`<ul>` at `absolute bottom-2 left-2` in `MapEditorPage.tsx`. But `MapView`
*already* unconditionally renders its own `<MapLegend layers={config.layers} />`
at that exact same position, regardless of `printLayout.showLegend`. Consequence
if implemented literally:
- `showLegend: false` would never actually hide the legend from a capture — the
  always-on `MapLegend` inside `MapView` would still render.
- `showLegend: true` would render the legend twice, stacked at the identical
  position.

Fix: added `hideLegend?: boolean` to `MapView` (suppresses its built-in
`MapLegend` when true) and pass `hideLegend` unconditionally in the export
branch, so the export overlay's `showLegend`-gated list is the *only* legend
source during a capture. Covered by a new MapView test
(`"hideLegend suppresses the built-in MapLegend"`). This does not affect
`MapView`'s behavior anywhere else (prop defaults to falsy, i.e. today's
behavior everywhere else — normal editor, map widget, etc.).

## Known limitation (as directed by the brief, not silently dropped)

`showScaleBar`/`showNorthArrow` from `PrintLayoutConfig` are **not** rendered
visually in this task. The checkboxes remain in `PrintLayoutPanel` for schema
shape (accepted by design), but the actual rendering (MapLibre `ScaleControl` /
positioned north-arrow icon) is a non-blocking future refinement.

## TDD evidence

- `useIsExportRender.test.ts`: written first with `React.createElement` instead
  of JSX (the brief's snippet used JSX syntax in a `.test.ts` file, which
  esbuild refuses to parse in a plain `.ts` file — confirmed via a real
  transform error before switching to `createElement`). RED confirmed
  (`Failed to resolve import "./useIsExportRender"`), then GREEN after
  implementing the hook. Added a third case (`exportRender=true` → `false`) to
  pin the exact-`"1"` contract.
- `exportReady.test.ts` (new, not explicitly named in the brief's file list but
  required by the task's own self-review instructions): asserts
  `document.body.getAttribute("data-export-ready") === "true"` and
  `document.body.dataset.exportReady === "true"`, plus a call-twice-doesn't-throw
  idempotency test. GREEN.
- `MapView.test.tsx`: added 3 new tests (`calls onReady once the map fires
  'idle'`, `does not call onReady before 'idle' fires`, `only calls onReady
  once even if 'idle' fires again`) plus the `hideLegend` test. RED confirmed
  first (`onReady` prop existed nowhere, assertions failed with 0 calls — a
  real "unimplemented feature" failure, not a crash). Required adding a
  `once(event, cb)` method to `MockMaplibreMap.ts` (the mock previously only
  had `on`/`fire`); `fire()` was changed to iterate a snapshot of the handler
  array since `once` handlers mutate it mid-iteration. GREEN after
  implementing `MapView`'s `onReady` wiring.
- `MapEditorPage.test.tsx` / `AppRuntimePage.test.tsx`: added end-to-end tests
  for the exportRender nude-chrome path (chrome hidden, printLayout overlays
  present, `data-export-ready` set). `MapEditorPage.test.tsx` previously
  rendered the page with **no Router context at all**; `useIsExportRender`
  needs one (`useSearchParams`), so I wrapped `renderEditor`'s render tree in
  `<MemoryRouter>` — this matches how the page is always rendered in
  production (`shell/src/shell/routes.tsx` mounts it under `<Routes>`), and
  was necessary for the existing 4 tests to keep passing (confirmed via a RED
  run: `useLocation() may be used only in the context of a <Router> component`
  on all 4 pre-existing tests before the fix).

## Files changed

- `shell/src/shell/exportReady.ts` (new)
- `shell/src/shell/exportReady.test.ts` (new)
- `shell/src/shell/useIsExportRender.ts` (new)
- `shell/src/shell/useIsExportRender.test.ts` (new)
- `shell/src/map/MapView.tsx` (`onReady`, `hideLegend` props)
- `shell/src/map/MapView.test.tsx` (+4 tests)
- `shell/src/pages/MapEditorPage.tsx` (exportRender nude chrome)
- `shell/src/pages/MapEditorPage.test.tsx` (+`MemoryRouter` wrapper, +1 test)
- `shell/src/pages/AppRuntimePage.tsx` (exportRender: hide action bar, mark ready)
- `shell/src/pages/AppRuntimePage.test.tsx` (+1 test)
- `shell/src/test/MockMaplibreMap.ts` (added `once()`, made `fire()` snapshot-safe)

## Self-review — exact DOM contract verification

Checked byte-for-byte against Task 6's already-shipped worker code
(`core/app/export/jobs.py`):
- `jobs.py:56`: `page.wait_for_selector('[data-export-ready="true"]', timeout=30_000, state="attached")`
  — `exportReady.ts` sets exactly `document.body.dataset.exportReady = "true"`,
  which produces the HTML attribute `data-export-ready="true"` on `<body>`.
  Verified in a test via `document.body.getAttribute("data-export-ready")`
  (not just "didn't throw").
- `jobs.py:105`: `...?exportToken={token}&exportRender=1` — `useIsExportRender()`
  checks `params.get("exportRender") === "1"`, exact literal match.
- Idempotency: `markExportReady()` called twice does not throw and leaves the
  attribute at `"true"` (test: `"is idempotent: calling it twice..."`).

## Full suite + build results

- `npm run test`: **127 files / 1023 tests passed**, 0 failed.
- `npm run build` (`tsc --noEmit && vite build`): clean, no new errors. Only
  pre-existing chunk-size warnings unrelated to this change.

## Concerns

- None blocking. The `hideLegend` addition to `MapView` is a small deviation
  from the plan's literal Step 9 code but fixes a real correctness bug (see
  above) rather than expanding scope.
- `AppRuntimePage`'s "ready" signal (config success + one `requestAnimationFrame`)
  is intentionally weaker than the map case, per the brief's own framing —
  documented here and in an inline code comment, not silently accepted as
  equivalent.

## Fix round 1 — Critical from code review (AppLayout chrome leaking into export capture)

### The finding

`MapEditorPage.tsx`'s exportRender early-return only controls what
`MapEditorPage` itself renders. `/maps/:pk` is nested inside `ProtectedLayout`
(`shell/src/shell/routes.tsx`), which wraps every child in `RequireAuth` +
`AppLayout`. `AppLayout.tsx` rendered its `<header>` (GeoStudio branding,
`NewItemButton`, `ImportFileButton`, username, "Déconnexion") and `<nav>`
sidebar (Catalogue/admin/SQL Lab links) **unconditionally**, regardless of
`exportRender`. Net effect: every exported map PNG/PDF would have shown the
app's navigation chrome and a "Déconnexion" button around the map. Invisible
in existing tests because `MapEditorPage.test.tsx` renders `MapEditorPage`
directly under a bare `MemoryRouter`, never through `AppLayout`/
`ProtectedLayout` — the integration gap between the two components was never
exercised.

By contrast `AppRuntimePage`'s route sits **outside** `ProtectedLayout`
entirely, so its own nude-chrome guard was already sufficient on its own —
this defect was specific to the map export path.

### What changed

Approach 1 from the brief, confirmed correct after checking `RequireAuth.tsx`:
Task 12 (exportToken bypass in `RequireAuth`) is not yet implemented, but is
specced to live inside `RequireAuth`, which stays in the tree in
`ProtectedLayout` regardless of this fix — only `AppLayout`'s own header/nav
markup needed to be skipped, not the auth gate around it.

`shell/src/shell/AppLayout.tsx`: `AppLayout` now calls `useIsExportRender()`
and, when true, returns `<>{children}</>` directly — no header, no nav, no
read-only demo banner. `RequireAuth` in `ProtectedLayout` is untouched and
still runs before `AppLayout` mounts, so Task 12's future `exportToken`
bypass work is unaffected: it will still be implemented inside
`RequireAuth`, upstream of this new early return.

Also closed (Minor, cheap): `MapEditorPage.test.tsx` and
`AppRuntimePage.test.tsx` now have an `afterEach` that deletes
`document.body.dataset.exportReady`, matching `exportReady.test.ts`'s existing
pattern — removes the latent test-order hazard the reviewer flagged (both
files render real components that call `markExportReady()`, which mutates
global `document.body` state with nothing to reset it between tests before
this fix).

### Regression test

Added to `shell/src/shell/routes.test.tsx` (real integration harness: renders
the actual `AppRoutes` tree, i.e. `ProtectedLayout` → `AppLayout`, with
`MapEditorPage` mocked to a plain `<div>` — the point is exercising
`AppLayout`'s own chrome-suppression, not `MapEditorPage`'s content):

- `"exportRender=1 on a protected map route hides AppLayout's header/nav
  chrome (Task 10 fix round 1)"` — navigates to `/maps/77?exportRender=1`,
  asserts `"GeoStudio"`, the "Déconnexion" button, and the "Catalogue" nav
  link are all absent, while the mocked page content (`"map-editor-77"`) is
  present.
- `"without exportRender, the same map route still renders AppLayout's
  header/nav chrome normally"` — same route without the query param, asserts
  all three chrome elements ARE present (guards against a fix that hides
  chrome unconditionally).

**RED before fix** (`git stash` on `AppLayout.tsx` only, ran
`npx vitest run src/shell/routes.test.tsx -t "exportRender=1 on a protected
map route"`):

```
 FAIL  src/shell/routes.test.tsx > exportRender=1 on a protected map route hides AppLayout's header/nav chrome (Task 10 fix round 1)
Error: expect(element).not.toBeInTheDocument()

expected document not to contain element, found <span
  class="text-lg font-bold"
>
  GeoStudio
</span> instead
 ❯ src/shell/routes.test.tsx:169:47
```

**GREEN after fix** (`npx vitest run src/shell/routes.test.tsx
src/shell/AppLayout.test.tsx src/pages/MapEditorPage.test.tsx
src/pages/AppRuntimePage.test.tsx`):

```
 ✓ src/shell/AppLayout.test.tsx (7 tests) 310ms
 ✓ src/pages/MapEditorPage.test.tsx (5 tests) 339ms
 ✓ src/pages/AppRuntimePage.test.tsx (11 tests) 576ms
 ✓ src/shell/routes.test.tsx (12 tests) 498ms

 Test Files  4 passed (4)
      Tests  35 passed (35)
```

### Full suite + build (round 1)

- `npx vitest run`: **127 files / 1025 tests passed**, 0 failed (was 1023
  before this round; +2 new tests, no regressions).
- `npx tsc --noEmit`: clean.
- `npx vite build`: succeeds. Only the same pre-existing chunk-size warnings
  (unrelated to this change, present before round 1 too).

### Concerns

- None blocking. Verified the fix does not interfere with Task 12: `RequireAuth`
  remains inside `ProtectedLayout`, above `AppLayout`, and is completely
  untouched by this change — its future `exportToken` bypass logic will run
  exactly where it was always specced to, before `AppLayout`'s new early
  return is ever reached.
- Commit: `e4fa46a` — `fix(shell): SP-17a — exportRender : masquer le chrome
  AppLayout pour l'export de carte`.
