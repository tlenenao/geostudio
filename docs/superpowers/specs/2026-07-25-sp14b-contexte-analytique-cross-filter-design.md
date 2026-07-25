# SP-14b — Contexte analytique global & cross-filter (design)

> **Date : 2026-07-25 · Statut : validé (brainstorm)**
> Deuxième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**. Couvre les quatre dimensions du
> « contexte analytique global » (temps × emprise × filtres × sélection) et le
> cross-filter par défaut, dans un seul plan. La « requête visuelle » (Filtrer
> → Joindre → Résumer → Trier) reste hors périmètre : elle dépend du moteur de
> pipeline livré par **SP-15** (A39), qui n'existe pas encore.

## 1. Objectif & non-buts

**Objectif.** Un dashboard où les widgets réagissent les uns aux autres et à
l'environnement (temps, emprise carte) sans câblage manuel : cliquer sur une
barre de chart filtre les autres widgets du même dataset ; déplacer la carte
rafraîchit les datasets qui l'ont demandé ; une plage de dates filtre tous les
datasets temporels de l'app ; l'état courant se partage par lien. Concrètement
les critères d'acceptation SP-14 visés ici : « un clic sur une barre filtre le
dashboard entier » et une partie de « l'état sérialisable dans l'URL ».

**Non-buts explicites** (reportés, pour ne pas fermer la porte mais ne pas les
construire ici) :

- Filtres typés dédiés select/slider (seul un widget **date-range** est livré
  en 14b, pour piloter manuellement la dimension temps) → **SP-14c**.
- Panneau « voir les entités » (drill table+carte détaillée d'une sélection) →
  **SP-14d** (widgets analytiques), avec le menu « explorer ».
- Cross-filter entre **datasets différents** (ex. par correspondance de nom de
  colonne) — seul le cross-filter entre widgets du **même dataset** est
  couvert ; le cas inter-datasets attend une modélisation des relations entre
  collections (proche du travail de jointure de SP-15).
- Cross-filter multi-valeurs (accumulation ctrl-click) — v1 : une valeur
  active par dataset, un second clic sur la même valeur l'efface (toggle).
- Mise en évidence visuelle du widget qui a émis le clic (highlight) — le
  widget d'origine n'est pas filtré par son propre clic, mais n'affiche pas
  non plus de style « sélectionné » dédié.
- Bookmarks nommés persistés côté serveur (« situations » cataloguées) — seule
  l'URL du navigateur porte l'état en v1, pas de nouvel objet de plateforme.
- Requête visuelle, SQL Lab, source `arcgis` pour dataset, MCP analytique —
  sous-parties suivantes de SP-14, non traitées ici.

Le modèle reste additif : `interactions` absent du config existant se comporte
comme `"manual"` (comportement actuel inchangé), les 13+ specs E2E existantes
restent vertes sans modification.

## 2. Modèle de données

**Dataset** (`core/app/configs/schemas.py`, additif à `DatasetPayload` de
SP-14a) :

```python
class DatasetPayload(BaseModel):
    source: Literal["collection"]
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte
```

Aucune validation serveur stricte de `timeField` contre le schéma de la
collection (même posture que `columns`, qui n'est déjà pas validé contre le
schéma réel — cf. SP-14a §3). Validation *avisée* côté shell dans
`DatasetEditPage`, qui gagne deux contrôles à côté du tableau de colonnes
existant : une liste déroulante « colonne temporelle » (alimentée par le
schéma fusionné, valeur vide = pas de contexte temporel pour ce dataset) et
une case à cocher « réagir au déplacement de la carte » (A29). Si `timeField`
référence une colonne devenue inexistante, la requête réelle échoue
proprement (§7, table des risques) — pas un nouveau mode de panne.

**`AppConfig`** (`shell/src/api/types.ts`), additif, même patron que
`navigationMode` (SP-13a) :

```ts
export type AppConfig = {
  // ... inchangé
  interactions?: "auto" | "manual"; // absent = "manual"
};
```

Une app **nouvellement créée** reçoit `interactions: "auto"` par défaut
(point d'insertion : `itemClient.ts:269`, même endroit que le défaut actuel de
`navigationMode`). Une app existante ouverte sans ce champ reste `"manual"` :
aucun comportement automatique nouveau tant que l'auteur ne l'active pas
explicitement (garde-fou roadmap §8, A27 : « le cross-filter qui surprend »).

## 3. Core — nouveaux opérateurs de filtre

Aujourd'hui, `_collect_filters`/`_where` (`core/app/features/repository.py`)
et le parsing `filters`/`_build_where` (`core/app/analytics/aggregate.py`) ne
supportent que l'égalité stricte (`champ = valeur`). Le contexte temporel
(bornes) et la sélection multi-id (`__in`) ont besoin de plus — extension
**symétrique** dans les deux modules, par suffixe sur la clé du filtre :

- `champ__gte` / `champ__lte` → `>=` / `<=`.
- `champ__in` → `IN (...)`, valeur = liste séparée par virgules.
- `champ` (sans suffixe) → comportement actuel inchangé.

Réutilise la coercion de type existante par colonne (`_coerce`) après avoir
retiré le suffixe pour le lookup de colonne ; les colonnes date/datetime
passent déjà en texte brut casé implicitement par Postgres/DuckDB, donc
`__gte`/`__lte` sur une colonne temporelle ne demande aucune nouvelle
coercion. Nom de colonne inconnu (suffixe retiré) → même erreur 422 qu'aujourd'hui
(`FilterError`/`UnknownAggregateField`). Aucun changement de paramétrage SQL
(toujours des requêtes préparées) — pas de nouvelle surface d'injection.

Correction incidente notée pendant l'exploration : côté `statistics`
(`buildAggregateBody` dans `itemClient.ts`), une clé `bbox` posée dans
`DataSource.query` est aujourd'hui absorbée à tort dans `body.filters` au lieu
du champ top-level `body.bbox` attendu par le serveur. Traitée en même temps
que le câblage de l'emprise (§5) puisque c'est le premier consommateur réel de
`bbox` sur ce chemin.

## 4. Shell — `AnalyticsContextProvider`

Nouveau `shell/src/builder/AnalyticsContext.tsx`, monté dans `AppRenderer`
entre `VariablesProvider` et `DataProvider` (un provider de plus dans la
chaîne déjà app-scopée, cf. exploration §1) :

```ts
type AnalyticsContextState = {
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null; // bbox
  crossFilter: Record<string /* datasetId */, {
    field: string; value: string | string[]; originWidgetId: string;
  } | undefined>;
};
```

- `useAnalyticsContext()` — lecture.
- `useSetTimeRange()`, `useSetExtent()`,
  `useSetCrossFilter(datasetId, field, value, originWidgetId)` — écriture.
  `setCrossFilter` avec la même `(field, value)` déjà active efface l'entrée
  (toggle off) ; une valeur différente la remplace.
- Tous les setters sont des **no-op silencieux** quand
  `config.interactions !== "auto"` : une app migrée reste identique même si un
  widget appelle ces hooks (aucune branche conditionnelle dispersée dans
  chaque widget à maintenir).

**Branchement dans `DataContext.tsx`** — la fonction qui construit `merged`
gagne une couche intermédiaire, entre la query de base et le `filters`
manuel déjà existant (qui garde la priorité) :

```ts
const contextPatch = derivePatch(source, analyticsCtx); // {} si source sans datasetId
const merged = {
  ...s,
  query: { ...s.query, ...contextPatch, ...(filters[sourceId] ?? {}) },
};
```

`derivePatch(source, ctx)` résout le dataset de la source (même cache que
`resolveDataset`) et n'agit que si `source.datasetId` est défini :

- `timeRange` + dataset `.timeField` → `{ [timeField+"__gte"]: from, [timeField+"__lte"]: to }`.
- `extent` + dataset `.reactsToExtent` → `{ bbox: "minx,miny,maxx,maxy" }`.
- `crossFilter[datasetId]` présent et `originWidgetId !== ctx.widgetId` →
  `{ [field]: value }` (ou `field+"__in"` si `value` est un tableau).

Sources inline (sans `datasetId`) : `derivePatch` retourne toujours `{}` —
comportement byte-identique à aujourd'hui, `data-widget.spec.ts`/`chart.spec.ts`
restent verts sans modification.

## 5. Câblage par widget

**Chart** (`chart.tsx` + `EChart.tsx`) : `EChart.tsx` gagne un prop
`onClick?: (params) => void` forwardé à l'event `click` d'ECharts. `chart.tsx`
déclare `events: ["categorySelected"]` (visible dans `ActionsPanel` comme les
autres événements) **et**, si `interactions === "auto"`, appelle directement
`useSetCrossFilter(datasetId, categoryField, clickedValue, widgetId)`. Les
deux canaux coexistent : le clic émet toujours sur le bus (câblage manuel
additionnel possible) et alimente le contexte automatiquement en mode `auto`.

**Table** (`data.tsx`) : le clic de ligne émet déjà `itemSelected` sur le bus.
Ajout : en mode `auto`, appelle aussi
`useSetCrossFilter(datasetId, pkColumn, rowId, widgetId)`.

**Carte** (`mapWidget.tsx` / `MapView.tsx`) :
- `MapView.onViewChange` gagne le bbox (`map.getBounds().toArray()`), en plus
  de `center`/`zoom` déjà consommés par `flyTo` — ajout additif, ne casse rien.
- Sur `extentChanged`, en mode `auto`, appelle `useSetExtent(bbox)` ;
  **debounce ~500 ms interne au provider** (pas au widget) pour absorber les
  `moveend` rapprochés d'un pan/zoom continu.
- Clic sur une feature (déjà câblé à `itemSelected`) alimente en plus
  `useSetCrossFilter(datasetId, pkColumn, featureId, widgetId)` en mode `auto`.

**Nouveau widget `dateRangeFilter`**
(`shell/src/builder/widgets/dateRangeFilter.tsx`) : deux sélecteurs de date,
écrit directement `useSetTimeRange({from, to})`. Contrairement à `filter.tsx`
(qui cible une `DataSource` précise via le bus), ce widget n'est lié à aucune
source — c'est un contrôle global, sans `events`/`actions` bus.

**CEL** (`shell/src/builder/expr.ts`) : `ExprContext` gagne une clé additive
`ctx?: { timeRange, extent, crossFilter }`, distincte de `vars` (pas de risque
de collision avec une variable d'app du même nom). Construite dans
`WidgetHost.tsx`/`ActionConditionBridge` à partir de `useAnalyticsContext()`,
à côté de l'`exprCtx` déjà assemblé. `configExpressionErrors.ts` étendu pour
reconnaître ce nouveau préfixe dans le lint de validation à la sauvegarde.

## 6. Sérialisation URL

Un unique query param opaque sur la route runtime existante
(`/apps/:pk/:pageId?`), sans toucher au segment `:pageId` :

```
/apps/:pk/:pageId?ctx=<base64url(JSON.stringify({timeRange, extent, crossFilter}))>
```

Choix d'un blob unique plutôt que d'exploser chaque dimension en query params
séparés : une seule fonction encode/decode, pas de schéma de clés à
maintenir, pas de collision possible avec un futur usage de query params.
Contrepartie assumée : URL non éditable à la main (objectif = partage de
lien, pas API d'URL).

- Lecture au montage d'`AppRuntimePage` (`useSearchParams`, premier usage de
  ce hook dans le shell) → hydrate l'état initial du provider.
- Écriture : à chaque changement de contexte, `setSearchParams(..., { replace: true })`
  (jamais `push`, pour ne pas empiler une entrée d'historique par clic),
  débounce ~500 ms partagé avec celui de l'emprise.
- Actif uniquement en mode `runtime` (pas `edit`/`preview`).
- `ctx` absent ou non parseable → contexte vide, comportement identique à
  aujourd'hui ; n'importe quelle app existante ouverte sans ce paramètre n'est
  jamais affectée.

## 7. Tests & risques

**Core** : cas unitaires `__gte`/`__lte`/`__in` (features + aggregate) sur
colonne valide, suffixe sur colonne inconnue (422 identique au cas actuel),
valeur non parseable.

**Shell (unitaires)** : `derivePatch` en fonction pure (même style que
`mergeDatasetSchema` de SP-14a) — bbox si `reactsToExtent`, bornes si
`timeField`, cross-filter exclu pour le widget d'origine, `{}` sans
`datasetId`. `AnalyticsContextProvider` : toggle du cross-filter, no-op strict
hors mode `auto`. Encodage/décodage URL en aller-retour.

**E2E nouvelles** (calquées sur `actions.spec.ts`/`datasets-shared.spec.ts`) :
1. Cross-filter automatique : chart + table sur le même dataset, clic sur une
   barre filtre la table, second clic sur la même barre l'efface.
2. Réactivité à l'emprise : dataset `reactsToExtent=true`, déplacement de la
   carte → refetch après debounce.
3. Plage temporelle : widget date-range + dataset `timeField` → filtre le
   widget consommateur.
4. URL restaure l'état : poser un cross-filter, recharger avec l'URL
   capturée, vérifier sa réapplication.
5. **Non-régression explicite** : une app existante sans `interactions`
   (`"manual"`) avec les mêmes widgets ne déclenche **aucun** filtrage
   automatique au clic.

| Risque | Garde-fou |
|---|---|
| `timeField` pointe une colonne inexistante | Erreur 400 à la requête réelle → état `error` du widget existant, pas un nouveau mode de panne ; avertissement non bloquant à l'édition |
| Deux mécanismes de câblage cohabitent (bus manuel + contexte auto) | Le contexte auto ne synthétise jamais de `config.messages` — pas de mélange dans `ActionsPanel` |
| Plusieurs widgets carte dans une même app | Le dernier déplacement gagne (état global unique) — limitation documentée |
| Nouveaux opérateurs `__gte/__lte/__in` élargissent la surface de filtre | Même validation de colonne qu'aujourd'hui, requêtes toujours paramétrées |
| Cross-filter actif mais invisible pour l'utilisateur | Hors périmètre strict de 14b ; indicateur visuel à considérer en 14c |
| Sur-ingénierie prématurée (multi-select, cross-dataset, drill) | Explicitement hors périmètre (§1) ; le modèle reste additif pour 14c/14d |
