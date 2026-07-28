# SP-14e — KPI riche & séries temporelles comparées (design)

> **Date : 2026-07-28 · Statut : validé (brainstorm)**
> Cinquième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur** et
> **SP-14d — Menu explorer & voir les entités**. Traite deux entrées de la
> liste « Widgets analytiques » de la feuille de route : **KPI card riche
> (delta vs référence, sparkline, seuils CEL)** et **séries temporelles avec
> comparaison de périodes**. Le reste de cette liste (pivot,
> sankey/treemap/sunburst/funnel, carte analytique par `encodings`,
> conteneurs onglets/modale/tiroir) reste hors périmètre — sous-parties SP-14
> ultérieures (14f…).

## 1. Objectif & non-buts

**Objectif.** Répondre à « est-ce que ça s'améliore ? » sans SQL : le widget
`indicator` affiche, en plus de sa valeur plate actuelle, un delta contre une
période de référence, un sparkline de la tendance récente et une pastille de
couleur pilotée par seuil CEL ; le widget `chart` (line/area) peut superposer
la période courante et une période de référence sur un axe relatif. Les deux
s'appuient sur la même mécanique : bucketing temporel côté serveur et
réutilisation de `derivePatch` avec une fenêtre temporelle substituée.

**Non-buts explicites** (reportés) :

- Pivot, sankey/treemap/sunburst/funnel, carte analytique par `encodings`,
  conteneurs onglets/modale/tiroir — reste de la liste « widgets
  analytiques », sous-parties SP-14 ultérieures.
- Requête visuelle, SQL Lab, source `arcgis`, MCP analytique — toujours hors
  périmètre (inchangé depuis 14a/14b/14c/14d).
- Bookmarks/situations nommées, cross-filter inter-datasets — toujours hors
  périmètre (inchangé depuis 14b).
- Migration de la **valeur plate par défaut** de `indicator`/`chart` vers
  l'agrégation serveur : le calcul client existant (`ctx.data.records`
  réduits en JS) reste inchangé et continue de s'appliquer quand aucune des
  nouvelles props n'est utilisée — zéro régression sur le comportement
  actuel. Seules les nouvelles fonctionnalités (delta, sparkline,
  comparaison) empruntent le nouveau chemin serveur.
- Granularité de bucket configurable par l'auteur — choix automatique
  uniquement selon la durée de la fenêtre (§3).
- Modes de référence au-delà de « période précédente » et « même période
  l'an dernier » (ex. offset personnalisé arbitraire) — v1 fermée à ces deux
  modes, extensible sans changement de modèle si besoin remonte.
- Seuils CEL : uniquement une pastille de couleur à 3 niveaux, jamais un
  message texte custom ni un impact sur `visibleWhen` (qui reste géré
  séparément).

Le modèle reste additif : `referencePeriod`, `sparkline`, `warningWhen`,
`criticalWhen` sur `indicator`, et le toggle « comparer périodes » sur
`chart`, sont tous optionnels et absents par défaut — une app existante
utilisant ces deux widgets n'est affectée en rien tant que ces props ne sont
pas explicitement posées dans le builder.

## 2. Core — bucketing temporel sur `/collections/{id}/aggregate`

`AggregateRequestBody` (`core/app/analytics/aggregate.py:24-31`) gagne un
champ optionnel :

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    bucket: Literal["day", "week", "month"] | None = None  # nouveau
```

Dans `run_collection_aggregate` (`aggregate.py:197-223`), `cat_expr`
(actuellement `_qi(request.groupBy)` ou `'Total'`, ligne 208) devient,
quand `bucket` est renseigné :

```python
cat_expr = f"DATE_TRUNC({_sql_lit(bucket)}, TRY_CAST({_qi(request.groupBy)} AS TIMESTAMP))"
```

Règles :

- `bucket` sans `groupBy` est une erreur explicite (`UnknownAggregateField`,
  même famille que les validations existantes de `_validate_fields`,
  `aggregate.py:68-84`) — bucketer suppose un champ à bucketer.
- `TRY_CAST` (déjà le patron utilisé pour les mesures numériques, `_agg_expr`,
  ligne 92) absorbe un champ non convertible en timestamp sans casser la
  requête (résultat `NULL`, regroupé dans un seul bucket `NULL` plutôt qu'une
  exception SQL) — cohérence avec le traitement déjà tolérant des mesures.
- Le reste du pipeline (filtres `__gte`/`__lte`/`__in`, bbox, dédup CDC,
  mesures multiples via `split`) est inchangé — extension additive pure,
  aucun appelant existant n'est affecté (`bucket` absent = comportement
  actuel byte-pour-byte).
- La réponse JSON : `DATE_TRUNC` renvoie un `datetime.date`/`datetime`
  DuckDB → Python ; FastAPI sérialise ces valeurs en ISO 8601 via
  `jsonable_encoder` sans code supplémentaire (comportement déjà observé
  pour d'autres champs de type date retournés bruts par ce module).

Côté shell, `itemClient.ts` : `STAT_KEYS` (`itemClient.ts:40`) gagne
`"bucket"`, et `buildAggregateBody` (`itemClient.ts:49-71`) transmet
`body.bucket = String(query.bucket)` si présent — même patron que
`groupBy`/`split`/`agg`/`field`.

## 3. Fenêtres temporelles — calcul partagé

Nouveau module `shell/src/lib/comparisonWindow.ts`, utilisé par `indicator`
et `chart` :

```ts
export type ReferenceMode = "previous" | "sameLastYear";

export function referenceWindow(
  current: { from: string; to: string },
  mode: ReferenceMode,
): { from: string; to: string } {
  const from = new Date(current.from), to = new Date(current.to);
  if (mode === "sameLastYear") {
    return { from: shiftYears(from, -1), to: shiftYears(to, -1) };
  }
  const durationMs = to.getTime() - from.getTime();
  const refTo = new Date(from.getTime());
  const refFrom = new Date(from.getTime() - durationMs);
  return { from: toISODate(refFrom), to: toISODate(refTo) };
}

export function bucketFor(current: { from: string; to: string }): "day" | "week" | "month" {
  const days = (new Date(current.to).getTime() - new Date(current.from).getTime()) / 86_400_000;
  return days <= 31 ? "day" : days <= 180 ? "week" : "month";
}
```

(`shiftYears`/`toISODate` : utilitaires triviaux, format `YYYY-MM-DD`
cohérent avec `dateRangeFilter.tsx:31-34` qui produit déjà ce format via
`<input type="date">`.)

**Activation** : ces fonctions ne sont appelées que si `ctx.timeRange !==
null` **et** `dataset.timeField` est défini (`DatasetConfig.timeField`,
`shell/src/api/types.ts:219-225`) — sinon `indicator`/`chart` restent dans
leur chemin plat/simple actuel, aucune requête supplémentaire n'est émise.

**Requêtes** : la fenêtre courante et la fenêtre de référence réutilisent
`derivePatch` (`shell/src/lib/analyticsPatch.ts:10-43`) **sans
modification** — chaque fenêtre est un `AnalyticsContextState` synthétique
où seul `timeRange` change, `extent`/`crossFilter` restant ceux du contexte
réel :

```ts
const patch = derivePatch(source, { ...analyticsCtx, timeRange: window }, datasets);
```

`derivePatch` produit déjà `[timeField]__gte/__lte` + `bbox` (si
`reactsToExtent`) + cross-filter — donc la fenêtre courante posée ici est
strictement équivalente à celle que `DataContext` appliquerait pour la
valeur plate, et la fenêtre de référence hérite exactement des mêmes filtres
ambiants (emprise, cross-filter), seule la période changeant. Le résultat
est fusionné dans une `DataSource` de type `"statistics"` (`groupBy:
dataset.timeField`, `bucket`, `agg`/`field` ou `measures` repris des props
du widget) passée à `client.queryDataSource` (`itemClient.ts:619`, route
`"statistics"` déjà câblée vers `/collections/{id}/aggregate`,
`itemClient.ts:626-630`).

## 4. KPI riche (`indicator` enrichi)

Nouvelles props optionnelles sur `indicator` (`shell/src/builder/widgets/
indicator.tsx`), toutes absentes par défaut :

```ts
{
  referencePeriod?: "previous" | "sameLastYear";  // absent/undefined = comportement actuel, pas de delta
  sparkline?: boolean;                             // défaut false
  warningWhen?: string;                            // expression CEL optionnelle
  criticalWhen?: string;                           // expression CEL optionnelle
}
```

**Rendu inchangé si** `!referencePeriod && !sparkline` : le `Component`
actuel (lignes 33-50) n'est pas touché dans ce cas — même calcul
`data.records.reduce`/`.length`.

**Rendu enrichi si** `referencePeriod` posé et (`ctx.timeRange` actif et
`dataset.timeField` défini) :

- Nouveau hook `useKpiComparison(source, dataset, analyticsCtx, {
  referencePeriod, sparkline, agg, field })`, actif seulement sous ces
  conditions, qui émet :
  - 1 requête `statistics` (fenêtre courante, sans `bucket`) → `value`
    (recalculée côté serveur au lieu du `reduce` client — cohérence : une
    fois qu'on interroge `/aggregate` pour la référence, la valeur courante
    utilise le même chemin plutôt que deux sources de vérité différentes
    pour le même nombre).
  - 1 requête `statistics` (fenêtre de référence, sans `bucket`) → `reference`.
  - `delta = value - reference`, `deltaPct = reference !== 0 ? delta / reference : null`.
- Si `sparkline` est vrai (indépendamment de `referencePeriod`, mais
  toujours sous condition `ctx.timeRange` + `timeField`) : 1 requête
  `statistics` supplémentaire, fenêtre courante, `bucket: bucketFor(ctx.timeRange)`
  → série de points `{ bucket, value }` rendue en mini-graphique (`EChart`
  lazy déjà utilisé par `chart.tsx:9`, réutilisé ici en mode minimal : pas
  d'axes visibles, une seule ligne).
- Affichage : valeur courante (gros chiffre, inchangé), sous elle un badge
  delta (`+12 % vs période précédente` / `-3 vs même période l'an dernier`,
  couleur neutre par défaut), le sparkline sous le badge si activé.

**Seuils CEL** : si `criticalWhen`/`warningWhen` posés, évalués via
`evaluateExpression` (`shell/src/builder/expr.ts:12-18`) avec
`{ vars, user, ctx: analyticsCtx, record: { value, delta, deltaPct } }` —
réutilisation du champ `record` existant de `ExprContext` (déjà présent
comme optionnel, `expr.ts:5-10`) plutôt qu'un nouveau champ, pour rester
dans le même contrat que `visibleWhen`. Ordre d'évaluation : `criticalWhen`
d'abord, puis `warningWhen`, sinon `ok` — une pastille de couleur
(rouge/orange/aucune) apparaît à côté de la valeur. Expressions absentes ou
en erreur (`evaluateExpression` retourne `undefined` sur erreur, ligne 15) →
pas de pastille, comportement silencieux cohérent avec `visibleWhen`.

## 5. Chart — mode « comparer périodes »

Nouveau toggle `compareEnabled: boolean` (défaut `false`) + `comparePeriod:
"previous" | "sameLastYear"` dans les props de `chart.tsx`, visible dans le
`PropsPanel` **seulement** si `props.chartType` vaut `"line"` ou `"area"`
(les autres types ne montrent pas le contrôle, pas de branche morte à
tester).

**Activation** : si `compareEnabled` et (`ctx.timeRange` actif et
`dataset.timeField` défini) — sinon le toggle reste sans effet visible
(chart affiche sa série unique actuelle, comme si `compareEnabled` était
faux ; pas d'état cassé si l'app n'a pas de `dateRangeFilter`).

**Requêtes** : 2 requêtes `statistics` bucketées (`bucket:
bucketFor(ctx.timeRange)`, même règle qu'au §3), l'une sur la fenêtre
courante, l'autre sur `referenceWindow(ctx.timeRange, comparePeriod)` —
même construction `derivePatch(source, { ...analyticsCtx, timeRange: window
}, datasets)` que le KPI.

**Alignement** : chaque série est réindexée sur un axe relatif — offset de
bucket depuis le début de sa propre fenêtre (« Jour 1 », « Jour 2 »… ou «
Semaine 1 »… selon le bucket choisi) au lieu des dates absolues renvoyées
par le serveur, pour que les deux séries se superposent visuellement malgré
des dates de calendrier différentes.

**Rendu** : 2 séries ECharts dans `buildOption` (`chartOption.ts`) — «
Période courante » (trait plein, couleur normale du thème) et « Référence »
(pointillé, couleur atténuée) — uniquement quand le mode comparaison est
actif ; sinon `buildOption` produit exactement l'option actuelle à une
série.

## 6. Tests & risques

**Core** (`core/tests/`) :
- `bucket` avec `groupBy` sur un champ date valide → lignes bucketées
  jour/semaine/mois correctement (`DATE_TRUNC` vérifié contre des lignes de
  test connues).
- `bucket` sans `groupBy` → `UnknownAggregateField` explicite.
- `bucket` sur un champ non convertible en timestamp → pas d'exception,
  résultat regroupé sous un bucket `NULL` (comportement `TRY_CAST` déjà
  établi pour les mesures).
- Non-régression : requêtes existantes sans `bucket` inchangées (suite
  `test_aggregate*` actuelle verte).

**Shell (unitaires)** :
- `comparisonWindow.test.ts` : `referenceWindow` pour les deux modes (cas
  limite mois de durée différente pour `sameLastYear`, ex. 29 février) ;
  `bucketFor` aux trois bornes (31/180 jours).
- `indicator.test.tsx` : rendu inchangé sans nouvelles props (non-
  régression explicite) ; delta/sparkline absents sans `ctx.timeRange` ou
  sans `dataset.timeField` même si `referencePeriod`/`sparkline` posés ;
  delta calculé correctement (mock `queryDataSource` sur les deux fenêtres) ;
  pastille critique/warning/ok selon les expressions CEL et les valeurs
  `{ value, delta, deltaPct }`.
- `chart.test.tsx` / `chartOption.test.ts` : toggle absent du `PropsPanel`
  hors `line`/`area` ; option à 2 séries seulement quand `compareEnabled`
  actif et conditions réunies ; option à 1 série sinon (non-régression).

**E2E** (étend `analytics-context.spec.ts`) :
1. App avec `dateRangeFilter` actif, `indicator` avec `referencePeriod:
   "previous"` → delta affiché cohérent avec les données (période courante
   vs période précédente calculée manuellement dans le scénario).
2. `sparkline: true` → mini-graphique présent avec le nombre de points
   attendu pour la durée de fenêtre choisie.
3. Seuil CEL (`criticalWhen: "record.value > 100"`) → pastille rouge sur un
   jeu de données dépassant le seuil, absente sinon.
4. `chart` en mode comparaison → 2 séries visibles, alignées sur l'axe
   relatif.
5. **Non-régression explicite** : `indicator`/`chart` sans les nouvelles
   props, ou dans une app sans `dateRangeFilter`, se comportent exactement
   comme avant (mêmes assertions que les scénarios 14b/14c/14d existants).
6. Les 18+ specs E2E existantes restent vertes.

| Risque | Garde-fou |
|---|---|
| `sameLastYear` sur une fenêtre chevauchant le 29 février | `shiftYears` documente le repli (ex. vers le 28 février) — comportement défini, pas un crash ; couvert par un test dédié |
| KPI émettant jusqu'à 3 requêtes réseau supplémentaires (valeur, référence, sparkline) | Toutes optionnelles et desactivées par défaut ; dédup React Query par `queryKey` si deux widgets partagent exactement la même fenêtre/dataset |
| Incohérence si la valeur plate (client) et la valeur enrichie (serveur) divergent légèrement (ex. filtre `NULL` géré différemment) | §4 : dès que `referencePeriod`/`sparkline` est actif, la valeur courante est recalculée par le même chemin serveur que la référence — une seule source de vérité par instance de widget, jamais un mélange client/serveur sur le même affichage |
| `bucket` avec un `groupBy` qui n'est pas le `timeField` du dataset (erreur d'auteur) | Hors périmètre widget (les props `indicator`/`chart` posent toujours `groupBy: dataset.timeField` elles-mêmes, jamais un champ arbitraire choisi par l'auteur pour cette fonctionnalité) |
| Sparkline sur un dataset sans données dans certains buckets | Mesures agrégées avec `COALESCE(..., 0)` déjà en place côté core (`_agg_expr`, `aggregate.py:94-100`) — bucket vide renvoie 0, pas une ligne manquante à gérer côté client |
