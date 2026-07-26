# SP-14d — Menu « explorer » & panneau « voir les entités » (design)

> **Date : 2026-07-26 · Statut : validé (brainstorm)**
> Quatrième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter** et **SP-14c — Filtres typés & indicateur**. Traite
> le renvoi explicite de 14b (« panneau "voir les entités" → SP-14d (widgets
> analytiques), avec le menu "explorer" ») et le critère d'acceptation SP-14
> « "voir les entités" ouvre les lignes sous-jacentes (table + carte) ». Le
> reste de la liste « Widgets analytiques » de la feuille de route (KPI
> riche, pivot, sankey/treemap/sunburst/funnel, séries temporelles
> comparées, carte analytique par `encodings`, conteneurs onglets/modale/
> tiroir) reste hors périmètre — sous-parties SP-14 ultérieures (14e, 14f…).

## 1. Objectif & non-buts

**Objectif.** Sur les widgets qui affichent des données liées à un dataset
partagé — Graphique, Table, Liste, Carte, Indicateur — un menu « explorer »
(bouton `⋮`) ouvre un panneau de drill qui montre les entités **brutes**
actuellement filtrées par le contexte analytique global (période × emprise ×
cross-filter), sous forme table + carte. Concrètement : un utilisateur qui a
cliqué une barre de chart ou posé une période veut voir *quelles lignes*
sont derrière l'agrégat affiché, sans écrire de SQL.

**Découverte clé (exploration du code) : ce plan ne touche pas `core`.**
L'endpoint OGC Features accepte déjà `limit`/`offset`
(`core/app/features/routes.py:127`, défaut `limit=100`), et les opérateurs
`__gte`/`__lte`/`__in` consommés par `derivePatch` existent depuis SP-14b
(`core/app/features/repository.py`). Le panneau interroge les entités via le
même chemin que n'importe quel widget `features` (`itemClient.
queryDataSource`, `shell/src/api/itemClient.ts:619`) — aucune route ni
paramètre serveur nouveau.

**Non-buts explicites** (reportés) :

- Export CSV/PNG depuis le menu explorer — listé sous SP-16/A30, pas ici. Le
  menu n'a qu'un seul item dans ce plan : « Voir les entités ».
- Les widgets filtres (`selectFilter`, `sliderFilter`, `dateRangeFilter`)
  n'ont pas le menu, bien qu'ils soient techniquement liés à un
  `dataSourceId` porteur d'un `datasetId` — ce sont des contrôles d'entrée,
  pas des widgets d'affichage. Éligibilité **par type de widget** (liste
  fermée posée dans chacun des 5 widgets), pas une règle structurelle dans
  `WidgetHost`.
- Le clic sur une ligne du panneau ne modifie **jamais**
  `AnalyticsContextState` (pas de nouveau cross-filter, pas de `flyTo` sur
  les autres widgets de l'app) — surbrillance locale au panneau uniquement.
  Le drill est une exploration en lecture seule, isolée du reste du
  tableau de bord.
- Pas de pagination serveur par curseur : un plafond client fixe (200
  entités, `limit: 200` sur la requête) avec message d'incitation à affiner
  le contexte si atteint. Pas de nouvelle route ni de nouveau paramètre
  côté core.
- Pas de nouvelle route applicative : le panneau est un tiroir superposé à
  l'app courante, jamais une navigation vers une nouvelle URL.
- Reste de la liste « Widgets analytiques » de la feuille de route (§ en-tête
  ci-dessus) — sous-parties suivantes de SP-14, non traitées ici.

Le modèle reste additif : le menu et le panneau n'apparaissent que quand
`mode !== "edit"` **et** `config.interactions === "auto"` (même garde que
l'indicateur de contexte de 14c) ; une app `interactions: "manual"` ou en
mode édition n'affiche jamais le bouton `⋮` — comportement inchangé, aucune
des 18+ specs E2E existantes n'est affectée.

## 2. `ExplorerContext` — état du panneau et gating

Nouveau `shell/src/builder/ExplorerContext.tsx`, calqué sur
`AnalyticsContext.tsx` (état + setters dans deux contextes séparés) :

```ts
export type ExplorerTarget = { datasetId: string; dataSourceId: string } | null;

// état : la cible actuellement explorée (null = panneau fermé)
function useExplorerTarget(): ExplorerTarget
// setters
function useOpenExplorer(): (target: { datasetId: string; dataSourceId: string }) => void
function useCloseExplorer(): () => void
// gating, calculé une fois par ExplorerProvider à partir de mode/interactions
function useExplorerEnabled(): boolean
```

`ExplorerProvider` prend `enabled: boolean` en prop (calculé par
`AppRenderer` : `mode !== "edit" && config.interactions === "auto"`,
identique à la garde de `AnalyticsContextIndicator`). `openExplorer` est un
no-op silencieux si `!enabled` — même pattern de garde que tous les setters
`AnalyticsContext` depuis 14b/14c.

Câblage dans `AppRenderer.tsx` : `ExplorerProvider` englobe
`AnalyticsContextProvider` (ou l'inverse, l'ordre n'importe pas — aucune
dépendance croisée dans les données, seulement dans le rendu) et
`ExplorerDrawer` est monté une fois, au même niveau que
`AnalyticsContextIndicator`.

## 3. Le menu — `ExplorerMenu.tsx`

Nouveau `shell/src/builder/widgets/ExplorerMenu.tsx`, composant partagé
posé dans les 5 widgets éligibles :

```tsx
<ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
```

Rendu : rien si `!useExplorerEnabled() || !datasetId` ; sinon un bouton `⋮`
discret en coin du widget (`aria-label="Explorer"`), qui ouvre un petit menu
avec un seul item aujourd'hui — « Voir les entités » (`aria-label="Voir les
entités"`), qui appelle `useOpenExplorer()({ datasetId, dataSourceId })`.

Posé dans `chart.tsx`, `data.tsx` (widgets `table` et `list`),
`mapWidget.tsx`, `indicator.tsx` — 2-3 lignes par fichier (import + une
ligne de JSX), aucun changement à `WidgetHost.tsx` puisque l'éligibilité est
décidée dans chaque widget, pas centralisée.

## 4. Le panneau — `ExplorerDrawer.tsx`

Nouveau `shell/src/builder/ExplorerDrawer.tsx`, monté une fois dans
`AppRenderer`. Ne rend rien si `useExplorerTarget()` est `null`. Tiroir
latéral plein-hauteur (`position: fixed`, glisse depuis la droite,
`z-index` au-dessus du contenu de l'app), fermeture par croix
(`aria-label="Fermer le panneau"`) ou touche Échap.

**Requête.** Résout `DatasetConfig` via `useQuery(["dataset", datasetId],
() => client.getDatasetConfig(datasetId))` — même `queryKey` que
`DataContext.tsx:27`, donc dédupliqué par React Query si le dataset est déjà
chargé par ailleurs dans l'app. Construit une `DataSource` synthétique :

```ts
const source: DataSource = { id: "__explorer__", type: "features", service: "", layer: "", datasetId, query: { limit: 200 } };
const patch = derivePatch(source, analyticsCtx, { [datasetId]: dataset });
const merged = { ...source, query: { ...source.query, ...patch } };
```

Parce que `"__explorer__"` ne correspond jamais à un `originSourceId` réel,
le cross-filter du dataset s'applique **toujours** dans le panneau — y
compris quand celui-ci est ouvert depuis le widget qui a lui-même posé ce
cross-filter (contrairement au widget d'origine, qui s'exclut lui-même via
`derivePatch`, `shell/src/lib/analyticsPatch.ts:31`). C'est le comportement
voulu : « voir les entités » montre toujours l'état filtré complet, jamais
la vue non filtrée du widget d'origine.

`useQuery(["datasource-explorer", datasetId, merged.query], () =>
client.queryDataSource(merged))` récupère les lignes (avec géométrie,
`queryDataSource` type `"features"`, `itemClient.ts:619`).

**Rendu.**
- En-tête : libellé du dataset (résolu depuis `DatasetConfig`, ou
  `datasetId` à défaut) + bouton fermer.
- Carte compacte en haut du tiroir : `MapView` (lazy, même composant que
  `mapWidget.tsx:10`), alimentée par `client.featuresUrl(merged)` — même
  mécanisme que le widget Carte, pas de nouvelle construction d'URL.
- Table en dessous : une colonne par propriété des enregistrements reçus,
  libellé = `dataset.columns[key]?.label ?? key` (première consommation du
  libellé métier `DatasetColumnMeta.label`, jusqu'ici jamais affiché par
  aucun widget — cf. 14c §1, qui l'avait explicitement écarté pour
  l'indicateur). Pagination client, `pageSize` fixe à 20, même logique que
  le widget `table` (`data.tsx:172-181`).
- Clic sur une ligne : met en surbrillance la géométrie correspondante sur
  la carte du tiroir via `handle.current?.highlight(record.geometry)`
  (même méthode impérative que `MapViewHandle` expose déjà, cf.
  `mapWidget.tsx:45-47`) — état **local au tiroir**, n'écrit jamais dans
  `AnalyticsContext` (§1).
- Si `records.length >= 200` : bandeau « Affinez le contexte (période,
  emprise, filtre) pour voir l'ensemble des entités — 200 premières
  affichées. »
- États `loading`/`error` : mêmes libellés que les widgets existants
  (`Chargement…`, `Erreur de données`).

## 5. Tests & risques

**Core.** Aucun (§1).

**Shell (unitaires).**
- `ExplorerContext.test.tsx` : `openExplorer`/`closeExplorer` no-op si
  `!enabled` ; état correctement remplacé par une nouvelle cible sans
  fermeture intermédiaire (ouvrir depuis un widget pendant que le panneau
  est déjà ouvert pour un autre dataset change juste la cible).
- `ExplorerMenu.test.tsx` : bouton absent si `!enabled` ou `!datasetId` ;
  clic sur l'item appelle `openExplorer` avec les bons `datasetId`/
  `dataSourceId`.
- `ExplorerDrawer.test.tsx` : rendu vide si cible `null` ; requête construite
  avec `derivePatch` appliqué (période + emprise + cross-filter, mock
  `queryDataSource`) ; toujours filtré même quand `dataSourceId` cible =
  l'origine du cross-filter (le point clé du §4) ; pagination 20/page ;
  bandeau de plafond si 200 lignes reçues ; clic sur une ligne appelle
  `highlight` sans jamais appeler un setter `AnalyticsContext`.
- Wiring : un test par widget éligible (5) vérifiant que `ExplorerMenu`
  reçoit bien `ctx.data?.datasetId` et `props.dataSourceId`.

**E2E** (étend `analytics-context.spec.ts`, calqué sur les scénarios 14b/
14c) :
1. App `auto`, cliquer une barre de chart (cross-filter posé) → ouvrir
   « Voir les entités » depuis un widget Table du même dataset → tiroir
   affiche les lignes filtrées (table + carte cohérentes avec le
   cross-filter).
2. Ouvrir « Voir les entités » depuis le widget Chart **qui a lui-même émis**
   le cross-filter → le tiroir montre quand même les lignes filtrées (pas
   l'ensemble non filtré que le chart s'affiche à lui-même).
3. Fermer le tiroir (croix et Échap) → app sous-jacente inchangée,
   `AnalyticsContextState` inchangé.
4. **Non-régression explicite** : une app `interactions: "manual"` n'affiche
   jamais le bouton `⋮`, quel que soit le widget.

| Risque | Garde-fou |
|---|---|
| Plafond de 200 lignes masque des entités pertinentes | Message explicite d'incitation à affiner le contexte (§4) ; limitation v1 assumée, améliorable plus tard par une vraie pagination serveur sans changement de modèle (`limit`/`offset` déjà supportés côté core) |
| Widget lié à une source sans `datasetId` (ex. source `static`) | `ExplorerMenu` ne rend rien (`!datasetId`), pas de requête possible |
| Double clic rapide sur deux menus différents | `ExplorerTarget` est un remplacement simple d'état (pas une pile) — la dernière cible ouverte gagne, comportement prévisible |
| Dataset avec beaucoup de colonnes → table illisible | Limitation v1 assumée (aucune sélection de colonnes dans ce plan, contrairement au widget `table` qui a `props.columns`) — améliorable en 14e si besoin remonte |
| Géométrie absente sur certaines entités (dataset non spatial) | Carte du tiroir affiche les entités avec géométrie, table montre tout ; pas de crash si `geometry` est `undefined` (même garde que `mapWidget.tsx` sur `data.error`) |
