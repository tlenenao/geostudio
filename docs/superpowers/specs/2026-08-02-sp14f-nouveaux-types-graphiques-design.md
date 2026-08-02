# SP-14f — Nouveaux types de graphiques : sankey, treemap, sunburst, funnel, histogramme binné (design)

> **Date : 2026-08-02 · Statut : validé (brainstorm)**
> Sixième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités** et **SP-14e — KPI riche &
> séries temporelles comparées**. Traite une partie de ce qui restait de la
> liste « Widgets analytiques » de la feuille de route, en continuité directe
> avec la note de 14e (« pivot, sankey/treemap/sunburst/funnel, carte
> analytique par `encodings`, conteneurs onglets/modale/tiroir — sous-parties
> SP-14 ultérieures (14f…) ») : les **4 nouveaux types de graphique**
> (sankey, treemap, sunburst, funnel) + l'**histogramme binné serveur**.
> Tableau croisé/pivot, carte analytique, conteneurs (onglets/modale/tiroir),
> requête visuelle, SQL Lab, source `arcgis`, MCP analytique restent hors
> périmètre — sous-parties SP-14 ultérieures (14g…).

## 1. Objectif & non-buts

**Objectif.** Ajouter 5 nouveaux modes au widget `chart` existant (même
approche que 14e : nouveaux modes d'un widget existant, pas un nouveau
widget), pour couvrir des questions que bar/line/pie ne peuvent pas
représenter : flux entre deux catégories (sankey), composition hiérarchique
(treemap/sunburst), entonnoir de conversion (funnel), distribution d'un champ
numérique (histogramme). `FunnelChart`, `SankeyChart`, `TreemapChart` sont
déjà enregistrés dans `EChart.tsx:7,22` (inutilisés à ce jour) ; seul
`SunburstChart` manque.

**Non-buts explicites** (reportés) :

- Tableau croisé/pivot, carte analytique par `encodings`, conteneurs
  onglets/modale/tiroir — reste de la liste « widgets analytiques »,
  sous-parties SP-14 ultérieures.
- Requête visuelle, SQL Lab, source `arcgis`, MCP analytique — toujours hors
  périmètre (inchangé depuis 14a-14e).
- Bookmarks/situations nommées, cross-filter inter-datasets — toujours hors
  périmètre (inchangé depuis 14b).
- Retrofit d'`encodings` sur bar/line/area/scatter/pie/doughnut/radar/
  heatmap/gauge/boxplot — ils gardent `categoryField`/`valueField` tels
  quels ; `encodings` n'est introduit que pour sankey et treemap/sunburst, où
  `categoryField`/`valueField` ne suffisent structurellement pas (§3).
- Sankey multi-étapes (plus d'un saut source→cible) — v1 fermée à un seul
  saut.
- Hiérarchie treemap/sunburst au-delà de 3 niveaux.
- Cross-filter au clic sur l'histogramme (filtrage par plage `field >= x AND
  field < y`, hors du modèle de cross-filter actuel à valeur unique) — la
  classe s'affiche mais n'est pas cliquable pour filtrer.
- Granularité de bin configurable autrement qu'un nombre de classes fixé par
  l'auteur (pas de largeur de bin explicite, pas de binning automatique par
  règle de Sturges ou équivalent).

Le modèle reste additif : les 5 nouvelles valeurs de `chartType`, `encodings`
et `bins` sont optionnels et sans effet sur bar/line/area/scatter/pie/
doughnut/radar/heatmap/gauge/boxplot existants — zéro régression.

## 2. Core — `groupBy` multi-niveaux et binning sur `/collections/{id}/aggregate`

`AggregateRequestBody` (`core/app/analytics/aggregate.py:26-34`) :

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None   # str seul : comportement actuel inchangé
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    bucket: Literal["day", "week", "month"] | None = None
    bins: int | None = None                  # nouveau
```

**`groupBy` liste (2-3 champs)** — produit des lignes « tidy » : une ligne
par combinaison observée, une colonne par niveau (nom de colonne réel, comme
aujourd'hui pour un `groupBy` simple) + la/les mesure(s). C'est le format
dont sankey (`["origin", "destination"]` → `{origin, destination, value}`) et
treemap/sunburst (`["region", "category", "subcategory"]` →
`{region, category, subcategory, value}`) ont besoin. Implémentation dans
`run_collection_aggregate` (`aggregate.py:203-232`) : `cat_expr` (ligne
215-217) et le `GROUP BY __cat` (ligne 230) deviennent une liste
d'expressions `_qi(field) AS <field>` projetées et groupées ensemble ; la clé
de sortie n'est plus systématiquement `__cat`/`category_key` mais une colonne
par champ de `groupBy` — `_pivot_measures` (ligne 170-177) est étendue pour
émettre toutes les colonnes de niveau au lieu d'une seule `category_key`.

Règles de validation (`_validate_fields`, ligne 71-90) :

- `bucket` reste réservé au cas `groupBy` à un seul champ — combiné à une
  liste, `UnknownAggregateField("bucket", "bucket requires a single-field
  groupBy")` (aucun sens applicatif : bucketer une hiérarchie n'a pas de
  sémantique définie, et aucun widget de ce plan n'en a besoin — le widget
  `chart` en mode comparaison de périodes, lui, pose toujours `groupBy` comme
  un champ unique, `dataset.timeField`).
- `split` (pivot large existant) et `groupBy` liste sont mutuellement
  exclusifs — `UnknownAggregateField("split", "split cannot combine with a
  multi-field groupBy")` : ce sont deux formats de sortie différents (large
  pivoté vs tidy) qui ne se composent pas.
- Chaque champ de la liste est validé individuellement contre
  `_valid_column_names` (ligne 64-68), comme le `groupBy` simple actuel.

**Binning (`bins`)** — actif seulement avec `field` posé (le champ numérique
à distribuer) et `groupBy` absent. Deux requêtes SQL dans
`run_collection_aggregate` : (1) `SELECT MIN(field), MAX(field) FROM live
{where_sql}` sur la même CTE dédupliquée (`_dedup_cte`, ligne 180-188) pour
borner les classes ; (2) `WIDTH_BUCKET(TRY_CAST(field AS DOUBLE), min, max,
bins)` en `GROUP BY`, agrégé par `COUNT(*)` (ou la mesure demandée via
`agg`/`field` — réutilise `_agg_expr`, ligne 93-107). Réponse : une ligne par
classe non vide, `{bucketIndex, bucketStart, bucketEnd, value}` (bornes
calculées côté Python à partir de `min`/`max`/`bins`, pas par DuckDB, pour
un contrôle exact de l'arrondi d'affichage). `bins` sans `field` →
`UnknownAggregateField("bins", "bins requires a field")`.

Côté shell, `itemClient.ts` : `STAT_KEYS` (ligne 40) gagne `"bins"` (déjà
transmis tel quel, comme `bucket`) ; `buildAggregateBody` (ligne 49-71)
transmet `groupBy` sans changement de forme — un `string` reste un `string`,
une provenance en liste (voir ci-dessous) est déjà un array JSON.

**`DataSourcePanel.tsx`** (ligne 78) : le champ texte « grouper par (axe X) »
reste un simple input libre, **sans nouveau composant** — une valeur
contenant une virgule (`"origin,destination"`) est scindée en liste avant
envoi (`patchQuery` transforme la chaîne en `string[]` si elle contient une
virgule, sinon garde le `string` simple — zéro changement pour tous les
usages actuels à un seul champ). Un nouveau champ numérique « Nombre de
classes (histogramme) » à côté du champ « Champ agrégé » alimente `bins`.

## 3. `encodings` — nouveau, seulement où c'est structurellement nécessaire

`ChartProps` (`chartOption.ts:6-20`) gagne :

```ts
export type ChartProps = {
  // ...existant...
  encodings?: {
    source?: string;   // sankey
    target?: string;   // sankey
    levels?: string[]; // treemap | sunburst, 1 à 3 champs, ordre = hiérarchie racine→feuille
    value?: string;     // sankey | treemap | sunburst — nom de la mesure retournée (défaut : premier champ non-niveau)
  };
  bins?: number; // histogramme, défaut 10
};
```

- **Funnel** réutilise `categoryField` (étape) / `valueField` (valeur) — même
  forme que `pie` : pas d'`encodings`.
- **Histogramme** réutilise `valueField` (champ numérique à binner, transmis
  côté source de données comme `field`) + nouveau `bins` — pas d'`encodings`
  non plus.
- **Sankey** et **treemap/sunburst** utilisent `encodings` — c'est la
  première utilisation du terme employé par la feuille de route pour la
  future carte analytique (« symbologie pilotée par dataset via les mêmes
  `encodings` que les charts ») : le mécanisme est générique par nom
  (`Record<rôle, nom de champ>`), introduit ici pour 2 types seulement, sans
  toucher aux 10 types existants.

`chartOption.ts` — nouvelles branches dans `buildOption` (après la branche
`boxplot`, ligne 127-134, même patron `finalize(props, {...})`) :

- **`funnel`** : `series: [{ type: "funnel", data: rows.map(r => ({ name:
  String(r[catKey]), value: num(r[valueKey]) })) }]` — `catKey`/`valueKey`
  résolus exactement comme la branche `pie` existante (ligne 81-91).
- **`histogram`** : rendu comme une série `bar` sur les lignes déjà binnées
  par le serveur (`bucketStart`-`bucketEnd` formatés en libellé de catégorie
  côté `pickCatKey`) — pas de nouveau composant ECharts, juste un axe X
  catégoriel construit à partir des bornes plutôt que des valeurs brutes.
- **`sankey`** : construit `nodes`/`links` à partir des lignes tidy
  (`encodings.source`/`target`/`value`) — chaque nœud unique (union des
  valeurs de `source` et de `target`) reçoit un champ interne non affiché
  `_role: "source" | "target"` (les deux si la valeur apparaît des deux
  côtés — auquel cas le rôle du dernier clic déterminant est résolu au
  moment du clic, voir §4) ; `series: [{ type: "sankey", data: nodes, links
  }]`.
- **`treemap` / `sunburst`** : construit un arbre à partir des lignes tidy et
  de `encodings.levels` (1 à 3 champs) — un nœud par valeur unique à chaque
  niveau, `value` agrégé en remontant (somme des feuilles), profondeur =
  `levels.length`. `series: [{ type: "treemap" | "sunburst", data: tree }]`.

## 4. Cross-filter au clic — généralisation avec résolution de l'ambiguïté sankey

Le patron actuel (`chart.tsx:200-205`, mode par défaut) : le clic sur un
point nommé émet `categorySelected` et pose un cross-filter
`(categoryField, name)`. Généralisé aux 5 nouveaux types :

- **Funnel** : identique au patron actuel — `categoryField` est le champ
  d'étape, `params.name` la valeur cliquée.
- **Treemap/sunburst** : `params.name` (ECharts fournit le nom du nœud
  cliqué, quel que soit son niveau) + `params.treePathInfo` (liste des
  ancêtres) — le cross-filter est posé sur le **niveau le plus profond
  cliqué** : `encodings.levels[params.treePathInfo.length - 1]` comme champ,
  `params.name` comme valeur. Cliquer un nœud racine filtre sur le premier
  niveau, cliquer une feuille filtre sur le dernier — cohérent avec
  l'attente d'un utilisateur qui explore de haut en bas.
- **Sankey** : ambiguïté réelle — un nom de nœud peut apparaître à la fois
  comme source et comme cible (ex. une étape intermédiaire). Résolue en
  gardant le `_role` tagué à la construction de l'option (§3) : le handler de
  clic ECharts sankey distingue déjà `params.dataType === "node"` (vs
  `"edge"`, ignoré — pas de cross-filter sur un clic de lien) ; parmi les
  nœuds partageant un même nom, le rôle du nœud effectivement cliqué
  (`params.data._role`, porté par l'objet nœud ECharts, invisible au rendu)
  détermine si c'est `encodings.source` ou `encodings.target` qui reçoit le
  filtre.
- **Histogramme** : pas de handler de clic (non-but explicite §1).

## 5. UI builder

- `CHART_TYPES` (`chart.tsx:15-19`) gagne 5 entrées : `["sankey", "Flux
  (sankey)"]`, `["treemap", "Zones hiérarchiques (treemap)"]`, `["sunburst",
  "Soleil hiérarchique (sunburst)"]`, `["funnel", "Entonnoir"]`,
  `["histogram", "Histogramme"]`.
- `PropsPanel` (`chart.tsx:43-123`) : les champs actuels « Champ catégorie /
  X » et « Champ valeur » (lignes 57-64) restent affichés tels quels pour
  `funnel` (catégorie = étape) et masqués pour `sankey`/`treemap`/`sunburst`
  au profit d'un éditeur `encodings` conditionnel :
  - `sankey` : deux `<select>` (options = colonnes du dataset résolu via
    `DatasetConfig.columns`, même source que `DataSourceSelect` /
    `dateRangeFilter` pour les champs disponibles) — « Champ source », «
    Champ cible ».
  - `treemap`/`sunburst` : une liste de 1 à 3 `<select>` avec boutons
    ajouter/retirer un niveau — « Niveau 1 », « Niveau 2 », « Niveau 3 ».
  - `histogram` : réutilise « Champ valeur » (champ numérique à binner) +
    nouveau champ numérique « Nombre de classes » (`bins`, défaut 10).
- `EChart.tsx` (ligne 7) : ajoute `SunburstChart` à l'import `echarts/charts`
  et à l'appel `echarts.use([...])` (ligne 19-27) — seul composant manquant,
  `FunnelChart`/`SankeyChart`/`TreemapChart` déjà présents.

## 6. Tests & risques

**Core** (`core/tests/test_analytics_aggregate.py`) :
- `groupBy` liste à 2 champs → lignes tidy avec les 2 colonnes nommées +
  mesure, groupées correctement.
- `groupBy` liste à 3 champs → idem, 3 colonnes.
- `bucket` + `groupBy` liste → `UnknownAggregateField` explicite.
- `split` + `groupBy` liste → `UnknownAggregateField` explicite.
- `bins` avec `field` → classes correctes contre un jeu de données connu
  (bornes min/max vérifiées, comptage par classe).
- `bins` sans `field` → `UnknownAggregateField` explicite.
- Non-régression : `groupBy` simple (`str`) produit exactement la sortie
  actuelle (suite existante verte).

**Shell (unitaires)** :
- `chartOption.test.ts` : une fonction par nouveau type (funnel, histogram,
  sankey, treemap, sunburst), suivant le patron des tests existants (ligne
  17 et suivantes) — option ECharts attendue à partir de lignes tidy
  connues ; tagging `_role` vérifié pour un nœud sankey apparaissant des deux
  côtés.
- `chart.test.tsx` : `PropsPanel` affiche les bons contrôles selon
  `chartType` (encodings vs champs actuels) ; clic sur treemap/sunburst pose
  le cross-filter sur le niveau le plus profond ; clic sur un nœud sankey
  résout le bon rôle.
- `EChart.test.tsx` (si existant) ou test de fumée : `SunburstChart` rendu
  sans erreur.

**E2E** (étend `analytics-context.spec.ts`) :
1. Widget `chart` en sankey sur un dataset à 2 dimensions → rendu, clic sur
   un nœud → cross-filter appliqué sur le bon champ (source ou cible selon
   le nœud cliqué).
2. Widget `chart` en treemap (2 niveaux) → clic sur une feuille → cross-
   filter sur le niveau 2 ; clic sur un nœud racine → cross-filter sur le
   niveau 1.
3. Widget `chart` en funnel → rendu + clic → cross-filter, comme un `pie`
   existant.
4. Widget `chart` en histogramme → rendu avec le nombre de classes attendu,
   pas de handler de clic.
5. **Non-régression explicite** : les 10 types existants (bar/line/area/
   scatter/pie/doughnut/radar/heatmap/gauge/boxplot) inchangés, `encodings`
   absent des configs existantes sans effet.
6. Les 18+ specs E2E existantes restent vertes.

| Risque | Garde-fou |
|---|---|
| `WIDTH_BUCKET` avec `min == max` (champ constant) | Repli explicite : un seul bucket couvrant toute la plage, pas de division par zéro (garde côté Python avant l'appel SQL) |
| Nœud sankey présent des deux côtés mais l'auteur n'a posé qu'un des deux champs `encodings` | Rôle manquant → pas de cross-filter émis pour ce clic (comportement silencieux, cohérent avec `categoryField` absent aujourd'hui, ligne 201) |
| Hiérarchie treemap/sunburst avec des valeurs `NULL`/vides à un niveau intermédiaire | Regroupées sous un nœud littéral `"—"` (cohérent avec l'absence de `COALESCE` texte ailleurs dans le module — décision d'affichage, pas de crash) |
| `groupBy` liste avec un champ dupliqué (ex. `["a", "a"]`) | Validation explicite : erreur `UnknownAggregateField("groupBy", "duplicate field")`, pas de comportement SQL indéfini |
| Nombre de classes (`bins`) déraisonnable (0, négatif, ou très grand) | Bornes `1 <= bins <= 100` validées côté core, erreur explicite hors de cette plage |
