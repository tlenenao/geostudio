## Task 1: `WidgetContext.breakpoint` threading

**Files:**
- Modify: `shell/src/builder/registry.ts:1-15`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx:191-199`
- Test: `shell/src/builder/WidgetHost.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WidgetContext.breakpoint?: Breakpoint` (`registry.ts`), read by
  any widget `Component` via `ctx.breakpoint`. Tasks 5-7 (`tabs`/`modal`/
  `drawer` runtime rendering) depend on this to size their internal
  `GridCanvas`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/WidgetHost.test.tsx` (after the existing tests,
same file, same `beforeEach`/mock setup already present):

```tsx
test("threads the breakpoint prop into the widget context", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ ctx }) => <div>bp:{ctx.breakpoint ?? "none"}</div> });
  render(<WidgetHost item={item("probe")} mode="runtime" breakpoint="md" />);
  expect(screen.getByText("bp:md")).toBeInTheDocument();
});

test("omits the breakpoint from the widget context when not provided", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ ctx }) => <div>bp:{ctx.breakpoint ?? "none"}</div> });
  render(<WidgetHost item={item("probe")} mode="runtime" />);
  expect(screen.getByText("bp:none")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: FAIL — `ctx.breakpoint` is `undefined` in both cases (first test
expects `"bp:md"`, gets `"bp:none"`); the prop doesn't exist on `WidgetHost`'s
props type yet so TypeScript will also flag it.

- [ ] **Step 3: Add `breakpoint` to `WidgetContext`**

In `shell/src/builder/registry.ts`, add the import and field:

```ts
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";

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
};
```

- [ ] **Step 4: Thread `breakpoint` through `WidgetHost`**

In `shell/src/builder/WidgetHost.tsx`, add the import and prop, and pass it
into `ctx`:

```tsx
import type { Page, RenderMode, WidgetItem } from "../api/types";
import type { Breakpoint } from "./grid";
```

```tsx
export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
  breakpoint,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
  breakpoint?: Breakpoint;
}) {
```

And in the final return, add `breakpoint` to the `ctx` object literal:

```tsx
      <Widget props={resolvedProps} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate, variables, user, breakpoint }} />
```

- [ ] **Step 5: Pass the live breakpoint from `AppRenderer`**

In `shell/src/builder/AppRenderer.tsx:198`, change the `renderItem` call to
forward `bp`:

```tsx
                    renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} breakpoint={bp} />}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: PASS (all tests in the file, including the two new ones).

Also run the full AppRenderer suite to catch any regression from the
`renderItem` signature change:

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/registry.ts shell/src/builder/WidgetHost.tsx shell/src/builder/WidgetHost.test.tsx shell/src/builder/AppRenderer.tsx
git commit -m "feat(shell): thread the active breakpoint into WidgetContext (SP-14j)"
```

---

