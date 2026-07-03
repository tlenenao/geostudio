import type { DataSource, WidgetItem } from "../api/types";
import { getWidget } from "./registry";

export function PropsPanel({
  item,
  dataSources,
  onChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  onChange: (props: Record<string, unknown>) => void;
}) {
  if (!item) {
    return <p className="text-xs text-slate-400">Aucun widget sélectionné.</p>;
  }
  const def = getWidget(item.widget);
  if (!def) {
    return <p className="text-xs text-slate-400">Widget inconnu : {item.widget}</p>;
  }
  const Panel = def.PropsPanel;
  return <Panel props={item.props} dataSources={dataSources} onChange={(p) => onChange(p)} />;
}
