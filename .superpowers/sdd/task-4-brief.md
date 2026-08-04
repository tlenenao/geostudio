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

