## Task 8: Shell — `clientTools.ts`

**Files:**
- Create: `shell/src/builder/copilot/clientTools.ts`
- Create: `shell/src/builder/copilot/clientTools.test.ts`

**Interfaces:**
- Consumes: `listWidgets()` (`../registry`), `WidgetPropDescriptor` (`../widgetPropSchema`).
- Produces: `buildClientToolSchemas(): Array<{ name: string; description: string; inputSchema: Record<string, unknown> }>`. Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/copilot/clientTools.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { buildClientToolSchemas } from "./clientTools";

describe("buildClientToolSchemas", () => {
  it("returns exactly the 5 client tools by name", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const names = buildClientToolSchemas().map((t) => t.name);
    expect(names).toEqual(["addWidget", "updateWidgetProps", "removeWidget", "addDataSource", "setFilter"]);
  });

  it("addWidget's enum lists every registered widget type", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const addWidget = buildClientToolSchemas().find((t) => t.name === "addWidget")!;
    const enumValues = (addWidget.inputSchema as { properties: { type: { enum: string[] } } }).properties.type.enum;
    expect(enumValues).toContain("text");
    expect(enumValues).toContain("chart");
    expect(enumValues).toHaveLength(22);
  });

  it("updateWidgetProps' schema includes chart's scalar fields", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const updateProps = buildClientToolSchemas().find((t) => t.name === "updateWidgetProps")!;
    const props = (updateProps.inputSchema as { properties: { props: { properties: Record<string, unknown> } } })
      .properties.props.properties;
    expect(props).toHaveProperty("chartType");
    expect(props).toHaveProperty("dataSourceId");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/copilot/clientTools.test.ts`
Expected: FAIL — `Cannot find module './clientTools'`.

- [ ] **Step 3: Implement**

Create `shell/src/builder/copilot/clientTools.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Schémas d'outils "client" pour le copilote (SP-20) — générés depuis le
// registre de widgets plutôt que maintenus à la main : un nouveau widget
// (builtin ou WC/extension — configSchema et WcWidgetManifest.props ont la
// même forme, cf. widgetPropSchema.ts) devient automatiquement éditable
// sans code copilote supplémentaire. Reconstruits à chaque tour (jamais mis
// en cache) pour capter les extensions chargées dynamiquement après le
// montage du builder (useActiveExtensions).
import { listWidgets } from "../registry";
import type { WidgetPropDescriptor } from "../widgetPropSchema";

type ClientToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };

function jsonSchemaForProp(p: WidgetPropDescriptor): Record<string, unknown> {
  if (p.type === "boolean") return { type: "boolean", description: p.label };
  if (p.type === "number") return { type: "number", description: p.label };
  return { type: "string", description: p.label }; // "string" | "dataSource"
}

export function buildClientToolSchemas(): ClientToolSchema[] {
  const widgets = listWidgets();
  const widgetTypes = widgets.map((w) => w.type);

  const updateProperties: Record<string, unknown> = {};
  for (const w of widgets) {
    for (const p of w.configSchema ?? []) {
      updateProperties[p.name] = jsonSchemaForProp(p);
    }
  }

  return [
    {
      name: "addWidget",
      description: "Ajoute un widget sur la page en cours d'édition, avec ses props par défaut.",
      inputSchema: {
        type: "object",
        properties: { type: { type: "string", enum: widgetTypes, description: "Type de widget à ajouter" } },
        required: ["type"],
      },
    },
    {
      name: "updateWidgetProps",
      description: "Modifie les props d'un widget déjà présent sur le canevas, identifié par son id.",
      inputSchema: {
        type: "object",
        properties: {
          widgetId: { type: "string", description: "Identifiant du widget (item.id)" },
          props: { type: "object", description: "Propriétés à fusionner sur le widget", properties: updateProperties },
        },
        required: ["widgetId", "props"],
      },
    },
    {
      name: "removeWidget",
      description: "Retire un widget de la page en cours d'édition.",
      inputSchema: {
        type: "object",
        properties: { widgetId: { type: "string", description: "Identifiant du widget (item.id)" } },
        required: ["widgetId"],
      },
    },
    {
      name: "addDataSource",
      description: "Ajoute une source de données à la config.",
      inputSchema: {
        type: "object",
        properties: {
          id: { type: "string" },
          type: { type: "string", enum: ["features", "static", "statistics"] },
          service: { type: "string" },
          layer: { type: "string", description: "Identifiant de la collection ou du dataset" },
        },
        required: ["id", "type", "service", "layer"],
      },
    },
    {
      name: "setFilter",
      description: "Modifie la requête (filtre) d'une source de données existante.",
      inputSchema: {
        type: "object",
        properties: {
          dataSourceId: { type: "string" },
          query: { type: "object", description: "Objet de requête/filtre appliqué à la source" },
        },
        required: ["dataSourceId", "query"],
      },
    },
  ];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/copilot/clientTools.test.ts`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/copilot/clientTools.ts shell/src/builder/copilot/clientTools.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): clientTools.ts — schémas d'outils client générés du registre (SP-20)

buildClientToolSchemas() dérive addWidget/updateWidgetProps/removeWidget/
addDataSource/setFilter depuis registry.ts (configSchema) — un widget
enregistré devient éditable par le copilote sans code dédié.
EOF
)"
```

---

