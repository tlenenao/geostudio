# Extraction de `shell/src/builder` et `shell/src/ui/kit` en packages partagés — Design

**Date** : 2026-09-07.
**Statut** : validé pour passage en plan d'implémentation (chantier A du diptyque
app-builder ; chantier B est côté `finance`,
`docs/superpowers/specs/2026-09-07-dashboard-builder-integration-design.md`).
**Déclencheur** : demande utilisateur de partager le no-code app builder de
geostudio (React + `AppConfig` déclaratif) avec le projet `finance`
(`/home/lenen/projets/finance`), comme **source unique**, pas comme fork qui
diverge — brainstorming mené le 2026-09-07, voir historique de session.

**Amende** `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` §9.5
(« SDK : le registre React reste interne ») — amendement inscrit dans ce
document le 2026-09-07, à lire avant ce chantier.

## 0. Ce qui a été vérifié avant d'écrire

- **Aucun `package.json` racine dans geostudio** — pas de workspace npm
  aujourd'hui ; `shell/`, `core/` sont des projets indépendants côte à côte
  sous un même dépôt git. À créer.
- **Volumétrie réelle** (comptée par `find`/`cat | wc -l`, hors fichiers de
  test) :
  - `shell/src/builder/` : 108 fichiers non-test, 14 661 lignes.
  - `shell/src/map/` : 20 fichiers non-test, 5 020 lignes (dont `MapView.tsx`
    seul, 1 422 lignes, deck.gl).
  - `shell/src/ui/kit/` : 39 composants non-test, 1 622 lignes.
  - `shell/src/i18n/catalog.fr.ts` : 1 658 lignes, dont 355 clés
    `builder.*`/`widget.*`/`appRenderer.*`/`map.*`.
- **Couplage externe de `builder/` + `map/`** (grep exhaustif des imports non
  relatifs et des appels `client.*`) :
  - Données : `client.queryDataSource`, `getDatasetConfig`,
    `getCollectionSchema`, `featuresUrl`, `listMapIcons`/`uploadMapIcon`/
    `fetchMapIconBlob`/`deleteMapIcon`, `updateFeature`/`createFeature`/
    `deleteFeature`, `sampleCollectionField`, `exportDataSource`,
    `getCollection`/`getCollectionPermission`, `presignAttachmentUpload`/
    `confirmAttachmentUpload`/`listAttachments`/`downloadAttachment`/
    `deleteAttachment`, `presignTerrain3DUpload`/`createTerrain3DUpload`/
    `getTerrain3DUploadJob`/`listHostedTerrain3DSources`,
    `listPublicItems`. Le reste (`runPipeline`, `getPipelineRuns`,
    `rollbackConfig`, `listConfigRevisions`, `copilotTurn`, `getReportRuns`,
    `getExportJob`/`createExport`, `getAppExportJob`/`createAppExport`) est
    utilisé par les sous-dossiers de `builder/` qui **restent** dans `shell/`
    (pipeline, copilot, print, report, appexport, ConfigHistoryPanel,
    AlertRuleEditor) — voir §1.2.
  - Identité : `auth/useAuth` (nom d'utilisateur, pour les conditions de
    message `user.name`), `auth/permissions`.
  - i18n : `t()` de `i18n/index.ts`, signature `t(key, params?)` avec
    interpolation `{param}` — **pas** `t(key, fallback)`.
  - UI : `ui/kit/Button`, `ui/kit/Panel`, `ui/kit/usePanelTrigger`,
    `ui/kit/Input` (ce dernier via `map/`).
  - Libs tierces : `@tanstack/react-query`, `echarts` (+ `charts`/
    `renderers`/`components`/`core`), `@maplibre/maplibre-gl-style-spec`,
    `maplibre-gl`, `@deck.gl/{core,layers,geo-layers,aggregation-layers,
    mapbox}`, `@loaders.gl/3d-tiles`, `lit` (Web Components), `dompurify`,
    `marked`, `cel-js`, `@xyflow/react` (pipeline/visualQuery, restent dans
    `shell/`), `react-oidc-context`.
- **`AppConfig`** (`shell/src/api/types.ts:967-978`) : `{ kind, theme,
  dataSources, messages, layout, pages?, variables?, navigationMode?,
  interactions?, printLayout? }` — déclaratif, sans logique cachée
  (règle d'architecture n°2 du CLAUDE.md geostudio), donc portable tel quel.
- **`DataSource`** (`types.ts:738-745`) : `{ id, type, service, layer,
  datasetId?, query }` — `service` est une chaîne libre (`"core"` pour
  geostudio) : le champ existe déjà pour distinguer un backend d'un autre.
- **finance a déjà forké une tranche de `ui/kit`** (`frontend/src/ui/kit/`,
  vu depuis le dépôt finance) avec un stub `i18n` documentant explicitement
  qu'il imite la signature réelle de `t()`. Les tokens CSS des deux projets
  utilisent le **même vocabulaire** (`surface`, `ink`/`ink-2`/`ink-3`,
  `rule`, `sunken`, `raised`, `accent`/`accent-ink`/`accent-soft`) — portage
  visuel sans divergence de design system.
- **E2E geostudio** : 166 passed / 4 skipped / 0 failed depuis le
  2026-09-06 (commit `a320c317`, cf. CLAUDE.md) — c'est le filet de
  non-régression de cette extraction.
- **SP-8 (SDK Web Components) est fermé** : SP-8a (contrat WC + pont
  WidgetHost), SP-8c (widget tiers réel, admin, permissions serveur,
  containment) livrés — jalon M5 fermé. C'est la précondition que §9.5 posait
  avant toute ouverture du registre ; elle est remplie, l'amendement de §9.5
  est donc défendable et pas un contournement.

## 1. Périmètre extrait

### 1.1 `packages/ui-kit` (nouveau package, ~1 700 lignes avec tests)

Tout `shell/src/ui/kit/` tel quel, sans modification fonctionnelle — c'est un
déplacement de dossier, pas une réécriture. `shell/` importe désormais
`@geostudio/ui-kit` au lieu de `../../ui/kit/...`.

### 1.2 `packages/app-builder` (nouveau package, ~11 000 lignes avec `map/`)

Depuis `shell/src/builder/`, sous-dossiers déplacés tels quels :

| Package `src/` | Origine | Contenu |
|---|---|---|
| `core/` | `builder/{registry,AppRenderer,GridCanvas,WidgetHost,grid,pages,theme,ActionBus,ActionBusContext,VariablesContext,DataContext,AnalyticsContext,AnalyticsContextIndicator,ExplorerContext,ExplorerDrawer,expr,actionMessages}.ts(x)` | Runtime : rendu, grille, bus d'actions, variables, données, cross-filter |
| `editor/` | `builder/{PropsPanel,WidgetPalette,LayoutEditor,PageManager,ThemePanel,VariablesPanel,DataSourcePanel,DataSourceSelect,DataSourcesEditContext,ActionsPanel,NavigationPanel,CrossFilterLinkEditor,widgetPropSchema,configExpressionErrors,PercentileInput}.ts(x)` | Surface d'édition consommée par le mode `edit` |
| `widgets/` | `builder/widgets/*` | Les 25 types de widgets (`text`, `image`, `button`, `chart`, `table`(`data`), `map`(`mapWidget`), `indicator`, `pivot`, `form`, `gallery`, `hero`, `modal`, `drawer`, `nav`(`navigation`), `tabs`, `filter`, `selectFilter`, `sliderFilter`, `dateRangeFilter`, `datasetCard`, `richSection`, `variableInput`, `ExplorerMenu`) + `iconLibrary`, `palette`, `sanitizeMarkdown`, `chartOption`, `mapSymbology`, `pivotTable` |
| `map/` | `shell/src/map/*` | `MapView` (deck.gl) + `MapSymbologyEditor`, `PopupEditor`, `BasemapSelect`, `TerrainPanel`, `CameraControls`, `MapLegend`, `LayerPicker`, `LayersPanel`, `MapMeasureSketchToolbar`, `FieldClassificationPicker`, `basemaps`, `formFieldStyles`, `geojsonIntrospect` |
| `wc/` | `builder/wc/*` | `registerWcWidget` (branche un manifeste WC dans le `registry` exporté — reste ici, pas dans `shell/`, car c'est un mode d'enregistrement de widget, pas une surface pilotant des objets de plateforme) |
| `types/` | sous-ensemble de `shell/src/api/types.ts` | `AppConfig`, `DataSource`, `DataSourceState`, `DatasetConfig`, `Page`, `WidgetItem`, `AppLayout`, `Variable`/`VariableType`, `ActionMessage`, `Theme`/`ThemeColors`, `RenderMode`, `PrintLayoutConfig` |
| `ports/` | nouveau | `BuilderDataClient`, `IdentityPort`, `I18nPort` (§2) |
| `i18n/` | sous-ensemble de `i18n/catalog.fr.ts` | Les ~355 clés `builder.*`/`widget.*`/`appRenderer.*`/`map.*`, catalogue par défaut du package |

**Reste dans `shell/src/builder/`**, parce que ces surfaces pilotent des
objets de plateforme geostudio sans équivalent générique (items, jobs,
révisions, alertes, MCP) : `pipeline/` (1 832 l.), `visualQuery/` (837 l.),
`copilot/` (413 l.), `print/` (230 l.), `report/` (214 l.), `appexport/`
(171 l.), `examples/` (compteur de démo, 138 l.), `AlertRuleEditor.tsx`,
`ConfigHistoryPanel.tsx`, `aggregates.ts`. Ces fichiers importent
`@geostudio/app-builder` pour `registry`/`AppRenderer`/etc. au lieu de leurs
voisins actuels.

## 2. Les trois ports injectés

Aucun fichier de `packages/app-builder` n'importe plus `../../api/ItemClientProvider`,
`../../auth/useAuth` ni `../../i18n` directement. Un `<AppBuilderProvider>`
les fournit par contexte React.

### 2.1 `BuilderDataClient`

```ts
// packages/app-builder/src/ports/dataClient.ts
export type BuilderDataClient = {
  // Requis — lus par le runtime de tout widget de données.
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  getDatasetConfig(datasetId: string): Promise<DatasetConfig>;
  getCollectionSchema(id: string): Promise<CollectionSchema>; // { pk, geometry, fields }
  featuresUrl(source: DataSource): string | undefined;

  // Requis — lus par l'éditeur (DataSourcePanel liste les datasets,
  // PropsPanel propose les champs).
  listDatasets(): Promise<DatasetSummary[]>;
  sampleFieldValues(collectionId: string, field: string): Promise<unknown[]>;

  // Optionnels — la surface UI correspondante se masque proprement si absent
  // (pas de throw, pas de bouton mort : WidgetPalette/PropsPanel filtrent
  // sur la présence de la capacité).
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
  attachments?: { /* presign/confirm/list/download/delete */ };
  terrain3d?: { /* presign/create/getJob/listHostedSources */ };
  exportDataSource?(source: DataSource): Promise<Blob>;
};
```

`ItemClient` de geostudio implémente déjà toutes les méthodes requises et la
totalité des optionnelles ; l'adaptateur (`shell/src/builder/geostudioDataClient.ts`,
nouveau, ~30 lignes) est une simple délégation 1:1, aucune logique. Une app
hôte comme `finance` implémente les 6 méthodes requises et laisse les
optionnelles `undefined`.

### 2.2 `IdentityPort`

```ts
export type IdentityPort = { username: string | null };
```

Consommé uniquement par `ActionConditionBridge` (conditions `user.name` sur
les `ActionMessage.when`). `shell/` passe `useAuth().username`, `finance`
passe `{ username: null }` (pas d'auth aujourd'hui côté finance).

### 2.3 `I18nPort`

```ts
export type I18nPort = { t(key: string, params?: Record<string, string | number>): string };
```

Le package embarque son propre catalogue (`i18n/catalog.fr.ts` du package,
extrait des 355 clés). Une app hôte peut fournir son propre `I18nPort` pour
surcharger ; sans rien fournir, le catalogue embarqué sert de défaut.
`scripts/check-i18n-coverage.mjs` (geostudio) est étendu pour couvrir
`packages/app-builder/src`.

## 3. Mécanique de consommation

- **Workspace npm racine** (`geostudio/package.json`, nouveau) :
  `{ "workspaces": ["shell", "packages/*"] }`. `shell/package.json` gagne
  `"@geostudio/ui-kit": "workspace:*"` et `"@geostudio/app-builder":
  "workspace:*"`.
- **Pas d'étape de build séparée pour les packages** : `packages/*/src` est
  du TypeScript source, compilé directement par le `vite build`/`vitest` de
  chaque consommateur (comme c'est déjà le cas en interne à `shell/`).
  `packages/*/package.json` a un champ `"main"`/`"types"` pointant sur
  `src/index.ts`, pas sur un `dist/`.
- **Dépendances lourdes en `peerDependencies`** des deux packages (react 19,
  react-dom 19, `@tanstack/react-query` 5, echarts 6, maplibre-gl 4,
  lucide-react, les `@radix-ui/*` utilisés par `ui/kit`, les `@deck.gl/*` et
  `@loaders.gl/3d-tiles` pour `map/`) — chaque consommateur les déclare dans
  son propre `package.json`.
- **`MapView` reste `lazy()`-chargé** dans `mapWidget.tsx` (déjà le cas) :
  deck.gl part dans un chunk séparé, aucun coût au démarrage pour une app
  hôte qui n'affiche jamais le widget `map`.
- **Consommation par `finance`** (dépôt tiers, pas de workspace commun) :
  `"@geostudio/app-builder": "file:../../geostudio/packages/app-builder"` +
  `"@geostudio/ui-kit": "file:../../geostudio/packages/ui-kit"` dans
  `finance/frontend/package.json`, plus l'alias correspondant dans
  `vite.config.ts` si nécessaire. Détail côté finance :
  `docs/superpowers/specs/2026-09-07-dashboard-builder-integration-design.md`.

## 4. Ordre des tâches (aperçu, détaillé dans le plan)

1. Définir et publier les types des 3 ports (`ports/`) + adaptateur
   `geostudioDataClient.ts` qui fait de `ItemClient` un `BuilderDataClient` —
   **valider par un test qu'aucune méthode requise ne manque** avant de
   toucher au reste.
2. Vérifier la faisabilité de la consommation en TS source sans build
   séparé : `packages/ui-kit` minimal (un composant), workspace configuré,
   `shell/` l'importe, `npm run build` passe. Point d'arrêt go/no-go avant
   d'aller plus loin.
3. Déplacer `ui/kit` intégralement vers `packages/ui-kit` ; `shell/` bascule
   ses imports ; E2E + unit rejoués.
4. Déplacer `types/`, `core/`, `editor/`, `widgets/`, `map/`, `wc/` vers
   `packages/app-builder`, un sous-dossier à la fois, avec bascule des
   imports dans les fichiers de `shell/src/builder/` qui restent sur place.
5. Extraire le sous-catalogue i18n du package ; brancher `I18nPort`.
6. E2E complète rejouée (doit rester verte, 166/166) ; revue finale de
   branche (subagent-driven-development, comme le reste de geostudio).

## 5. Risques

- **TS source sans build** (§3) est vérifié en tâche 2, avant d'investir
  dans le déplacement des ~13 000 lignes restantes — c'est le risque
  principal du chantier, traité en premier délibérément.
- **`map/` est gros (5 020 l., deck.gl)** pour une app qui ne l'utilisera
  peut-être jamais réellement (finance a son propre widget carte maison,
  maplibre nu sans deck.gl) — accepté : `lazy()` neutralise le coût, et le
  périmètre « cœur + widgets + carte + cross-filter » a été choisi
  explicitement (pas de découpage `map/` à part en v1).
- **Dérive de scope** : ce chantier ne touche ni `pipeline/`, ni
  `visualQuery/`, ni `copilot/`, ni les objets de plateforme geostudio
  (items, jobs) — un besoin qui y toucherait est hors périmètre de cette
  spec.
