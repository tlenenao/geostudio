// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";

export function registerNavigationWidget(): void {
  registerWidget({
    type: "nav",
    label: "Navigation",
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      { name: "direction", type: "string", label: "Direction", default: "horizontal" },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Orientation
          <select
            aria-label="Orientation du menu"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.direction ?? "horizontal")}
            onChange={(e) => onChange({ ...props, direction: e.target.value })}
          >
            <option value="horizontal">Horizontale</option>
            <option value="vertical">Verticale</option>
          </select>
        </label>
        <p className="text-[10px] text-slate-400">
          Affiche automatiquement toutes les pages de l'application.
        </p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const pages = ctx.pages ?? [];
      const vertical = props.direction === "vertical";
      if (pages.length === 0) return <p className="text-xs text-slate-400">Aucune page.</p>;
      return (
        <nav className={`flex gap-1 ${vertical ? "flex-col" : "flex-row flex-wrap"}`}>
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 text-sm text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => ctx.navigate?.(p.id)}
            >
              {p.name}
            </button>
          ))}
        </nav>
      );
    },
  });
}
