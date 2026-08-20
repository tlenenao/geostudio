## Task 9: Shell — `applyClientOp.ts`

**Files:**
- Create: `shell/src/builder/copilot/applyClientOp.ts`
- Create: `shell/src/builder/copilot/applyClientOp.test.ts`

**Interfaces:**
- Consumes: `getWidget` (`../registry`), `getPageLayout`/`setPageLayout` (`../pages`), `nextFreePosition` (`../grid`), `AppConfig`/`DataSource`/`WidgetItem` (`../../api/types`).
- Produces: `RawClientOp` type, `applyClientOp(raw: RawClientOp, config: AppConfig, activePageId: string): AppConfig` (pure). Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/copilot/applyClientOp.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach } from "vitest";
import type { AppConfig } from "../../api/types";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { applyClientOp } from "./applyClientOp";

function emptyConfig(): AppConfig {
  return {
    kind: "app", theme: {} as AppConfig["theme"], dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

describe("applyClientOp", () => {
  beforeEach(() => {
    _resetRegistry();
    registerBuiltinWidgets();
  });

  it("addWidget adds an item with the widget's default props/size", () => {
    const config = applyClientOp({ op: "addWidget", args: { type: "text" } }, emptyConfig(), "page-1");
    expect(config.layout.items).toHaveLength(1);
    expect(config.layout.items[0].widget).toBe("text");
    expect(config.layout.items[0].props).toEqual({ text: "Nouveau texte", dataSourceId: "" });
  });

  it("addWidget with an unknown type is a no-op", () => {
    const config = applyClientOp({ op: "addWidget", args: { type: "not-a-real-widget" } }, emptyConfig(), "page-1");
    expect(config.layout.items).toHaveLength(0);
  });

  it("updateWidgetProps merges only keys present in configSchema, coerced by type", () => {
    let config = applyClientOp({ op: "addWidget", args: { type: "indicator" } }, emptyConfig(), "page-1");
    const widgetId = config.layout.items[0].id;
    config = applyClientOp(
      { op: "updateWidgetProps", args: { widgetId, props: { label: "Incidents ouverts", agg: 42, notARealProp: "x" } } },
      config, "page-1",
    );
    expect(config.layout.items[0].props).toEqual({
      dataSourceId: "", label: "Incidents ouverts", agg: "42", field: "",
    });
  });

  it("removeWidget removes the item by id", () => {
    let config = applyClientOp({ op: "addWidget", args: { type: "text" } }, emptyConfig(), "page-1");
    const widgetId = config.layout.items[0].id;
    config = applyClientOp({ op: "removeWidget", args: { widgetId } }, config, "page-1");
    expect(config.layout.items).toHaveLength(0);
  });

  it("addDataSource appends a new source, ignoring a duplicate id", () => {
    let config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" } },
      emptyConfig(), "page-1",
    );
    expect(config.dataSources).toEqual([{ id: "ds1", type: "features", service: "ogc", layer: "incidents", query: {} }]);
    config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "other" } },
      config, "page-1",
    );
    expect(config.dataSources).toHaveLength(1); // duplicate id ignored
  });

  it("setFilter updates an existing source's query", () => {
    let config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" } },
      emptyConfig(), "page-1",
    );
    config = applyClientOp(
      { op: "setFilter", args: { dataSourceId: "ds1", query: { status: "open" } } },
      config, "page-1",
    );
    expect(config.dataSources[0].query).toEqual({ status: "open" });
  });

  it("an unknown op name is a no-op, never throws", () => {
    const config = emptyConfig();
    const result = applyClientOp({ op: "deleteEverything", args: {} }, config, "page-1");
    expect(result).toBe(config);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: FAIL — `Cannot find module './applyClientOp'`.

- [ ] **Step 3: Implement**

Create `shell/src/builder/copilot/applyClientOp.ts`:

```ts
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

export function applyClientOp(raw: RawClientOp, config: AppConfig, activePageId: string): AppConfig {
  const layout = getPageLayout(config, activePageId);

  switch (raw.op) {
    case "addWidget": {
      const type = String(raw.args.type ?? "");
      const def = getWidget(type);
      if (!def) return config;
      const { x, y } = nextFreePosition(layout.items);
      const item: WidgetItem = {
        id: crypto.randomUUID(), widget: type, x, y,
        w: def.defaultSize.w, h: def.defaultSize.h, props: { ...def.defaultProps },
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
        items: layout.items.map((i) => (i.id === widgetId ? { ...i, props: { ...i.props, ...safePatch } } : i)),
      });
    }
    case "removeWidget": {
      const widgetId = String(raw.args.widgetId ?? "");
      return setPageLayout(config, activePageId, {
        ...layout, items: layout.items.filter((i) => i.id !== widgetId),
      });
    }
    case "addDataSource": {
      const { id, type, service, layer } = raw.args as { id: string; type: DataSource["type"]; service: string; layer: string };
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/copilot/applyClientOp.ts shell/src/builder/copilot/applyClientOp.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): applyClientOp.ts — exécute les opérations du copilote (SP-20)

Pure, réutilise nextFreePosition/getPageLayout/setPageLayout — même
chemin que la palette/PropsPanel. updateWidgetProps filtre et coerce par
configSchema (jamais un merge opaque) ; un op au nom inconnu est un no-op.
EOF
)"
```

---

