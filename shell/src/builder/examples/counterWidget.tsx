// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget, useBusAction } from "../sdk";

export function registerCounterExampleWidget(): void {
  registerWidget({
    type: "example.counter",
    label: "Compteur (exemple SDK)",
    defaultProps: { initial: 0 },
    defaultSize: { w: 2, h: 2 },
    events: ["changed"],
    actions: ["reset"],
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        Valeur initiale
        <input
          aria-label="Valeur initiale"
          type="number"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={String(props.initial ?? 0)}
          onChange={(e) => onChange({ ...props, initial: Number(e.target.value) })}
        />
      </label>
    ),
    Component: ({ props, ctx }) => {
      const [count, setCount] = useState(Number(props.initial ?? 0));
      useBusAction(ctx.bus, ctx.widgetId, "reset", () => setCount(Number(props.initial ?? 0)));
      function increment() {
        const next = count + 1;
        setCount(next);
        ctx.bus?.emit(ctx.widgetId ?? "", "changed", { count: next });
      }
      return (
        <div className="flex h-full flex-col items-center justify-center gap-1">
          <span className="text-2xl font-semibold">{count}</span>
          <button
            type="button"
            className="rounded-md border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
            onClick={increment}
          >
            +1
          </button>
        </div>
      );
    },
  });
}
