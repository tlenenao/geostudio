# Task 14 Report: `ItemClient` — révisions et rollback

## What I implemented

- `shell/src/api/types.ts`: new exported type
  `ConfigRevisionInfo = { version: number; createdAt: string }`, and two new
  methods on the `ItemClient` interface, placed next to `saveMapConfig` (the
  nearest generic "config" methods, since these two aren't specific to any
  one resource kind):
  ```ts
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
  ```
- `shell/src/api/itemClient.ts` (`CoreItemClient`, inside `createItemClient`):
  both methods resolve the item's `configId` via `GET /configs/by-item/{pk}`
  (same pattern as ten existing call sites), then:
  - `listConfigRevisions`: `GET /configs/{id}/revisions`, mapping
    `created_at` → `createdAt`.
  - `rollbackConfig`: `POST /configs/{id}/rollback` with `{ version }`.
  Added `ConfigRevisionInfo` to the `./types` import list.
- `shell/src/staticExport/StaticItemClient.ts`: both methods added to the
  "reste de l'interface" block, each calling the existing `unsupported()`
  helper (rejects with `"Non disponible dans un export statique (aucun
  backend)."`, which matches the `/export statique/` test assertion).

No other `ItemClient` implementation existed in the codebase — `npm run
build` (`tsc --noEmit`) passed clean on the first try after the two
implementations were added, meaning no test mocks or other structural
implementers were missing the two new methods.

## What I tested and results

- `cd shell && npx vitest run src/api/itemClient.test.ts
  src/staticExport/StaticItemClient.test.ts` — 153 passed (0 failed).
- `cd shell && npm run build` — `tsc --noEmit && vite build` both green.

## TDD Evidence

### RED

Command:
```
cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/StaticItemClient.test.ts
```

Output (relevant excerpt):
```
 × listConfigRevisions résout la config par item puis lit ses révisions 3ms
   → client.listConfigRevisions is not a function
 × rollbackConfig poste la version demandée sur la config résolue 2ms
   → client.rollbackConfig is not a function
 × rollbackConfig propage l'erreur quand le serveur refuse la version 1ms
   → client.rollbackConfig is not a function
 ...
 FAIL  src/staticExport/StaticItemClient.test.ts > StaticItemClient > les révisions ne sont pas disponibles hors ligne
 TypeError: client.listConfigRevisions is not a function

 Test Files  2 failed (2)
      Tests  4 failed | 149 passed (153)
```
Why expected: the two methods didn't exist yet on either `ItemClient`
implementation — `not a function` is the correct failure mode before adding
the interface methods and their implementations.

### GREEN

Command:
```
cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/
```

Output (relevant excerpt):
```
 ✓ src/api/itemClient.test.ts (148 tests) 1115ms

 Test Files  2 passed (2)
      Tests  153 passed (153)
```

Note: two stderr lines about `GET https://core.test/harvest/layers` being an
unhandled MSW request appear during this run, in *pre-existing* tests
(`listLayerSources still returns one service when the other fails`,
`listLayerSources passes q to /collections and filters Martin sources
client-side`) that are unrelated to this task and unmodified by it — not new
warnings introduced by this change.

`npm run build`:
```
> tsc --noEmit && vite build
...
✓ built in 30.46s
```

## Files changed

- `shell/src/api/types.ts` — `ConfigRevisionInfo` type + two `ItemClient`
  interface methods.
- `shell/src/api/itemClient.ts` — `ConfigRevisionInfo` import + two method
  implementations on `CoreItemClient`.
- `shell/src/api/itemClient.test.ts` — 3 new tests.
- `shell/src/staticExport/StaticItemClient.ts` — two method implementations
  rejecting via `unsupported()`.
- `shell/src/staticExport/StaticItemClient.test.ts` — 1 new test (two
  assertions).

Commit: `3be2064` — `feat(shell): expose les révisions de config et le
rollback sur ItemClient`

## Self-review findings

- Both methods implemented on both `CoreItemClient` and `StaticItemClient` —
  confirmed.
- `StaticItemClient`'s rejection message contains "export statique" — the
  shared `UNSUPPORTED` constant string is `"Non disponible dans un export
  statique (aucun backend)."`, matches the test's `/export statique/` regex —
  confirmed.
- `ConfigRevisionInfo` exported from `shell/src/api/types.ts`, imported in
  `shell/src/api/itemClient.ts` — confirmed.
- Test output pristine for the new tests; the two pre-existing MSW stderr
  warnings in unrelated tests are not new.
- No overbuilding: exactly the two methods + one type from the brief, no
  extra abstractions.
- `npm run build` revealed no other `ItemClient`-implementing object needing
  the new methods (this was the brief's Step 6 contingency, but it did not
  trigger — the build passed on the first run after implementation).

## Issues or concerns

- None. Unrelated pre-existing modifications to
  `.superpowers/sdd/task-13-brief.md`, `.superpowers/sdd/task-13-report.md`,
  and `.superpowers/sdd/task-14-brief.md` were present in the working tree at
  session start (task-ID reuse from a different, unrelated plan/session) and
  were deliberately left unstaged/uncommitted — only the five files named in
  the brief's Step 7 were staged and committed.
