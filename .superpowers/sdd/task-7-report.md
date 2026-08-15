# Task 7 report — export entry becomes mode-aware at load

## What I implemented

Replaced the full contents of `shell/src/staticExport/entry.tsx` exactly as specified in the
task brief (`.superpowers/sdd/task-7-brief.md`, Step 1). The pre-existing file matched the
brief's assumed "before" state exactly (verified by reading it first).

Summary of the change:
- New `loadConnection()`: fetches `./geostudio-connection.json`; returns `null` on a non-OK
  response (404 in Statique bundles, which never include this file — Task 2/3), otherwise
  parses and returns `{ coreUrl: string }`.
- New `buildClient(config, connection)`: if `connection` is present, builds a live client via
  `createItemClient({ coreUrl: connection.coreUrl, getToken: () => undefined })` (Connecté
  mode); otherwise falls back to `createStaticItemClient(config)` (Statique mode, unchanged
  behavior).
- `bootstrap()` now always fetches `geostudio-app-config.json` first (unchanged), then calls
  `loadConnection()` and `buildClient()` to pick the client before rendering.
- `enableMockAuth()` remains an unconditional top-level call, executed before `bootstrap()`
  runs, in both modes — untouched by this change.
- Updated header comment to describe both modes and explicitly document the getToken pitfall
  (per the brief's text).
- Added imports: `createItemClient` from `../api/itemClient`, and the `ItemClient` type from
  `../api/types` (alongside the existing `AppConfig` import).

## Build/typecheck output

1. `cd shell && npm run build:export-runtime` (i.e. `vite build --config vite.export.config.ts`):
   **PASS** — built `dist-export/` successfully (3913 modules transformed, no errors; only the
   pre-existing "chunk larger than 500kB" advisory warnings, unrelated to this change).

2. Note: `build:export-runtime` itself is just `vite build --config vite.export.config.ts` — it
   does **not** run `tsc --noEmit` (unlike the plain `npm run build` script, which is
   `tsc --noEmit && vite build`). Vite's esbuild-based transform strips types but does not fully
   type-check across files. To satisfy the task's requirement to confirm the file "typechecks
   cleanly," I additionally ran `npx tsc --noEmit` directly in `shell/`: **PASS**, no output, no
   errors.

## Files changed

- `shell/src/staticExport/entry.tsx` (modified, 33 insertions / 9 deletions)

## Self-review findings

Explicitly re-read the committed diff (`git diff` before commit) line by line against the
security constraint from the task instructions:

- Confirmed `getToken: () => undefined` is a **literal hardcoded closure** on the line that
  constructs the Connecté-mode client — not a reference to `useAuth().getAccessToken` or any
  other token-returning function.
- Confirmed `useAuth`/`getAccessToken` do not appear anywhere else in the file — the only
  import from `../auth/useAuth` is `enableMockAuth`, unchanged from before.
- Confirmed `enableMockAuth()` is still called unconditionally at module top level (before
  `bootstrap()` is even invoked), independent of which mode is later detected at fetch time —
  so `AppRenderer`'s `useAuth()` call (via `ActionConditionBridge`) never throws in either mode.
- Confirmed the diff is otherwise an exact transcription of the brief's given code (compared
  brief block against committed file content).

## Concerns

None. One minor observation (not a defect, just noting it for the record): the task brief
describes `build:export-runtime` as running "both builds `dist-export/` and runs TS checking as
part of the Vite build for this entry" — in practice this script does not invoke `tsc`
separately, and Vite's esbuild transform does not perform full cross-file type checking. I ran
`npx tsc --noEmit` explicitly to close that gap; it passed cleanly.
