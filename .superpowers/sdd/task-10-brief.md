## Task 10: Shell — thread `theme` through both the editor and the render path

**Files:**
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/PropsPanel.tsx`
- Modify: `shell/src/builder/PropsPanel.test.tsx`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/WidgetHost.test.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`

**Interfaces:**
- Produces: `WidgetDefinition["PropsPanel"]` receives an additional
  `theme?: Theme` field (editor-time); `WidgetContext` (consumed by
  `WidgetDefinition["Component"]`) also gains `theme?: Theme` (render-time —
  needed so a `"theme-primary"` palette resolves to the *same* color both in
  the editor's preview and in the actually-published widget; without this,
  `Component` would have no way to resolve `"theme-primary"` and would
  silently fall back to default colors at render, while the editor showed
  the right ones — caught during this plan's self-review, not part of the
  original spec).

**Two separate threading paths, both needed:**
1. Editor time: `AppBuilderPage.tsx` → `PropsPanel` (wrapper) → `def.PropsPanel`.
2. Render time: `AppRenderer.tsx` (the one call site that matters — it is
   "the one runtime" per `CLAUDE.md` rule 3, used for edit/preview/runtime
   modes alike) → `WidgetHost` → `WidgetContext.theme` → `def.Component`.

**Deliberate scope limit, both paths**: the four other `<WidgetHost>`/
`<PropsPanel>` call sites inside `tabs.tsx`/`drawer.tsx`/`modal.tsx` (via
`LayoutEditor.tsx`, for their own nested children) do **not** get `theme`
threaded in this task — a map widget nested inside a container widget
simply doesn't see a theme, on both the editing and the rendering side,
consistently. This is the same already-handled `themeColors: undefined`
state as a standalone map (Task 4/6/7), not a crash or a silent wrong
color — `resolvePalette("theme-primary", undefined)` returns `null`,
`MapSymbologyEditor` doesn't even offer the option, and `buildMapPaint`
falls back to its hardcoded default when no palette is provided at all.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/PropsPanel.test.tsx`:

```tsx
test("passes theme through to the widget's PropsPanel", () => {
  const receivedThemes: (unknown | undefined)[] = [];
  registerWidget({
    type: "theme-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: ({ theme }) => {
      receivedThemes.push(theme);
      return null;
    },
    Component: () => null,
  });
  render(
    <PropsPanel
      item={{ id: "1", widget: "theme-probe", x: 0, y: 0, w: 1, h: 1, props: {} }}
      dataSources={[]}
      theme={{ colors: { primary: "#2563eb" } }}
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
  );
  expect(receivedThemes).toEqual([{ colors: { primary: "#2563eb" } }]);
});
```

(`registerWidget`/`getWidget` come from `../builder/registry`, already
imported by neighboring tests in this file — check the existing imports at
the top and reuse them, don't re-add a duplicate import.)

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx -t "theme through"`
Expected: FAIL — `PropsPanel` accepts no `theme` prop (TS error) or the
widget's `PropsPanel` never receives it.

- [ ] **Step 3: Update the registry type — both `PropsPanel` and `WidgetContext`**

In `shell/src/builder/registry.ts`:

```ts
import type { DataSource, DataSourceState, Page, RenderMode, Theme } from "../api/types";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, unknown>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
  breakpoint?: Breakpoint;
  theme?: Theme;
};
```

```ts
  PropsPanel: (p: {
    props: P;
    onChange: (props: P) => void;
    dataSources: DataSource[];
    theme?: Theme;
  }) => ReactNode;
```

- [ ] **Step 4: Thread it through the `PropsPanel` wrapper**

In `shell/src/builder/PropsPanel.tsx`:

```ts
import type { DataSource, Theme, WidgetItem } from "../api/types";

export function PropsPanel({
  item,
  dataSources,
  theme,
  onChange,
  onVisibleWhenChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  theme?: Theme;
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
}) {
  ...
      <Panel props={item.props} dataSources={dataSources} theme={theme} onChange={(p) => onChange(p)} />
  ...
```

- [ ] **Step 5: Pass it from `AppBuilderPage.tsx`**

```tsx
              <PropsPanel
                item={selected}
                dataSources={draft.dataSources}
                theme={draft.theme}
                onChange={updateSelectedProps}
                onVisibleWhenChange={updateSelectedVisibleWhen}
              />
```

`LayoutEditor.tsx`'s own `<PropsPanel>` call (used by `tabs`/`drawer`/
`modal` for their nested children) is **not** changed in this task — it
keeps omitting `theme`, which is valid since the prop is optional (see
Interfaces note above).

- [ ] **Step 6: Run to verify the editor-time test passes**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx`
Expected: PASS.

- [ ] **Step 7: Thread `theme` through the render path — write the failing test first**

Add to `shell/src/builder/WidgetHost.test.tsx` (find its existing render
helper/imports and reuse them):

```tsx
test("passes theme through to the widget's Component via ctx", () => {
  const receivedThemes: (unknown | undefined)[] = [];
  registerWidget({
    type: "theme-ctx-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: ({ ctx }) => {
      receivedThemes.push(ctx.theme);
      return null;
    },
  });
  render(
    <WidgetHost
      item={{ id: "1", widget: "theme-ctx-probe", x: 0, y: 0, w: 1, h: 1, props: {} }}
      mode="runtime"
      theme={{ colors: { primary: "#2563eb" } }}
    />,
  );
  expect(receivedThemes).toEqual([{ colors: { primary: "#2563eb" } }]);
});
```

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx -t "theme through to the widget's Component"`
Expected: FAIL — `WidgetHost` accepts no `theme` prop.

- [ ] **Step 8: Implement**

In `shell/src/builder/WidgetHost.tsx`:

```tsx
import type { Page, RenderMode, Theme, WidgetItem } from "../api/types";

export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
  breakpoint,
  theme,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
  breakpoint?: Breakpoint;
  theme?: Theme;
}) {
  // ... unchanged body ...
  return (
    <WidgetErrorBoundary>
      <Widget
        props={resolvedProps}
        ctx={{
          mode,
          data,
          bus: bus ?? undefined,
          widgetId: item.id,
          pages,
          navigate,
          variables,
          user,
          breakpoint,
          theme,
        }}
      />
    </WidgetErrorBoundary>
  );
}
```

In `shell/src/builder/AppRenderer.tsx`, at its one `<WidgetHost>` call site
(around line 210 — re-read the surrounding JSX before editing, since this
plan does not reproduce it verbatim), add `theme={config.theme}` alongside
the existing props passed there. The three other call sites
(`tabs.tsx`/`drawer.tsx`/`modal.tsx`, via `LayoutEditor.tsx`'s own
`<WidgetHost item={item} mode="edit" />`) are **not** changed — same
documented scope limit as Step 5.

- [ ] **Step 9: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: PASS.

- [ ] **Step 10: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green — this also proves the ~22 other widgets' `Component`/
`PropsPanel` implementations still compile unchanged (structural typing:
none of them destructure `theme`/`ctx.theme`, only `mapWidget.tsx` will,
starting Task 11).

- [ ] **Step 11: Commit**

```bash
git add shell/src/builder/registry.ts shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx shell/src/builder/WidgetHost.tsx shell/src/builder/WidgetHost.test.tsx shell/src/builder/AppRenderer.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): theme accessible aux widgets, à l'édition et au rendu

WidgetDefinition.PropsPanel ET WidgetContext (Component) reçoivent le
theme de l'AppConfig englobant — nécessaire pour que la palette
"Thème du site" du widget carte (SP-25) résolve à la même couleur dans
l'éditeur et dans le rendu publié. Un widget imbriqué dans
tabs/drawer/modal ne le reçoit pas encore (LayoutEditor ne le propage
pas, aux deux endroits) — limite assumée, mêmes garanties qu'une carte
standalone sans theme.
EOF
)"
```

---

