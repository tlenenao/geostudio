# SP-14c — Filtres typés (select/slider) & indicateur de contexte actif (design)

> **Date : 2026-07-26 · Statut : validé (brainstorm)**
> Troisième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés** et **SP-14b — Contexte
> analytique global & cross-filter**. Complète la famille de « filtres
> typés » commencée en 14b (seul un widget `dateRangeFilter` livré alors) et
> traite le point explicitement laissé en suivi par 14b : le cross-filter
> filtre le tableau de bord sans aucun retour visuel. La « requête visuelle »
> et « SQL Lab » restent hors périmètre (sous-parties suivantes de SP-14, cf.
> feuille de route).

## 1. Objectif & non-buts

**Objectif.** Deux nouveaux widgets filtres — **select** (valeurs discrètes,
multi-sélection) et **slider** (plage numérique) — alimentés directement par
un dataset déjà utilisé dans l'app, sans configuration technique
supplémentaire ; et un **indicateur visuel** du contexte analytique actif
(période, emprise, cross-filter par dataset), avec effacement individuel ou
global. Ensemble, ils couvrent le critère d'acceptation SP-14 « filtres
lisibles par un non-technicien » et ferment le trou UX identifié par la
revue finale de 14b (« cross-filter actif mais invisible »).

**Non-buts explicites** (reportés) :

- Les options du select et les bornes du slider reflètent **tout le
  dataset**, jamais la vue déjà réduite par le contexte actif (période,
  emprise, autre cross-filter) — pas de narrowing en cascade dans ce plan.
  Améliorable plus tard sans changement de modèle (cf. §6, risques).
- Libellés de chips de l'indicateur = **noms de colonne bruts**, pas les
  libellés métier (`DatasetColumnMeta.label`) saisis dans l'éditeur de
  dataset — éviter d'exposer la carte des datasets résolus en dehors de
  `DataContext` pour ce premier jet.
- Cross-filter entre **datasets différents** — toujours hors périmètre
  (inchangé depuis 14b).
- Bookmarks nommés persistés côté serveur — toujours hors périmètre.
- Requête visuelle, SQL Lab, source `arcgis` pour dataset, MCP analytique —
  sous-parties suivantes de SP-14, non traitées ici.
- **Aucun changement core** dans ce plan : les deux nouveaux widgets
  consomment l'endpoint `/collections/{id}/aggregate` existant
  (`groupBy`+`count` pour les valeurs distinctes, `measures=[min,max]` pour
  les bornes), déjà exposé au shell via `itemClient.queryDataSource` (SP-11b/
  14a). Vérifié par lecture du code (`core/app/analytics/aggregate.py`) :
  sans `groupBy`, l'agrégat retourne une seule ligne `"Total"` avec une
  colonne par mesure nommée par son `label` — exactement la forme dont le
  slider a besoin (`{min, max}`).

Le modèle reste additif : une app existante en `interactions: "manual"`
n'affiche jamais l'indicateur et les nouveaux widgets n'écrivent jamais dans
le contexte (mêmes garde-fous que 14b, cf. §3).

## 2. Modèle de données — extension du cross-filter

`CrossFilterEntry.value` (`shell/src/builder/AnalyticsContext.tsx`) gagne une
troisième forme, pour porter une plage numérique en plus d'une égalité ou
d'une liste déjà supportées depuis 14b :

```ts
export type CrossFilterEntry = {
  field: string;
  value: string | string[] | { from: string; to: string }; // + plage (slider)
  originSourceId: string;
};
```

`derivePatch` (`shell/src/lib/analyticsPatch.ts`) gagne une branche
symétrique aux deux existantes :

```ts
if (Array.isArray(crossFilter.value)) patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
else if (typeof crossFilter.value === "object") {
  patch[`${crossFilter.field}__gte`] = crossFilter.value.from;
  patch[`${crossFilter.field}__lte`] = crossFilter.value.to;
} else patch[crossFilter.field] = crossFilter.value;
```

Réutilise les suffixes `__gte`/`__lte` déjà supportés côté core par 14b
(`features/repository.py`, `analytics/aggregate.py`) — aucun changement
serveur. `sameCrossFilterValue` généralisé en comparaison JSON uniforme
(`typeof a === "string" && typeof b === "string" ? a === b : JSON.stringify(a) === JSON.stringify(b)`)
au lieu du cas spécial tableau actuel, pour couvrir aussi la plage.

**Nouveau setter `clearCrossFilter(datasetId: string): void`** dans
`AnalyticsContextProvider` (même garde `if (!active) return`) — supprime
directement l'entrée, sans passer par la logique de toggle. Deux
consommateurs :

1. Le select multi-valeurs qui repasse à zéro coché : appeler
   `setCrossFilter(datasetId, field, [], widgetId)` enverrait
   `field__in=""` au serveur (une valeur, pas « aucun filtre » — bug
   silencieux). `clearCrossFilter` évite complètement ce cas.
2. Le bouton `×` par chip de l'indicateur (§5).

Aucun changement à la sérialisation URL (`AppRuntimePage`, 14b) : elle
encode/décode `AnalyticsContextState` en bloc, agnostique de la forme de
`CrossFilterEntry.value` — la plage traverse l'aller-retour JSON sans code
dédié. Un cas de test round-trip supplémentaire suffit (§6).

## 3. Widgets `selectFilter` et `sliderFilter`

Même schéma de props et de `PropsPanel` que `chart.tsx` (précédent direct,
`categoryField` y est déjà un champ texte libre — pas de nouveau composant
de sélection de schéma introduit ici) :

```ts
defaultProps: { dataSourceId: "", field: "", label: "" }
```

`PropsPanel` : `<DataSourceSelect>` existant (choix parmi les
`dataSources` de l'app — l'auteur pointe vers une source qui alimente déjà
un chart/table/carte du dataset visé, typiquement déjà « promue » en
dataset partagé depuis 14a) + un input texte « Champ » + un input texte
« Libellé ». Aucune source dédiée à créer pour le filtre : contrairement à
une configuration de source « statistiques » (qui exigerait de retaper à la
main `groupBy`/`measures` dans `DataSourcePanel`), l'auteur réutilise une
source qu'il a déjà.

**Résolution à l'exécution.** Le `Component` lit `ctx.data.datasetId`
(fourni par `DataProvider`/`WidgetHost` comme pour n'importe quel widget lié
à `dataSourceId` — cf. `data.tsx`/`chart.tsx`) puis appelle **lui-même**
`client.queryDataSource(...)` avec une source synthétique — précédent direct
côté widgets qui appellent le client hors du pipeline `DataProvider` :
`form.tsx`, `gallery.tsx`, `datasetCard.tsx` font déjà ça. `queryDataSource`
résout `datasetId → collectionId` en interne (`resolveDataset`, vérifié dans
le code de 14a) : le widget n'a jamais besoin de connaître l'id de
collection.

**`selectFilter`** :
```ts
client.queryDataSource({
  id: `analytics-filter-${ctx.widgetId}`, type: "statistics", service: "core",
  layer: "", datasetId, query: { groupBy: field },
});
```
Réponse = une ligne par valeur distincte (`id` = valeur, `properties.value`
= comptage, forme déjà produite par `buildAggregateBody`/`queryDataSource`
pour toute source `statistics`). Rendu : liste de cases à cocher. Toute
case cochée/décochée recalcule le tableau complet des valeurs cochées et
appelle `useSetCrossFilter(datasetId, field, valeurs, widgetId)` ; tableau
vide → `clearCrossFilter(datasetId)` (§2).

**`sliderFilter`** :
```ts
client.queryDataSource({
  id: `analytics-filter-${ctx.widgetId}`, type: "statistics", service: "core",
  layer: "", datasetId,
  query: { measures: [{ field, agg: "min", label: "min" }, { field, agg: "max", label: "max" }] },
});
```
Réponse = une ligne unique `{min, max}` (§1). Rendu : deux poignées bornées
par `[min, max]`. Relâcher une poignée appelle
`useSetCrossFilter(datasetId, field, { from, to }, widgetId)` ; revenir
exactement sur `[min, max]` (pas de filtrage réel) appelle
`clearCrossFilter(datasetId)` plutôt que d'écrire une plage inutile.

**Champ inconnu ou non numérique.** Mêmes erreurs qu'aujourd'hui
(`UnknownAggregateField` 422 pour un champ inconnu ; `TRY_CAST(... AS
DOUBLE)` déjà défensif côté core pour `min`/`max` sur un champ texte —
renvoie `NULL`/`0` selon la ligne, pas un crash). Le widget affiche un état
vide/erreur, même pattern que `DataSourceState.error` existant.

Les deux widgets sont des **no-op silencieux** hors mode `interactions:
"auto"` — même garde que tous les setters `AnalyticsContext` depuis 14b
(`active` check dans le provider) : aucune branche conditionnelle
supplémentaire à maintenir dans le widget lui-même.

## 4. Réutilisation vs. 14b — ce qui ne change pas

- `dateRangeFilter` (14b) reste inchangé : un contrôle global, sans
  `dataSourceId`, pour piloter `timeRange`.
- Chart/table/carte (14b) : cross-filter par clic, inchangé. Le select
  multi-valeurs est le premier consommateur réel de `crossFilter.value:
  string[]` en écriture directe (jusqu'ici seul `derivePatch` en lecture
  l'utilisait, câblé mais jamais exercé par un widget — aucun câblage
  chart/table n'écrit de tableau aujourd'hui).
- CEL (`ctx.crossFilter`) : la nouvelle forme `{from, to}` d'une entrée est
  visible telle quelle dans les expressions (`ctx.crossFilter[datasetId]
  .value`), sans transformation — cohérent avec l'additivité du modèle.

## 5. Indicateur de contexte actif

Nouveau `shell/src/builder/AnalyticsContextIndicator.tsx`, monté dans
`AppRenderer.tsx` à côté de `AnalyticsContextProvider` (avant `GridCanvas`),
actif seulement quand `mode !== "edit"` **et** `config.interactions ===
"auto"` (mêmes conditions que le reste de l'auto-mode 14b — l'édition ne
déclenche jamais d'interaction live).

Une barre de chips, une par dimension active dans `AnalyticsContextState` :

- `timeRange` non nul → « Période : {from} → {to} », `×` appelle
  `setTimeRange(null)`.
- `extent` non nul → « Emprise carte active », `×` appelle `setExtent(null)`.
- chaque entrée de `crossFilter` → « {field} : {valeur formatée} » (tableau
  → jointure virgule ; plage → `{from} → {to}` ; scalaire → tel quel), `×`
  appelle `clearCrossFilter(datasetId)`.
- Bouton « Tout effacer » visible seulement si 2+ chips actives — appelle
  les trois primitives ci-dessus sur tout l'état courant.
- Contexte entièrement vide → l'indicateur ne rend rien (pas de barre vide).

Pas de dépendance à `DataContext`/`datasets` : l'indicateur ne consomme que
`useAnalyticsContext()` et les setters déjà exportés par
`AnalyticsContext.tsx` (§2).

## 6. Tests & risques

**Core.** Aucun (aucun changement core dans ce plan).

**Shell (unitaires).**
- `analyticsPatch.test.ts` : nouvelle branche plage (`{from,to}` →
  `__gte`/`__lte`), non-régression des deux branches existantes.
- `AnalyticsContext.test.tsx` : `clearCrossFilter` supprime l'entrée sans
  passer par le toggle ; `sameCrossFilterValue` généralisée (scalaire,
  tableau, plage) ; no-op strict hors mode `auto` pour le nouveau setter ;
  round-trip URL avec une entrée en forme plage.
- `selectFilter.test.tsx` : options construites depuis une réponse
  `queryDataSource` mockée ; cocher/décocher écrit le tableau complet ;
  revenir à zéro coché appelle `clearCrossFilter`, jamais `setCrossFilter`
  avec un tableau vide.
- `sliderFilter.test.tsx` : bornes lues depuis `{min,max}` mocké ; relâcher
  une poignée écrit `{from,to}` ; revenir exactement sur `[min,max]` appelle
  `clearCrossFilter`.
- `AnalyticsContextIndicator.test.tsx` : une chip par dimension active,
  rendu vide sans contexte, `×` isolé par dimension, « Tout effacer »
  seulement si 2+ chips, jamais rendu si `interactions !== "auto"`.

**E2E** (étend `analytics-context.spec.ts`, calqué sur les scénarios 14b) :
1. Select multi-valeurs : cocher deux valeurs filtre une table liée au même
   dataset (`__in`) ; tout décocher restaure la table complète.
2. Slider : glisser une poignée filtre par plage (`__gte`/`__lte`) ; revenir
   sur les bornes complètes restaure les données non filtrées.
3. Indicateur : poser un cross-filter (clic chart) + une période (widget
   date-range) → deux chips visibles ; `×` sur une seule l'efface sans
   toucher l'autre ; « Tout effacer » vide tout.
4. **Non-régression explicite** : une app `interactions: "manual"` avec les
   mêmes widgets n'affiche jamais l'indicateur et un clic/une sélection sur
   select/slider ne déclenche aucun filtrage.

| Risque | Garde-fou |
|---|---|
| Options de select / bornes de slider non réduites par le contexte actif | Limitation documentée v1 (§1) ; améliorable sans changement de modèle (les widgets liraient `datasets[datasetId]` en plus, comme `derivePatch` le fait déjà pour les autres sources) |
| Champ non numérique choisi pour le slider | `TRY_CAST(...AS DOUBLE)` déjà défensif côté core (repli `0`/`NULL`, pas de crash) ; widget affiche un état vide plutôt qu'un plantage |
| Champ inconnu (texte libre, même risque que `categoryField` de chart) | Même 422 `UnknownAggregateField` qu'aujourd'hui, état d'erreur du widget |
| Multi-select revenant à zéro coché | Résolu explicitement par `clearCrossFilter` plutôt qu'un tableau vide (§2) |
| Chips de l'indicateur en noms de colonne bruts, pas les libellés métier du dataset | Limitation v1 assumée (§1), pas de plomberie `datasets` supplémentaire hors `DataContext` |
| Widget select/slider pointé vers une source sans `datasetId` | `ctx.data.datasetId` absent → widget affiche un état vide explicite (« liez ce filtre à une source dataset »), pas une requête qui échoue silencieusement |
