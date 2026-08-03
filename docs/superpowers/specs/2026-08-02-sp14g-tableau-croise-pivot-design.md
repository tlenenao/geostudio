# SP-14g — Tableau croisé / pivot (design)

> **Date : 2026-08-02 · Statut : validé (brainstorm)**
> Septième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées** et **SP-14f — Nouveaux types de
> graphiques**. Traite le premier des éléments encore listés « hors
> périmètre » par 14f (« Tableau croisé/pivot, carte analytique, conteneurs
> [...], requête visuelle, SQL Lab, source `arcgis`, MCP analytique — sous-
> parties SP-14 ultérieures (14g…) ») : le **tableau croisé (pivot)**.
> Carte analytique, conteneurs (onglets/modale/tiroir), requête visuelle,
> SQL Lab, source `arcgis`, MCP analytique restent hors périmètre —
> sous-parties SP-14 ultérieures (14h…).

## 1. Objectif & non-buts

**Objectif.** Un nouveau widget `pivot` qui affiche un vrai crosstab 2D
(lignes × colonnes × une ou plusieurs mesures, avec totaux de ligne, de
colonne et grand total) — la question type étant « pour chaque région, la
somme des incidents par trimestre », affichée en grille plutôt qu'en
graphique. Contrairement à 14e/14f (nouveaux modes du widget `chart`
existant), c'est un **nouveau type de widget** : son rendu (une vraie table
HTML à deux axes d'en-têtes) n'a pas d'équivalent dans les modes ECharts
existants et ne s'exprime pas avec le vocabulaire `categoryField`/
`valueField`/`encodings` du widget `chart`.

**Constat clé qui cadre l'approche.** Deux mécanismes de pivot existent déjà
côté core, avec des capacités différentes :
- Le `groupBy` **multi-champ** (`core/app/analytics/aggregate.py:293-299`,
  livré en SP-14f pour sankey/treemap/sunburst) accepte déjà une liste de
  `measures` arbitraire et renvoie des lignes tidy
  `{champ1, champ2, mesure1, mesure2, ...}` — **une ligne par combinaison
  observée**, une colonne par mesure.
- Le `split` **pivot large existant** (`aggregate.py:307-314`, utilisé pour
  les séries de graphique) ne route que par `agg`/`field` — **une seule
  mesure**, jamais la liste `measures`.

Ce widget a besoin de plusieurs mesures simultanément (ex. somme et moyenne
côte à côte) : il consomme donc le `groupBy` multi-champ existant (2 champs :
lignes, colonnes) et **reconstruit la grille côté client** à partir des
lignes tidy déjà renvoyées — **zéro changement core, zéro changement
`DataSourcePanel`**. C'est le même geste que sankey/treemap en 14f : lire des
rôles de champ (`encodings.rows`/`encodings.columns`) sur des lignes tidy
déjà produites par un mécanisme core générique.

**Non-buts explicites** (reportés) :

- Hiérarchie de lignes à plusieurs niveaux (plus d'un champ lignes) — v1
  fermée à exactement 1 champ lignes + 1 champ colonnes. Un `groupBy` à 3
  champs ou plus n'est pas consommé par ce widget.
- Cross-filter sur une cellule de données (poserait un filtre à deux champs
  simultanément, hors du modèle de cross-filter actuel à un seul couple
  `{field, value}` par dataset, `CrossFilterEntry`,
  `AnalyticsContext.tsx:5`) — seuls les en-têtes de ligne et de colonne sont
  cliquables (§4), jamais les cellules de données ni la ligne/colonne
  « Total ».
- Distinction « 0 réel » vs « pas de données » dans une cellule vide — comme
  `_pivot_split` existant (`aggregate.py:170-188`) qui remplit déjà les
  combinaisons absentes à 0, toute combinaison lignes×colonnes absente des
  lignes tidy reçues vaut 0 en cellule, y compris pour `avg`/`min`/`max`
  (simplification assumée, cohérente avec le comportement déjà en
  production ailleurs dans le module).
- Tri/réordonnancement manuel des lignes ou des colonnes, export du pivot en
  CSV — tri alphabétique fixe des valeurs de lignes et de colonnes en v1, pas
  de bouton d'export dédié (le widget `table` a déjà un rôle d'export
  générique si besoin, hors périmètre d'y toucher ici).
- Carte analytique par `encodings`, conteneurs (onglets/modale/tiroir),
  requête visuelle, SQL Lab, source `arcgis`, MCP analytique — reste de la
  liste « widgets analytiques » / périmètre SP-14, sous-parties ultérieures.
- Bookmarks/situations nommées, cross-filter inter-datasets — toujours hors
  périmètre (inchangé depuis 14b).

Le modèle reste additif : un nouveau type de widget, aucune modification des
widgets `chart`/`table`/`indicator` existants, aucune modification de
`/collections/{id}/aggregate` ni de `DataSourcePanel.tsx` — zéro régression
possible sur l'existant par construction (aucun fichier partagé modifié en
dehors de l'enregistrement du nouveau widget, §3).

## 2. Données — réutilisation intégrale de l'existant

L'auteur configure une source `statistics` exactement comme pour sankey en
14f : `groupBy: "region,quarter"` (2 champs, `DataSourcePanel.tsx:88-91`,
scission virgule déjà supportée) + une ou plusieurs `measures`
(`DataSourcePanel.tsx:112-137`, éditeur déjà existant, inchangé). `/aggregate`
route déjà cette forme vers `_pivot_multi_measures`
(`aggregate.py:202-209`, `run_collection_aggregate:293-299`) et renvoie des
lignes tidy `{region, quarter, sum_amount, avg_amount, ...}` — une ligne par
combinaison `(region, quarter)` observée dans les données, colonnes de mesure
nommées par `_measure_label` (label explicite ou `${agg}_${field}` par
défaut).

Aucune ligne de `core/`, `itemClient.ts` ou `DataSourcePanel.tsx` ne change
pour ce plan.

## 3. Widget `pivot` — nouveau fichier, props & reshape

Nouveau fichier `shell/src/builder/widgets/pivot.tsx`, exportant
`registerPivotWidget()`, appelé depuis `registerBuiltinWidgets()`
(`shell/src/builder/widgets/index.tsx`) au même niveau que
`registerChartWidget()`.

```ts
type PivotProps = {
  dataSourceId?: string;
  encodings?: { rows?: string; columns?: string };
  title?: string;
};
```

**`PropsPanel`** : `DataSourceSelect` + deux champs texte « Champ lignes » /
« Champ colonnes » (`encodings.rows`/`encodings.columns`) — même patron que
les deux `<select>` « Champ source »/« Champ cible » du sankey
(`chart.tsx:77-88`), en `<input>` texte libre ici plutôt qu'un `<select>`
d'après le schéma de colonnes (pas de `DatasetConfig` résolu systématiquement
disponible dans le panneau au moment de l'édition — cohérent avec le champ
« Champ catégorie / X » existant, lui aussi un `<input>` texte libre) + champ
« Titre » optionnel.

**Fonction de reshape pure** (testable isolément, sans rendu — même esprit
que `chartOption.ts`/`resolveClickFilter`), dans un module
`shell/src/builder/widgets/pivotTable.ts` :

```ts
type PivotMeasureColumns = string[]; // labels de mesure, ordre = ordre de première apparition dans les lignes reçues
type PivotGrid = {
  rowValues: string[];    // triées alphabétiquement
  colValues: string[];    // triées alphabétiquement
  measures: PivotMeasureColumns;
  cell(row: string, col: string, measure: string): number;      // 0 si combinaison absente
  rowTotal(row: string, measure: string): number;
  colTotal(col: string, measure: string): number;
  grandTotal(measure: string): number;
};

function buildPivotGrid(records: DataRecord[], rowsField: string, colsField: string): PivotGrid | null;
```

`buildPivotGrid` retourne `null` — et le `Component` affiche alors un message
de configuration, même convention que les autres widgets non configurés (ex.
`chart.tsx:238` « Aucune donnée ») — dans trois cas : `rowsField`/`colsField`
vides, un enregistrement ne porte pas ces deux propriétés (données non
conformes à un `groupBy` à 2 champs), ou aucune propriété de mesure ne reste
une fois `rowsField`/`colsField` exclus (aucune mesure configurée sur la
source). Les labels de mesure sont déduits des clés de
`records[0].properties` autres que `rowsField`/`colsField` (même technique
que `firstField` dans `data.tsx:19-21`, généralisée à plusieurs clés) ;
l'ordre de première apparition est conservé pour un rendu stable.

## 4. Rendu & cross-filter

**Rendu** — une seule `<table>`, deux lignes d'en-tête :
- Ligne 1 : une cellule vide (coin), puis une cellule par valeur de colonne
  avec `colSpan = measures.length` (fusionnée en une seule cellule si
  `measures.length === 1` — pas de deuxième ligne d'en-tête dans ce cas),
  puis une cellule « Total » (même `colSpan`).
- Ligne 2 (seulement si `measures.length > 1`) : le libellé de chaque mesure
  répété sous chaque colonne et sous « Total ».
- Une ligne de données par valeur de lignes : la valeur en première cellule
  (`<th scope="row">`), une cellule par `(colonne, mesure)`, puis le total de
  ligne par mesure (`rowTotal`).
- Une dernière ligne « Total » : le total de colonne par mesure
  (`colTotal`) puis le grand total par mesure (`grandTotal`) dans le coin
  inférieur droit.

**Cross-filter** — clic sur une cellule d'en-tête de ligne (`<th
scope="row">`) → `setCrossFilter(datasetId, encodings.rows, rowValue,
dataSourceId)` ; clic sur une cellule d'en-tête de colonne (ligne 1) →
`setCrossFilter(datasetId, encodings.columns, colValue, dataSourceId)` —
appel identique à celui du clic de catégorie sur `chart.tsx:246`, juste
déclenché depuis deux zones distinctes du tableau plutôt que par un seul
handler `onClick` ECharts. La ligne/colonne « Total » et les cellules de
données ne portent aucun handler de clic (non-but §1).

**Drill** — `ExplorerMenu` (`shell/src/builder/widgets/ExplorerMenu.tsx`)
ajouté au coin du widget avec `datasetId`/`dataSourceId` de la source liée,
même convention que `chart`/`table`/`list` — portée dataset entière, pas
scopée à une cellule.

## 5. Tests

**Unit (Vitest)** — `pivotTable.test.ts` : fonction `buildPivotGrid` pure,
sans rendu :
- 1 mesure, grille 2×2 complète → cellules, totaux de ligne, de colonne,
  grand total corrects.
- Multi-mesures (2+) → chaque mesure a ses propres totaux, ordre des
  colonnes de mesure cohérent avec l'ordre de première apparition.
- Combinaison lignes×colonnes absente des données → cellule à 0, incluse
  dans les totaux comme n'importe quelle valeur.
- `encodings.rows`/`encodings.columns` vide, ou absent des propriétés du
  premier enregistrement → `null`.

`pivot.test.tsx` : `PropsPanel` affiche les deux champs `encodings.rows`/
`encodings.columns` ; clic sur un en-tête de ligne appelle `setCrossFilter`
avec `(datasetId, encodings.rows, rowValue, dataSourceId)` ; clic sur un
en-tête de colonne avec `encodings.columns` ; clic sur une cellule de donnée
ou sur la ligne/colonne « Total » n'appelle jamais `setCrossFilter`.

**E2E (Playwright)** — étend `shell/e2e/analytics-context.spec.ts` :
1. Widget `pivot` sur un dataset à 2 dimensions + 1 mesure → la grille rendue
   contient les valeurs de cellule, le total de ligne, le total de colonne et
   le grand total attendus (valeurs vérifiées contre un fixture connu, pas
   seulement le nombre de lignes/colonnes).
2. Clic sur un en-tête de ligne → une seconde table du même dataset,
   affichée à côté, perd effectivement des lignes (preuve empirique par une
   table réelle, même style que le scénario histogramme de 14f — pas
   seulement « la requête change »).
3. Clic sur un en-tête de colonne → même vérification, filtrée par le champ
   colonnes cette fois.
4. Widget `pivot` non configuré (`encodings.rows`/`columns` vide) → message
   de configuration affiché, pas de crash.
5. Les 39+ specs E2E existantes restent vertes.

| Risque | Garde-fou |
|---|---|
| Enregistrements avec des clés de propriétés dans un ordre différent d'une ligne à l'autre (JSON ne garantit pas d'ordre stable entre objets) | Les labels de mesure sont déduits une fois depuis `records[0]`, pas recalculés par ligne — un ordre différent sur une ligne ultérieure n'affecte que la valeur, jamais l'ensemble de colonnes de mesure affichées |
| Valeur de ligne ou de colonne contenant une valeur `NULL`/vide | Regroupée sous une clé littérale `"—"` avant tri, cohérente avec le traitement des valeurs manquantes en treemap/sunburst (14f, `aggregate.py`) |
| Grille très large (beaucoup de valeurs de colonnes distinctes) | Non traité explicitement en v1 — la `<table>` déborde horizontalement dans son conteneur de widget comme le fait déjà `table.tsx`, pas de scroll horizontal dédié ni de pagination de colonnes (limite connue, pas un bug) |
| `measures.length === 0` (aucune mesure configurée sur la source) | `buildPivotGrid` retourne `null` (même chemin que `encodings` vide, §3) — un seul message de configuration pour tous les cas de source incomplète, pas d'état intermédiaire « grille vide » à gérer séparément |
| Tri alphabétique de valeurs numériques (ex. années « 2, 10, 9 » triées comme des chaînes) | Non traité en v1 — `rowValues`/`colValues` sont triées avec `localeCompare`, sans détection de type numérique ; limite connue, cohérente avec l'absence de tri configurable (§1 non-buts) |
