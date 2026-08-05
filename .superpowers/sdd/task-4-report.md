# Task 4 report — Shell: types, itemClient, hooks (SP-14m bookmarks)

## What I implemented

Followed the brief literally, mirroring the existing `createDatasetItem`/`getDatasetConfig`/`useCreateDataset` pattern.

1. `shell/src/api/types.ts`
   - Extended `ResourceType` with `"bookmark"`.
   - Added `BookmarkCrossFilterValue`, `BookmarkCrossFilterEntry`, `BookmarkPayload` (byte-for-byte mirror of `AnalyticsContextState`'s `timeRange`/`extent`/`crossFilter`, plus `appId`/`pageId`), and `CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload`, placed right after `CreateDatasetInput`.
   - Added `createBookmarkItem(input: CreateBookmarkInput): Promise<Item>` and `getBookmarkConfig(pk: string): Promise<BookmarkPayload>` to the `ItemClient` interface, right after `createDatasetItem`.

2. `shell/src/api/itemClient.ts`
   - Added `BookmarkPayload, CreateBookmarkInput` to the type import.
   - Implemented `createBookmarkItem` (POSTs `{ version: 1, kind: "bookmark", bookmark }` to `/configs`, returns an `Item` with `resourceType: "bookmark"`) and `getBookmarkConfig` (GETs `/configs/by-item/{pk}`, throws if `config.bookmark` is missing), inserted between `createDatasetItem` and `getDatasetConfig`.

3. `shell/src/api/hooks.ts`
   - Added `CreateBookmarkInput` to the type import.
   - Added `useCreateBookmark()` mutation hook (calls `client.createBookmarkItem`, invalidates `["items"]` on success), inserted right after `useCreateDataset`.

## What I tested

- `shell/src/api/itemClient.test.ts`: appended 3 tests right after the existing "getDatasetConfig throws when the config has no dataset payload" test (same style/harness as the dataset tests — `makeClient()` / `server.use(...)`):
  - `createBookmarkItem posts a bookmark payload and returns a bookmark Item`
  - `getBookmarkConfig reads the bookmark payload from the by-item config`
  - `getBookmarkConfig throws when the config has no bookmark payload`
- `shell/src/api/hooks.test.tsx`: added `useCreateBookmark` to the `./hooks` import, appended `useCreateBookmark creates a bookmark and invalidates items` right after the `useCreateMap` test, using the file's `makeWrapper(client)` helper (same pattern as `useCreateMap`'s test).

## TDD Evidence

### RED

Command: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx`

Result (before implementing the types/itemClient/hooks changes): 4 failed, 117 passed.

```
FAIL  src/api/hooks.test.tsx > useCreateBookmark creates a bookmark and invalidates items
TypeError: (0 , useCreateBookmark) is not a function

FAIL  src/api/itemClient.test.ts > createBookmarkItem posts a bookmark payload and returns a bookmark Item
TypeError: makeClient(...).createBookmarkItem is not a function

FAIL  src/api/itemClient.test.ts > getBookmarkConfig reads the bookmark payload from the by-item config
TypeError: makeClient(...).getBookmarkConfig is not a function

FAIL  src/api/itemClient.test.ts > getBookmarkConfig throws when the config has no bookmark payload
TypeError: makeClient(...).getBookmarkConfig is not a function
```

This is the expected failure: the new client methods/hook don't exist yet.

### GREEN

Command: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx`

Result after implementation: `Test Files 2 passed (2)`, `Tests 121 passed (121)`.

Full suite: `cd shell && npm run test` → `Test Files 110 passed (110)`, `Tests 844 passed (844)` — no regressions.

Typecheck/build: `cd shell && npm run build` (runs `tsc --noEmit && vite build`) → succeeded, no type errors.

## Files changed

- `shell/src/api/types.ts`
- `shell/src/api/itemClient.ts`
- `shell/src/api/hooks.ts`
- `shell/src/api/itemClient.test.ts`
- `shell/src/api/hooks.test.tsx`

Commit: `4677132` — `feat(shell): bookmark item client + hook (SP-14m)`

## Self-review

- Completeness: all brief steps (1–10) done, including the full suite run and typecheck.
- Quality: code placed consistently alongside the `createDatasetItem`/`getDatasetConfig`/`useCreateDataset` pattern; same naming/style conventions (error messages `"createBookmarkItem: core returned no itemId"`, `"getBookmarkConfig: config has no bookmark payload"`, matching the dataset equivalents).
- Discipline (YAGNI): nothing beyond the brief was added — no client-side translation helpers between `AnalyticsContextState` and `BookmarkPayload` (deliberately out of scope per the brief; Tasks 5/6 will build that).
- Testing: TDD followed (RED confirmed via `TypeError: ... is not a function`, then GREEN); tests exercise real behavior through the MSW-backed `createItemClient` / a real `useMutation` hook, not mocks-of-mocks (the hook test mocks only the `ItemClient` surface, per the existing `useCreateMap` pattern already in this file).

No issues found; no deviations from the brief. Note: this file previously held a stale report from an unrelated task (SP-14l) — overwritten with this task's report.

## Post-review fix (commit e1cc4d6)

Task review flagged one Important finding on commit `4677132`: `BookmarkPayload.crossFilter` in `shell/src/api/types.ts` was typed `Record<string, BookmarkCrossFilterEntry>`, but `AnalyticsContextState.crossFilter` (`shell/src/builder/AnalyticsContext.tsx:10`) is typed `Record<string, CrossFilterEntry | undefined>` — the `| undefined` was missing on the bookmark side, breaking the brief's explicit "byte-for-byte mirror" requirement (Task 5/6 would fail to typecheck when assigning `analyticsContext.crossFilter` into a bookmark payload). Verified the mismatch directly by reading both files — real, not a false positive.

### Fix applied

In `shell/src/api/types.ts`:
- Widened `BookmarkPayload.crossFilter` to `Record<string, BookmarkCrossFilterEntry | undefined>`.
- Added the documented-echo comment above `BookmarkCrossFilterValue`/`BookmarkCrossFilterEntry`/`BookmarkPayload`, matching the `WcWidgetManifest` echo convention already used lower in the file:
  ```
  // Écho documenté de AnalyticsContextState (shell/src/builder/AnalyticsContext.tsx)
  // — même forme, dupliquée ici plutôt qu'importée : api/ ne dépend jamais de
  // builder/. Si AnalyticsContextState change de forme, répercuter le
  // changement ici aussi.
  ```

### Verification after the fix

- `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx` → `Test Files 2 passed (2)`, `Tests 121 passed (121)` (no test literals needed updating — the change only widens a type, no runtime behavior changes).
- `cd shell && npm run build` (`tsc --noEmit && vite build`) → succeeded, no type errors.
- `cd shell && npm run test` (full suite) → `Test Files 110 passed (110)`, `Tests 844 passed (844)` — no regressions.

### Files changed

- `shell/src/api/types.ts`

Commit: `e1cc4d6` — `fix(shell): widen BookmarkPayload.crossFilter to match AnalyticsContextState`
