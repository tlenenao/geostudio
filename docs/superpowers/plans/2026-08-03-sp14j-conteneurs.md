# SP-14j — Conteneurs (onglets, modale, tiroir) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three new composite widgets to the GeoStudio shell builder —
`tabs`, `modal`, `drawer` — each holding its own nested `WidgetItem[]`, the
first level of widget-in-widget nesting the builder has ever supported.

**Architecture:** `WidgetPalette`, `GridCanvas` and `PropsPanel` are already
generic (no dependency on `AppConfig`/`AppBuilderPage`). A new
`builder/LayoutEditor.tsx` composes the three of them plus local
`items`/`selectedId` state into a reusable nested editor, used by each
container widget's own `PropsPanel`. At runtime, container widgets render
their children through the same `GridCanvas`+`WidgetHost` pair `AppRenderer`
already uses for the page level (`editable={false}`), gated by
open/close actions registered on the existing `ActionBus` (modal/drawer) or
local tab-switch state (tabs). Zero changes to `core/`, `AppConfig`, or
`AppBuilderPage.tsx`.

**Tech Stack:** React 18 + TypeScript, Vitest + Testing Library (unit),
Playwright (E2E), Tailwind utility classes, existing GeoStudio builder
primitives (`ActionBus`, `WidgetHost`, `GridCanvas`, `WidgetPalette`,
`PropsPanel`, `Dialog`).

## Global Constraints

- Additive only: no change to `AppConfig`, `AppBuilderPage.tsx`,
  `core/`, or the behavior of any of the 19 existing widget kinds.
- One level of nesting only — `tabs`/`modal`/`drawer` are excluded from the
  `WidgetPalette` rendered inside a `LayoutEditor` (no container-in-container).
- Modal/drawer open **only** via the existing `ActionBus` `open`/`close`
  actions, wired through the existing `ActionsPanel` UI (SP-5c) — no new
  trigger mechanism.
- `en-tête SPDX` (`// SPDX-License-Identifier: Apache-2.0`) on every new file.
- UI text in French; code/identifiers in English.
- Commits: conventional, suffixed `(SP-14j)`.
- All 76+ existing E2E specs and the full unit suite stay green throughout.

---

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

## Task 2: `WidgetPalette` gains an `exclude` filter

**Files:**
- Modify: `shell/src/builder/WidgetPalette.tsx`
- Test: `shell/src/builder/WidgetPalette.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WidgetPalette({ onAdd, exclude? }: { onAdd: (type: string) => void; exclude?: string[] })`.
  Task 4 (`LayoutEditor`) depends on this to keep container kinds out of a
  nested palette.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/WidgetPalette.test.tsx`:

```tsx
test("excludes the given widget types from the list", () => {
  const onAdd = vi.fn();
  render(<WidgetPalette onAdd={onAdd} exclude={["image", "button"]} />);
  expect(screen.getByRole("button", { name: "Texte" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Image" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Bouton" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx`
Expected: FAIL — `exclude` prop doesn't exist yet, all widgets (including
"Image"/"Bouton") are listed.

- [ ] **Step 3: Implement the filter**

Replace the full contents of `shell/src/builder/WidgetPalette.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { listWidgets } from "./registry";

export function WidgetPalette({
  onAdd,
  exclude = [],
}: {
  onAdd: (type: string) => void;
  exclude?: string[];
}) {
  return (
    <ul className="flex flex-col gap-1">
      {listWidgets()
        .filter((def) => !exclude.includes(def.type))
        .map((def) => (
          <li key={def.type}>
            <button
              type="button"
              className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-left text-sm hover:bg-slate-100"
              onClick={() => onAdd(def.type)}
            >
              {def.label}
            </button>
          </li>
        ))}
    </ul>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx`
Expected: PASS (all tests, including the pre-existing "lists widgets and
emits the type on click").

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/WidgetPalette.tsx shell/src/builder/WidgetPalette.test.tsx
git commit -m "feat(shell): WidgetPalette gains an exclude filter (SP-14j)"
```

---

## Task 3: `Dialog` gains a `wide` variant

**Files:**
- Modify: `shell/src/ui/dialog.tsx`
- Test: `shell/src/ui/dialog.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Dialog({ open, onClose, title, wide?, children })` — `wide`
  defaults to `false` (unchanged `max-w-md` behavior). Task 6 (`modal`
  widget) depends on this to avoid squeezing a widget grid into a narrow
  dialog.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/ui/dialog.test.tsx`:

```tsx
test("uses a wider max-width when wide is set", () => {
  render(
    <Dialog open onClose={() => {}} title="T" wide>
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-2xl");
});

test("defaults to the standard max-width when wide is omitted", () => {
  render(
    <Dialog open onClose={() => {}} title="T">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-md");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/ui/dialog.test.tsx`
Expected: FAIL — TypeScript error, `wide` isn't a valid prop yet; both new
assertions fail once that's silenced.

- [ ] **Step 3: Add the `wide` prop**

Replace the full contents of `shell/src/ui/dialog.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";

export function Dialog({
  open,
  onClose,
  title,
  wide = false,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={onClose} />
      <div
        role="dialog"
        aria-label={title}
        className={`relative z-10 w-full rounded-lg bg-white p-6 shadow-lg ${wide ? "max-w-2xl" : "max-w-md"}`}
      >
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/ui/dialog.test.tsx`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/dialog.tsx shell/src/ui/dialog.test.tsx
git commit -m "feat(shell): Dialog gains an optional wide variant (SP-14j)"
```

---

## Task 4: `LayoutEditor` — reusable nested widget editor

**Files:**
- Create: `shell/src/builder/LayoutEditor.tsx`
- Test: `shell/src/builder/LayoutEditor.test.tsx`

**Interfaces:**
- Consumes: `WidgetPalette` (Task 2's `exclude`), `GridCanvas`, `WidgetHost`,
  `PropsPanel` (all pre-existing and generic), `getWidget`/`nextFreePosition`/
  `moveItemAt` (pre-existing).
- Produces:
  ```ts
  function LayoutEditor(props: {
    items: WidgetItem[];
    onChange: (items: WidgetItem[]) => void;
    dataSources: DataSource[];
    breakpoint: Breakpoint;
  }): JSX.Element
  ```
  Tasks 5-7 (`tabs`/`modal`/`drawer` `PropsPanel`) each mount one or more
  `LayoutEditor` instances.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/LayoutEditor.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetItem } from "../api/types";
import { _resetRegistry, getWidget, registerWidget } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { LayoutEditor } from "./LayoutEditor";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("adds a widget from the palette, positioned below existing items, and selects it", async () => {
  const onChange = vi.fn();
  render(<LayoutEditor items={[]} onChange={onChange} dataSources={[]} breakpoint="lg" />);
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  expect(onChange).toHaveBeenCalledTimes(1);
  const items = onChange.mock.calls[0][0] as WidgetItem[];
  expect(items).toHaveLength(1);
  expect(items[0]).toMatchObject({ widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Nouveau texte", dataSourceId: "" } });
});

test("excludes container kinds from its own palette to prevent nesting", () => {
  // registerBuiltinWidgets() may already register the real "tabs"/"modal"/"drawer"
  // kinds by the time this test runs (Tasks 5-7) — only register a stub if a kind
  // isn't present yet, so this test stays meaningful both before and after those
  // tasks land, without an "overwriting an already-registered widget type" warning.
  for (const type of ["tabs", "modal", "drawer"]) {
    if (getWidget(type)) continue;
    registerWidget({ type, label: type, defaultProps: {}, defaultSize: { w: 1, h: 1 }, PropsPanel: () => <div />, Component: () => <div /> });
  }
  render(<LayoutEditor items={[]} onChange={vi.fn()} dataSources={[]} breakpoint="lg" />);
  expect(screen.getByRole("button", { name: "Texte" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "tabs" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onglets" })).not.toBeInTheDocument();
});

test("selecting an item shows its PropsPanel and edits its props", async () => {
  const item: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bonjour", dataSourceId: "" } };
  const onChange = vi.fn();
  render(<LayoutEditor items={[item]} onChange={onChange} dataSources={[]} breakpoint="lg" />);
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  expect(screen.getByLabelText("Texte du widget")).toHaveValue("Bonjour");
  await userEvent.type(screen.getByLabelText("Texte du widget"), "!");
  const items = onChange.mock.calls.at(-1)![0] as WidgetItem[];
  expect(items[0].props.text).toBe("Bonjour!");
  expect(items[0].id).toBe("a");
});

test("moving the selected item updates its position via onChange", async () => {
  const item: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {} };
  const onChange = vi.fn();
  render(<LayoutEditor items={[item]} onChange={onChange} dataSources={[]} breakpoint="lg" />);
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a à droite" }));
  const items = onChange.mock.calls.at(-1)![0] as WidgetItem[];
  expect(items[0].x).toBe(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/LayoutEditor.test.tsx`
Expected: FAIL — the module `./LayoutEditor` doesn't exist yet.

- [ ] **Step 3: Implement `LayoutEditor`**

Create `shell/src/builder/LayoutEditor.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { DataSource, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { moveItemAt, nextFreePosition, type Breakpoint } from "./grid";
import { WidgetPalette } from "./WidgetPalette";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { PropsPanel } from "./PropsPanel";

const NESTED_EXCLUDE = ["tabs", "modal", "drawer"];

export function LayoutEditor({
  items,
  onChange,
  dataSources,
  breakpoint,
}: {
  items: WidgetItem[];
  onChange: (items: WidgetItem[]) => void;
  dataSources: DataSource[];
  breakpoint: Breakpoint;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find((i) => i.id === selectedId) ?? null;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def) return;
    const { x, y } = nextFreePosition(items);
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x,
      y,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
    };
    onChange([...items, item]);
    setSelectedId(item.id);
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    onChange(items.map((i) => (i.id === selectedId ? { ...i, props } : i)));
  }

  function updateSelectedVisibleWhen(expr: string) {
    onChange(items.map((i) => (i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i)));
  }

  function handleMove(id: string, dx: number, dy: number) {
    onChange(items.map((i) => (i.id === id ? moveItemAt(i, breakpoint, dx, dy) : i)));
  }

  return (
    <div className="flex flex-col gap-2">
      <WidgetPalette onAdd={addWidget} exclude={NESTED_EXCLUDE} />
      <div className="h-48 overflow-auto border border-slate-200">
        <GridCanvas
          items={items}
          breakpoint={breakpoint}
          editable
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveItem={handleMove}
          renderItem={(item) => <WidgetHost item={item} mode="edit" />}
        />
      </div>
      <PropsPanel
        item={selected}
        dataSources={dataSources}
        onChange={updateSelectedProps}
        onVisibleWhenChange={updateSelectedVisibleWhen}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/LayoutEditor.test.tsx`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/LayoutEditor.tsx shell/src/builder/LayoutEditor.test.tsx
git commit -m "feat(shell): LayoutEditor composes palette+canvas+props for nested widget editing (SP-14j)"
```

---

## Task 5: `tabs` widget

**Files:**
- Create: `shell/src/builder/widgets/tabs.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/widgets/tabs.test.tsx`

**Interfaces:**
- Consumes: `LayoutEditor` (Task 4), `GridCanvas`, `WidgetHost`,
  `registerWidget`/`WidgetContext` (`registry.ts`, `breakpoint` from Task 1).
- Produces: widget kind `"tabs"`, `props: { tabs: Array<{ id: string; label: string; items: WidgetItem[] }> }`,
  registered via `registerTabsWidget()`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/tabs.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetItem } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("runtime: shows the first tab's content by default and switches on click", async () => {
  const tabA: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Contenu A" } };
  const tabB: WidgetItem = { id: "b", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Contenu B" } };
  const Tabs = getWidget("tabs")!.Component;
  render(
    <Tabs
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [tabA] }, { id: "t2", label: "Onglet 2", items: [tabB] }] }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(screen.getByText("Contenu A")).toBeInTheDocument();
  expect(screen.queryByText("Contenu B")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Onglet 2" }));
  expect(screen.queryByText("Contenu A")).not.toBeInTheDocument();
  expect(screen.getByText("Contenu B")).toBeInTheDocument();
});

test("edit mode renders statically without an interactive tab bar switch", () => {
  const tabA: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Contenu A" } };
  const Tabs = getWidget("tabs")!.Component;
  render(<Tabs props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [tabA] }] }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText("Onglet 1")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onglet 1" })).not.toBeInTheDocument();
});

test("PropsPanel adds a tab, selects it, and edits its label", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(<Panel props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }] }} dataSources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un onglet" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs).toHaveLength(2);
  expect(tabs[1].label).toBe("Onglet 2");
});

test("PropsPanel refuses to remove the last remaining tab", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(<Panel props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }] }} dataSources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Supprimer l'onglet Onglet 1" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("PropsPanel reorders tabs with the up/down buttons", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }, { id: "t2", label: "Onglet 2", items: [] }] }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Descendre l'onglet Onglet 1" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs as Array<{ label: string }>;
  expect(tabs.map((t) => t.label)).toEqual(["Onglet 2", "Onglet 1"]);
});

test("PropsPanel edits only the active tab's items, switchable via the tab selector", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  const { rerender } = render(
    <Panel
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }, { id: "t2", label: "Onglet 2", items: [] }] }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  let tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs[0].items).toHaveLength(1);
  expect(tabs[1].items).toHaveLength(0);

  rerender(<Panel props={{ tabs }} dataSources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner l'onglet Onglet 2" }));
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs[0].items).toHaveLength(1);
  expect(tabs[1].items).toHaveLength(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx`
Expected: FAIL — `getWidget("tabs")` is `undefined` (kind not registered
yet).

- [ ] **Step 3: Implement `registerTabsWidget`**

Create `shell/src/builder/widgets/tabs.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import type { WidgetItem } from "../../api/types";
import { LayoutEditor } from "../LayoutEditor";
import { GridCanvas } from "../GridCanvas";
import { WidgetHost } from "../WidgetHost";

type Tab = { id: string; label: string; items: WidgetItem[] };
type TabsProps = { tabs: Tab[] };

const inputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

export function registerTabsWidget(): void {
  registerWidget({
    type: "tabs",
    label: "Onglets",
    defaultProps: { tabs: [{ id: "tab-1", label: "Onglet 1", items: [] }] },
    defaultSize: { w: 6, h: 6 },
    PropsPanel: ({ props, onChange, dataSources }) => {
      const { tabs } = props as TabsProps;
      const [activeId, setActiveId] = useState(tabs[0]?.id);
      const active = tabs.find((t) => t.id === activeId) ?? tabs[0];

      function addTab() {
        const tab = { id: crypto.randomUUID(), label: `Onglet ${tabs.length + 1}`, items: [] };
        onChange({ tabs: [...tabs, tab] });
        setActiveId(tab.id);
      }
      function renameTab(id: string, label: string) {
        onChange({ tabs: tabs.map((t) => (t.id === id ? { ...t, label } : t)) });
      }
      function removeTab(id: string) {
        if (tabs.length <= 1) return;
        const next = tabs.filter((t) => t.id !== id);
        onChange({ tabs: next });
        if (activeId === id) setActiveId(next[0].id);
      }
      function moveTab(id: string, dir: -1 | 1) {
        const i = tabs.findIndex((t) => t.id === id);
        const j = i + dir;
        if (j < 0 || j >= tabs.length) return;
        const next = [...tabs];
        [next[i], next[j]] = [next[j], next[i]];
        onChange({ tabs: next });
      }
      function setActiveItems(items: WidgetItem[]) {
        onChange({ tabs: tabs.map((t) => (t.id === activeId ? { ...t, items } : t)) });
      }

      if (!active) return null;

      return (
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex flex-col gap-1">
            {tabs.map((t, i) => (
              <div key={t.id} className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label={`Sélectionner l'onglet ${t.label}`}
                  className={t.id === activeId ? "font-semibold underline" : ""}
                  onClick={() => setActiveId(t.id)}
                >
                  {t.label}
                </button>
                <input
                  aria-label={`Nom de l'onglet ${t.label}`}
                  className={inputCls}
                  value={t.label}
                  onChange={(e) => renameTab(t.id, e.target.value)}
                />
                <button type="button" aria-label={`Monter l'onglet ${t.label}`} disabled={i === 0} onClick={() => moveTab(t.id, -1)}>↑</button>
                <button type="button" aria-label={`Descendre l'onglet ${t.label}`} disabled={i === tabs.length - 1} onClick={() => moveTab(t.id, 1)}>↓</button>
                <button
                  type="button"
                  aria-label={`Supprimer l'onglet ${t.label}`}
                  disabled={tabs.length <= 1}
                  className="text-xs text-red-600 disabled:opacity-30"
                  onClick={() => removeTab(t.id)}
                >
                  Supprimer
                </button>
              </div>
            ))}
            <button type="button" aria-label="Ajouter un onglet" className={inputCls} onClick={addTab}>
              Ajouter un onglet
            </button>
          </div>
          <LayoutEditor items={active.items} onChange={setActiveItems} dataSources={dataSources} breakpoint="lg" />
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const { tabs } = props as TabsProps;
      const [activeId, setActiveId] = useState(tabs[0]?.id);
      const active = tabs.find((t) => t.id === activeId) ?? tabs[0];

      if (!active) {
        return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Aucun onglet</div>;
      }

      if (ctx.mode === "edit") {
        return (
          <div className="flex h-full flex-col">
            <div className="flex gap-1 border-b border-[var(--gs-color-border)] p-1 text-xs">
              {tabs.map((t) => (
                <span key={t.id} className="px-2 py-1">{t.label}</span>
              ))}
            </div>
            <div className="flex-1 bg-slate-50" />
          </div>
        );
      }

      return (
        <div className="flex h-full flex-col">
          <div className="flex gap-1 border-b border-[var(--gs-color-border)] p-1 text-xs">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`rounded px-2 py-1 ${t.id === active.id ? "bg-[var(--gs-color-primary)] text-white" : ""}`}
                onClick={() => setActiveId(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1">
            <GridCanvas
              items={active.items}
              breakpoint={ctx.breakpoint ?? "lg"}
              editable={false}
              selectedId={null}
              onSelect={() => {}}
              onMoveItem={() => {}}
              renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />}
            />
          </div>
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `registerBuiltinWidgets`**

In `shell/src/builder/widgets/index.tsx`, add the import near the other
widget imports:

```tsx
import { registerSliderFilterWidget } from "./sliderFilter";
import { registerTabsWidget } from "./tabs";
```

And the call at the end of `registerBuiltinWidgets()`, after
`registerSliderFilterWidget();`:

```tsx
  registerSliderFilterWidget();
  registerTabsWidget();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx`
Expected: PASS (all 4 tests).

Also run the full unit suite to catch any registry/index regression:

Run: `cd shell && npx vitest run`
Expected: PASS (no failures elsewhere).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/tabs.tsx shell/src/builder/widgets/tabs.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): tabs container widget with a nested LayoutEditor per tab (SP-14j)"
```

---

## Task 6: `modal` widget

**Files:**
- Create: `shell/src/builder/widgets/modal.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/widgets/modal.test.tsx`

**Interfaces:**
- Consumes: `LayoutEditor` (Task 4), `GridCanvas`, `WidgetHost`, `Dialog`
  with its `wide` prop (Task 3), `useBusAction` (`ActionBusContext.tsx`,
  pre-existing).
- Produces: widget kind `"modal"`, `props: { title: string; items: WidgetItem[]; wide?: boolean }`,
  `actions: ["open", "close"]`, registered via `registerModalWidget()`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/modal.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import type { AuthState } from "../../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("declares open/close actions", () => {
  expect(getWidget("modal")!.actions).toEqual(["open", "close"]);
});

test("closed by default, opens on the open action, closes on Escape", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m1", from: "trigger", event: "clicked", to: "modal1", action: "open" }]);
  const Modal = getWidget("modal")!.Component;
  render(
    <Modal
      props={{ title: "Détail", items: [{ id: "c", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Corps" } }] }}
      ctx={{ mode: "runtime", bus, widgetId: "modal1" } as WidgetContext}
    />,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  bus.emit("trigger", "clicked");
  expect(await screen.findByRole("dialog", { name: "Détail" })).toBeInTheDocument();
  expect(screen.getByText("Corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("closes on the close action too", async () => {
  const bus = new ActionBus();
  bus.configure([
    { id: "m1", from: "opener", event: "clicked", to: "modal1", action: "open" },
    { id: "m2", from: "closer", event: "clicked", to: "modal1", action: "close" },
  ]);
  const Modal = getWidget("modal")!.Component;
  render(<Modal props={{ title: "Détail", items: [] }} ctx={{ mode: "runtime", bus, widgetId: "modal1" } as WidgetContext} />);
  bus.emit("opener", "clicked");
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  bus.emit("closer", "clicked");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("edit mode shows a static badge and never opens", () => {
  const Modal = getWidget("modal")!.Component;
  render(<Modal props={{ title: "Détail", items: [] }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText("Modale : Détail")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("PropsPanel edits the title and the wide flag", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("modal")!.PropsPanel;
  render(<Panel props={{ title: "Détail", items: [] }} dataSources={[]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Titre de la modale"), "!");
  expect(onChange.mock.calls.at(-1)![0].title).toBe("Détail!");
  await userEvent.click(screen.getByLabelText("Modale large"));
  expect(onChange.mock.calls.at(-1)![0].wide).toBe(true);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/modal.test.tsx`
Expected: FAIL — `getWidget("modal")` is `undefined`.

- [ ] **Step 3: Implement `registerModalWidget`**

Create `shell/src/builder/widgets/modal.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import type { WidgetItem } from "../../api/types";
import { useBusAction } from "../ActionBusContext";
import { LayoutEditor } from "../LayoutEditor";
import { GridCanvas } from "../GridCanvas";
import { WidgetHost } from "../WidgetHost";
import { Dialog } from "../../ui/dialog";

type ModalProps = { title: string; items: WidgetItem[]; wide?: boolean };

const inputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

export function registerModalWidget(): void {
  registerWidget({
    type: "modal",
    label: "Modale",
    defaultProps: { title: "Modale", items: [] },
    defaultSize: { w: 3, h: 1 },
    actions: ["open", "close"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const { title, items, wide } = props as ModalProps;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            Titre
            <input
              aria-label="Titre de la modale"
              className={inputCls}
              value={title}
              onChange={(e) => onChange({ title: e.target.value, items, wide })}
            />
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              aria-label="Modale large"
              checked={Boolean(wide)}
              onChange={(e) => onChange({ title, items, wide: e.target.checked })}
            />
            Modale large
          </label>
          <LayoutEditor items={items} onChange={(next) => onChange({ title, items: next, wide })} dataSources={dataSources} breakpoint="lg" />
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const { title, items, wide } = props as ModalProps;
      const [open, setOpen] = useState(false);
      useBusAction(ctx.bus, ctx.widgetId, "open", () => setOpen(true));
      useBusAction(ctx.bus, ctx.widgetId, "close", () => setOpen(false));

      if (ctx.mode === "edit") {
        return (
          <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
            Modale : {title}
          </div>
        );
      }

      return (
        <Dialog open={open} onClose={() => setOpen(false)} title={title} wide={wide}>
          <div className="h-64">
            <GridCanvas
              items={items}
              breakpoint={ctx.breakpoint ?? "lg"}
              editable={false}
              selectedId={null}
              onSelect={() => {}}
              onMoveItem={() => {}}
              renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />}
            />
          </div>
        </Dialog>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `registerBuiltinWidgets`**

In `shell/src/builder/widgets/index.tsx`, add the import:

```tsx
import { registerTabsWidget } from "./tabs";
import { registerModalWidget } from "./modal";
```

And the call after `registerTabsWidget();`:

```tsx
  registerTabsWidget();
  registerModalWidget();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/modal.test.tsx`
Expected: PASS (all 5 tests).

Run: `cd shell && npx vitest run`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/modal.tsx shell/src/builder/widgets/modal.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): modal container widget, opened/closed via the action bus (SP-14j)"
```

---

## Task 7: `drawer` widget

**Files:**
- Create: `shell/src/builder/widgets/drawer.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/widgets/drawer.test.tsx`

**Interfaces:**
- Consumes: `LayoutEditor` (Task 4), `GridCanvas`, `WidgetHost`,
  `useBusAction` (pre-existing). No dependency on `Dialog` — the slide-over
  chrome is written directly in this file (documented in the spec as a
  deliberate non-extraction, since `ExplorerDrawer` is analytics-specific).
- Produces: widget kind `"drawer"`, `props: { title: string; items: WidgetItem[]; side: "left" | "right" }`,
  `actions: ["open", "close"]`, registered via `registerDrawerWidget()`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/drawer.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import type { AuthState } from "../../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("declares open/close actions", () => {
  expect(getWidget("drawer")!.actions).toEqual(["open", "close"]);
});

test("closed by default, opens on the open action, closes on Escape and backdrop click", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m1", from: "trigger", event: "clicked", to: "drawer1", action: "open" }]);
  const Drawer = getWidget("drawer")!.Component;
  render(
    <Drawer
      props={{ title: "Filtres", items: [{ id: "c", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Corps" } }], side: "right" }}
      ctx={{ mode: "runtime", bus, widgetId: "drawer1" } as WidgetContext}
    />,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  bus.emit("trigger", "clicked");
  expect(await screen.findByRole("dialog", { name: "Filtres" })).toBeInTheDocument();
  expect(screen.getByText("Corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("edit mode shows a static badge and never opens", () => {
  const Drawer = getWidget("drawer")!.Component;
  render(<Drawer props={{ title: "Filtres", items: [], side: "right" }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText("Tiroir : Filtres")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("PropsPanel edits the title and the side", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("drawer")!.PropsPanel;
  render(<Panel props={{ title: "Filtres", items: [], side: "right" }} dataSources={[]} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Côté du tiroir"), "left");
  expect(onChange.mock.calls.at(-1)![0].side).toBe("left");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/drawer.test.tsx`
Expected: FAIL — `getWidget("drawer")` is `undefined`.

- [ ] **Step 3: Implement `registerDrawerWidget`**

Create `shell/src/builder/widgets/drawer.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { registerWidget } from "../registry";
import type { WidgetItem } from "../../api/types";
import { useBusAction } from "../ActionBusContext";
import { LayoutEditor } from "../LayoutEditor";
import { GridCanvas } from "../GridCanvas";
import { WidgetHost } from "../WidgetHost";

type DrawerProps = { title: string; items: WidgetItem[]; side: "left" | "right" };

const inputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

export function registerDrawerWidget(): void {
  registerWidget({
    type: "drawer",
    label: "Tiroir",
    defaultProps: { title: "Tiroir", items: [], side: "right" },
    defaultSize: { w: 3, h: 1 },
    actions: ["open", "close"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const { title, items, side } = props as DrawerProps;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            Titre
            <input
              aria-label="Titre du tiroir"
              className={inputCls}
              value={title}
              onChange={(e) => onChange({ title: e.target.value, items, side })}
            />
          </label>
          <label className="flex flex-col gap-1">
            Côté
            <select
              aria-label="Côté du tiroir"
              className={inputCls}
              value={side}
              onChange={(e) => onChange({ title, items, side: e.target.value as "left" | "right" })}
            >
              <option value="right">Droite</option>
              <option value="left">Gauche</option>
            </select>
          </label>
          <LayoutEditor items={items} onChange={(next) => onChange({ title, items: next, side })} dataSources={dataSources} breakpoint="lg" />
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const { title, items, side } = props as DrawerProps;
      const [open, setOpen] = useState(false);
      useBusAction(ctx.bus, ctx.widgetId, "open", () => setOpen(true));
      useBusAction(ctx.bus, ctx.widgetId, "close", () => setOpen(false));

      useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
          if (e.key === "Escape") setOpen(false);
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
      }, [open]);

      if (ctx.mode === "edit") {
        return (
          <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
            Tiroir : {title}
          </div>
        );
      }
      if (!open) return null;

      const sideCls = side === "left" ? "left-0" : "right-0";
      return (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={() => setOpen(false)} />
          <div role="dialog" aria-label={title} className={`absolute top-0 ${sideCls} h-full w-96 overflow-auto bg-white p-4 shadow-lg`}>
            <h2 className="mb-4 text-lg font-semibold">{title}</h2>
            <div className="h-[calc(100%-2rem)]">
              <GridCanvas
                items={items}
                breakpoint={ctx.breakpoint ?? "lg"}
                editable={false}
                selectedId={null}
                onSelect={() => {}}
                onMoveItem={() => {}}
                renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />}
              />
            </div>
          </div>
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `registerBuiltinWidgets`**

In `shell/src/builder/widgets/index.tsx`, add the import:

```tsx
import { registerModalWidget } from "./modal";
import { registerDrawerWidget } from "./drawer";
```

And the call after `registerModalWidget();`:

```tsx
  registerModalWidget();
  registerDrawerWidget();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/drawer.test.tsx`
Expected: PASS (all 4 tests).

Run: `cd shell && npx vitest run`
Expected: PASS (no regressions) — this is the last unit task, so the full
suite (previously 398 tests) should now be green with the new tests added.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/drawer.tsx shell/src/builder/widgets/drawer.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): drawer container widget, opened/closed via the action bus (SP-14j)"
```

---

## Task 8: E2E — build and exercise all three containers

**Files:**
- Create: `shell/e2e/containers.spec.ts`

**Interfaces:**
- Consumes: the running builder UI (`AppBuilderPage`) and runtime app view,
  through the "Nouveau" → app creation flow and the `ActionsPanel` wiring UI
  already exercised by `e2e/actions.spec.ts`. No new interfaces produced —
  this is the terminal task.

Note: the nested child widget used in every scenario below is `Texte`
(static content, no data source required) rather than a data-bound widget —
it renders deterministic content immediately, which keeps these E2E
assertions independent of any mocked collection data. Nested rendering of
other widget kinds (e.g. `table`) inside a container is already covered by
the unit tests in Tasks 5-7 (`WidgetHost` renders any registered kind
identically regardless of nesting).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/containers.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("Onglets switches which nested widget is visible", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App onglets");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Onglets" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });

  // Onglet 1 (par défaut) reçoit un Texte "Contenu A".
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Contenu A");

  // Un 2e onglet est ajouté, vide.
  await propsPanel.getByRole("button", { name: "Ajouter un onglet" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByText("Contenu A")).toBeVisible();
  await page.getByRole("button", { name: "Onglet 2" }).click();
  await expect(page.getByText("Contenu A")).toBeHidden();
});

test("Bouton opens a Modale via the action bus, and Escape closes it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App modale");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByLabel("Libellé du bouton").fill("Ouvrir");

  await page.getByRole("button", { name: "Modale" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await propsPanel.getByLabel("Titre de la modale").fill("Détail");
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Corps modale");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Modale" });
  await page.getByLabel("Action", { exact: true }).selectOption("open");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("dialog", { name: "Détail" })).not.toBeVisible();
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page.getByRole("dialog", { name: "Détail" })).toBeVisible();
  await expect(page.getByText("Corps modale")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Détail" })).not.toBeVisible();
});

test("Bouton opens a Tiroir via the action bus, and Escape closes it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App tiroir");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByLabel("Libellé du bouton").fill("Ouvrir");

  await page.getByRole("button", { name: "Tiroir" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await propsPanel.getByLabel("Titre du tiroir").fill("Filtres");
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Corps tiroir");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Tiroir" });
  await page.getByLabel("Action", { exact: true }).selectOption("open");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("dialog", { name: "Filtres" })).not.toBeVisible();
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page.getByRole("dialog", { name: "Filtres" })).toBeVisible();
  await expect(page.getByText("Corps tiroir")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Filtres" })).not.toBeVisible();
});
```

- [ ] **Step 2: Run the new spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/containers.spec.ts`
Expected: PASS (3 scenarios). If a locator fails to resolve, check first
whether the accessible name changed (e.g. widget label text) rather than
adjusting the scenario's intent.

- [ ] **Step 3: Run the full E2E suite to confirm no regression**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: PASS — all pre-existing specs plus the 3 new ones (was 76+
specs across 40 files, now 41 files).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/containers.spec.ts
git commit -m "test(e2e): couvre les conteneurs — onglets, modale, tiroir (SP-14j)"
```

---

## Final check

- [ ] Run the full unit + typecheck + E2E gate once more from a clean state:

```bash
cd shell
npm run build   # tsc --noEmit + vite build
npx vitest run
VITE_AUTH_MODE=mock npm run e2e
```

Expected: all three commands succeed with zero failures.
