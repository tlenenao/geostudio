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
    configSchema: [
      { name: "title", type: "string", label: "Titre", default: "Tiroir" },
      { name: "side", type: "string", label: "Côté", default: "right" },
    ],
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
                renderItem={(item) => (
                  <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} breakpoint={ctx.breakpoint} />
                )}
              />
            </div>
          </div>
        </div>
      );
    },
  });
}
