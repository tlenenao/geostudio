# Task 10 report — Shell : thread `theme` through both the editor and the render path

## What I found in the 7 real files before editing

- `shell/src/builder/registry.ts` — matched the brief's assumed shape almost
  verbatim: `WidgetContext` (mode/navigate/pages/variables/data/bus/widgetId/
  user/breakpoint) and `WidgetDefinition.PropsPanel` (props/onChange/
  dataSources) with no `theme` field yet.
- `shell/src/builder/PropsPanel.tsx` — the wrapper matched the brief exactly:
  destructures `item`/`dataSources`/`onChange`/`onVisibleWhenChange`, renders
  `<Panel props={item.props} dataSources={dataSources} onChange={...} />`.
- `shell/src/builder/WidgetHost.tsx` — matched the brief: destructures
  `item`/`mode`/`pages`/`navigate`/`breakpoint`, builds `ctx` inline in the
  `<Widget ctx={{ mode, data, bus, widgetId, pages, navigate, variables,
  user, breakpoint }} />` JSX.
- `shell/src/builder/AppRenderer.tsx` — the one `<WidgetHost>` call site is
  at line 210 (as the brief predicted, "around line 210"), inside
  `GridCanvas`'s `renderItem`, passing `item`/`mode`/`pages`/`navigate`/
  `breakpoint`. `config.theme` is available in scope (used a few lines above
  for `themeToCssVars(config.theme)`).
- `shell/src/pages/AppBuilderPage.tsx` — the one `<PropsPanel>` call site
  (line 441) passes `item={selected}`/`dataSources={draft.dataSources}`/
  `onChange`/`onVisibleWhenChange`. `draft.theme` already exists and is used
  elsewhere in the file (`ThemePanel theme={draft.theme}`).
- `PropsPanel.test.tsx` / `WidgetHost.test.tsx` — both matched the brief's
  assumptions about existing imports/helpers (`registerWidget`/
  `_resetRegistry` from `./registry`, a `wrapper` providing
  `QueryClientProvider`+`ItemClientProvider` for `PropsPanel.test.tsx`, an
  `item()` helper + `vi.mock("../auth/useAuth")` for `WidgetHost.test.tsx`).

No divergence from the brief's assumed signatures — proceeded without
escalating.

Also verified: `Theme`/`ThemeColors` types already exist in
`shell/src/api/types.ts` (lines 624-635), and `AppConfig.theme: Theme` is
non-optional (line 642), so `config.theme` at the `AppRenderer` call site is
always a valid `Theme` value.

## What I implemented

### Path 1 — Editor time (`AppBuilderPage.tsx` → `PropsPanel` → `def.PropsPanel`)

- `registry.ts`: `WidgetDefinition["PropsPanel"]` gains `theme?: Theme`.
- `PropsPanel.tsx`: wrapper gains `theme?: Theme` prop, forwards it to
  `<Panel theme={theme} ... />`.
- `AppBuilderPage.tsx`: its one `<PropsPanel>` call site now passes
  `theme={draft.theme}`.

### Path 2 — Render time (`AppRenderer.tsx` → `WidgetHost` → `WidgetContext.theme` → `def.Component`)

- `registry.ts`: `WidgetContext` gains `theme?: Theme`.
- `WidgetHost.tsx`: gains `theme?: Theme` prop, forwards it into the `ctx`
  object passed to `def.Component`.
- `AppRenderer.tsx`: its one `<WidgetHost>` call site now passes
  `theme={config.theme}`.

### Deliberate scope limit (verified, not touched)

`tabs.tsx`, `drawer.tsx`, `modal.tsx`, `LayoutEditor.tsx` were **not**
modified — `git diff --stat` on those four files after the whole task shows
no changes.

## TDD evidence

### Path 1 (editor) — RED

Added the test from the brief to `PropsPanel.test.tsx` (plus importing
`registerWidget` alongside the already-imported `_resetRegistry`).

```
$ npx vitest run src/builder/PropsPanel.test.tsx -t "theme through"
 × passes theme through to the widget's PropsPanel 35ms
   → expected [ undefined ] to deeply equal [ { colors: { primary: '#2563eb' } } ]
 Test Files  1 failed (1)
      Tests  1 failed | 5 skipped (6)
```

### Path 1 (editor) — GREEN

After implementing registry.ts / PropsPanel.tsx / AppBuilderPage.tsx:

```
$ npx vitest run src/builder/PropsPanel.test.tsx
 ✓ src/builder/PropsPanel.test.tsx (6 tests) 195ms
 Test Files  1 passed (1)
      Tests  6 passed (6)
```

### Path 2 (render) — RED

Added the test from the brief to `WidgetHost.test.tsx`.

```
$ npx vitest run src/builder/WidgetHost.test.tsx -t "theme through to the widget's Component"
 × passes theme through to the widget's Component via ctx 23ms
   → expected [ undefined ] to deeply equal [ { colors: { primary: '#2563eb' } } ]
 Test Files  1 failed (1)
      Tests  1 failed | 12 skipped (13)
```

### Path 2 (render) — GREEN

After implementing registry.ts / WidgetHost.tsx / AppRenderer.tsx:

```
$ npx vitest run src/builder/WidgetHost.test.tsx
 ✓ src/builder/WidgetHost.test.tsx (13 tests) 70ms
 Test Files  1 passed (1)
      Tests  13 passed (13)
```

## Scope-limit grep check

```
$ grep -rn "<WidgetHost" src/ --include="*.tsx" | grep -v test
src/builder/AppRenderer.tsx:210:                      <WidgetHost      ← theme threaded
src/builder/widgets/modal.tsx:79:                <WidgetHost           ← untouched
src/builder/LayoutEditor.tsx:69:          renderItem={(item) => <WidgetHost item={item} mode="edit" />}   ← untouched
src/builder/widgets/drawer.tsx:106:                  <WidgetHost       ← untouched
src/builder/widgets/tabs.tsx:171:                <WidgetHost           ← untouched

$ grep -rn "<PropsPanel" src/ --include="*.tsx" | grep -v test
src/builder/LayoutEditor.tsx:72:      <PropsPanel                      ← untouched
src/pages/AppBuilderPage.tsx:441:              <PropsPanel             ← theme threaded

$ git diff --stat -- src/builder/widgets/modal.tsx src/builder/widgets/drawer.tsx src/builder/widgets/tabs.tsx src/builder/LayoutEditor.tsx
(no output — zero diff, confirmed untouched)
```

Confirmed: only the two named top-level call sites (`AppRenderer.tsx`'s
`<WidgetHost>`, `AppBuilderPage.tsx`'s `<PropsPanel>`) got `theme` threaded.

## Full shell-gates output

- `npm run lint` → clean (`eslint .`, no output/errors).
- `npm run format:check` → `All matched files use Prettier code style!`
- `npx vitest run` (full suite) →
  - 1st run: **1 flaky failure**, unrelated to this task:
    `src/pages/MapEditorPage.test.tsx > exportRender=1 renders a nude
    chrome...` (`TypeError: Cannot read properties of undefined (reading
    'fire')`). Verified pre-existing / order-dependent, not a regression:
    (a) passes in isolation both before (`git stash`) and after my changes;
    (b) a 2nd full-suite run passed cleanly.
  - 2nd run (full suite): **161 files passed (161), 1423 tests passed
    (1423)** — matches the reference count of 161 files / 1421 tests + the
    2 new tests this task adds (1 in `PropsPanel.test.tsx`, 1 in
    `WidgetHost.test.tsx`) = 1423. No regression.
- `npm run build` → green (`tsc --noEmit && vite build` succeeded, 4204
  modules transformed; only pre-existing chunk-size warnings, unrelated).

## Files changed

- `shell/src/builder/registry.ts`
- `shell/src/builder/PropsPanel.tsx`
- `shell/src/builder/PropsPanel.test.tsx`
- `shell/src/builder/WidgetHost.tsx`
- `shell/src/builder/WidgetHost.test.tsx`
- `shell/src/builder/AppRenderer.tsx`
- `shell/src/pages/AppBuilderPage.tsx`

Exactly the 7 files the brief lists — confirmed via `git status --porcelain`
on those paths before commit, and nothing else was staged.

## Deviations from the brief

None. Implementation matches the brief's code snippets verbatim (down to
the exact JSX prop ordering in `WidgetHost`'s `ctx` object and
`AppRenderer`'s `<WidgetHost>` call). The only addition beyond the brief's
literal test snippet was wrapping the new `PropsPanel.test.tsx` test in the
file's existing `{ wrapper }` (providing `QueryClientProvider` +
`ItemClientProvider`), matching the convention every other test in that
file already uses — harmless since the probe widget doesn't need it, but
keeps the test consistent with its neighbors.

## Self-review findings

- **Completeness**: both paths threaded and independently proven RED→GREEN.
- **Quality**: matches existing prop-threading conventions exactly (same
  destructuring style, same optional-prop pattern as `breakpoint`).
- **Discipline**: scope limit verified by grep + `git diff --stat` showing
  zero changes to `tabs.tsx`/`drawer.tsx`/`modal.tsx`/`LayoutEditor.tsx`.
- **Testing**: RED genuinely observed for both paths (ran the exact `-t`
  filtered commands from the brief before implementing), GREEN confirmed
  after. No regression: full suite test count matches reference + 2 new
  tests. The one failure seen on the first full-suite run was verified as a
  pre-existing flake unrelated to this task (passes in isolation on both
  sides of my diff, and a repeat full run was clean).

## Concerns

None blocking. Note for whoever runs the full suite next: the
`MapEditorPage.test.tsx > exportRender=1 ...` test appears to be flaky
under full-suite ordering (unrelated to `theme`/builder files) — worth a
look if it recurs, but out of this task's scope (not in the 7-file list,
and untouched by this diff).
