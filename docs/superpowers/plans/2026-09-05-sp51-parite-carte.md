# SP-51 — Parité carte : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les écarts de parité entre l'éditeur de carte autonome
(`shell/src/pages/MapEditorPage.tsx` + `shell/src/map/*`) et le widget carte
de l'App Builder (`shell/src/builder/widgets/mapWidget.tsx`) identifiés par
GAP-52 (4 jumelles réelles sur 5 annoncées — la 5e, palette theme-primary,
est déjà implémentée, cf. spec §2.5), GAP-53 (outils de mesure jamais
montés en édition), GAP-35 (opacité raster sans UI), GAP-45 (peinture brute
sans UI), GAP-36 (aucune UI d'auteur pour une couche `deck`) — et vérifier
la clôture déjà acquise de GAP-46 (persistance collectionId/pkColumn sur une
couche `feature`, déjà corrigée par SP-42).

**Architecture:** 9 tâches, dans l'ordre du moins au plus risqué défini par
la spec §9. Chaque tâche pose son filet de test avant de toucher le code
(TDD), sauf la Tâche 1 qui est une vérification pure (aucun code à
protéger, rien à modifier).

**Tech Stack:** TypeScript/React + Vitest (shell). Aucune tâche de ce plan
ne touche au cœur Python.

**Document source :**
`docs/superpowers/specs/2026-09-05-sp51-parite-carte-design.md` (sections
citées : §2 GAP-52 poste par poste, §3 GAP-53, §4 GAP-35, §5 GAP-45, §6
GAP-36, §7 coordination SP-54, §8 GAP-46, §9 ordre).

## Global Constraints

- **Coordination SP-54 (spec §7) — à lire avant de lancer ce plan ou
  SP-54 en parallèle.** Les deux chantiers sont issus de la même revue,
  découpés après SP-43. Chevauchement confirmé : `shell/src/api/base.ts`
  (SP-54 y ajoute une invalidation de `datasetCache` ; ce plan n'y touche
  pas, sauf si la Tâche 8, ci-dessous, découvre un besoin imprévu).
  Chevauchement probable mais non garanti sur `shell/src/api/types.ts`
  (interface `ItemClient` — SP-54 y ajoute `createGroup`/`addMember`/
  `Me` étendu ; ce plan n'y ajoute qu'une méthode, `sampleDataSourceField`,
  Tâche 8). **Recommandation : séquencer ce plan et le plan SP-54 (l'un
  puis l'autre, ordre indifférent) ou les confier à la même session/agent
  si une exécution simultanée est souhaitée.** Ne pas lancer deux
  implémenteurs différents en parallèle sans l'un des deux garde-fous —
  précédent CLAUDE.md « Sessions concurrentes sur le même arbre ».
- **`ItemClient` reste le sas unique** (règle n°1 CLAUDE.md) : toute
  nouvelle capacité passe par une méthode de l'interface exportée, jamais
  par un appel direct au cœur depuis un composant.
- **Config déclarative, pas de logique cachée** (règle n°2 CLAUDE.md) :
  les nouveaux réglages (basemap/terrain/caméra du widget, `deck` layer,
  peinture brute) sont tous des champs de document, jamais un état caché
  côté composant qui ne survivrait pas à un rechargement.
- **TDD systématique** : chaque tâche écrit son test avant son code, sauf
  mention contraire (vérification pure).
- **Suite complète rejouée avant de clore chaque tâche** :
  `cd shell && npx vitest run` (au minimum les fichiers touchés + suite
  complète avant le dernier commit de la tâche, piège CLAUDE.md n°6).
- Commits **conventional**, français, un sujet par commit
  (`feat(shell): ...`, `test(shell): ...`, `fix(shell): ...`).
- **Régénération OpenAPI/types TS** : aucune tâche de ce plan ne touche au
  cœur ni à une route HTTP — pas de régénération attendue.
- **Hors périmètre explicite (spec §10)** : le contrat `ItemClient` existant
  (seule extension additive : Tâche 8), l'exposition MCP de la création
  d'une couche `deck`, toute modification de `domains/layers.ts`/`base.ts`
  hors de la Tâche 8, la 5e jumelle du GAP-52 (déjà implémentée).

---

## Task 1 : vérification de clôture de GAP-46 (aucune correction)

Risque : nul. Aucun code de production modifié — cette tâche confirme que
le défaut décrit par GAP-46 (persistance `collectionId`/`pkColumn` sur une
couche `feature`) est déjà corrigé et déjà couvert par deux filets
distincts, et documente cette clôture pour qu'un futur backlog ne le
rouvre pas par erreur (cf. spec §8).

**Files:**
- Aucun fichier modifié.
- Vérifie : `shell/src/api/base.ts:70-82`, `shell/src/api/itemClient.test.ts:583-625,657-678`.

- [ ] **Step 1 : relire `toFrontLayer()` cas `"feature"`, confirmer la lecture de `collectionId`/`pkColumn`**

```bash
sed -n '70,82p' shell/src/api/base.ts
```

Attendu : lignes 77-78 lisent déjà `...(l.collectionId ? { collectionId: l.collectionId } : {})`
et `...(l.pkColumn ? { pkColumn: l.pkColumn } : {})` dans la branche `case "feature"`.

- [ ] **Step 2 : lancer les deux tests qui couvrent ce cas précis**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "getMapConfig reads collectionId/pkColumn on a feature"
cd shell && npx vitest run src/api/itemClient.test.ts -t "feature: every optional field survives"
```

Expected: les deux passent (2 passed).

- [ ] **Step 3 : falsifier un instant pour confirmer que le filet réagirait à une régression**

Retirer temporairement `...(l.pkColumn ? { pkColumn: l.pkColumn } : {}),` de la
branche `case "feature"` de `toFrontLayer()` dans `shell/src/api/base.ts`,
relancer les deux tests ci-dessus, confirmer qu'**au moins un des deux**
échoue, puis restaurer (`git checkout -- shell/src/api/base.ts`).

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "feature: every optional field survives"
# confirmer FAIL sur out.pkColumn, puis restaurer le fichier
git diff --stat shell/src/api/base.ts   # doit être vide après restauration
```

- [ ] **Step 4 : aucun commit de code — documenter la clôture dans le message du commit suivant**

Cette tâche ne produit aucun diff à committer (vérification pure). La
confirmation de clôture est portée par ce plan lui-même (ce fichier) et par
la spec SP-51 §8 — ne pas créer de commit vide.

---

## Task 2 (GAP-53) : câbler `interactiveTools` dans `MapEditorPage`

Risque : très bas. Mécanisme déjà partagé avec le widget carte
(`ctx.mode !== "edit"`, `mapWidget.tsx:321`) — aucune logique nouvelle,
juste une prop manquante sur l'instance de `MapView` en mode édition.

**Files:**
- Modify: `shell/src/pages/MapEditorPage.tsx` (instance `MapView` du mode
  édition normal, ligne ~145 — **pas** l'instance du mode export, ligne
  ~96, qui reste délibérément sans outils, rendu figé pour Playwright)
- Test: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `MapView`'s prop `interactiveTools?: boolean`
  (`shell/src/map/MapView.tsx:890`), qui monte déjà
  `MapMeasureSketchToolbar` (bouton texte « Mesurer »,
  `shell/src/map/MapMeasureSketchToolbar.tsx:421-427`) quand elle vaut
  `true` et que la carte est prête.
- Produces: rien de nouveau consommé ailleurs.

- [ ] **Step 1 : écrire le test avant le câblage**

```ts
// shell/src/pages/MapEditorPage.test.tsx — ajouter à la suite des tests existants
test("les outils de mesure/croquis sont montés en édition (GAP-53)", async () => {
  stubMatchMedia(false);
  const client = makeClient({/* même patron que les tests existants du fichier */});
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <MapEditorPage pk="1" />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("mapview-ready")).toBeInTheDocument());
  // Adapter le sélecteur exact au mock MapView réellement utilisé par ce
  // fichier (il monte le vrai MapView, mocké seulement au niveau
  // maplibre-gl/deck.gl — cf. imports du fichier) : la carte doit devenir
  // "ready" (mapInstances mock) avant que le bouton apparaisse, comme pour
  // tout test existant de ce fichier qui affirme sur le rendu post-idle.
  expect(await screen.findByRole("button", { name: "Mesurer" })).toBeInTheDocument();
});
```

Lire d'abord 2-3 tests existants du fichier qui attendent la carte "ready"
(le patron exact de synchronisation avec `mapInstances`/l'événement `idle`
mocké) avant d'écrire celui-ci — ne pas deviner le mécanisme d'attente.

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (bouton absent)**

```bash
cd shell && npx vitest run src/pages/MapEditorPage.test.tsx -t "GAP-53"
```

Expected: `FAIL` — le bouton « Mesurer » n'existe pas.

- [ ] **Step 3 : câbler `interactiveTools` sur l'instance d'édition**

```tsx
// shell/src/pages/MapEditorPage.tsx, instance MapView du mode édition (~ligne 145)
<MapView
  ref={mapViewRef}
  config={draft}
  onViewChange={setView}
  interactiveTools
  getAuthToken={client.getAuthToken}
  getCoreUrl={client.getCoreUrl}
  loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
/>
```

Toujours `true` (pas conditionné à `!readOnly`) : mesurer une distance ou
faire un croquis ne modifie pas `draft`/ne nécessite pas la permission
d'écriture — c'est un outil de lecture, symétrique du mode
Aperçu/Exécution où il est déjà systématiquement actif.

- [ ] **Step 4 : lancer le test, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/pages/MapEditorPage.test.tsx -t "GAP-53"
```

- [ ] **Step 5 : suite complète du fichier + suite complète shell**

```bash
cd shell && npx vitest run src/pages/MapEditorPage.test.tsx
cd shell && npx vitest run
```

- [ ] **Step 6 : commit**

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "$(cat <<'EOF'
fix(shell): monte les outils de mesure/croquis dans l'éditeur de carte

GAP-53 : MapEditorPage ne passait jamais interactiveTools à MapView, les
rendant accessibles seulement en mode Aperçu/Exécution d'App ou sur un
site publié. Mécanisme déjà partagé avec le widget carte de l'App
Builder (ctx.mode !== "edit") — oubli de câblage, pas un mécanisme neuf.
EOF
)"
```

---

## Task 3 (GAP-35) : contrôle d'opacité pour une couche raster

Risque : bas. Round-trip API déjà complet (`RawMapLayer.opacity`,
`toFrontLayer()` cas `"raster"`) — seul le contrôle UI manque.

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx` (nouveau bloc conditionnel pour
  `layer.kind === "raster"`, symétrique du bloc existant pour
  `vector`/`feature`)
- Test: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `MapLayer` cas `raster` (`opacity?: number`,
  `shell/src/api/types.ts:204-211`).
- Produces: rien de nouveau côté `ItemClient` — `onChange` sur `MapLayer[]`
  suffit, patron déjà utilisé par `toggle`/`remove`/`move` dans ce même
  fichier.

- [ ] **Step 1 : lire le patron existant du bloc conditionnel**

```bash
sed -n '215,231p' shell/src/map/LayersPanel.tsx
```

- [ ] **Step 2 : écrire le test avant le contrôle**

```ts
// shell/src/map/LayersPanel.test.tsx
test("une couche raster expose un contrôle d'opacité (GAP-35)", () => {
  const layers: MapLayer[] = [
    { id: "r1", title: "Ortho", visible: true, kind: "raster", tilesUrl: "https://t", opacity: 1 },
  ];
  const onChange = vi.fn();
  render(<LayersPanel layers={layers} onChange={onChange} />);
  const slider = screen.getByRole("slider", { name: /opacité/i });
  fireEvent.change(slider, { target: { value: "0.4" } });
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "r1", opacity: 0.4 }),
  ]);
});
```

Adapter le rôle ARIA exact (`slider` via `<input type="range">`, ou un
`spinbutton` via `<input type="number">` — trancher au Step 3 selon ce qui
est le plus cohérent avec `CameraControls.tsx`, qui utilise déjà un
`<input type="range">` pour un réglage 0-1 continu analogue).

- [ ] **Step 3 : lancer le test, vérifier qu'il échoue (contrôle absent)**

```bash
cd shell && npx vitest run src/map/LayersPanel.test.tsx -t "GAP-35"
```

- [ ] **Step 4 : ajouter le bloc conditionnel raster**

```tsx
// shell/src/map/LayersPanel.tsx — à côté du bloc vector/feature existant (~ligne 215)
{layer.kind === "raster" && (
  <div className="basis-full pl-2">
    <label className="flex flex-col gap-1 text-sm">
      Opacité — {Math.round((layer.opacity ?? 1) * 100)}%
      <input
        aria-label="Opacité"
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={layer.opacity ?? 1}
        onChange={(e) =>
          onChange(
            layers.map((l) =>
              l.id === layer.id ? { ...l, opacity: Number(e.target.value) } : l,
            ),
          )
        }
      />
    </label>
  </div>
)}
```

- [ ] **Step 5 : lancer le test, vérifier qu'il passe, puis la suite du fichier**

```bash
cd shell && npx vitest run src/map/LayersPanel.test.tsx
```

- [ ] **Step 6 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ajoute un contrôle d'opacité pour une couche raster

GAP-35 : opacity était lu/écrit/appliqué au rendu (raster-opacity,
MapView.tsx) mais aucune UI ne permettait de le changer après la
création (LayerPicker.tsx le fixait à 1). LayersPanel n'avait aucun
bloc d'édition pour une couche raster, contrairement à vector/feature.
EOF
)"
```

---

## Task 4 (GAP-52/basemap) : sélection de fond de carte dans le widget

Risque : bas — réutilisation directe de `BasemapSelect`
(`shell/src/map/BasemapSelect.tsx`), déjà utilisé par `MapEditorPage`, sans
modification du composant lui-même.

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (`PropsPanel` : ajoute
  `BasemapSelect` ; `Component` : lit `props.basemapStyle` au lieu de
  `DEFAULT_STYLE` figé)
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `BasemapSelect({ value, onChange })`, `BASEMAPS` (liste des
  fonds disponibles, `shell/src/map/basemaps.ts`).
- Produces: nouveau champ de props `basemapStyle?: string` sur l'instance
  du widget `map` — persisté comme toute autre prop de widget (document
  déclaratif, règle n°2 CLAUDE.md), lu par `AppRenderer` sans changement.

- [ ] **Step 1 : écrire le test avant le câblage**

```ts
// shell/src/builder/widgets/mapWidget.test.tsx
test("PropsPanel expose un sélecteur de fond de carte (GAP-52/basemap)", () => {
  const onChange = vi.fn();
  render(renderPropsPanel({ props: { dataSourceId: "" }, onChange }));
  const select = screen.getByRole("combobox", { name: "Fond de carte" });
  fireEvent.change(select, { target: { value: "https://demotiles.maplibre.org/style.json" } });
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ basemapStyle: "https://demotiles.maplibre.org/style.json" }),
  );
});

test("Component utilise props.basemapStyle s'il est défini (GAP-52/basemap)", () => {
  render(renderComponent({ props: { dataSourceId: "ds1", basemapStyle: "https://custom/style.json" } }));
  // lastConfig est capturé par le mock MapView (mapWidget.test.tsx:17) :
  expect(lastConfig?.basemap.style).toBe("https://custom/style.json");
});
```

Lire `renderPropsPanel`/`renderComponent` (helpers existants du fichier,
~lignes 120-150) avant d'écrire ces deux tests — ne pas deviner leur
signature exacte.

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "GAP-52/basemap"
```

- [ ] **Step 3 : ajouter `BasemapSelect` au `PropsPanel`**

```tsx
// mapWidget.tsx — import
import { BasemapSelect } from "../../map/BasemapSelect";

// PropsPanel, avant MapSymbologyEditor
<BasemapSelect
  value={String(props.basemapStyle ?? DEFAULT_STYLE)}
  onChange={(style) => onChange({ ...props, basemapStyle: style })}
/>
```

- [ ] **Step 4 : lire `props.basemapStyle` dans `Component`**

```tsx
// mapWidget.tsx — Component, construction de `config`
const config: MapConfig = {
  basemap: { style: String(props.basemapStyle ?? DEFAULT_STYLE) },
  ...
};
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent, puis la suite du fichier**

```bash
cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx
```

- [ ] **Step 6 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte de l'App Builder expose le choix du fond de carte

GAP-52 (1/4) : DEFAULT_STYLE était figé en dur, aucune UI ne permettait
à un auteur d'App de choisir un autre fond — contrairement à l'éditeur
de carte autonome (BasemapSelect). Réutilise le même composant partagé.
EOF
)"
```

---

## Task 5 (GAP-52/terrain) : terrain 3D configurable dans le widget

Risque : bas à moyen — réutilisation de `TerrainPanel`
(`shell/src/map/TerrainPanel.tsx`), qui dépend de `useInstanceInfo()` (déjà
appelable depuis n'importe quel composant sous le `QueryClientProvider` de
l'App Builder — même précédent que `MapSymbologyEditor`/`PopupEditor`,
composants partagés montés dans ce même `PropsPanel`).

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (`PropsPanel` : ajoute
  `TerrainPanel` ; `Component` : lit `props.terrain`)
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `TerrainPanel({ value: MapTerrainConfig | null, onChange })`.
- Produces: nouveau champ de props `terrain?: MapTerrainConfig | null`.

- [ ] **Step 1 : vérifier que `TerrainPanel` fonctionne isolément dans un test avec un `ItemClient` partiel**

```bash
grep -n "listHostedTerrain3DSources" shell/src/map/TerrainPanel.tsx shell/src/builder/widgets/mapWidget.test.tsx
```

`TerrainPanel` appelle `client.listHostedTerrain3DSources()` — vérifier
qu'il gère déjà un `client` partiel sans planter (même patron que
`listMapIcons?.()` documenté ligne 229-236 de `mapWidget.tsx` — si
`TerrainPanel` n'a pas ce garde, l'ajouter dans **ce fichier `TerrainPanel.tsx`
directement** avant de continuer, c'est un prérequis, pas une régression à
tolérer silencieusement dans les tests de ce widget).

- [ ] **Step 2 : écrire les tests avant le câblage**

```ts
test("PropsPanel expose le panneau de terrain (GAP-52/terrain)", () => {
  const onChange = vi.fn();
  render(renderPropsPanel({ props: { dataSourceId: "" }, onChange }));
  expect(screen.getByText("Terrain")).toBeInTheDocument(); // ou le libellé exact de TerrainPanel
});

test("Component transmet props.terrain à MapView (GAP-52/terrain)", () => {
  const terrain = { tilesUrl: "https://t/{z}/{x}/{y}.png", encoding: "terrarium" as const };
  render(renderComponent({ props: { dataSourceId: "ds1", terrain } }));
  expect(lastConfig?.terrain).toEqual(terrain);
});
```

- [ ] **Step 3 : lancer les tests, vérifier qu'ils échouent**

- [ ] **Step 4 : ajouter `TerrainPanel` au `PropsPanel`, lire `props.terrain` dans `Component`**

```tsx
// mapWidget.tsx — import
import { TerrainPanel } from "../../map/TerrainPanel";

// PropsPanel
<TerrainPanel
  value={(props.terrain as MapTerrainConfig | null) ?? null}
  onChange={(terrain) => onChange({ ...props, terrain })}
/>

// Component — construction de `config`
const config: MapConfig = {
  basemap: { style: String(props.basemapStyle ?? DEFAULT_STYLE) },
  terrain: (props.terrain as MapTerrainConfig | null) ?? null,
  ...
};
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent, puis la suite du fichier**

```bash
cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx
```

- [ ] **Step 6 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte de l'App Builder configure un terrain 3D

GAP-52 (2/4) : MapConfig.terrain n'était jamais posé par le widget,
bien que MapView le supporte pleinement. Réutilise TerrainPanel, déjà
partagé avec l'éditeur de carte autonome.
EOF
)"
```

---

## Task 6 (GAP-52/caméra) : contrôle pitch/bearing dans le widget

Risque : bas — réutilisation de `CameraControls`
(`shell/src/map/CameraControls.tsx`), aucune modification du composant.

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (`PropsPanel` : ajoute
  `CameraControls` ; `Component` : lit `props.cameraPitch`/
  `props.cameraBearing`)
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `CameraControls({ pitch, bearing, onChange })`.
- Produces: nouveaux champs de props `cameraPitch?: number`,
  `cameraBearing?: number`.

- [ ] **Step 1 : écrire les tests avant le câblage**

```ts
test("PropsPanel expose les contrôles de caméra (GAP-52/camera)", () => {
  const onChange = vi.fn();
  render(renderPropsPanel({ props: { dataSourceId: "" }, onChange }));
  const pitchSlider = screen.getByRole("slider", { name: "Inclinaison de la caméra" });
  fireEvent.change(pitchSlider, { target: { value: "30" } });
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ cameraPitch: 30 }));
});

test("Component transmet la caméra à la vue (GAP-52/camera)", () => {
  render(renderComponent({ props: { dataSourceId: "ds1", cameraPitch: 45, cameraBearing: 90 } }));
  expect(lastConfig?.view.pitch).toBe(45);
  expect(lastConfig?.view.bearing).toBe(90);
});
```

Vérifier le libellé ARIA exact de `CameraControls` (`aria-label="Inclinaison
de la caméra"` pour le pitch, symétrique pour le bearing) avant d'écrire —
lu dans `shell/src/map/CameraControls.tsx`, ne pas deviner.

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

- [ ] **Step 3 : ajouter `CameraControls` au `PropsPanel`, lire les deux props dans `Component`**

```tsx
// mapWidget.tsx — import
import { CameraControls } from "../../map/CameraControls";

// PropsPanel
<CameraControls
  pitch={Number(props.cameraPitch ?? 0)}
  bearing={Number(props.cameraBearing ?? 0)}
  onChange={({ pitch, bearing }) =>
    onChange({ ...props, cameraPitch: pitch, cameraBearing: bearing })
  }
/>

// Component — construction de `config`
const config: MapConfig = {
  basemap: { style: String(props.basemapStyle ?? DEFAULT_STYLE) },
  view: {
    center: [2.4, 46.6],
    zoom: 5,
    pitch: Number(props.cameraPitch ?? 0),
    bearing: Number(props.cameraBearing ?? 0),
  },
  terrain: (props.terrain as MapTerrainConfig | null) ?? null,
  ...
};
```

- [ ] **Step 4 : lancer les tests, vérifier qu'ils passent, puis la suite du fichier**

```bash
cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx
```

- [ ] **Step 5 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 6 : commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte de l'App Builder configure la caméra 3D

GAP-52 (3/4) : pitch/bearing n'étaient jamais réglables par l'auteur,
la vue restait toujours à plat (center/zoom fixes). Réutilise
CameraControls, déjà partagé avec l'éditeur de carte autonome.
EOF
)"
```

---

## Task 7 (GAP-45) : éditeur de peinture MapLibre brute (mode avancé)

Risque : moyen — surface d'auteur nouvelle (pas de composant partagé
préexistant à réutiliser). À valider strictement : une entrée malformée ne
doit jamais faire planter le rendu de la carte (`layer.paint` invalide
serait transmis tel quel à MapLibre).

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx` (bloc « Avancé » repliable, sous
  `LayerSymbologyEditor`, pour `vector`/`feature`)
- Test: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `MapLayer.paint?: Record<string, unknown>` (déjà dans le type,
  cas `vector` et `feature`).
- Produces: rien de nouveau côté `ItemClient` — `onChange` sur
  `MapLayer[]`, même patron que les tâches précédentes.

- [ ] **Step 1 : écrire le test avant l'éditeur**

```ts
test("un éditeur JSON avancé permet d'écrire layer.paint (GAP-45)", () => {
  const layers: MapLayer[] = [
    { id: "v1", title: "V", visible: true, kind: "vector", tilesUrl: "https://t", sourceLayer: "s" },
  ];
  const onChange = vi.fn();
  render(<LayersPanel layers={layers} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: /avancé/i, expanded: false }));
  const textarea = screen.getByRole("textbox", { name: /peinture maplibre/i });
  fireEvent.change(textarea, { target: { value: '{"fill-color":"#f00"}' } });
  fireEvent.blur(textarea);
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "v1", paint: { "fill-color": "#f00" } }),
  ]);
});

test("un JSON invalide affiche une erreur sans appeler onChange (GAP-45)", () => {
  const layers: MapLayer[] = [
    { id: "v1", title: "V", visible: true, kind: "vector", tilesUrl: "https://t", sourceLayer: "s" },
  ];
  const onChange = vi.fn();
  render(<LayersPanel layers={layers} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: /avancé/i, expanded: false }));
  const textarea = screen.getByRole("textbox", { name: /peinture maplibre/i });
  fireEvent.change(textarea, { target: { value: "{not json" } });
  fireEvent.blur(textarea);
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

- [ ] **Step 3 : ajouter le bloc « Avancé » repliable dans `LayersPanel.tsx`**

Poser `aria-expanded`/`aria-controls` sur le déclencheur (convention
CLAUDE.md du 2026-09-01, même si son application mécanique n'est pas
encore câblée dépôt-large — cf. `REV-088` — ne pas ajouter un 8e site non
conforme à une convention déjà tranchée). Composant local à
`LayersPanel.tsx`, état `useState<string | null>` pour le brouillon texte
(distinct de `layer.paint` tant que le JSON n'est pas valide, pour ne
jamais perdre la frappe de l'auteur sur une faute de frappe temporaire) :

```tsx
function LayerPaintAdvancedEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(layer.paint ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);
  function commit() {
    try {
      const parsed = JSON.parse(draft) as Record<string, unknown>;
      setError(null);
      onChangeLayer({ ...layer, paint: parsed });
    } catch {
      setError("JSON invalide — la peinture n'a pas été enregistrée.");
    }
  }
  return (
    <div className="basis-full pl-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        className="text-xs underline"
        onClick={() => setOpen((o) => !o)}
      >
        Avancé : peinture MapLibre
      </button>
      {open && (
        <div id={panelId}>
          <textarea
            aria-label="Peinture MapLibre (JSON)"
            className="mt-1 h-24 w-full rounded-md border border-rule bg-surface p-2 font-mono text-xs"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
          />
          {error && <p role="alert" className="text-xs text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
```

Monter `<LayerPaintAdvancedEditor layer={layer} onChangeLayer={...} />`
juste après `<LayerSymbologyEditor ... />` dans le bloc conditionnel
`vector`/`feature` existant.

- [ ] **Step 4 : lancer les tests, vérifier qu'ils passent, puis la suite du fichier**

```bash
cd shell && npx vitest run src/map/LayersPanel.test.tsx
```

- [ ] **Step 5 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 6 : commit**

```bash
git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): éditeur avancé de peinture MapLibre brute (couches vector/feature)

GAP-45 : layer.paint faisait un round-trip API complet et servait de
repli au rendu quand symbology est absent, mais aucune UI ne l'écrivait
jamais — seul un document édité hors produit (MCP/API) pouvait
l'utiliser. Ajoute un panneau replié par défaut, JSON validé avant
tout onChange (une entrée invalide affiche une erreur sans jamais
committer une peinture cassée).
EOF
)"
```

---

## Task 8 (GAP-52/Jenks) : classification Jenks pour le widget carte

Risque : moyen à élevé — seule tâche de ce plan qui étend `ItemClient`
(additif). Filet préalable : le test qui affirme aujourd'hui l'absence de
l'option Jenks (`mapWidget.test.tsx:218-235`) doit être **remplacé**, pas
laissé en contradiction avec le nouveau comportement — vérifier qu'aucun
autre test ne dépend de son assertion actuelle avant de le modifier.

**Files:**
- Modify: `shell/src/api/types.ts` (ajoute `sampleDataSourceField` à
  l'interface `ItemClient`)
- Modify: `shell/src/api/domains/datasets.ts` (implémentation, symétrique
  de `queryDataSource` déjà présente dans ce fichier)
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (`jenksAvailable={true}`,
  `sampleField` réel)
- Test: `shell/src/api/itemClient.test.ts` (nouvelle méthode),
  `shell/src/builder/widgets/mapWidget.test.tsx` (remplace le test
  d'absence par un test de présence + un test de résolution asynchrone)

**Interfaces:**
- Consumes: `ItemClientBase.resolveDataset(pk): Promise<ResolvedDataset>`
  (`shell/src/api/base.ts:121,191`), déjà utilisé par
  `datasets.ts::queryDataSource`.
- Produces: `ItemClient.sampleDataSourceField(source: { layer: string;
  datasetId?: string }, field: string, limit: number): Promise<number[]>`
  — nouvelle méthode additive, ne change la signature d'aucune méthode
  existante.

**⚠️ Note de conception, à confirmer avant le Step 3** (ne pas supposer) :
vérifier que `sampleCollectionField` (déjà dans `domains/layers.ts`) et la
nouvelle `sampleDataSourceField` (dans `domains/datasets.ts`) n'entrent pas
en conflit de nommage ou de responsabilité — la première reste utilisée
telle quelle par `LayersPanel.tsx` (qui a toujours un `collectionId`
synchrone), la seconde est réservée aux hôtes qui n'ont qu'un `DataSource`
(le widget carte).

- [ ] **Step 1 : écrire le test de la nouvelle méthode `ItemClient` (avant de l'implémenter)**

```ts
// shell/src/api/itemClient.test.ts
test("sampleDataSourceField résout collectionId via resolveDataset puis échantillonne", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "communes", columns: {} } },
      }),
    ),
    http.post("https://core.test/collections/communes/aggregate", () =>
      HttpResponse.json({ categoryKey: "value", rows: [{ value: 1 }, { value: 2 }] }),
    ),
  );
  const values = await makeClient().sampleDataSourceField({ layer: "", datasetId: "ds1" }, "pop", 50);
  expect(values).toEqual([1, 2]);
});

test("sampleDataSourceField utilise directement layer quand datasetId est absent", async () => {
  server.use(
    http.post("https://core.test/collections/communes/aggregate", () =>
      HttpResponse.json({ categoryKey: "value", rows: [{ value: 3 }] }),
    ),
  );
  const values = await makeClient().sampleDataSourceField({ layer: "communes" }, "pop", 50);
  expect(values).toEqual([3]);
});
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent (méthode inexistante)**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "sampleDataSourceField"
```

- [ ] **Step 3 : ajouter la méthode à l'interface, puis l'implémentation**

```ts
// shell/src/api/types.ts — interface ItemClient, à côté de sampleCollectionField
sampleDataSourceField(
  source: { layer: string; datasetId?: string },
  field: string,
  limit: number,
): Promise<number[]>;
```

```ts
// shell/src/api/domains/datasets.ts — ajouter à DatasetsMethods et à l'objet retourné
async sampleDataSourceField(
  source: { layer: string; datasetId?: string },
  field: string,
  limit: number,
): Promise<number[]> {
  const resolved = source.datasetId ? await resolveDataset(source.datasetId) : null;
  const collectionId = resolved?.collectionId ?? source.layer;
  const data = await request<{ categoryKey: string | string[]; rows: { value: number }[] }>(
    "POST",
    `/collections/${collectionId}/aggregate`,
    { field, sample: limit },
  );
  return data.rows.map((r) => Number(r.value));
},
```

Ajouter `"sampleDataSourceField"` à `DatasetsMethods` (le `Pick<ItemClient,
...>` en tête du fichier) et `resolveDataset` à la destructure de `base` si
elle n'y est pas déjà (elle l'est : `datasets.ts` importe déjà
`resolveDataset` pour `getDatasetConfig`/`queryDataSource`).

- [ ] **Step 4 : lancer les tests de la nouvelle méthode, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "sampleDataSourceField"
```

- [ ] **Step 5 : remplacer le test d'absence de Jenks par un test de présence, câbler le widget**

```ts
// mapWidget.test.tsx — SUPPRIMER le test "Jenks option is absent..." (ligne
// ~218-235), le remplacer par :
test("Jenks est proposé et fonctionne via sampleDataSourceField (GAP-52/jenks)", async () => {
  const client = { ...baseClient, sampleDataSourceField: vi.fn().mockResolvedValue([1, 2, 3, 4]) };
  render(renderPropsPanel({ client, props: { dataSourceId: "ds1" }, dataSources: [{ id: "ds1", type: "features", service: "core", layer: "communes", query: {} }] }));
  const select = screen.getByRole("combobox", { name: /classification/i });
  fireEvent.change(select, { target: { value: "jenks" } });
  expect(Array.from(select.options).some((o) => o.value === "jenks")).toBe(true);
  // déclencher "Recalculer" si applicable, vérifier que sampleDataSourceField est appelée
  // avec { layer: dataSource.layer, datasetId } — adapter au flux réel de
  // MapSymbologyEditor (bouton "Recalculer" du domaine couleur/taille).
});
```

Adapter précisément au flux existant de `MapSymbologyEditor` (bouton
« Recalculer » du domaine couleur, cf. `busy === "color"` dans ce
composant) — lire ce composant avant d'écrire l'assertion finale, ne pas
deviner l'intitulé exact du bouton.

```tsx
// mapWidget.tsx — PropsPanel
jenksAvailable={true}
sampleField={(field, limit) =>
  client.sampleDataSourceField(
    { layer: dataSource?.layer ?? "", datasetId },
    field,
    limit,
  )
}
```

Retirer le commentaire ligne 219-222 devenu faux (« ce host n'en a pas »)
et le remplacer par une note expliquant la résolution asynchrone
désormais réelle.

- [ ] **Step 6 : lancer la suite du fichier, vérifier zéro régression**

```bash
cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx
```

- [ ] **Step 7 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 8 : commit**

```bash
git add shell/src/api/types.ts shell/src/api/domains/datasets.ts \
  shell/src/api/itemClient.test.ts shell/src/builder/widgets/mapWidget.tsx \
  shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): la classification Jenks fonctionne dans le widget carte de l'App Builder

GAP-52 (4/4) : jenksAvailable était figé à false, sampleField levait
systématiquement (pas de collectionId résolu de façon synchrone au
PropsPanel). Ajoute ItemClient.sampleDataSourceField(), symétrique de
queryDataSource(), qui résout collectionId via resolveDataset() quand
la source passe par un datasetId, ou l'utilise directement sinon —
même patron déjà éprouvé par runStatistics sur ce même widget.
EOF
)"
```

---

## Task 9 (GAP-36) : UI d'auteur pour une couche `'deck'`

Risque : le plus élevé de ce plan — surface neuve la plus large (nouveau
chemin de création + édition inline par type). Round-trip API déjà complet
(`RawMapLayer.deckType/dataUrl/props`, `toFrontLayer()` cas `"deck"`,
`base.ts:60-67`) — uniquement de l'UI à ajouter.

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx` (nouveau formulaire d'ajout
  « Visualisation agrégée (deck.gl) »)
- Modify: `shell/src/map/LayersPanel.tsx` (nouveau bloc d'édition inline
  pour `layer.kind === "deck"`)
- Test: `shell/src/map/LayerPicker.test.tsx`, `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `MapLayer` cas `deck` (`deckType: "heatmap" | "hexbin" |
  "column"`, `dataUrl: string`, `props?: Record<string, unknown>`,
  `shell/src/api/types.ts:225-233`).
- Produces: rien de nouveau côté `ItemClient` — patron `onAdd`/`onChange`
  déjà établi par les tâches précédentes.

- [ ] **Step 1 : écrire le test d'ajout avant le formulaire**

```ts
// shell/src/map/LayerPicker.test.tsx
test("ajoute une couche deck.gl (heatmap) par URL (GAP-36)", () => {
  const onAdd = vi.fn();
  render(<LayerPicker onAdd={onAdd} />);
  fireEvent.change(screen.getByLabelText("Titre de la visualisation"), { target: { value: "Densité" } });
  fireEvent.change(screen.getByLabelText("Type de visualisation"), { target: { value: "heatmap" } });
  fireEvent.change(screen.getByLabelText("URL des données (GeoJSON)"), { target: { value: "https://d/points.geojson" } });
  fireEvent.click(screen.getByRole("button", { name: "Ajouter la visualisation" }));
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({ kind: "deck", deckType: "heatmap", dataUrl: "https://d/points.geojson" }),
  );
});
```

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue**

- [ ] **Step 3 : ajouter le formulaire dans `LayerPicker.tsx`**

Même patron que le bloc « Ajouter une couche par URL GeoJSON » déjà
présent (état local `deckTitle`/`deckType`/`deckUrl`, bouton désactivé tant
que titre/URL sont vides) :

```tsx
const [deckTitle, setDeckTitle] = useState("");
const [deckType, setDeckType] = useState<"heatmap" | "hexbin" | "column">("heatmap");
const [deckUrl, setDeckUrl] = useState("");

function addDeckLayer() {
  if (!deckTitle.trim() || !deckUrl.trim()) return;
  onAdd({
    id: crypto.randomUUID(),
    title: deckTitle,
    visible: true,
    kind: "deck",
    deckType,
    dataUrl: deckUrl,
  });
  setDeckTitle("");
  setDeckUrl("");
}
```

```tsx
<div className="border-t border-rule pt-2">
  <p className="mb-1 text-xs font-medium text-ink-2">Ajouter une visualisation agrégée (deck.gl)</p>
  <div className="flex flex-col gap-1">
    <input aria-label="Titre de la visualisation" ... value={deckTitle} onChange={...} />
    <select aria-label="Type de visualisation" value={deckType} onChange={...}>
      <option value="heatmap">Carte de chaleur (heatmap)</option>
      <option value="hexbin">Hexagones (hexbin)</option>
      <option value="column">Colonnes 3D</option>
    </select>
    <input aria-label="URL des données (GeoJSON)" ... value={deckUrl} onChange={...} />
    <Button type="button" size="sm" disabled={!deckTitle.trim() || !deckUrl.trim()} onClick={addDeckLayer}>
      Ajouter la visualisation
    </Button>
  </div>
</div>
```

- [ ] **Step 4 : lancer le test d'ajout, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/map/LayerPicker.test.tsx
```

- [ ] **Step 5 : écrire le test d'édition inline avant le bloc `LayersPanel`**

```ts
test("une couche deck expose un contrôle de rayon (heatmap/hexbin) (GAP-36)", () => {
  const layers: MapLayer[] = [
    { id: "d1", title: "D", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "https://d" },
  ];
  const onChange = vi.fn();
  render(<LayersPanel layers={layers} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Rayon"), { target: { value: "40" } });
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "d1", props: expect.objectContaining({ radius: 40 }) }),
  ]);
});
```

- [ ] **Step 6 : lancer le test, vérifier qu'il échoue, puis ajouter le bloc dans `LayersPanel.tsx`**

```tsx
{layer.kind === "deck" && (
  <div className="basis-full pl-2">
    {(layer.deckType === "heatmap" || layer.deckType === "hexbin") && (
      <label className="flex flex-col gap-1 text-sm">
        Rayon
        <input
          aria-label="Rayon"
          type="number"
          min={1}
          value={Number((layer.props as { radius?: number } | undefined)?.radius ?? 30)}
          onChange={(e) =>
            onChange(
              layers.map((l) =>
                l.id === layer.id
                  ? { ...l, props: { ...l.props, radius: Number(e.target.value) } }
                  : l,
              ),
            )
          }
        />
      </label>
    )}
    {layer.deckType === "column" && (
      <label className="flex flex-col gap-1 text-sm">
        Échelle de hauteur
        <input
          aria-label="Échelle de hauteur"
          type="number"
          min={0}
          value={Number((layer.props as { elevationScale?: number } | undefined)?.elevationScale ?? 1)}
          onChange={(e) =>
            onChange(
              layers.map((l) =>
                l.id === layer.id
                  ? { ...l, props: { ...l.props, elevationScale: Number(e.target.value) } }
                  : l,
              ),
            )
          }
        />
      </label>
    )}
  </div>
)}
```

Vérifier au préalable, dans `MapView.tsx::buildDeckLayer`, les clés de
`props` réellement consommées par chaque `deckType` (`radius` pour
heatmap/hexbin, `elevationScale` pour column, ou d'autres noms — **ne pas
deviner**, lire le code de rendu avant d'écrire ce bloc).

- [ ] **Step 7 : lancer les tests, vérifier qu'ils passent, puis les deux suites de fichiers**

```bash
cd shell && npx vitest run src/map/LayerPicker.test.tsx src/map/LayersPanel.test.tsx
```

- [ ] **Step 8 : suite complète shell**

```bash
cd shell && npx vitest run
```

- [ ] **Step 9 : commit**

```bash
git add shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx \
  shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): UI d'auteur pour une couche deck.gl agrégée (heatmap/hexbin/column)

GAP-36 : le type de couche 'deck' et son rendu étaient pleinement
implémentés et testés unitairement avec une config écrite à la main,
mais aucune UI ne permettait jamais d'en créer une (LayerPicker) ni de
régler ses paramètres (LayersPanel) — rien dans le produit ne pouvait
en produire une. L'exposition MCP reste hors périmètre (spec §6) :
update_config/save_map_config génériques permettent déjà à une IA
d'écrire cette couche directement.
EOF
)"
```

---

## Vérification finale du plan

- [ ] Suite Vitest complète : `cd shell && npx vitest run`
- [ ] `npm run build` (tsc --noEmit + vite build) pour confirmer qu'aucun
  nouveau champ de props (`basemapStyle`/`terrain`/`cameraPitch`/
  `cameraBearing` sur le widget, `sampleDataSourceField` sur `ItemClient`)
  ne casse la vérification de types.
- [ ] Suite E2E complète (`npm run e2e`) — au moins un scénario touche
  `MapEditorPage`/le widget carte de l'App Builder (piège CLAUDE.md n°6 :
  lancer la suite complète avant de clore, pas un sous-ensemble).
- [ ] Relire la spec §7 (coordination SP-54) avant de fusionner cette
  branche si le plan SP-54 a progressé en parallèle sur `base.ts`/
  `types.ts` — résoudre tout conflit par relecture des deux diffs, jamais
  par un merge automatique aveugle sur ces deux fichiers précis.
