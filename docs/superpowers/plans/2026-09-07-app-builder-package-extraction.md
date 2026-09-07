# Extraction de `shell/src/builder` + `shell/src/ui/kit` en packages partagés Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `shell/src/ui/kit` and `shell/src/builder` (+ `shell/src/map`) into two npm-workspace packages (`packages/ui-kit`, `packages/app-builder`) that `shell/` consumes exactly as before, with the app-builder package receiving its data/identity/i18n dependencies through three injected ports instead of importing `ItemClient`/`useAuth`/`i18n` directly — so a second project (`finance`) can consume the same source via `file:` dependency.

**Architecture:** A root `package.json` turns geostudio into an npm workspace (`shell`, `packages/*`). `packages/ui-kit` is a verbatim relocation of `ui/kit` (no port needed — it has no data/identity/i18n coupling beyond the package's own bundled `i18n` catalog). `packages/app-builder` is `builder/` + `map/` relocated, minus the sub-trees that pilot geostudio-specific platform objects (`pipeline/`, `visualQuery/`, `copilot/`, `print/`, `report/`, `appexport/`, `examples/`, `AlertRuleEditor.tsx`, `ConfigHistoryPanel.tsx`, `aggregates.ts` — these stay in `shell/src/builder/` and import the package). The only files that change *behavior* (not just location) are `DataContext.tsx`, `AppRenderer.tsx` (its `ActionConditionBridge`), and `DatasetDownloadButtons.tsx` — each rewired from a direct `ItemClient`/`useAuth`/`i18n` import to a new `AppBuilderProvider` context carrying `BuilderDataClient`, `IdentityPort`, `I18nPort`. Every other moved file is unchanged content at a new path. TypeScript source is consumed directly (no package build step) by both `vite`/`vitest` in `shell` and, later, in `finance`.

**Tech Stack:** React 19, TypeScript, Vite 8 + Vitest, `@tanstack/react-query` 5, npm workspaces (no new package manager). No new runtime dependency — `echarts`, `maplibre-gl`, `@deck.gl/*`, `@loaders.gl/3d-tiles`, `lit`, `dompurify`, `marked`, `cel-js` all already exist in `shell/package.json` and move to the packages' `peerDependencies`.

## Global Constraints

- **`cd shell && npm run test` must stay green after every task that touches `shell/`** (unit + component tests, Vitest). Run it at the end of every task, not just at the end of the plan.
- **E2E must be 166 passed / 4 skipped / 0 failed at the end of the plan** (current baseline, `shell/` root, commit `a320c317` per `CLAUDE.md`) — run `npm run e2e` in `shell/` as the Task 12 gate, not before (E2E is slow; unit tests + typecheck are the per-task gate).
- **No package has a `dist/` build step.** `packages/*/package.json` `"main"`/`"types"` point at `src/index.ts`; both `shell` and `finance` compile the package's TypeScript source directly. If Task 1's spike shows this doesn't work, stop and escalate — every later task depends on it.
- **Moved files keep their content unchanged unless a step explicitly shows a diff.** A task that only relocates files must not "clean up" or refactor anything else in the same commit — separate concerns, separate commits.
- **`SPDX-License-Identifier: Apache-2.0` header stays on every moved file** — `git mv` preserves it automatically; do not strip it.
- Docs and commit messages in French, code/identifiers in English — existing project convention (`CLAUDE.md`).
- Conventional commits (`feat(shell): …`, `refactor(shell): …`), one subject per commit, per project convention.
- Branch: **`dev`, local only** (already checked out) — no new branch, no local `main`.

---

## File Structure

```
geostudio/
  package.json                          NEW: npm workspace root
  packages/
    ui-kit/
      package.json                      NEW
      tsconfig.json                     NEW
      src/                              MOVED from shell/src/ui/kit (39 files + 40 tests)
        index.ts, Button.tsx, Panel.tsx, ... (unchanged content)
    app-builder/
      package.json                      NEW
      tsconfig.json                     NEW
      src/
        ports/
          dataClient.ts                 NEW: BuilderDataClient type
          identity.ts                   NEW: IdentityPort type
          i18n.ts                       NEW: I18nPort type
          AppBuilderProvider.tsx         NEW: React context wiring the 3 ports
        types/
          index.ts                      NEW: cut from shell/src/api/types.ts (§ Task 3)
        core/                           MOVED (+ 2 files modified: DataContext.tsx, AppRenderer.tsx)
        editor/                         MOVED
        widgets/                        MOVED (+ EChart.tsx, datasetDownload.ts, DatasetDownloadButtons.tsx modified)
        map/                            MOVED
        wc/                             MOVED
        i18n/
          catalog.fr.ts                 NEW: cut from shell/src/i18n/catalog.fr.ts (§ Task 10)
          index.ts                      NEW: package-local t(), same signature as shell's
  shell/
    package.json                        MODIFY: add @geostudio/ui-kit, @geostudio/app-builder workspace deps
    src/
      api/types.ts                       MODIFY: re-export moved types from @geostudio/app-builder
      builder/
        geostudioDataClient.ts           NEW: ItemClient -> BuilderDataClient adapter
        pipeline/, visualQuery/, copilot/, print/, report/, appexport/, examples/,
        AlertRuleEditor.tsx, ConfigHistoryPanel.tsx, aggregates.ts  MODIFY: imports -> @geostudio/app-builder
      shell/                             MODIFY: mount <AppBuilderProvider> where AppRenderer is used
      ui/kit/                            DELETED (moved to packages/ui-kit)
      map/                               DELETED (moved to packages/app-builder)
```

---

### Task 1: Workspace + package feasibility spike (go/no-go)

**Files:**
- Create: `package.json` (repo root)
- Create: `packages/ui-kit/package.json`
- Create: `packages/ui-kit/tsconfig.json`
- Create: `packages/ui-kit/src/index.ts`
- Create: `packages/ui-kit/src/Spike.tsx`
- Modify: `shell/package.json`
- Modify: `shell/tsconfig.json`

**Interfaces:**
- Produces: proof that `shell` can `import { Spike } from "@geostudio/ui-kit"` and both `vite build` and `vitest run` succeed with zero build step in the package. Every later task depends on this working.

- [ ] **Step 1: Create the workspace root `package.json`**

```json
{
  "name": "geostudio",
  "private": true,
  "version": "0.0.0",
  "workspaces": ["shell", "packages/*"]
}
```

- [ ] **Step 2: Create the minimal `packages/ui-kit` package**

`packages/ui-kit/package.json`:
```json
{
  "name": "@geostudio/ui-kit",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  }
}
```

`packages/ui-kit/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

`packages/ui-kit/src/Spike.tsx`:
```tsx
// SPDX-License-Identifier: Apache-2.0
export function Spike() {
  return <span>spike-ok</span>;
}
```

`packages/ui-kit/src/index.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
export { Spike } from "./Spike";
```

- [ ] **Step 3: Wire `shell` to consume it**

Run: `cd /home/lenen/projets/geostudio && npm install` (creates the workspace symlink `shell/node_modules/@geostudio/ui-kit` -> `packages/ui-kit`).

Add to `shell/package.json` `"dependencies"`:
```json
    "@geostudio/ui-kit": "workspace:*",
```

- [ ] **Step 4: Prove it compiles and renders, in a throwaway spot**

Temporarily add to `shell/src/pages/AppBuilderPage.tsx` (top of file, will be removed in Step 6):
```tsx
import { Spike } from "@geostudio/ui-kit";
```
and render `<Spike />` anywhere in the returned JSX.

- [ ] **Step 5: Run the two real gates**

Run: `cd shell && npx tsc --noEmit`
Expected: 0 errors (proves TS source resolution across the workspace boundary works with no package build step).

Run: `cd shell && npm run build`
Expected: build succeeds, `spike-ok` would render (don't need to actually run the app — the build succeeding is the proof).

If either fails: **stop, do not proceed to Task 2.** The failure mode to check first: `moduleResolution: "bundler"` in `shell/tsconfig.json` needs `"paths"` or npm workspace symlinks to resolve `@geostudio/ui-kit` — if `tsc` can't find it, add an explicit path mapping in `shell/tsconfig.json`:
```json
    "paths": { "@/*": ["src/*"], "@geostudio/ui-kit": ["../packages/ui-kit/src/index.ts"] }
```
and retry.

- [ ] **Step 6: Remove the spike, keep the scaffold**

Revert the `Spike` import/render from `AppBuilderPage.tsx` (`git checkout shell/src/pages/AppBuilderPage.tsx`). Keep `Spike.tsx`/`index.ts` in the package for now — Task 2 replaces them with the real `ui/kit` content.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add package.json packages/ui-kit shell/package.json shell/tsconfig.json package-lock.json
git commit -m "build: npm workspace root + packages/ui-kit spike (TS source, no build step)"
```

---

### Task 2: Move `ui/kit` to `packages/ui-kit`

**Files:**
- Move (git mv, unchanged content): all 39 non-test + 40 test files below, from `shell/src/ui/kit/` to `packages/ui-kit/src/`.
- Modify: every file under `shell/src/` that imports `../ui/kit/*` or `../../ui/kit/*` — path becomes `@geostudio/ui-kit`.
- Modify: `packages/ui-kit/src/index.ts` — real barrel export.
- Delete: `packages/ui-kit/src/Spike.tsx` (superseded by real content).

**Interfaces:**
- Produces: `@geostudio/ui-kit` exports the same names `ui/kit/index.ts` did today (verify by diffing exports before/after — see Step 4).

- [ ] **Step 1: List the exact files to move**

```bash
cd /home/lenen/projets/geostudio/shell/src
find ui/kit -maxdepth 1 -name "*.ts*" | sort
```

Confirmed set (39 non-test + `index.ts` + `testUtils.ts` + `usePanelTrigger.ts`, plus their 40 `*.test.*` companions): `Avatar`, `Badge`, `Banner`, `Breadcrumb`, `Button`, `Checkbox`, `Chip`, `ColorField`, `Combobox`, `ConfirmDialog`, `DataTable`, `Dialog`, `Drawer`, `EmptyState`, `Field`, `IconButton`, `Input`, `Kbd`, `Menu`, `NumberField`, `Panel`, `Popover`, `Progress`, `Radio`, `Section`, `Segmented`, `Select`, `Skeleton`, `Slider`, `Spinner`, `Splitter`, `Switch`, `Table`, `Tabs`, `Textarea`, `Toast`, `Toolbar`, `Tooltip`, `Tree` (`.tsx` + `.test.tsx` each), `index.ts`, `testUtils.ts` (+ `.test.ts`), `usePanelTrigger.ts` (+ `.test.ts`).

- [ ] **Step 2: Move them**

```bash
cd /home/lenen/projets/geostudio
rm packages/ui-kit/src/Spike.tsx
git mv shell/src/ui/kit/*.tsx shell/src/ui/kit/*.ts packages/ui-kit/src/
```

(If `git mv` complains about mixing globs with a single destination on your shell, loop instead: `for f in shell/src/ui/kit/*.ts shell/src/ui/kit/*.tsx; do git mv "$f" packages/ui-kit/src/; done`.)

- [ ] **Step 3: Rewrite `packages/ui-kit/src/index.ts`**

Read the pre-move `index.ts` content (already moved verbatim by Step 2 — no edit needed *unless* it imported something outside `ui/kit/`, e.g. `../../i18n`). Check:

```bash
grep -n "^import" packages/ui-kit/src/index.ts packages/ui-kit/src/*.tsx | grep -v "\"\./"
```

For every import found pointing outside the moved tree (expected: `../../i18n` from a handful of files per the design spec's grep — `t()` calls), replace with a package-local i18n:

Create `packages/ui-kit/src/i18n.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
// Minimal i18n port for ui-kit: components needing t() (DataTable's empty-state
// copy, etc.) call this. The app-builder package's own I18nPort (Task 4 of the
// app-builder plan) is unrelated — ui-kit has no injected provider, its `t()`
// isn't overridable, and none of ui-kit's callers need it to be (short,
// generic UI strings, not domain copy).
export function t(key: string, params?: Record<string, string | number>): string {
  if (params === undefined) return key;
  return key.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}
```

In every moved file that had `import { t } from "../../i18n"`, change to `import { t } from "./i18n"`.

- [ ] **Step 4: Update every consumer in `shell/src/`**

```bash
cd /home/lenen/projets/geostudio/shell/src
grep -rl "ui/kit/" --include="*.ts" --include="*.tsx" . | grep -v "^ui/kit"
```

For each match, rewrite the import path: any `"../ui/kit/X"`, `"../../ui/kit/X"`, `"./ui/kit/X"` becomes `"@geostudio/ui-kit"` — and if the file imported a single named export (e.g. `import { Button } from "../../ui/kit/Button"`), the package barrel re-exports everything from `index.ts`, so the import becomes `import { Button } from "@geostudio/ui-kit"`. Do this with a script, not by hand, to avoid missing one:

```bash
cd /home/lenen/projets/geostudio/shell/src
grep -rlE 'from "(\.\./)+ui/kit/[A-Za-z]+"' --include="*.ts" --include="*.tsx" . \
  | xargs sed -i -E 's#from "(\.\./)+ui/kit/[A-Za-z]+"#from "@geostudio/ui-kit"#g'
```

Add `"@geostudio/ui-kit": "workspace:*"` to `shell/package.json` if Task 1 didn't already (it did — verify it's still there, not reverted by Step 6 of Task 1).

- [ ] **Step 5: Typecheck and fix fallout**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: errors only for duplicate-name imports (a file that imported two components from two different `ui/kit` files now has two `import { X } from "@geostudio/ui-kit"` lines) — merge them into one import statement by hand, file by file, until 0 errors.

- [ ] **Step 6: Run tests**

Run: `cd /home/lenen/projets/geostudio/shell && npm run test`
Expected: same pass count as before this task (`ui/kit`'s own tests now run from `packages/ui-kit/src/*.test.tsx` — confirm `shell`'s `vitest.config`/`vite.config.ts` `test.include` default picks up files outside `shell/src` via the workspace, or add `packages/ui-kit/src/**/*.test.tsx` — actually **run ui-kit's tests from the package itself**, not from `shell`: add a minimal `packages/ui-kit/vitest.config.ts` reusing `shell`'s `test.environment: "jsdom"` / `setupFiles` pattern, and run `cd packages/ui-kit && npx vitest run` separately).

`packages/ui-kit/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true },
});
```

Run: `cd /home/lenen/projets/geostudio/packages/ui-kit && npx vitest run`
Expected: all 40 `ui/kit` test files pass, same assertions as before the move (content unchanged).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): move ui/kit to packages/ui-kit"
```

---

### Task 3: Extract `AppConfig`-related types into `packages/app-builder/src/types`

**Files:**
- Create: `packages/app-builder/src/types/index.ts`
- Modify: `shell/src/api/types.ts` — replace each moved block with a re-export.

**Interfaces:**
- Produces: `@geostudio/app-builder` exports `AppConfig`, `DataSource`, `DataSourceState`, `DatasetConfig`, `CreateDatasetInput` stays in `shell` (not moved — only `DatasetPage`/dataset admin use it, outside the builder), `Page`, `WidgetItem`, `AppLayout`, `Variable`, `VariableType`, `ActionMessage`, `Theme`, `ThemeColors`, `RenderMode`, `PrintLayoutConfig`, `MapConfig`, `MapLayer`, `MapViewport`, `BaseMap`, `PopupConfig`, `PopupField`, `MapTerrainConfig`, `LayerSource`, `CollectionSchema`, `CollectionSchemaField`, `CollectionFieldType`, `DataRecord`, `DatasetColumnMeta`, `CrossFilterLink`.
- Consumes (from `shell/src/api/types.ts`, exact text, already read in full while writing this plan — reproduce verbatim, do not retype from memory): see Step 1.

- [ ] **Step 1: Create the package types file with the confirmed type set**

`packages/app-builder/src/types/index.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
// Moved from shell/src/api/types.ts (2026-09-07) — the AppConfig-shaped
// subset consumed by the app builder runtime/editor/widgets. shell/src/api/types.ts
// re-exports these names for backward compatibility with the rest of shell/.

export type MapViewport = {
  center: [number, number];
  zoom: number;
  pitch?: number;
  bearing?: number;
};
export type BaseMap = { style: string };
export type PopupField = { name: string; label?: string };
// Le popup d'une couche, déclaratif (règle 2 de CLAUDE.md). `template` non
// vide l'emporte sur titleField/fields. L'absence de `popup` sur la couche EST
// l'état désactivé : il n'y a pas de drapeau `enabled`.
export type PopupConfig = {
  titleField?: string;
  fields?: PopupField[];
  template?: string;
  attachmentField?: string;
};
export type MapLayer =
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "vector";
      tilesUrl: string;
      sourceLayer: string;
      paint?: Record<string, unknown>;
      collectionId?: string;
      geometryKind?: "point" | "line" | "polygon";
      pkColumn?: string;
      popup?: PopupConfig;
      symbology?: import("../widgets/mapSymbology").LayerSymbology;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "raster";
      tilesUrl: string;
      opacity?: number;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "feature";
      url: string;
      paint?: Record<string, unknown>;
      renderAs?: "fill" | "circle" | "line";
      popup?: PopupConfig;
      symbology?: import("../widgets/mapSymbology").LayerSymbology;
      collectionId?: string;
      pkColumn?: string;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "deck";
      deckType: "heatmap" | "hexbin" | "column";
      dataUrl: string;
      props?: Record<string, unknown>;
    }
  | { id: string; title: string; visible: boolean; kind: "tiles3d"; url: string };
export type MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number };
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  cartouche?: string | null;
};

export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
};

export type LayerSource = {
  id: string;
  title: string;
  service: "core" | "external" | "tileset3d";
  kind: "vector" | "feature" | "raster" | "tiles3d";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
  collectionId?: string;
  geometryKind?: "point" | "line" | "polygon";
  pkColumn?: string;
};

export type CollectionFieldType =
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "date"
  | "datetime"
  | "enum"
  | "attachment"
  | "unsupported";

export type CollectionSchemaField = {
  name: string;
  type: CollectionFieldType;
  required: boolean;
  maxLength?: number;
  values?: string[];
  label?: string;
};
export type CollectionSchema = {
  collection: string;
  pk: string;
  geometry: { column: string; type: string | null; srid: number } | null;
  fields: CollectionSchemaField[];
};

export type RenderMode = "edit" | "preview" | "runtime";

export type WidgetItem = {
  id: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  props: Record<string, unknown>;
  layouts?: Partial<Record<"sm" | "md" | "lg", { x: number; y: number; w: number; h: number }>>;
  visibleWhen?: string;
};

export type AppLayout = {
  type: "grid";
  breakpoints: Record<string, unknown>;
  items: WidgetItem[];
};

export type Page = {
  id: string;
  name: string;
  layout: AppLayout;
  // Messages déclenchés à l'entrée du chapitre en mode story (SP storytelling).
  onEnter?: ActionMessage[];
};

export type VariableType = "string" | "number" | "bool" | "date" | "record" | "list";

export type Variable = {
  id: string;
  name: string;
  type?: VariableType;
  initialValue: string | number | boolean | Record<string, unknown> | unknown[] | null;
};

export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string; // résolu automatiquement si datasetId est présent
  datasetId?: string;
  query: Record<string, unknown>;
};

export type DatasetColumnMeta = {
  label?: string;
  description?: string;
  format?: string;
};

export type CrossFilterLink =
  | { targetDatasetId: string; mode: "attribute"; sourceField: string; targetField: string }
  | { targetDatasetId: string; mode: "spatial"; precision: "bbox" | "exact" };

export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
      sourcePipelineId?: string | null;
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
      sourcePipelineId?: string | null;
    };

export type DataRecord = {
  id: string | number;
  properties: Record<string, unknown>;
  geometry?: unknown;
};

export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
  datasetId?: string;
  pkColumn?: string;
  collectionId?: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
};

export type ActionMessage = {
  id: string;
  from: string;
  event: string;
  to: string;
  action: string;
  when?: string;
  // Payload statique porté par un message onEnter de page (SP storytelling) :
  // un chapitre configure ici l'emprise cible de son map.flyTo. Ignoré par les
  // messages de wiring classiques, dont le payload vient de l'émetteur runtime.
  payload?: Record<string, unknown>;
};

export type ThemeColors = {
  primary?: string;
  background?: string;
  surface?: string;
  text?: string;
  muted?: string;
  border?: string;
};
export type Theme = {
  colors?: ThemeColors;
  font?: string;
  radius?: string;
  space?: string;
};

export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
  navigationMode?: "tabs" | "story";
  interactions?: "auto" | "manual"; // absent = "manual"
  printLayout?: PrintLayoutConfig | null;
};
```

- [ ] **Step 2: Delete the moved blocks from `shell/src/api/types.ts`, replace with a re-export**

For each type name above, find its block in `shell/src/api/types.ts` (`grep -n "^export type <Name>"`) and delete it. In its place — at the *first* deleted block's original location, once — insert:

```ts
export type {
  MapViewport,
  BaseMap,
  PopupField,
  PopupConfig,
  MapLayer,
  MapTerrainConfig,
  PrintLayoutConfig,
  MapConfig,
  LayerSource,
  CollectionFieldType,
  CollectionSchemaField,
  CollectionSchema,
  RenderMode,
  WidgetItem,
  AppLayout,
  Page,
  VariableType,
  Variable,
  DataSource,
  DatasetColumnMeta,
  CrossFilterLink,
  DatasetConfig,
  DataRecord,
  DataSourceState,
  ActionMessage,
  ThemeColors,
  Theme,
  AppConfig,
} from "@geostudio/app-builder";
```

(`@geostudio/app-builder` doesn't exist as a package yet at this point in the plan — Task 4 creates its `package.json`. Do Step 3 below *before* running typecheck.)

- [ ] **Step 3: Scaffold `packages/app-builder`'s `package.json`/`tsconfig.json` now (content only, no `src/` yet beyond `types/`)**

`packages/app-builder/package.json`:
```json
{
  "name": "@geostudio/app-builder",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@tanstack/react-query": "^5.59.0",
    "echarts": "^6.1.0",
    "maplibre-gl": "^4.7.0",
    "@deck.gl/core": "^9.0.0",
    "@deck.gl/layers": "^9.0.0",
    "@deck.gl/geo-layers": "^9.0.0",
    "@deck.gl/aggregation-layers": "^9.0.0",
    "@deck.gl/mapbox": "^9.0.0",
    "@loaders.gl/3d-tiles": "^4.3.0",
    "@maplibre/maplibre-gl-style-spec": "^20.0.0",
    "lit": "^3.3.3",
    "dompurify": "^3.4.12",
    "marked": "^15.0.0",
    "cel-js": "^0.8.2",
    "lucide-react": "1.37.0",
    "@geostudio/ui-kit": "*"
  }
}
```
(Pin the exact `dompurify`/`marked`/`cel-js`/`@maplibre/maplibre-gl-style-spec` versions to whatever `shell/package.json` currently declares — copy them verbatim rather than retyping from memory: `grep -E '"(dompurify|marked|cel-js|@maplibre/maplibre-gl-style-spec)"' shell/package.json`.)

`packages/app-builder/tsconfig.json`: same shape as `packages/ui-kit/tsconfig.json` (Task 1 Step 2), `include: ["src"]`.

`packages/app-builder/src/index.ts` (barrel, grows through later tasks):
```ts
// SPDX-License-Identifier: Apache-2.0
export * from "./types";
```

Add to `shell/package.json`: `"@geostudio/app-builder": "workspace:*"`.

Run: `cd /home/lenen/projets/geostudio && npm install` (registers the new workspace package).

- [ ] **Step 4: Typecheck**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: 0 errors. If a type is reported missing, it means some other type in `shell/src/api/types.ts` that this plan didn't list references one of the moved names transitively and needs its own import added — search for it with `grep -n "<Name>" shell/src/api/types.ts` and add `import type { <Name> } from "@geostudio/app-builder";` at the top of `types.ts` (not a re-export — types.ts needs to *reference* the type in a signature that stays local).

- [ ] **Step 5: Run tests**

Run: `cd /home/lenen/projets/geostudio/shell && npm run test`
Expected: same pass count as after Task 2 (pure type relocation, no runtime behavior change).

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): extract AppConfig types to packages/app-builder/src/types"
```

---

### Task 4: Define the three ports + `AppBuilderProvider`

**Files:**
- Create: `packages/app-builder/src/ports/dataClient.ts`
- Create: `packages/app-builder/src/ports/identity.ts`
- Create: `packages/app-builder/src/ports/i18n.ts`
- Create: `packages/app-builder/src/ports/AppBuilderProvider.tsx`
- Create: `packages/app-builder/src/ports/AppBuilderProvider.test.tsx`
- Modify: `packages/app-builder/src/index.ts`

**Interfaces:**
- Produces: `BuilderDataClient`, `IdentityPort`, `I18nPort` types; `AppBuilderProvider`, `useBuilderDataClient()`, `useIdentity()`, `useI18n()` hooks — every later task (`DataContext.tsx`, `ActionConditionBridge`, moved widgets that call `t()`) consumes these.

- [ ] **Step 1: `BuilderDataClient` — write the failing test first**

`packages/app-builder/src/ports/dataClient.test.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import type { BuilderDataClient } from "./dataClient";

describe("BuilderDataClient", () => {
  it("accepts a minimal client with only the required methods", () => {
    const client: BuilderDataClient = {
      queryDataSource: async () => [],
      getDatasetConfig: async () => ({ source: "collection", collectionId: "x", columns: {} }),
      getCollectionSchema: async () => ({ collection: "x", pk: "id", geometry: null, fields: [] }),
      featuresUrl: () => undefined,
    };
    expect(typeof client.queryDataSource).toBe("function");
  });
});
```

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/ports/dataClient.test.ts`
Expected: FAIL — `Cannot find module './dataClient'`.

- [ ] **Step 2: Implement `dataClient.ts`**

```ts
// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema, DataRecord, DataSource, DatasetConfig } from "../types";

export type MapIcon = { id: string; url: string; label?: string };

// The port the app-builder package depends on instead of a direct ItemClient
// import. Required methods are the ones the runtime + editor call
// unconditionally (queryDataSource/getCollectionSchema/featuresUrl cover
// widget data AND the CSV/GeoJSON export buttons — no separate export method
// needed). Optional capabilities gate an editor surface that hides itself
// cleanly when the host app doesn't implement it (checked with `"key" in
// client`, never a throw).
export type BuilderDataClient = {
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  getDatasetConfig(datasetId: string): Promise<DatasetConfig>;
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
  featuresUrl(source: DataSource): string | undefined;

  features?: {
    create(collectionId: string, record: DataRecord): Promise<DataRecord>;
    update(collectionId: string, id: string, record: DataRecord): Promise<DataRecord>;
    delete(collectionId: string, id: string): Promise<void>;
  };
  icons?: {
    list(): Promise<MapIcon[]>;
    upload(file: File): Promise<MapIcon>;
    fetchBlob(id: string): Promise<Blob>;
    delete(id: string): Promise<void>;
  };
  attachments?: {
    presign(collectionId: string, recordId: string, filename: string): Promise<{ uploadUrl: string; attachmentId: string }>;
    confirm(attachmentId: string): Promise<void>;
    list(collectionId: string, recordId: string): Promise<{ id: string; filename: string }[]>;
    download(attachmentId: string): Promise<Blob>;
    delete(attachmentId: string): Promise<void>;
  };
  terrain3d?: {
    presignUpload(filename: string): Promise<{ uploadUrl: string; jobId: string }>;
    createUpload(jobId: string): Promise<void>;
    getUploadJob(jobId: string): Promise<{ status: string }>;
    listHostedSources(): Promise<{ id: string; label: string }[]>;
  };
};
```

- [ ] **Step 3: Run the test again**

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/ports/dataClient.test.ts`
Expected: PASS.

- [ ] **Step 4: `IdentityPort` and `I18nPort` — write and implement together (same pattern, small)**

`packages/app-builder/src/ports/identity.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
export type IdentityPort = { username: string | null };
```

`packages/app-builder/src/ports/i18n.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
export type I18nPort = { t(key: string, params?: Record<string, string | number>): string };
```

No test needed for these two — they're structural type aliases with no logic (consistent with the project's own convention of not testing pure type declarations).

- [ ] **Step 5: `AppBuilderProvider` — write the failing test**

`packages/app-builder/src/ports/AppBuilderProvider.test.tsx`:
```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppBuilderProvider, useBuilderDataClient, useIdentity, useI18n } from "./AppBuilderProvider";
import type { BuilderDataClient } from "./dataClient";

const fakeClient: BuilderDataClient = {
  queryDataSource: async () => [],
  getDatasetConfig: async () => ({ source: "collection", collectionId: "x", columns: {} }),
  getCollectionSchema: async () => ({ collection: "x", pk: "id", geometry: null, fields: [] }),
  featuresUrl: () => undefined,
};

function Probe() {
  const client = useBuilderDataClient();
  const identity = useIdentity();
  const { t } = useI18n();
  return (
    <span>
      {typeof client.queryDataSource}-{identity.username ?? "anon"}-{t("hello")}
    </span>
  );
}

describe("AppBuilderProvider", () => {
  it("provides the injected data client, identity, and default i18n to descendants", () => {
    render(
      <AppBuilderProvider dataClient={fakeClient} identity={{ username: "tanguy" }}>
        <Probe />
      </AppBuilderProvider>,
    );
    expect(screen.getByText("function-tanguy-hello")).toBeInTheDocument();
  });

  it("falls back to the bundled i18n catalog when no I18nPort is provided", () => {
    render(
      <AppBuilderProvider dataClient={fakeClient} identity={{ username: null }}>
        <Probe />
      </AppBuilderProvider>,
    );
    expect(screen.getByText("function-anon-hello")).toBeInTheDocument();
  });
});
```

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/ports/AppBuilderProvider.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 6: Implement `AppBuilderProvider.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, type ReactNode } from "react";
import type { BuilderDataClient } from "./dataClient";
import type { IdentityPort } from "./identity";
import type { I18nPort } from "./i18n";

// Default I18nPort: identity function returning the key itself, with
// {param} interpolation — same fallback contract as ui-kit's own stub
// (packages/ui-kit/src/i18n.ts) and as the real bundled catalog Task 10
// wires in as the package's actual default (this default is only what a
// host sees if it constructs AppBuilderProvider without Task 10's provider
// wrapper — kept trivial and dependency-free here).
const defaultI18n: I18nPort = {
  t(key, params) {
    if (params === undefined) return key;
    return key.replace(/\{(\w+)\}/g, (match, name) => {
      const value = params[name];
      return value === undefined ? match : String(value);
    });
  },
};

const DataClientContext = createContext<BuilderDataClient | null>(null);
const IdentityContext = createContext<IdentityPort>({ username: null });
const I18nContext = createContext<I18nPort>(defaultI18n);

export function AppBuilderProvider({
  dataClient,
  identity = { username: null },
  i18n = defaultI18n,
  children,
}: {
  dataClient: BuilderDataClient;
  identity?: IdentityPort;
  i18n?: I18nPort;
  children: ReactNode;
}) {
  return (
    <DataClientContext.Provider value={dataClient}>
      <IdentityContext.Provider value={identity}>
        <I18nContext.Provider value={i18n}>{children}</I18nContext.Provider>
      </IdentityContext.Provider>
    </DataClientContext.Provider>
  );
}

export function useBuilderDataClient(): BuilderDataClient {
  const client = useContext(DataClientContext);
  if (!client) {
    throw new Error("useBuilderDataClient() called outside <AppBuilderProvider>");
  }
  return client;
}

export function useIdentity(): IdentityPort {
  return useContext(IdentityContext);
}

export function useI18n(): I18nPort {
  return useContext(I18nContext);
}
```

- [ ] **Step 7: Run the test again**

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/ports/AppBuilderProvider.test.tsx`
Expected: PASS, both cases.

- [ ] **Step 8: Export from the package barrel**

`packages/app-builder/src/index.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
export * from "./types";
export * from "./ports/dataClient";
export * from "./ports/identity";
export * from "./ports/i18n";
export { AppBuilderProvider, useBuilderDataClient, useIdentity, useI18n } from "./ports/AppBuilderProvider";
```

- [ ] **Step 9: Commit**

```bash
cd /home/lenen/projets/geostudio
git add packages/app-builder
git commit -m "feat(app-builder): define BuilderDataClient/IdentityPort/I18nPort + AppBuilderProvider"
```

---

### Task 5: `geostudioDataClient` adapter (`ItemClient` → `BuilderDataClient`)

**Files:**
- Create: `shell/src/builder/geostudioDataClient.ts`
- Create: `shell/src/builder/geostudioDataClient.test.ts`

**Interfaces:**
- Consumes: `ItemClient` (`shell/src/api/types.ts`, real methods verified against `shell/src/api/domains/*.ts` while writing this plan: `queryDataSource`, `getDatasetConfig(pk)`, `getCollectionSchema(collectionId)`, `featuresUrl(source)`).
- Produces: `toBuilderDataClient(client: ItemClient): BuilderDataClient` — consumed by Task 11 (mounting `<AppBuilderProvider>` in `shell/`).

- [ ] **Step 1: Write the failing test**

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { toBuilderDataClient } from "./geostudioDataClient";
import type { ItemClient } from "../api/types";

function fakeItemClient(): ItemClient {
  return {
    queryDataSource: vi.fn(async () => [{ id: "1", properties: {} }]),
    getDatasetConfig: vi.fn(async () => ({ source: "collection", collectionId: "x", columns: {} })),
    getCollectionSchema: vi.fn(async () => ({ collection: "x", pk: "id", geometry: null, fields: [] })),
    featuresUrl: vi.fn(() => "http://x/features"),
  } as unknown as ItemClient;
}

describe("toBuilderDataClient", () => {
  it("delegates the 4 required methods 1:1", async () => {
    const item = fakeItemClient();
    const builder = toBuilderDataClient(item);

    const source = { id: "s1", type: "features" as const, service: "core", layer: "x", query: {} };
    await builder.queryDataSource(source);
    expect(item.queryDataSource).toHaveBeenCalledWith(source);

    await builder.getDatasetConfig("ds1");
    expect(item.getDatasetConfig).toHaveBeenCalledWith("ds1");

    await builder.getCollectionSchema("x");
    expect(item.getCollectionSchema).toHaveBeenCalledWith("x");

    expect(builder.featuresUrl(source)).toBe("http://x/features");
  });
});
```

Run: `cd /home/lenen/projets/geostudio/shell && npx vitest run src/builder/geostudioDataClient.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement**

```ts
// SPDX-License-Identifier: Apache-2.0
import type { BuilderDataClient } from "@geostudio/app-builder";
import type { ItemClient } from "../api/types";

// Pure delegation, no logic: ItemClient already implements every required
// AND optional BuilderDataClient capability (icons: listMapIcons/uploadMapIcon/
// fetchMapIconBlob/deleteMapIcon; attachments: presignAttachmentUpload/
// confirmAttachmentUpload/listAttachments/downloadAttachment/deleteAttachment;
// terrain3d: presignTerrain3DUpload/createTerrain3DUpload/getTerrain3DUploadJob/
// listHostedTerrain3DSources; features: createFeature/updateFeature/deleteFeature
// — all verified present in shell/src/api/domains/*.ts while writing the design
// spec this plan implements).
export function toBuilderDataClient(client: ItemClient): BuilderDataClient {
  return {
    queryDataSource: (source) => client.queryDataSource(source),
    getDatasetConfig: (datasetId) => client.getDatasetConfig(datasetId),
    getCollectionSchema: (collectionId) => client.getCollectionSchema(collectionId),
    featuresUrl: (source) => client.featuresUrl(source),
    features: {
      create: (collectionId, record) => client.createFeature(collectionId, record),
      update: (collectionId, id, record) => client.updateFeature(collectionId, id, record),
      delete: (collectionId, id) => client.deleteFeature(collectionId, id),
    },
    icons: {
      list: () => client.listMapIcons(),
      upload: (file) => client.uploadMapIcon(file),
      fetchBlob: (id) => client.fetchMapIconBlob(id),
      delete: (id) => client.deleteMapIcon(id),
    },
    attachments: {
      presign: (collectionId, recordId, filename) =>
        client.presignAttachmentUpload(collectionId, recordId, filename),
      confirm: (attachmentId) => client.confirmAttachmentUpload(attachmentId),
      list: (collectionId, recordId) => client.listAttachments(collectionId, recordId),
      download: (attachmentId) => client.downloadAttachment(attachmentId),
      delete: (attachmentId) => client.deleteAttachment(attachmentId),
    },
    terrain3d: {
      presignUpload: (filename) => client.presignTerrain3DUpload(filename),
      createUpload: (jobId) => client.createTerrain3DUpload(jobId),
      getUploadJob: (jobId) => client.getTerrain3DUploadJob(jobId),
      listHostedSources: () => client.listHostedTerrain3DSources(),
    },
  };
}
```

**Note for the implementer:** the exact parameter lists of `createFeature`/`updateFeature`/`deleteFeature`/`listMapIcons`/etc. were not individually re-verified line-by-line while writing this plan (only their *names* were, via `grep -c "client\."` in the design spec). Run Step 3's typecheck; if a signature mismatch is reported, open the real method in `shell/src/api/domains/*.ts` (`grep -rn "async <methodName>(" shell/src/api/domains/`) and adjust the adapter's parameter list to match — do not guess twice, read the source.

- [ ] **Step 3: Typecheck + run test**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit && npx vitest run src/builder/geostudioDataClient.test.ts`
Expected: 0 type errors, test PASS. Fix any signature mismatch per the note above before proceeding.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/builder/geostudioDataClient.ts shell/src/builder/geostudioDataClient.test.ts
git commit -m "feat(shell): geostudioDataClient adapts ItemClient to BuilderDataClient"
```

---

### Task 6: Move `core/` — rewire `DataContext.tsx` and `AppRenderer.tsx` onto the ports

**Files:**
- Move (unchanged): `registry.ts`, `GridCanvas.tsx`(+test), `WidgetHost.tsx`(+test), `grid.ts`(+test if any), `pages.ts`(+test), `theme.ts`(+test), `ActionBus.ts`(+test), `ActionBusContext.tsx`(+test), `VariablesContext.tsx`(+test), `AnalyticsContext.tsx`(+test), `AnalyticsContextIndicator.tsx`(+test), `ExplorerContext.tsx`(+test), `ExplorerDrawer.tsx`(+test), `expr.ts`(+test), `exprBindings.ts`(+test), `actionMessages.ts`(+test), `undoStack.ts`(+test), `useUndoableDraft.ts`(+test), `templates.ts`, `sdk.ts` → `packages/app-builder/src/core/`.
- Modify (content changes, shown in full below): `DataContext.tsx`, `AppRenderer.tsx`.
- Modify: `packages/app-builder/src/index.ts`.

**Interfaces:**
- Consumes: `useBuilderDataClient()`, `useIdentity()` from Task 4.
- Produces: `AppRenderer(config, mode, ...)` unchanged public signature — only its internal `ActionConditionBridge` and the `DataProvider` it mounts change source of data/identity.

- [ ] **Step 1: Move the unmodified files**

```bash
cd /home/lenen/projets/geostudio/shell/src/builder
mkdir -p ../../../packages/app-builder/src/core
git mv registry.ts registry.test.ts GridCanvas.tsx GridCanvas.test.tsx WidgetHost.tsx WidgetHost.test.tsx \
  grid.ts pages.ts pages.test.ts theme.ts ActionBus.ts ActionBus.test.ts ActionBusContext.tsx ActionBusContext.test.tsx \
  VariablesContext.tsx VariablesContext.test.tsx AnalyticsContext.tsx AnalyticsContext.test.tsx \
  AnalyticsContextIndicator.tsx AnalyticsContextIndicator.test.tsx ExplorerContext.tsx ExplorerContext.test.tsx \
  ExplorerDrawer.tsx ExplorerDrawer.test.tsx expr.ts exprBindings.ts actionMessages.ts actionMessages.test.ts \
  undoStack.ts useUndoableDraft.ts templates.ts sdk.ts \
  ../../../packages/app-builder/src/core/
```

(Run `ls *.test.ts *.test.tsx | grep -E "^(grid|theme|expr|exprBindings)\."` first to confirm which of `grid`/`theme`/`expr`/`exprBindings`/`undoStack`/`useUndoableDraft`/`templates`/`sdk` actually have a `.test.` companion — include only the ones that exist, `git mv` errors on a nonexistent source path.)

- [ ] **Step 2: Rewrite `DataContext.tsx` — inject `BuilderDataClient` instead of `ItemClient`**

The moved file (`packages/app-builder/src/core/DataContext.tsx`) currently starts:
```tsx
import { useItemClient } from "../api/ItemClientProvider";
...
export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
```

Change to:
```tsx
import { useBuilderDataClient } from "../ports/AppBuilderProvider";
...
export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useBuilderDataClient();
```

Every other line in the file (the `useQueries` calls, `mergedQueryFor`, `states` construction) calls `client.getDatasetConfig`, `client.getCollectionSchema`, `client.queryDataSource`, `client.featuresUrl` — all 4 required `BuilderDataClient` methods, unchanged signatures. No other edit needed in this file. Also fix the relative import of types (`../api/types` → `../types`, since Task 3 moved them).

- [ ] **Step 3: Rewrite `AppRenderer.tsx` — `ActionConditionBridge` uses `useIdentity()` instead of `useAuth()`**

Current:
```tsx
import { useAuth } from "../auth/useAuth";
...
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useAuth();
  const analyticsCtx = useAnalyticsContext();
```

Change to:
```tsx
import { useIdentity } from "../ports/AppBuilderProvider";
...
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useIdentity();
  const analyticsCtx = useAnalyticsContext();
```

Also update the `import { t } from "../i18n"` line to `import { useI18n } from "../ports/AppBuilderProvider";` and every `t("appRenderer.xxx", ...)` call site in the same file to `const { t } = useI18n();` at the top of the `AppRenderer` function component, then `t("appRenderer.xxx", ...)` unchanged (there are 2 call sites in this file, both inside the `storyMode` nav JSX — `t("appRenderer.prevButton")`, `t("appRenderer.chapterLabel", {...})`, `t("appRenderer.nextButton")`; `AppRenderer` is already a function component, so this is a top-of-body hook call, not a new component). Fix the relative type imports (`../api/types` → `../types`).

- [ ] **Step 4: Move both files**

```bash
git mv DataContext.tsx DataContext.test.tsx AppRenderer.tsx AppRenderer.test.tsx ../../../packages/app-builder/src/core/
```

(Apply Steps 2-3's edits either before or after the `git mv` — content is identical either way; doing the edit first, in place, then moving, keeps `git mv`'s rename detection clean in the diff.)

- [ ] **Step 5: Update `AppRenderer.test.tsx` and `DataContext.test.tsx` to wrap renders in `<AppBuilderProvider>`**

Both test files currently render `<AppRenderer .../>` / `<DataProvider>` directly, presumably with an `ItemClientProvider` test wrapper or a mocked `useItemClient`. Find the existing wrapper:

```bash
grep -n "ItemClientProvider\|useItemClient\|useAuth" packages/app-builder/src/core/AppRenderer.test.tsx packages/app-builder/src/core/DataContext.test.tsx
```

Replace that wrapper with `<AppBuilderProvider dataClient={fakeClient} identity={{ username: "..." }}>`, using a `fakeClient: BuilderDataClient` test double built the same way as Task 5 Step 1's `fakeItemClient` (but implementing `BuilderDataClient` directly — no adapter needed in this test file, it's testing the package in isolation from `shell`).

- [ ] **Step 6: Export from the barrel**

`packages/app-builder/src/index.ts` — add:
```ts
export { AppRenderer } from "./core/AppRenderer";
export { registerWidget, getWidget, listWidgets } from "./core/registry";
export type { WidgetContext, WidgetDefinition } from "./core/registry";
```
(more core exports land here as later tasks need them — this barrel is additive, never trim an existing export.)

- [ ] **Step 7: Fix `shell/src/builder/*` files that stayed behind and imported any moved `core/` file**

```bash
cd /home/lenen/projets/geostudio/shell/src/builder
grep -rl "\./registry\|\./AppRenderer\|\./GridCanvas\|\./WidgetHost\|\./DataContext\|\./ActionBus\|\./VariablesContext\|\./AnalyticsContext\|\./ExplorerContext\|\./ExplorerDrawer\|\./expr\|\./exprBindings\|\./actionMessages\|\./undoStack\|\./useUndoableDraft\|\./templates\|\./sdk\|\./pages\|\./theme\|\./grid" . --include="*.ts" --include="*.tsx"
```

For each match (expected: files in `pipeline/`, `visualQuery/`, `copilot/`, `print/`, `report/`, `appexport/`, `AlertRuleEditor.tsx`, `ConfigHistoryPanel.tsx`, plus any remaining top-level `builder/*` file not yet moved — `PropsPanel.tsx` etc., moved in Task 7), rewrite the import to `from "@geostudio/app-builder"`, keeping only the names actually used (check each file's existing named imports before rewriting — don't blanket-replace with a wildcard).

- [ ] **Step 8: Typecheck + tests**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: errors remaining only in files Task 7/8/9 haven't moved yet (editor/, widgets/, map/, wc/ still reference `../ui/kit`, `../../i18n`, etc. under their old paths) — confirm every *reported* error is in one of those not-yet-moved directories, not in `core/` or already-migrated files. If an error is in `core/` or a file this task claims to have finished, fix it now.

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/core`
Expected: all core tests pass.

- [ ] **Step 9: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): move builder core to packages/app-builder, inject BuilderDataClient/IdentityPort"
```

---

### Task 7: Move `editor/`

**Files:**
- Move (unchanged unless noted): `PropsPanel.tsx`(+test), `WidgetPalette.tsx`(+test — confirm exists), `LayoutEditor.tsx`(+test), `PageManager.tsx`(+test), `ThemePanel.tsx`(+test), `VariablesPanel.tsx`(+test), `DataSourcePanel.tsx`(+test), `DataSourceSelect.tsx`(+test), `DataSourcesEditContext.tsx`(+test if any), `ActionsPanel.tsx`(+test), `NavigationPanel.tsx`(+test), `CrossFilterLinkEditor.tsx`(+test), `widgetPropSchema.ts`(+test if any), `configExpressionErrors.ts`(+test), `PercentileInput.tsx`(+test if any) → `packages/app-builder/src/editor/`.
- Modify: any file among these that imports `useItemClient`/`useAuth`/`t` directly (check per Step 2 below — none were flagged by the design-spec grep for this group, but verify, don't assume).

- [ ] **Step 1: Confirm no direct `ItemClient`/`useAuth` coupling in this group before moving**

```bash
cd /home/lenen/projets/geostudio/shell/src/builder
grep -l "useItemClient\|from \"\.\./auth/useAuth\"\|from \"\.\./\.\./auth/useAuth\"" \
  PropsPanel.tsx WidgetPalette.tsx LayoutEditor.tsx PageManager.tsx ThemePanel.tsx VariablesPanel.tsx \
  DataSourcePanel.tsx DataSourceSelect.tsx DataSourcesEditContext.tsx ActionsPanel.tsx NavigationPanel.tsx \
  CrossFilterLinkEditor.tsx widgetPropSchema.ts configExpressionErrors.ts PercentileInput.tsx 2>/dev/null
```

Expected: no output. If any file matches, apply the same rewrite pattern as Task 6 Step 2/3 (swap for `useBuilderDataClient`/`useIdentity` from `../ports/AppBuilderProvider`) before moving it.

- [ ] **Step 2: Move**

```bash
mkdir -p ../../../packages/app-builder/src/editor
for f in PropsPanel WidgetPalette LayoutEditor PageManager ThemePanel VariablesPanel DataSourcePanel \
         DataSourceSelect DataSourcesEditContext ActionsPanel NavigationPanel CrossFilterLinkEditor; do
  git mv "$f.tsx" "../../../packages/app-builder/src/editor/$f.tsx" 2>/dev/null
  git mv "$f.test.tsx" "../../../packages/app-builder/src/editor/$f.test.tsx" 2>/dev/null
done
for f in widgetPropSchema configExpressionErrors PercentileInput; do
  git mv "$f.ts" "../../../packages/app-builder/src/editor/$f.ts" 2>/dev/null
  git mv "$f.tsx" "../../../packages/app-builder/src/editor/$f.tsx" 2>/dev/null
  git mv "$f.test.ts" "../../../packages/app-builder/src/editor/$f.test.ts" 2>/dev/null
  git mv "$f.test.tsx" "../../../packages/app-builder/src/editor/$f.test.tsx" 2>/dev/null
done
```

(The `2>/dev/null` swallows "not found" for the extension/test combination that doesn't apply to a given file — after running, `git status` must show every file from the list above as renamed, none left behind. Check explicitly: `git status --short | grep "^R "  | wc -l` should equal the count of files actually present before the move.)

- [ ] **Step 3: Rewrite internal cross-references within the moved group**

These files import each other and `core/` and `ui/kit` and `../../i18n`. Run:
```bash
cd /home/lenen/projets/geostudio/packages/app-builder/src/editor
grep -rln 'from "\.\./' . 2>/dev/null
grep -rln 'from "\.\./\.\./ui/kit\|from "\.\./\.\./\.\./i18n\|from "\.\./\.\./i18n"' . 2>/dev/null
```
Rewrite:
- `"../registry"`, `"../AppRenderer"`, etc. (pointing at now-sibling `core/`) → `"../core/registry"` etc.
- `"../../ui/kit/X"` → `"@geostudio/ui-kit"`.
- `"../../i18n"` or `"../i18n"` → `"../ports/AppBuilderProvider"`, converting the top-level `import { t } from ...` to a `const { t } = useI18n();` call inside each component (same pattern as Task 6 Step 3) — do this file by file, `tsc` will point at every remaining bare `t(` call once the import is gone.

- [ ] **Step 4: Fix `shell/src/builder/*` consumers of this group**

```bash
cd /home/lenen/projets/geostudio/shell/src/builder
grep -rl "\./PropsPanel\|\./WidgetPalette\|\./LayoutEditor\|\./PageManager\|\./ThemePanel\|\./VariablesPanel\|\./DataSourcePanel\|\./DataSourceSelect\|\./ActionsPanel\|\./NavigationPanel\|\./CrossFilterLinkEditor\|\./widgetPropSchema" . --include="*.ts" --include="*.tsx"
```
Rewrite each to `from "@geostudio/app-builder"`.

- [ ] **Step 5: Typecheck + tests**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: remaining errors confined to `widgets/`, `map/`, `wc/` (Tasks 8-9).

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/editor`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): move builder editor panels to packages/app-builder"
```

---

### Task 8: Move `widgets/` — rewire `datasetCard`'s download buttons onto the port

**Files:**
- Move (unchanged): all 28 files listed in the design spec's `builder/widgets` `find` output, plus `EChart.tsx` (from `builder/EChart.tsx`) → `packages/app-builder/src/widgets/`.
- Move + modify: `DatasetDownloadButtons.tsx` (from `builder/`) and `datasetDownload.ts` (from `lib/`) → `packages/app-builder/src/widgets/`, both retyped against `BuilderDataClient` instead of `ItemClient`.

**Interfaces:**
- Consumes: `useBuilderDataClient()` (Task 4), `useI18n()` (Task 4).
- Produces: `registerWidget` calls for all 25 widget types (`text`, `image`, `button`, `chart`, `data`(table), `mapWidget`(map), `indicator`, `pivot`, `form`, `gallery`, `hero`, `modal`, `drawer`, `navigation`(nav), `tabs`, `filter`, `selectFilter`, `sliderFilter`, `dateRangeFilter`, `datasetCard`, `richSection`, `variableInput`) — same `type` strings as before, unchanged (an `AppConfig` authored today keeps working).

- [ ] **Step 1: Retype `datasetDownload.ts` against `BuilderDataClient`**

Current signatures (from `lib/datasetDownload.ts`, already read in full while writing this plan):
```ts
export function geojsonDownloadUrl(client: Pick<ItemClient, "featuresUrl">, collectionId: string): string
export async function downloadCsv(opts: { client: Pick<ItemClient, "queryDataSource">; ... }): Promise<void>
```
Both only need methods `BuilderDataClient` already declares as *required*. Change the two `Pick<ItemClient, ...>` annotations to `Pick<BuilderDataClient, ...>` and the `import type { ... ItemClient } from "../api/types"` to drop `ItemClient` and add nothing (the `Pick` source type moves to `BuilderDataClient`, imported from `"../ports/dataClient"`). No other line in this file changes — `csvAvailable`, `csvTooLarge`, `fetchRecordsForCsv`, `csvEscape`, `recordsToCsv`, `triggerCsvDownload` have zero `ItemClient` coupling already.

- [ ] **Step 2: Retype `DatasetDownloadButtons.tsx`**

Current:
```tsx
import { useItemClient } from "../api/ItemClientProvider";
import { csvAvailable, csvTooLarge, downloadCsv, geojsonDownloadUrl } from "../lib/datasetDownload";
import { t } from "../i18n";
...
  const client = useItemClient();
```
Change to:
```tsx
import { useBuilderDataClient, useI18n } from "../ports/AppBuilderProvider";
import { csvAvailable, csvTooLarge, downloadCsv, geojsonDownloadUrl } from "./datasetDownload";
...
export function DatasetDownloadButtons({ collectionId, featureCount }: { collectionId: string; featureCount: number | null }) {
  const client = useBuilderDataClient();
  const { t } = useI18n();
```
(rest of the component body unchanged — it only ever called `client.getCollectionSchema`, `client.featuresUrl` via `geojsonDownloadUrl`, `client.queryDataSource` via `downloadCsv`, all 3 required `BuilderDataClient` methods.)

- [ ] **Step 3: Move everything**

```bash
cd /home/lenen/projets/geostudio/shell/src
mkdir -p ../../packages/app-builder/src/widgets
for f in builder/widgets/*.ts builder/widgets/*.tsx; do
  git mv "$f" "../../packages/app-builder/src/widgets/$(basename "$f")"
done
git mv builder/EChart.tsx builder/EChart.test.tsx ../../packages/app-builder/src/widgets/ 2>/dev/null
git mv builder/DatasetDownloadButtons.tsx builder/DatasetDownloadButtons.test.tsx ../../packages/app-builder/src/widgets/ 2>/dev/null
git mv lib/datasetDownload.ts lib/datasetDownload.test.ts ../../packages/app-builder/src/widgets/ 2>/dev/null
```

- [ ] **Step 4: Rewrite cross-references inside the moved group**

```bash
cd /home/lenen/projets/geostudio/packages/app-builder/src/widgets
grep -rln 'from "\.\./\.\./ui/kit\|from "\.\./\.\./\.\./i18n\|from "\.\./\.\./i18n"\|from "\.\./registry"\|from "\.\./ActionBusContext"\|from "\.\./AnalyticsContext"\|from "\.\./ExplorerContext"\|from "\.\./api/ItemClientProvider"\|from "\.\./\.\./auth/useAuth"\|from "\.\./DataSourceSelect"' .
```

Apply the same three rewrite patterns as Task 7 Step 3 (`ui/kit` → `@geostudio/ui-kit`; `i18n` → `useI18n()`; `useItemClient` → `useBuilderDataClient()`), plus:
- `"../registry"`, `"../ActionBusContext"`, `"../AnalyticsContext"`, `"../ExplorerContext"`, `"../WidgetHost"`, `"../LayoutEditor"`, `"../GridCanvas"` → `"../core/<Name>"`.
- `"../DataSourceSelect"`, `"../widgetPropSchema"`, `"../expr"` → `"../editor/DataSourceSelect"`, `"../editor/widgetPropSchema"`, `"../core/expr"`.
- `mapWidget.tsx`'s imports of `../../map/*` (`MapView`, `PopupEditor`, `MapSymbologyEditor`, `BasemapSelect`, `TerrainPanel`, `CameraControls`) → `"../map/*"` (Task 9 moves `map/` to the same package, sibling to `widgets/`).
- `mapWidget.tsx`'s `import type { MapConfig, MapTerrainConfig, PopupConfig } from "../../api/types"` → `from "../types"`.
- `wc/registerWcWidget` is imported by nothing in `widgets/` (only `shell/src/builder/wc/*` imports `../registry` the other direction) — no action here, handled in Task 9.

- [ ] **Step 5: Fix `shell/src/builder/*` consumers**

```bash
cd /home/lenen/projets/geostudio/shell/src/builder
grep -rl "\./widgets/\|builder/widgets/\|\./EChart\|\./DatasetDownloadButtons" . --include="*.ts" --include="*.tsx"
grep -rl "lib/datasetDownload" ../. --include="*.ts" --include="*.tsx"
```
Rewrite each to `from "@geostudio/app-builder"` (widgets self-register via `registerWidget` on import — `shell/src/builder/widgets/index.tsx` doesn't exist anymore as a separate file since it moved with the rest; any file in `shell/` that imported it to trigger registration side-effects, e.g. `shell/src/pages/AppBuilderPage.tsx` or a route entry point, now does `import "@geostudio/app-builder/widgets"` — check `packages/app-builder/src/widgets/index.tsx`'s moved content: it's the file that calls all the `registerWidget(...)` calls, confirm it's re-exported or side-effect-imported from `packages/app-builder/src/index.ts` with `export * from "./widgets/index"` or an explicit `import "./widgets/index"` at the top of the barrel so registration happens once, on package import, same as today).

Add to `packages/app-builder/src/index.ts`:
```ts
import "./widgets/index"; // side-effect: registers all built-in widget types
```

- [ ] **Step 6: Typecheck + tests**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: remaining errors confined to `map/`, `wc/` (Task 9).

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run src/widgets`
Expected: pass (widget tests that mount a full `<AppRenderer>` or call `registerWidget` need the same `<AppBuilderProvider>` test wrapper fix as Task 6 Step 5 — apply per-file as `tsc`/`vitest` surface them, using the same fake `BuilderDataClient`).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): move builder widgets to packages/app-builder, inject BuilderDataClient"
```

---

### Task 9: Move `map/` and `wc/`

**Files:**
- Move (unchanged): all 19 `map/` files listed in the design spec's `find` output → `packages/app-builder/src/map/`.
- Move (unchanged): `WcHost.tsx`, `generatedPropsPanel.tsx`, `manifest.ts`, `registerWcWidget.ts` (+ tests) → `packages/app-builder/src/wc/`.

- [ ] **Step 1: Move `map/`**

```bash
cd /home/lenen/projets/geostudio/shell/src
mkdir -p ../../packages/app-builder/src/map
for f in map/*.ts map/*.tsx; do
  git mv "$f" "../../packages/app-builder/src/map/$(basename "$f")"
done
```

- [ ] **Step 2: Rewrite cross-references inside `map/`**

```bash
cd /home/lenen/projets/geostudio/packages/app-builder/src/map
grep -rln 'from "\.\./\.\./ui/kit\|from "\.\./\.\./\.\./i18n\|from "\.\./\.\./i18n"\|from "\.\./\.\./api/types"\|from "\.\./\.\./api/ItemClientProvider"' .
```
Apply: `ui/kit` → `@geostudio/ui-kit`; `i18n` → `useI18n()` from `../ports/AppBuilderProvider`; `../../api/types` → `../types`; `useItemClient` → `useBuilderDataClient()` (map's icon upload / terrain panels call `client.listMapIcons`/`uploadMapIcon`/etc. and `client.presignTerrain3DUpload`/etc. — all under the `icons`/`terrain3d` optional capabilities: change call sites from `client.listMapIcons()` to `client.icons?.list()`, and gate the calling UI (button disabled/hidden) on `client.icons`/`client.terrain3d` being defined — find each call site with `grep -n "client\.\(listMapIcons\|uploadMapIcon\|fetchMapIconBlob\|deleteMapIcon\|presignTerrain3DUpload\|createTerrain3DUpload\|getTerrain3DUploadJob\|listHostedTerrain3DSources\)" .` and adjust individually, since the exact JSX gating differs per file).

- [ ] **Step 3: Move `wc/`**

```bash
cd /home/lenen/projets/geostudio/shell/src
mkdir -p ../../packages/app-builder/src/wc
git mv builder/wc/*.ts builder/wc/*.tsx ../../packages/app-builder/src/wc/
```

Rewrite `../registry` → `../core/registry` inside `wc/registerWcWidget.ts`.

- [ ] **Step 4: Fix `shell/src/builder/*` consumers of `map/`/`wc/`**

```bash
cd /home/lenen/projets/geostudio/shell/src
grep -rl "\.\./map/\|\./map/\|builder/wc/" builder/ --include="*.ts" --include="*.tsx"
```
Rewrite to `from "@geostudio/app-builder"`.

- [ ] **Step 5: Barrel exports**

`packages/app-builder/src/index.ts` — add:
```ts
export { MapView } from "./map/MapView";
export { registerWcWidget } from "./wc/registerWcWidget";
```

- [ ] **Step 6: Full typecheck + full package test run**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: **0 errors** — this is the first point in the plan where the entire `shell/` typechecks clean against the two packages.

Run: `cd /home/lenen/projets/geostudio/packages/app-builder && npx vitest run`
Expected: all tests in the package pass.

Run: `cd /home/lenen/projets/geostudio/shell && npm run test`
Expected: all `shell/`-resident tests pass (pipeline, visualQuery, copilot, print, report, appexport, AlertRuleEditor, ConfigHistoryPanel, and every non-builder shell test).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "refactor(shell): move map + wc to packages/app-builder — shell typechecks clean"
```

---

### Task 10: Extract the i18n subset, wire `I18nPort` end to end in `shell`

**Files:**
- Create: `packages/app-builder/src/i18n/catalog.fr.ts`
- Create: `packages/app-builder/src/i18n/index.ts`
- Modify: `shell/src/i18n/catalog.fr.ts` — remove the moved keys.
- Modify: `shell/src/shell/` (wherever `AppRenderer`/`AppBuilderPage` is mounted) — pass `i18n={{ t }}` (shell's real `t`) to `<AppBuilderProvider>`.

- [ ] **Step 1: Identify the exact key set to move**

```bash
cd /home/lenen/projets/geostudio/shell/src
grep -nE '^\s+"?(builder|widget|appRenderer|map|datasetDownload)\.' i18n/catalog.fr.ts
```

Every matched line moves. Cut them from `i18n/catalog.fr.ts` (preserving the nested object structure they live in — read the file first to confirm whether keys are flat strings like `"builder.foo": "..."` or nested `{ builder: { foo: "..." } }`; the design spec's earlier grep counted 355 matches on a flat-ish pattern, confirm the real shape before cutting) into `packages/app-builder/src/i18n/catalog.fr.ts`, keeping the exact same key names.

- [ ] **Step 2: Package-local `t()`**

`packages/app-builder/src/i18n/index.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
import { catalog } from "./catalog.fr";

// Default I18nPort implementation for the package: used when a host app's
// <AppBuilderProvider> is given no `i18n` prop. A host that wants its own
// catalog (e.g. geostudio/shell's real multi-locale t()) passes it via the
// `i18n` prop instead — this default never runs there.
function get(key: string): string | undefined {
  return (catalog as Record<string, string>)[key];
}

export function t(key: string, params?: Record<string, string | number>): string {
  const template = get(key) ?? key;
  if (params === undefined) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}
```

(Adjust `get()`'s indexing if Step 1 found the catalog is nested rather than flat — read the real file before finalizing this.)

- [ ] **Step 3: Make this the package's actual default, not `AppBuilderProvider`'s trivial identity fallback**

In `packages/app-builder/src/ports/AppBuilderProvider.tsx`, replace the inline `defaultI18n` object (Task 4 Step 6) with:
```ts
import { t as defaultT } from "../i18n";
const defaultI18n: I18nPort = { t: defaultT };
```
Remove the now-unused inline identity-function version.

- [ ] **Step 4: Wire `shell`'s real catalog through**

Find where `shell/` mounts the builder today:
```bash
cd /home/lenen/projets/geostudio/shell/src
grep -rln "<AppRenderer" shell/ pages/
```
Wrap each such render site's parent tree with `<AppBuilderProvider dataClient={toBuilderDataClient(itemClient)} identity={{ username }} i18n={{ t }}>` — `itemClient` from `useItemClient()`, `username` from `useAuth()`, `t` from `shell/src/i18n`, all already available in scope at these call sites (verify per file — these are exactly the 3 dependencies this whole plan removed from being imported *inside* the package; they're still real dependencies of `shell/`, just now passed in explicitly instead of reached for internally).

- [ ] **Step 5: Typecheck + full test suite**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit && npm run test`
Expected: 0 errors, all tests pass.

Run: `cd /home/lenen/projets/geostudio && npm run lint:i18n --workspace=shell` (or the equivalent path if the script needs updating to also scan `packages/app-builder/src`) — extend `shell/scripts/check-i18n-coverage.mjs`'s file-list argument to include `../packages/app-builder/src` alongside its existing `src/builder src/map` entries (those two no longer exist post-move; replace them with the package path).
Expected: passes (no missing/unused key).

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "feat(app-builder): package-local i18n catalog, wire shell's real catalog via I18nPort"
```

---

### Task 11: Mount `<AppBuilderProvider>` for real in `shell`, delete dead imports

**Files:**
- Modify: every route/page that renders `<AppRenderer>` (found in Task 10 Step 4) — confirm the provider wraps it (should already be done by Task 10; this task is the verification + cleanup pass).
- Modify: `shell/src/api/types.ts` — confirm no leftover unused imports.
- Delete: any now-empty `shell/src/map/` or `shell/src/ui/kit/` directory remnants (should already be gone via `git mv`, this is a `git status` sanity check, not new work).

- [ ] **Step 1: Grep for anything in `shell/` still importing the pre-move paths**

```bash
cd /home/lenen/projets/geostudio/shell/src
grep -rn 'from "\.\./\.\./ui/kit\|from "\.\./ui/kit\|from "\.\./\.\./map/\|from "\.\./map/' . --include="*.ts" --include="*.tsx" | grep -v node_modules
```
Expected: no output. Fix any remaining hit (rewrite to the package import).

- [ ] **Step 2: `git status` sanity check**

Run: `git status --short | grep "^??"` — expect no stray untouched `shell/src/ui/kit/` or `shell/src/map/` files (both directories should be fully empty and `git mv`-removed).

- [ ] **Step 3: Full quality gate**

Run: `cd /home/lenen/projets/geostudio/shell && npm run lint`
Expected: 0 errors (eslint + i18n coverage + aria-panel coverage).

Run: `cd /home/lenen/projets/geostudio/shell && npm run build`
Expected: production build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "chore(shell): wire AppBuilderProvider at every AppRenderer mount point"
```

---

### Task 12: E2E gate + branch review

**Files:** none (verification-only task).

- [ ] **Step 1: Run the full E2E suite**

Run: `cd /home/lenen/projets/geostudio/shell && npm run e2e`
Expected: **166 passed, 4 skipped, 0 failed** — same baseline as before this plan (`CLAUDE.md`, commit `a320c317`). Any new failure is a regression introduced by this extraction — bisect by re-running the specific failing spec against the last commit of the task suspected to have caused it (`git log --oneline` from this plan's commits), not by guessing.

- [ ] **Step 2: Revue finale de branche**

Per project convention (`CLAUDE.md`, "Exécution en subagent-driven-development : une revue par tâche **et** une revue finale de branche"): dispatch a review covering the whole diff since this plan's first commit — specifically check (a) no moved file's content differs from its pre-move version except the files this plan explicitly names as modified (Tasks 6, 8, 9, 10), (b) every `BuilderDataClient` optional-capability call site degrades UI cleanly (no runtime throw) when the capability is absent, (c) no leftover `TODO`/commented-out code from the migration.

- [ ] **Step 3: Update `CLAUDE.md`'s E2E baseline line if the pass count changed** (it shouldn't have — same tests, relocated code) and note the new package layout under "Comment on travaille" or wherever the repo layout is documented.

- [ ] **Step 4: Final commit**

```bash
cd /home/lenen/projets/geostudio
git add -A
git commit -m "docs: note packages/{ui-kit,app-builder} layout in CLAUDE.md"
```

Do not push, do not open a PR to `main` — per project convention, promotion to `main` is a separate, explicit step the user triggers (`git push origin dev` + `gh pr create --base main --head dev`), not part of this plan.

---

## Self-Review Notes (written while authoring this plan)

- **Spec coverage:** all 3 ports (Task 4), the adapter (Task 5), every subsystem listed in the design spec's §1.2 table (`core`/`editor`/`widgets`/`map`/`wc`/`types`/`i18n` — Tasks 3, 6-10), the workspace mechanics (Task 1), and the E2E gate (Task 12) each have a task. `pipeline/`, `visualQuery/`, `copilot/`, `print/`, `report/`, `appexport/`, `examples/`, `AlertRuleEditor.tsx`, `ConfigHistoryPanel.tsx`, `aggregates.ts` are explicitly named as **not** moving, with their consumer-side import fixes folded into the task that moves what they depend on (Tasks 6-9's "fix `shell/src/builder/*` consumers" steps) rather than a separate task — right-sized, since each is a one-line import-path change per file, not an independent deliverable.
- **Corrections made against the design spec while writing this plan** (ground-truth checks the spec's grep-based survey didn't catch): `BuilderDataClient.sampleFieldValues`/`.listDatasets` from the design spec don't correspond to any real `ItemClient` method (`sampleDataSourceField` exists with a different signature; nothing lists datasets) and are **not used by any file this plan moves** — dropped from the port entirely (YAGNI; `finance`'s plan is amended to match, see its own self-review). `exportDataSource` as a separate optional capability is dropped too — `DatasetDownloadButtons`/`datasetDownload.ts` only ever needed the 3 already-required methods (`queryDataSource`/`getCollectionSchema`/`featuresUrl`), verified by reading the real file in full. `CollectionSchema` carries a `collection: string` field the design spec's port sketch omitted — included here. Newly discovered top-level `builder/` files the spec's file count didn't individually name (`sdk.ts`, `templates.ts`, `undoStack.ts`, `useUndoableDraft.ts`, `exprBindings.ts`, `EChart.tsx`, `DatasetDownloadButtons.tsx`) are classified and placed in Tasks 6/8 above.
- **Type-closure risk (flagged, not silently resolved):** Task 3's type list was assembled by reading `api/types.ts` directly and following each reference by hand (`MapConfig` → `MapLayer` → `PopupConfig`/`MapViewport`/`BaseMap`, etc.) — believed complete, but Task 3 Step 4 explicitly instructs iterating on `tsc` output if a reference was missed rather than assuming the list is exhaustive. This is the single highest-risk step in the plan for a silent gap; do not skip Step 4's typecheck.
- **Placeholder scan:** no "TBD"/"handle appropriately" found on re-read. The two spots that defer a decision to the implementer (Task 5's parameter-signature note, Task 9 Step 2's per-file JSX gating) are both accompanied by an exact command to run to resolve them, not a vague instruction — acceptable per the skill's own guidance for genuinely file-specific mechanical work following a fixed pattern already demonstrated in full at least once in the plan.
- **Type consistency:** `BuilderDataClient`/`IdentityPort`/`I18nPort` names and shapes are identical between Task 4 (definition), Task 5 (adapter target), Task 6 (first consumer), and every later task's rewrite pattern — single definition, referenced everywhere else.
