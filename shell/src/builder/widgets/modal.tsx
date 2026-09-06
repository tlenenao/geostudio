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
    configSchema: [{ name: "title", type: "string", label: "Titre", default: "Modale" }],
    actions: ["open", "close"],
    PropsPanel: ({ props, onChange, dataSources, variables }) => {
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
          <LayoutEditor
            items={items}
            onChange={(next) => onChange({ title, items: next, wide })}
            dataSources={dataSources}
            breakpoint="lg"
            variables={variables}
          />
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
              onRemoveItem={() => {}}
              renderItem={(item) => (
                <WidgetHost
                  item={item}
                  mode={ctx.mode}
                  pages={ctx.pages}
                  navigate={ctx.navigate}
                  breakpoint={ctx.breakpoint}
                />
              )}
            />
          </div>
        </Dialog>
      );
    },
  });
}
