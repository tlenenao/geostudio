// SPDX-License-Identifier: Apache-2.0
import type { DataSource, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

export function PropsPanel({
  item,
  dataSources,
  onChange,
  onVisibleWhenChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
}) {
  if (!item) {
    return <p className="text-xs text-slate-400">Aucun widget sélectionné.</p>;
  }
  const def = getWidget(item.widget);
  if (!def) {
    return <p className="text-xs text-slate-400">Widget inconnu : {item.widget}</p>;
  }
  const Panel = def.PropsPanel;
  const visibleWhen = item.visibleWhen ?? "";
  const error = visibleWhen ? validateExpression(visibleWhen) : null;
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        Condition d'affichage
        <textarea
          aria-label="Condition d'affichage (visibleWhen)"
          className="rounded-md border border-slate-300 p-2 font-mono text-xs"
          value={visibleWhen}
          onChange={(e) => onVisibleWhenChange(e.target.value)}
        />
        {error && (
          <span role="alert" className="text-xs text-red-600">
            {error}
          </span>
        )}
      </label>
      <Panel props={item.props} dataSources={dataSources} onChange={(p) => onChange(p)} />
    </div>
  );
}
