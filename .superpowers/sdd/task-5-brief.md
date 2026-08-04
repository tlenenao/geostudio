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

