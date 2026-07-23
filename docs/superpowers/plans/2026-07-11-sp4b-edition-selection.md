# SP-4b — Édition depuis sélection : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Table et Carte émettent `itemSelected` au clic sur une ligne/entité (comme le widget Liste le fait déjà) ; le widget Formulaire (livré par SP-4a) déclare une action `loadRecord` qui bascule en mode édition, pré-remplit les champs (et la géométrie point) depuis l'enregistrement sélectionné, et câble `feature.update`/`feature.delete` — deuxième sous-phase de SP-4, cf. [SP-4 — Formulaires dans le builder](../specs/2026-07-10-sp4-formulaires-builder-design.md) §1.

**Architecture:** Même bus d'actions que SP-4a (`ActionBus`, `useBusAction`) — Table/Carte émettent `itemSelected` avec un `DataRecord` complet, exactement comme Liste le fait déjà (`shell/src/builder/widgets/data.tsx`) ; le Formulaire déclare `actions: [..., "loadRecord"]` et bascule en mode édition, aucun nouveau mécanisme de bus. Le clic-sur-la-carte est la seule pièce entièrement nouvelle : `MapView.tsx` n'a aujourd'hui aucun hit-testing, seulement des couches GeoJSON en lecture — cette tâche y ajoute un écouteur de clic MapLibre par couche « feature », propre (attache/détache sans fuite), qui remonte le GeoJSON Feature cliqué (déjà porteur de son `id`, `properties`, `geometry` depuis le cœur OGC) via une nouvelle prop `onFeatureClick`.

**Tech Stack:** React 19 + TypeScript + Vitest + Testing Library (tests unitaires), MapLibre GL JS (déjà utilisé, `shell/src/map/MapView.tsx`), `@tanstack/react-query` (déjà utilisé). FastAPI (cœur — **aucune modification** ; `updateFeature`/`deleteFeature` sur `ItemClient` et les routes cœur correspondantes sont déjà livrées par SP-4a/SP-3b).

## Global Constraints

- **Aucun changement backend.** `PUT`/`DELETE /collections/{id}/items/{fid}` existent déjà et sont testés côté cœur (SP-3b) ; `ItemClient.updateFeature`/`.deleteFeature` existent déjà côté shell (SP-4a, posés mais non consommés) — ce plan est le premier à les appeler.
- **`PUT` remplace l'intégralité de l'objet** (pas de PATCH partiel, décision actée dès SP-3b/SP-4a). Conséquence directe pour ce plan : le payload `properties` soumis en édition doit inclure **tous** les champs configurés (sauf `unsupported`), **y compris les champs masqués (`hidden`)** — pas seulement les champs visibles/rendus. Omettre un champ masqué à la resoumission effacerait silencieusement sa valeur côté serveur lors d'une modification. Ce risque n'existait pas en SP-4a (création seule, aucune valeur préexistante à perdre) ; il devient réel dès que `updateFeature` entre en jeu — Task 5 le traite explicitement.
- **`itemSelected` transporte toujours un `DataRecord` complet** (`{ id, properties, geometry? }`, `shell/src/api/types.ts:159-163`) — Table et Carte émettent exactement la même forme que Liste (`shell/src/builder/widgets/data.tsx:47`), pour que `loadRecord` (Formulaire) et `flyTo`/`highlight` (Carte) restent interchangeables sur n'importe quelle source.
- **Le clic carte s'appuie sur l'`id` GeoJSON déjà fourni par le cœur.** Les endpoints `GET /collections/{id}/items[/{fid}]` (SP-3b) renvoient déjà chaque Feature avec un `id` au niveau racine (confirmé par `itemClient.ts`'s `queryDataSource` : `id: f.id ?? i`) — MapLibre expose nativement cet `id` sur les features cliqués (`e.features[0].id`) sans configuration `generateId`/`promoteId` supplémentaire côté `MapView`. Aucun changement du côté `addSource` n'est nécessaire pour ça.
- **UI d'édition non littéralement spécifiée, mais nécessaire à un flux utilisable** : le bandeau « Modification de l'enregistrement #… », le bouton « Annuler » et le bouton « Supprimer » (avec confirmation native `window.confirm`) sont des décisions de cadrage de ce plan, pas des exigences mot-à-mot de la spec — documentées ici pour transparence, cohérentes avec l'esprit de la spec (édition depuis sélection, feature.delete câblé).
- **Comportement après écriture réussie** (spec §6, étendu ici pour update/delete) : `feature.create` → repasse en mode création (vide) ; `feature.update` → reste sur l'enregistrement édité (ne vide pas le formulaire) ; `feature.delete` → repasse en mode création (l'enregistrement n'existe plus). Les trois cas invalident `["datasource"]` et émettent `submitted` (delete réutilise le même événement — la spec n'en nomme pas de distinct).
- **`updateFeature`/`deleteFeature` prennent un `fid: string`** (`shell/src/api/types.ts:116-117`) alors que `DataRecord.id: string | number` — toujours `String(record.id)`/`String(editingId)` à l'appel.
- Docs et messages utilisateur en français ; code/identifiants en anglais.
- TDD systématique ; commits conventional en français ; `cd shell && npm run test` et `npm run build` (`tsc --noEmit` + vite build) verts à la fin de chaque tâche.
- **Hors périmètre de ce plan** (différé à SP-4c par la spec §1) : template galerie « Application de saisie », spec E2E Playwright « déclarer un incident », vérification UI viewer (masquage des boutons d'écriture).

---

## Task 1: Table — émet `itemSelected` au clic sur une ligne

**Files:**
- Modify: `shell/src/builder/widgets/data.tsx:61-62` (déclaration `events`), `:128-131` (ligne `<tr>`)
- Modify: `shell/src/builder/widgets/data.test.tsx:62-66` (test existant étendu), et ajout d'un nouveau test en fin de fichier

**Interfaces:**
- Produces: `table` déclare désormais `events: ["itemSelected"]`, émis avec le `DataRecord` complet de la ligne cliquée — même forme que Liste.
- Consumes: rien de nouveau — `ctx.bus`/`ctx.widgetId` existent déjà dans `WidgetContext`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/data.test.tsx`, remplacer le test existant (actuellement lignes 62-66) :

```ts
test("list declares itemSelected event and setFilter action", () => {
  expect(getWidget("list")!.events).toContain("itemSelected");
  expect(getWidget("list")!.actions).toContain("setFilter");
  expect(getWidget("table")!.actions).toContain("setFilter");
});
```

par :

```ts
test("list and table declare itemSelected event and setFilter action", () => {
  expect(getWidget("list")!.events).toContain("itemSelected");
  expect(getWidget("list")!.actions).toContain("setFilter");
  expect(getWidget("table")!.events).toContain("itemSelected");
  expect(getWidget("table")!.actions).toContain("setFilter");
});
```

Puis ajouter en fin de fichier :

```ts
test("table emits itemSelected with the clicked row", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "flyTo", handler);
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime", bus, widgetId: "table1",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  await userEvent.click(screen.getByRole("cell", { name: "Parc A" }));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" } });
});
```

(`ActionBus` est déjà importé dans ce fichier — vérifier la ligne d'import existante `import { ActionBus } from "../ActionBus";` avant d'en ajouter une nouvelle.)

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: FAIL — `getWidget("table")!.events` est `undefined` (`table` ne déclare aucun `events` aujourd'hui), donc `.toContain` échoue ; le clic sur la cellule n'émet rien (`handler` jamais appelé).

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/data.tsx`, dans le bloc `registerWidget({ type: "table", ... })`, entre `defaultSize` (ligne 61) et `actions` (ligne 62), ajouter :

```ts
    events: ["itemSelected"],
```

Puis, dans le `<tbody>` du `Component` de `table` (lignes 126-132), modifier la ligne `<tr>` (ligne 128) :

```tsx
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className="cursor-pointer hover:bg-[var(--gs-color-surface)]"
                  onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r)}
                >
                  {columns.map((c) => <td key={c} className="border-b border-[var(--gs-color-border)] p-1">{String(r.properties[c] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/data.tsx src/builder/widgets/data.test.tsx
git commit -m "feat(shell): widget Table — émet itemSelected au clic sur une ligne (SP-4b)"
```

---

## Task 2: `MapView` — détection de clic sur une couche « feature »

**Files:**
- Modify: `shell/src/test/MockMaplibreMap.ts:1-77` (extension de `on`/ajout de `off`/`fireOnLayer`)
- Modify: `shell/src/map/MapView.tsx:7` (import), `:17-61` (`applyLayers`), `:89-162` (composant : refs, prop, appels)
- Modify: `shell/src/map/MapView.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `MapView` accepte une nouvelle prop `onFeatureClick?: (record: DataRecord) => void`, invoquée quand l'utilisateur clique sur une entité d'une couche `kind: "feature"`. Task 3 la consomme depuis `mapWidget.tsx`.
- Consumes: `DataRecord` (existant, `shell/src/api/types.ts`).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/test/MockMaplibreMap.ts`, remplacer entièrement le fichier par :

```ts
export type Recorded = { id: string; spec: unknown };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: { style: string; center: [number, number]; zoom: number };
  handlers: Record<string, Array<() => void>> = {};
  layerHandlers: Record<string, Array<(e: unknown) => void>> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  controls: unknown[] = [];
  removed = false;
  throwOnAddLayer = new Set<string>();
  flyToArgs: unknown[] = [];

  constructor(opts: MockMap["opts"]) {
    this.opts = opts;
    mapInstances.push(this);
  }

  on(event: string, arg2: string | (() => void), cb?: (e: unknown) => void) {
    if (typeof arg2 === "string" && cb) {
      const key = `${event}:${arg2}`;
      (this.layerHandlers[key] ??= []).push(cb);
    } else if (typeof arg2 === "function") {
      (this.handlers[event] ??= []).push(arg2);
      if (event === "load") arg2();
    }
    return this;
  }
  off(event: string, layerId: string, cb: (e: unknown) => void) {
    const key = `${event}:${layerId}`;
    this.layerHandlers[key] = (this.layerHandlers[key] ?? []).filter((h) => h !== cb);
  }
  fire(event: string) {
    this.handlers[event]?.forEach((cb) => cb());
  }
  fireOnLayer(event: string, layerId: string, payload: unknown) {
    this.layerHandlers[`${event}:${layerId}`]?.forEach((cb) => cb(payload));
  }
  addSource(id: string, spec: unknown) {
    const rec: Recorded & { setData?: (d: unknown) => void } = { id, spec };
    rec.setData = (d: unknown) => {
      rec.spec = { ...(rec.spec as object), data: d };
    };
    this.sources.push(rec);
  }
  flyTo(opts: unknown) {
    this.flyToArgs.push(opts);
  }
  addLayer(layer: { id: string; [k: string]: unknown }) {
    if (this.throwOnAddLayer.has(layer.id)) throw new Error(`boom ${layer.id}`);
    this.layers.push(layer);
  }
  getLayer(id: string) {
    return this.layers.find((l) => l.id === id);
  }
  getSource(id: string) {
    return this.sources.find((s) => s.id === id);
  }
  removeLayer(id: string) {
    this.layers = this.layers.filter((l) => l.id !== id);
  }
  removeSource(id: string) {
    this.sources = this.sources.filter((s) => s.id !== id);
  }
  getCenter() {
    return { lng: this.opts.center[0], lat: this.opts.center[1] };
  }
  getZoom() {
    return this.opts.zoom;
  }
  loaded() {
    return true;
  }
  isStyleLoaded() {
    return true;
  }
  addControl(control: unknown) {
    this.controls.push(control);
    return this;
  }
  removeControl(control: unknown) {
    this.controls = this.controls.filter((c) => c !== control);
    return this;
  }
  remove() {
    this.removed = true;
  }
}
```

(Seuls les champs `layerHandlers`, la signature de `on`, la méthode `off`, et la méthode `fireOnLayer` sont nouveaux — le reste du fichier est inchangé, réécrit ici en entier pour un `Write` propre.)

Puis, dans `shell/src/map/MapView.test.tsx`, ajouter en fin de fichier :

```ts
test("emits a feature click via onFeatureClick", () => {
  const onFeatureClick = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  render(<MapView config={cfg} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "a", {
    features: [{ id: 7, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } }],
  });
  expect(onFeatureClick).toHaveBeenCalledWith({
    id: 7,
    properties: { nom: "Parc A" },
    geometry: { type: "Point", coordinates: [1, 2] },
  });
});

test("does nothing when a click event carries no features", () => {
  const onFeatureClick = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  render(<MapView config={cfg} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "a", { features: [] });
  expect(onFeatureClick).not.toHaveBeenCalled();
});

test("detaches the old layer's click handler when config.layers replaces it", () => {
  const onFeatureClick = vi.fn();
  const first: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  const { rerender } = render(<MapView config={first} onFeatureClick={onFeatureClick} />);
  const map = mapInstances[0];
  const second: MapConfig = {
    ...config,
    layers: [{ id: "b", title: "B", visible: true, kind: "feature", url: "https://fs/b" }],
  };
  rerender(<MapView config={second} onFeatureClick={onFeatureClick} />);
  map.fireOnLayer("click", "a", { features: [{ id: 1, properties: {}, geometry: null }] });
  expect(onFeatureClick).not.toHaveBeenCalled();
  map.fireOnLayer("click", "b", { features: [{ id: 2, properties: {}, geometry: null }] });
  expect(onFeatureClick).toHaveBeenCalledWith({ id: 2, properties: {}, geometry: null });
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL sur les 3 nouveaux tests — `MockMap.fireOnLayer` n'existe pas encore avant l'édition de Step 1 (si Step 1 est déjà appliqué au mock, alors `MapView` n'a encore aucun code qui appelle `map.on("click", layer.id, ...)`, donc `fireOnLayer` ne déclenche jamais `onFeatureClick`) — dans les deux cas, `onFeatureClick` n'est jamais appelé.

- [ ] **Step 3: Implémenter**

Dans `shell/src/map/MapView.tsx`, modifier l'import de types (ligne 7) :

```ts
import type { DataRecord, MapConfig } from "../api/types";
```

Remplacer `applyLayers` (lignes 17-61) :

```ts
function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  onFeatureClick: (record: DataRecord) => void,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    const prevHandler = clickHandlers.get(id);
    if (prevHandler) {
      map.off("click", id, prevHandler);
      clickHandlers.delete(id);
    }
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({
          id: layer.id,
          type: "fill",
          source: layer.id,
          "source-layer": layer.sourceLayer,
          paint: layer.paint ?? {},
        });
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
        const handler = (e: maplibregl.MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f) return;
          onFeatureClick({ id: (f.id ?? "") as string | number, properties: f.properties ?? {}, geometry: f.geometry });
        };
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map. Roll back any
      // half-added source/layer so it can't orphan or clash on the next apply.
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
}
```

Modifier la signature du composant et ajouter les refs (lignes 89-107) :

```ts
export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
    onFeatureClick?: (record: DataRecord) => void;
  }
>(function MapView({ config, onViewChange, onFeatureClick }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(new Map());
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const layersRef = useRef(config.layers);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
```

Modifier les deux appels à `applyLayers` : dans le `map.on("load", ...)` (ligne 123 dans le fichier original) :

```ts
      applyLayers(map, layersRef.current, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
```

et dans le `useEffect` sur `config.layers` (ligne 146 dans le fichier original) :

```ts
    applyLayers(map, config.layers, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS — tous les tests, y compris les 12 déjà existants (aucun n'est cassé par le 4ᵉ/5ᵉ paramètre ajouté à `applyLayers`, car les deux call sites sont mis à jour ensemble).

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/test/MockMaplibreMap.ts src/map/MapView.tsx src/map/MapView.test.tsx
git commit -m "feat(shell): MapView — détection de clic sur une couche feature (SP-4b)"
```

---

## Task 3: Carte — émet `itemSelected` au clic sur une entité

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx:29` (déclaration `events`), `:55-59` (prop `onFeatureClick`)
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx:14-31` (mock `MapView` étendu), `:52-55` (test étendu), ajout d'un nouveau test

**Interfaces:**
- Produces: `map` déclare `events: ["extentChanged", "itemSelected"]`, émis avec le `DataRecord` renvoyé par `MapView.onFeatureClick` (Task 2).
- Consumes: `MapView`'s `onFeatureClick` prop (Task 2).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/mapWidget.test.tsx`, remplacer le mock de `MapView` (lignes 14-31) :

```tsx
vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange, onFeatureClick }: {
        config: { layers: { url?: string }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
        onFeatureClick?: (record: { id: string | number; properties: Record<string, unknown>; geometry?: unknown }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9 })}>
          layers:{config.layers.length} url:{config.layers[0]?.url ?? ""}
          <button
            type="button"
            data-testid="feature"
            onClick={() => onFeatureClick?.({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } })}
          >
            feature
          </button>
        </div>
      );
    },
  ),
}));
```

Puis remplacer le test existant (lignes 52-55) :

```ts
test("map declares extentChanged event and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toContain("extentChanged");
  expect(getWidget("map")!.actions).toEqual(expect.arrayContaining(["flyTo", "highlight"]));
});
```

par :

```ts
test("map declares extentChanged/itemSelected events and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toEqual(["extentChanged", "itemSelected"]);
  expect(getWidget("map")!.actions).toEqual(expect.arrayContaining(["flyTo", "highlight"]));
});
```

Puis ajouter en fin de fichier :

```ts
test("map emits itemSelected when a feature is clicked", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "itemSelected", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />);
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } });
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL — `getWidget("map")!.events` vaut encore `["extentChanged"]` (pas d'`itemSelected`) ; le bouton `data-testid="feature"` n'existe déjà dans le mock (ajouté au Step 1), mais `mapWidget.tsx` ne passe encore aucune prop `onFeatureClick` à `MapView`, donc le clic n'émet rien sur le bus.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/mapWidget.tsx`, ligne 29 :

```ts
    events: ["extentChanged", "itemSelected"],
```

Et dans le JSX (lignes 55-59), ajouter la prop après `onViewChange` :

```tsx
          <MapView
            ref={handle}
            config={config}
            onViewChange={(v) => ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v)}
            onFeatureClick={(record) => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record)}
          />
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/mapWidget.tsx src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): widget Carte — émet itemSelected au clic sur une entité (SP-4b)"
```

---

## Task 4: Formulaire — action `loadRecord`, mode édition, bouton Annuler

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx:8` (import), `:273-301` (état + `resetTo`), `:373` (bandeau d'édition), `:399` (déclaration `actions`)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: action bus `loadRecord` sur le widget `form`, qui bascule `FormComponent` en mode édition (état `editingId: string | number | null`). `resetTo()` (existant, Task SP-4a) est modifié pour aussi remettre `editingId` à `null`.
- Consumes: `DataRecord` (existant), émis par Table/Carte (Tasks 1/3) ou tout autre widget compatible.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.tsx`, l'import de types (ligne 8) devra devenir (préparé ici, câblé au Step 3) :
```ts
import type { CollectionSchema, DataRecord, DataSource } from "../../api/types";
```

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter en fin de fichier :

```tsx
test("loadRecord pre-fills the form from the selected record's properties", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue("Fuite existante"));
  expect(screen.getByLabelText("Gravité")).toHaveValue("moyenne");
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});

test("loadRecord pre-fills longitude/latitude for a Point geometry", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const client = { createFeature: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields: visibleFields, submitLabel: "Enregistrer", geometryType: "Point" }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer: "incidents" }, bus, widgetId: "form1" } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  bus.emit("table1", "itemSelected", {
    id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" },
    geometry: { type: "Point", coordinates: [2.35, 48.85] },
  });
  await waitFor(() => expect(screen.getByLabelText("Longitude")).toHaveValue(2.35));
  expect(screen.getByLabelText("Latitude")).toHaveValue(48.85);
});

test("the Annuler button exits edit mode and clears the form", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(screen.queryByText(/Modification de l'enregistrement/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Titre")).toHaveValue("");
});

test("form declares loadRecord alongside reset", () => {
  expect(getWidget("form")!.actions).toEqual(["reset", "loadRecord"]);
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — `loadRecord` n'est déclaré dans aucune action du widget (`bus.configure` route vers une action qui n'existe pas côté `form1`, donc `bus.emit` ne fait rien), le bandeau « Modification de l'enregistrement » n'existe pas, le bouton « Annuler » n'existe pas.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, appliquer l'import préparé au Step 1 (ligne 8).

Dans `FormComponent`, ajouter l'état `editingId` juste après `const [genericError, setGenericError] = useState(false);` (ligne 285) :

```ts
  const [editingId, setEditingId] = useState<string | number | null>(null);
```

Remplacer `resetTo` (lignes 292-300) pour qu'il remette aussi `editingId` à `null` :

```ts
  function resetTo() {
    setValues({});
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setLon("");
    setLat("");
    setEditingId(null);
    write.reset();
  }
```

Juste après la ligne `useBusAction(ctx.bus, ctx.widgetId, "reset", resetTo);` (ligne 301), ajouter :

```ts
  function handleLoadRecord(payload?: unknown) {
    const record = payload as DataRecord | undefined;
    if (!record) return;
    setEditingId(record.id);
    setValues({ ...record.properties });
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    const geom = record.geometry as { type?: string; coordinates?: number[] } | undefined;
    if (geometryType === "Point" && geom?.type === "Point" && Array.isArray(geom.coordinates)) {
      setLon(String(geom.coordinates[0]));
      setLat(String(geom.coordinates[1]));
    } else {
      setLon("");
      setLat("");
    }
  }
  useBusAction(ctx.bus, ctx.widgetId, "loadRecord", handleLoadRecord);
```

Dans le JSX, juste avant `<div className="mt-auto flex items-center gap-2">` (ligne 373), ajouter le bandeau d'édition :

```tsx
      {editingId !== null && (
        <p className="text-xs text-[var(--gs-color-muted)]">
          Modification de l'enregistrement #{String(editingId)}
          <button type="button" className="ml-2 text-xs underline" onClick={resetTo}>Annuler</button>
        </p>
      )}
```

Enfin, dans `registerFormWidget()`, ligne 399 :

```ts
    actions: ["reset", "loadRecord"],
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — action loadRecord, mode édition, bouton Annuler (SP-4b)"
```

---

## Task 5: Formulaire — soumission création/modification (`feature.update`)

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` — juste après la déclaration de `fields` (liste `allFields`), la mutation `write` (`const write = useMutation({...})`), la boucle qui construit `properties` dans `handleSubmit`, et la branche de succès du `try` de `handleSubmit`. **Ces quatre points sont désormais après les insertions de Task 4** (état `editingId`, `handleLoadRecord`, bandeau d'édition) — repérer chacun par son contenu (nom de variable/fonction), pas par un numéro de ligne figé.
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: en mode édition (`editingId !== null`), la soumission appelle `ItemClient.updateFeature(collectionId, String(editingId), feature)` au lieu de `createFeature`, et ne réinitialise pas le formulaire après succès.
- Consumes: `ItemClient.updateFeature` (existant, SP-4a), `editingId` (Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter en fin de fichier :

```tsx
test("submitting while editing calls updateFeature with the record id and stays on the record", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const { client } = renderConnectedForm({ client: { updateFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByDisplayValue("Fuite existante");
  await userEvent.clear(screen.getByLabelText("Titre"));
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite corrigée");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.updateFeature).toHaveBeenCalledWith("incidents", "7", {
      type: "Feature",
      properties: { titre: "Fuite corrigée", gravite: "moyenne" },
      geometry: null,
    }),
  );
  expect(screen.getByLabelText("Titre")).toHaveValue("Fuite corrigée");
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});

test("createFeature is still called (not updateFeature) when not editing", async () => {
  const updateFeature = vi.fn();
  const { client } = renderConnectedForm({ client: { updateFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(client.createFeature).toHaveBeenCalled());
  expect(updateFeature).not.toHaveBeenCalled();
});

test("updating a record resubmits a hidden field's original value unchanged", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const { client } = renderConnectedForm({ client: { updateFeature }, bus });
  bus.emit("table1", "itemSelected", {
    id: 7,
    properties: { titre: "Fuite existante", gravite: "moyenne", notes_internes: "confidentiel" },
  });
  await screen.findByDisplayValue("Fuite existante");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.updateFeature).toHaveBeenCalledWith("incidents", "7", {
      type: "Feature",
      properties: { titre: "Fuite existante", gravite: "moyenne", notes_internes: "confidentiel" },
      geometry: null,
    }),
  );
});
```

(`notes_internes` fait déjà partie de `visibleFields` — cf. `form.test.tsx`, `{ name: "notes_internes", ..., hidden: true, required: false }` — utilisé tel quel par `renderConnectedForm()`'s valeur par défaut.)

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — les trois nouveaux tests échouent : `updateFeature` n'est jamais appelé (la mutation appelle toujours `createFeature`), et le champ masqué `notes_internes` n'est jamais inclus dans `properties` (la boucle actuelle n'itère que les champs visibles).

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, dans `FormComponent`, juste après la déclaration de `fields` (lignes 276-278), ajouter :

```ts
  const allFields = ((props.fields as FormField[] | undefined) ?? []).filter((f) => f.type !== "unsupported");
```

Remplacer la mutation `write` (posée en SP-4a — repérer le bloc `const write = useMutation({ ... });`, désormais situé après l'état `editingId` et avant `resetTo` ajoutés en Task 4) :

```ts
  const write = useMutation({
    mutationFn: (input: { properties: Record<string, unknown>; geometry: unknown | null }) => {
      const collectionId = ctx.data?.layer ?? "";
      const feature = { type: "Feature" as const, properties: input.properties, geometry: input.geometry };
      return editingId !== null
        ? client.updateFeature(collectionId, String(editingId), feature)
        : client.createFeature(collectionId, feature);
    },
  });
```

Dans `handleSubmit`, remplacer la boucle qui construit `properties` (juste après `setGenericError(false);`, avant le calcul de `geometry`) pour itérer `allFields` au lieu de `fields` :

```ts
    const properties: Record<string, unknown> = {};
    allFields.forEach((f) => {
      if (values[f.name] !== undefined) properties[f.name] = values[f.name];
    });
```

Puis, dans le `try` de `handleSubmit` (juste après `await write.mutateAsync({ properties, geometry });`), remplacer la branche de succès pour ne réinitialiser qu'en mode création :

```ts
    try {
      await write.mutateAsync({ properties, geometry });
      queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      if (editingId === null) {
        resetTo();
      }
    } catch (err) {
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — soumission création/modification, préserve les champs masqués (SP-4b)"
```

---

## Task 6: Formulaire — suppression (`feature.delete`)

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` — juste après la mutation `write` (posée/modifiée en Task 5), ajout de la mutation `remove` + `handleDelete` ; dans le bandeau d'édition (ajouté en Task 4), ajout du bouton Supprimer. **Repérer par contenu** (nom de variable/fonction, texte du bandeau), les numéros de ligne d'origine ne sont plus valables après les insertions des Tasks 4-5.
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: en mode édition, un bouton « Supprimer » (avec confirmation native) appelle `ItemClient.deleteFeature(collectionId, String(editingId))`, invalide `["datasource"]`, émet `submitted`, puis repasse en mode création.
- Consumes: `ItemClient.deleteFeature` (existant, SP-4a), `editingId`/`resetTo` (Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter en fin de fichier :

```tsx
test("Supprimer calls deleteFeature after confirmation, invalidates, and exits edit mode", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const deleteFeature = vi.fn().mockResolvedValue(undefined);
  const { client, invalidateSpy } = renderConnectedForm({ client: { deleteFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(client.deleteFeature).toHaveBeenCalledWith("incidents", "7"));
  expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["datasource"] });
  expect(screen.queryByText(/Modification de l'enregistrement/)).not.toBeInTheDocument();
});

test("Supprimer does nothing when the confirmation is declined", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const deleteFeature = vi.fn();
  const { client } = renderConnectedForm({ client: { deleteFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(client.deleteFeature).not.toHaveBeenCalled();
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — le bouton « Supprimer » n'existe pas encore dans le rendu.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, juste après la déclaration de la mutation `write` (après le bloc ajouté/modifié en Task 5, avant `function resetTo() {`), ajouter :

```ts
  const remove = useMutation({
    mutationFn: () => client.deleteFeature(ctx.data?.layer ?? "", String(editingId)),
  });

  async function handleDelete() {
    if (editingId === null) return;
    if (!window.confirm("Supprimer cet enregistrement ?")) return;
    try {
      await remove.mutateAsync();
      queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties: {} });
      resetTo();
    } catch (err) {
      setGenericError(true);
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", { message: err instanceof Error ? err.message : "unknown" });
    }
  }
```

Puis, dans le bandeau d'édition (ajouté en Task 4), ajouter le bouton juste après « Annuler » :

```tsx
      {editingId !== null && (
        <p className="text-xs text-[var(--gs-color-muted)]">
          Modification de l'enregistrement #{String(editingId)}
          <button type="button" className="ml-2 text-xs underline" onClick={resetTo}>Annuler</button>
          <button
            type="button"
            className="ml-2 text-xs text-red-600 underline"
            disabled={remove.isPending}
            onClick={handleDelete}
          >
            Supprimer
          </button>
        </p>
      )}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — suppression feature.delete (SP-4b)"
```

---

## Couverture spec → tâches (auto-vérification)

- §1 SP-4b « La Table émet itemSelected (comme le widget List le fait déjà) » → Task 1.
- §1 SP-4b « la Carte émet aussi itemSelected au clic sur une entité — travail nouveau » → Tasks 2-3.
- §1 SP-4b « le Formulaire déclare une action loadRecord qui bascule en mode édition » → Task 4.
- §1 SP-4b « feature.update/feature.delete câblés » → Tasks 5-6.
- §1 SP-4b « invalidation TanStack Query des data sources affectées après toute écriture (§5) » → déjà couvert par le mécanisme SP-4a (`["datasource"]`), réutilisé sans modification par update (Task 5) et delete (Task 6).
- §2 « Sélection→édition... Table et Carte émettent itemSelected avec le DataRecord complet ; le Formulaire déclare actions: ["loadRecord", "reset"] » → Tasks 1, 3, 4 (ordre `["reset", "loadRecord"]` — l'ordre des deux chaînes dans le tableau n'a pas de sémantique, seule leur présence compte).
- §3 architecture (bus, `centerFromPayload`/`geometryFromPayload` comme précédent pour transporter des payloads structurés) → Task 4 (`handleLoadRecord` suit le même style de cast que la Carte).
- §6 « reste sur l'enregistrement si feature.update » → Task 5.
- §7 stratégie de tests « Table et Carte émettent itemSelected... le Formulaire déclare loadRecord qui bascule en mode édition... feature.update/feature.delete câblés » → couvert par les tests de chaque tâche (bus wiring, pré-remplissage, branchement update/delete).
- §9 risques « le binding sélection→édition est le morceau dur » → confirmé par l'ampleur de Task 2 (seule pièce entièrement nouvelle du plan, hit-testing MapLibre).
- Hors périmètre explicite de ce plan (SP-4c) : template galerie, spec E2E, vérification UI viewer — non traités ici, conformément à la spec §1.
