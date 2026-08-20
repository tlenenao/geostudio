## Task 7: Shell — `registry.ts` gains `configSchema`, backfill 22 builtin widgets

**Files:**
- Create: `shell/src/builder/widgetPropSchema.ts`
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/widgets/dateRangeFilter.tsx`, `datasetCard.tsx`, `chart.tsx`, `data.tsx` (list + table), `drawer.tsx`, `indicator.tsx`, `index.tsx` (text + image + button), `gallery.tsx`, `hero.tsx`, `richSection.tsx`, `filter.tsx`, `selectFilter.tsx`, `mapWidget.tsx`, `navigation.tsx`, `modal.tsx`, `tabs.tsx`, `sliderFilter.tsx`, `form.tsx`, `pivot.tsx`
- Create: `shell/src/builder/widgetPropSchema.test.ts`

**Interfaces:**
- Produces: `WidgetPropDescriptor` type (`shell/src/builder/widgetPropSchema.ts`), `WidgetDefinition.configSchema?: WidgetPropDescriptor[]` (`registry.ts`). Consumed by Task 9 (`clientTools.ts`) and Task 10 (`applyClientOp.ts`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/widgetPropSchema.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry, listWidgets } from "./registry";
import { registerBuiltinWidgets } from "./widgets";

describe("configSchema", () => {
  it("every builtin widget declares a configSchema (possibly empty)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    for (const w of listWidgets()) {
      expect(w.configSchema, `widget "${w.type}" has no configSchema`).toBeDefined();
    }
  });

  it("text widget's configSchema matches its scalar defaultProps", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const text = listWidgets().find((w) => w.type === "text");
    expect(text?.configSchema).toEqual([
      { name: "text", type: "string", label: "Texte", default: "Nouveau texte" },
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ]);
  });

  it("chart widget's configSchema covers all 15 scalar props", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const chart = listWidgets().find((w) => w.type === "chart");
    expect(chart?.configSchema).toHaveLength(15);
    expect(chart?.configSchema?.map((p) => p.name)).toContain("chartType");
  });

  it("tabs widget has an empty configSchema (its only prop, `tabs`, is array-shaped, out of scope for v1)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const tabs = listWidgets().find((w) => w.type === "tabs");
    expect(tabs?.configSchema).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts`
Expected: FAIL — `Cannot find module './widgetPropSchema'`.

- [ ] **Step 3: Create the shared type**

Create `shell/src/builder/widgetPropSchema.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Forme partagée par WidgetDefinition.configSchema (builtin widgets, ce
// fichier) et WcWidgetManifest.props (widgets WC/extension, SP-8,
// shell/src/builder/wc/manifest.ts) — même shape, délibérément non
// unifiées par un import commun pour ne pas toucher le module SP-8 : le
// typage structurel de TypeScript suffit à rendre les deux compatibles
// partout où clientTools.ts (Task 9) les consomme ensemble.
export type WidgetPropDescriptor = {
  name: string;
  type: "string" | "number" | "boolean" | "dataSource";
  label: string;
  default: unknown;
};
```

- [ ] **Step 4: Add `configSchema` to `WidgetDefinition`**

In `shell/src/builder/registry.ts`, add the import and the field:

Change:
```ts
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
```
to:
```ts
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
import type { WidgetPropDescriptor } from "./widgetPropSchema";
```

Change:
```ts
export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};
```
to:
```ts
export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  // Sous-ensemble des props éditables par le copilote (SP-20) — seules les
  // props scalaires (string/number/boolean/dataSource) ; les props
  // array/object (colonnes de table, items de tiroir, encodages...) restent
  // hors de portée, non listées ici.
  configSchema?: WidgetPropDescriptor[];
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};
```

- [ ] **Step 5: Backfill each widget**

`shell/src/builder/widgets/dateRangeFilter.tsx`:
```ts
    defaultProps: { label: "Période" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { label: "Période" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [{ name: "label", type: "string", label: "Libellé", default: "Période" }],
```

`shell/src/builder/widgets/datasetCard.tsx`:
```ts
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "showDownload", type: "boolean", label: "Afficher le téléchargement", default: true },
      { name: "title", type: "string", label: "Titre", default: "" },
    ],
```

`shell/src/builder/widgets/chart.tsx`:
```ts
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous",
    },
```
Insert right after that closing `},` of `defaultProps` (before `defaultSize`):
```ts
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "chartType", type: "string", label: "Type de graphique", default: "bar" },
      { name: "categoryField", type: "string", label: "Champ catégorie", default: "" },
      { name: "valueField", type: "string", label: "Champ valeur", default: "" },
      { name: "stack", type: "boolean", label: "Empilé", default: false },
      { name: "legend", type: "boolean", label: "Légende", default: true },
      { name: "zoom", type: "boolean", label: "Zoom", default: false },
      { name: "xAxisType", type: "string", label: "Type d'axe X", default: "category" },
      { name: "yAxisType", type: "string", label: "Type d'axe Y", default: "value" },
      { name: "yAxisFormat", type: "string", label: "Format axe Y", default: "" },
      { name: "yAxisUnit", type: "string", label: "Unité axe Y", default: "" },
      { name: "title", type: "string", label: "Titre", default: "" },
      { name: "advancedOption", type: "string", label: "Option ECharts avancée (JSON)", default: "" },
      { name: "compareEnabled", type: "boolean", label: "Comparaison de période", default: false },
      { name: "comparePeriod", type: "string", label: "Période de comparaison", default: "previous" },
    ],
```

`shell/src/builder/widgets/data.tsx` — two widgets in this file. For `type: "list"`:
```ts
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "titleField", type: "string", label: "Champ titre", default: "" },
    ],
```
For `type: "table"`:
```ts
    defaultProps: { dataSourceId: "", columns: [], pageSize: 10 },
    defaultSize: { w: 6, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", columns: [], pageSize: 10 },
    defaultSize: { w: 6, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "pageSize", type: "number", label: "Lignes par page", default: 10 },
    ],
```

`shell/src/builder/widgets/drawer.tsx`:
```ts
    defaultProps: { title: "Tiroir", items: [], side: "right" },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { title: "Tiroir", items: [], side: "right" },
    defaultSize: { w: 3, h: 1 },
    configSchema: [
      { name: "title", type: "string", label: "Titre", default: "Tiroir" },
      { name: "side", type: "string", label: "Côté", default: "right" },
    ],
```

`shell/src/builder/widgets/indicator.tsx`:
```ts
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
```
→
```ts
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Indicateur" },
      { name: "agg", type: "string", label: "Agrégation", default: "count" },
      { name: "field", type: "string", label: "Champ", default: "" },
    ],
```

`shell/src/builder/widgets/index.tsx` — three widgets. For `type: "text"`:
```ts
    defaultProps: { text: "Nouveau texte", dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
```
→
```ts
    defaultProps: { text: "Nouveau texte", dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
    configSchema: [
      { name: "text", type: "string", label: "Texte", default: "Nouveau texte" },
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ],
```
For `type: "image"`:
```ts
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "src", type: "string", label: "URL", default: "" },
      { name: "alt", type: "string", label: "Texte alternatif", default: "" },
    ],
```
For `type: "button"`:
```ts
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
```
→
```ts
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    configSchema: [
      { name: "label", type: "string", label: "Libellé", default: "Bouton" },
      { name: "href", type: "string", label: "Lien", default: "" },
    ],
```

`shell/src/builder/widgets/gallery.tsx`:
```ts
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
```
→
```ts
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
    configSchema: [
      { name: "type", type: "string", label: "Type d'item", default: "" },
      { name: "tag", type: "string", label: "Tag", default: "" },
      { name: "limit", type: "number", label: "Nombre max", default: 12 },
      { name: "columns", type: "number", label: "Colonnes", default: 3 },
    ],
```

`shell/src/builder/widgets/hero.tsx`:
```ts
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
```
→
```ts
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
    configSchema: [
      { name: "title", type: "string", label: "Titre", default: "Titre" },
      { name: "subtitle", type: "string", label: "Sous-titre", default: "" },
      { name: "backgroundImageUrl", type: "string", label: "Image de fond (URL)", default: "" },
      { name: "ctaLabel", type: "string", label: "Libellé du bouton", default: "" },
      { name: "ctaHref", type: "string", label: "Lien du bouton", default: "" },
      { name: "align", type: "string", label: "Alignement", default: "left" },
    ],
```

`shell/src/builder/widgets/richSection.tsx`:
```ts
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
```
→
```ts
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
    configSchema: [{ name: "markdown", type: "string", label: "Markdown", default: "" }],
```

`shell/src/builder/widgets/filter.tsx`:
```ts
    defaultProps: { field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 1 },
    configSchema: [
      { name: "field", type: "string", label: "Champ à filtrer", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/selectFilter.tsx`:
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
```
→
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "field", type: "string", label: "Champ", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/mapWidget.tsx`:
```ts
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
```
→
```ts
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    configSchema: [{ name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" }],
```

`shell/src/builder/widgets/navigation.tsx`:
```ts
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [{ name: "direction", type: "string", label: "Direction", default: "horizontal" }],
```

`shell/src/builder/widgets/modal.tsx`:
```ts
    defaultProps: { title: "Modale", items: [] },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { title: "Modale", items: [] },
    defaultSize: { w: 3, h: 1 },
    configSchema: [{ name: "title", type: "string", label: "Titre", default: "Modale" }],
```

`shell/src/builder/widgets/tabs.tsx`:
```ts
    defaultProps: { tabs: [{ id: "tab-1", label: "Onglet 1", items: [] }] },
    defaultSize: { w: 6, h: 6 },
```
→
```ts
    defaultProps: { tabs: [{ id: "tab-1", label: "Onglet 1", items: [] }] },
    defaultSize: { w: 6, h: 6 },
    // Son seul champ, `tabs`, est array-shaped — hors de portée pour
    // updateWidgetProps en v1 (cf. Global Constraints). Rien à lister ici.
    configSchema: [],
```

`shell/src/builder/widgets/sliderFilter.tsx`:
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "field", type: "string", label: "Champ", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/form.tsx`:
```ts
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
```
→
```ts
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
    // `fields` est array-shaped (hors de portée) ; `geometryType` est un
    // enum nullable qui ne rentre pas dans les 4 types de
    // WidgetPropDescriptor — laissé de côté plutôt que forcé.
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "submitLabel", type: "string", label: "Libellé du bouton", default: "Enregistrer" },
    ],
```

`shell/src/builder/widgets/pivot.tsx`:
```ts
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "title", type: "string", label: "Titre", default: "" },
    ],
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts src/builder/registry.test.tsx`
Expected: PASS.

- [ ] **Step 7: Run the full shell type-check + test suite**

Run: `cd shell && npm run build && npm run test`
Expected: PASS (tsc --noEmit + vite build succeed, all 22 widget files still register correctly, no other test broke).

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgetPropSchema.ts shell/src/builder/registry.ts shell/src/builder/widgets/ shell/src/builder/widgetPropSchema.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): configSchema sur WidgetDefinition, backfill des 22 widgets (SP-20)

Chaque widget builtin déclare désormais la liste de ses props scalaires
éditables (string/number/boolean/dataSource) — les props array/object
(columns, items, fields, encodings, tabs) restent hors schéma, hors
périmètre v1 du copilote. Base pour clientTools.ts (génération des outils
"client" depuis le registre, Task 9).
EOF
)"
```

---

