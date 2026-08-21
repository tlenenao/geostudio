// SPDX-License-Identifier: Apache-2.0
// Exécute une opération "client" proposée par le copilote (SP-20) en
// réutilisant les mêmes fonctions pures que la palette/PropsPanel
// (grid.ts/pages.ts) — toute opération traverse donc le même chemin que
// l'UI manuelle. Pure : le résultat passe par setDraft (undo SP-19) côté
// appelant (CopilotPanel), jamais ici.
import type { AppConfig, DataSource, WidgetItem } from "../../api/types";
import { nextFreePosition } from "../grid";
import { getPageLayout, setPageLayout } from "../pages";
import { getWidget } from "../registry";

// Forme brute reçue du cœur (Pydantic ClientOp côté serveur, JSON opaque) —
// peut être n'importe quel nom d'outil que le LLM a proposé, y compris un
// nom halluciné qui ne correspond à aucun des 5 op ci-dessous : voir le
// `default` du switch plus bas.
export type RawClientOp = { op: string; args: Record<string, unknown> };

function coerceProp(value: unknown, type: "string" | "number" | "boolean" | "dataSource"): unknown {
  if (type === "number") return Number(value);
  if (type === "boolean") return Boolean(value);
  return String(value ?? ""); // "string" | "dataSource"
}

export function applyClientOp(
  raw: RawClientOp,
  config: AppConfig,
  activePageId: string,
): AppConfig {
  const layout = getPageLayout(config, activePageId);

  switch (raw.op) {
    case "addWidget": {
      const type = String(raw.args.type ?? "");
      const def = getWidget(type);
      if (!def) return config;
      const { x, y } = nextFreePosition(layout.items);
      const item: WidgetItem = {
        id: crypto.randomUUID(),
        widget: type,
        x,
        y,
        w: def.defaultSize.w,
        h: def.defaultSize.h,
        props: { ...def.defaultProps },
      };
      return setPageLayout(config, activePageId, { ...layout, items: [...layout.items, item] });
    }
    case "updateWidgetProps": {
      const widgetId = String(raw.args.widgetId ?? "");
      const patch = (raw.args.props ?? {}) as Record<string, unknown>;
      const item = layout.items.find((i) => i.id === widgetId);
      if (!item) return config;
      const schema = getWidget(item.widget)?.configSchema ?? [];
      const allowed = new Map(schema.map((p) => [p.name, p.type]));
      const safePatch: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(patch)) {
        const type = allowed.get(key);
        if (!type) continue; // clé hors configSchema : jamais fusionnée telle quelle
        safePatch[key] = coerceProp(value, type);
      }
      return setPageLayout(config, activePageId, {
        ...layout,
        items: layout.items.map((i) =>
          i.id === widgetId ? { ...i, props: { ...i.props, ...safePatch } } : i,
        ),
      });
    }
    case "removeWidget": {
      const widgetId = String(raw.args.widgetId ?? "");
      return setPageLayout(config, activePageId, {
        ...layout,
        items: layout.items.filter((i) => i.id !== widgetId),
      });
    }
    case "addDataSource": {
      const { id, type, service, layer } = raw.args as {
        id: string;
        type: DataSource["type"];
        service: string;
        layer: string;
      };
      if (!id || config.dataSources.some((s) => s.id === id)) return config;
      const source: DataSource = { id, type, service, layer, query: {} };
      return { ...config, dataSources: [...config.dataSources, source] };
    }
    case "setFilter": {
      const dataSourceId = String(raw.args.dataSourceId ?? "");
      const query = (raw.args.query ?? {}) as Record<string, unknown>;
      return {
        ...config,
        dataSources: config.dataSources.map((s) => (s.id === dataSourceId ? { ...s, query } : s)),
      };
    }
    default:
      return config;
  }
}
