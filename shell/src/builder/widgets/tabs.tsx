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
              renderItem={(item) => (
                <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} breakpoint={ctx.breakpoint} />
              )}
            />
          </div>
        </div>
      );
    },
  });
}
