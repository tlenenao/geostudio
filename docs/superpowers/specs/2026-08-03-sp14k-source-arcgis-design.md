# SP-14k — Source `arcgis` : référencer une couche ArcGIS Feature Service en direct (design)

> **Date : 2026-08-03 · Statut : validé (brainstorm)**
> Onzième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot**, **SP-14h — Carte analytique**,
> **SP-14i — SQL Lab** et **SP-14j — Conteneurs**. Traite un des éléments
> encore listés « hors périmètre » par 14j (« requête visuelle, source
> `arcgis`, MCP analytique — sous-parties SP-14 ultérieures (14k…) ») :
> **source `arcgis`**, « référencement d'un Feature Service comme source de
> dataset (la partie moissonnage/copie reste en SP-12) » (feuille de route
> §SP-14). MCP analytique reste hors périmètre — sous-partie SP-14 ultérieure
> (14l…). **Requête visuelle** reste également hors périmètre : elle dépend
> du moteur de pipeline livré par **SP-15** (A39, ETL no-code), qui n'existe
> pas encore (aucune spec/plan SP-15 au dépôt à ce jour) — traitée après
> SP-15, pas comme prochaine sous-partie SP-14.

## 1. Objectif & non-buts

**Objectif.** Aujourd'hui un `Dataset` (SP-14a) ne peut référencer qu'une
collection locale (`source: "collection"`, passthrough vers
`/collections/{id}/items|aggregate`, PostGIS). SP-14k ajoute une deuxième
variante `source: "arcgis"` : le dataset pointe vers une couche d'un
ArcGIS Feature Service **déjà moissonnée en mode référence** (connecteur
`ArcgisConnector`, SP-12d) et interroge cette couche **en direct** à chaque
requête — sans jamais copier ses entités dans une collection locale. C'est
le complément exact du mode `copy` de SP-12 (qui, lui, matérialise une
collection locale et rend le dataset consommable via `source: "collection"`
sans aucun changement) : SP-14k couvre le cas où l'auteur veut rester
synchronisé avec la source distante plutôt que de figer une copie.

**Constat clé qui cadre l'approche.** `/collections/{id}/aggregate`
n'interroge pas Postgres : il lit le **GeoParquet CDC du lakehouse SP-11**
via DuckDB (`run_collection_aggregate`). Un dataset `arcgis` n'a par
construction aucune copie GeoParquet — le mode `copy` de SP-12 existe
justement pour produire cette copie quand elle est voulue. L'agrégation
d'une source `arcgis` ne peut donc pas réutiliser `run_collection_aggregate` :
elle demande une traduction indépendante vers l'API de statistiques native
d'ArcGIS REST (`outStatistics`/`groupByFieldsForStatistics`), avec une
parité nécessairement partielle (§4).

**Non-buts explicites** (reportés ou exclus) :

- **Copie/matérialisation locale.** Reste le mode `copy` de SP-12,
  inchangé ; SP-14k ne duplique pas ce chemin.
- **Authentification ArcGIS (token/OAuth).** Services publics uniquement,
  même posture que le connecteur SP-12d (documentée comme résiduelle dans
  `CLAUDE.md`) — cohérence plutôt que résoudre ce chantier ici.
- **`bucket` (histogramme temporel) et `split` (pivot deux dimensions) pour
  une source `arcgis`.** Pas d'équivalent direct côté API statistiques
  ArcGIS REST ; les reconstruire demanderait de rapatrier les entités brutes
  côté cœur pour agréger nous-mêmes, ce qui annule l'intérêt d'une
  agrégation serveur distante et peut être coûteux sur une grande couche.
  Rejet explicite avec une erreur 400 plutôt qu'un silence trompeur.
- **Saisie libre d'une URL de couche dans `DatasetEditPage`.** Le seul point
  d'entrée est le catalogue d'items déjà moissonnés en mode référence
  (flux SP-12d existant, inchangé) — pas de second flux de saisie d'URL en
  parallèle du moissonnage.
- **Écriture vers ArcGIS.** Lecture seule, comme le reste du module
  `harvest`.
- **Cache partagé entre workers/replicas (Redis).** Hors périmètre depuis
  la sortie de Redis (jalon M1) ; cache TTL en mémoire, par worker
  uniquement (§4).
- **Requête visuelle, MCP analytique.** Sous-parties SP-14 ultérieures (cf.
  en-tête).

Le modèle reste additif : rien ici ne doit devoir être défait pour les
sous-parties suivantes, et les 82+ specs E2E existantes restent vertes sans
modification (aucun dataset existant n'a `source: "arcgis"`).

## 2. Modèle de données

**`DatasetPayload`** (`core/app/configs/schemas.py`, additif à SP-14a/b) :

```python
class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None   # requis si source == "collection"
    arcgisItemId: str | None = None   # requis si source == "arcgis"
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None
    reactsToExtent: bool = False
```

Validateur additif (même patron que la validation `collectionId` de SP-14a
§4) : exactement un des deux identifiants renseigné selon `source`, l'autre
`None`. Aucune config existante n'est affectée — `source` est déjà un champ
requis sans défaut depuis SP-14a, donc toute config `kind="dataset"`
existante porte déjà explicitement `"collection"`.

`arcgisItemId` référence un `Item` de `resource_type="external"` créé par le
moissonnage SP-12d en `mode="reference"` — pas une nouvelle notion, le
catalogue d'items moissonnés existe déjà.

**Shell** (`shell/src/api/types.ts`, `DatasetConfig`) : même extension
miroir (`source: "collection" | "arcgis"`, `arcgisItemId?: string`).

## 3. Catalogue — repérer une couche ArcGIS déjà moissonnée

`repo.list_layer_records` (`core/app/harvest/repository.py:118-129`) filtre
aujourd'hui `HarvestRecord.tiles_url.is_not(None)` — il exclut donc
silencieusement toutes les couches `layer_kind="feature"` (ArcGIS, WFS en
référence), qui n'ont jamais de `tiles_url`. `GET /harvest/layers` ne peut
donc pas servir tel quel de picker pour SP-14k.

Ajout symétrique : `list_feature_layer_records` (même requête, filtrée
`HarvestRecord.layer_kind == "feature"`, retourne `item_id`, `title`,
`items_url` au lieu de `tiles_url`), exposée par une nouvelle route
`GET /harvest/feature-layers?q=` (même garde `can()` par item que
`/harvest/layers`). Réponse : `{"layers": [{"id", "title", "itemsUrl"}]}`.

Prérequis opérationnel (inchangé, déjà livré) : un admin crée une
`HarvestSource` `type="arcgis"`, `mode="reference"` pointant la racine du
`FeatureServer` — chaque couche devient un item `external` distinct,
rafraîchi par le job de moissonnage planifié existant (SP-12). SP-14k ne
touche pas à ce flux, il consomme seulement son résultat.

## 4. Core — proxy de requête live

Nouveau module `core/app/harvest/live_query.py` (reste dans `harvest/` —
réutilise l'`ArcgisConnector`, l'egress guard SP-12d, `HarvestRecord` ;
un module `core/app/datasets/` séparé resterait de la sur-ingénierie, même
raisonnement que SP-14a §3).

- `resolve_arcgis_source(session, tenant_id, item_id)` → l'`external_url`
  de la couche (lookup `HarvestRecord` par `item_id`) ; 404 si l'item
  n'existe pas ou n'est pas une couche feature ArcGIS moissonnée.
- `translate_features_query(filters, bbox, limit, offset)` → paramètres
  ArcGIS (`where=`, `geometry=`/`geometryType=esriGeometryEnvelope`/
  `inSR=4326`/`spatialRel=esriSpatialRelIntersects` pour `bbox`,
  `resultRecordCount`/`resultOffset`, `f=geojson`). Réutilise le
  vocabulaire de filtre `__gte`/`__lte`/`__in` introduit en SP-14b (mêmes
  clés que pour une source `collection`, pas un second langage de filtre à
  apprendre pour l'auteur).
- `translate_aggregate_query(groupBy, measures, filters, bbox)` →
  `groupByFieldsForStatistics` (liste de champs, y compris plusieurs —
  ArcGIS le supporte nativement, à la différence de `bucket`/`split`) et
  `outStatistics` (mappe `agg: count/sum/avg/min/max`, qui correspondent
  déjà 1:1 aux `statisticType` ArcGIS de même nom). Rejette `bucket`/
  `split`/`bins` avec une erreur 400 explicite (§1).
- Réponses traduites vers le **même contrat** que les endpoints
  `collection` : `FeatureCollection` (`type`, `features`, `numberMatched`,
  `numberReturned`, `links`) pour les features (ArcGIS `f=geojson` produit
  déjà un GeoJSON proche, reformaté aux clés attendues) ; `{categoryKey,
  rows}` pour l'agrégat (les `attributes` de chaque entrée `features[]` de
  la réponse `f=json` à statistiques sont reformatés en lignes `{champ de
  groupe: valeur, libellé de mesure: valeur}`, même forme que celle produite
  par `run_collection_aggregate` pour le cas groupBy simple/multiple sans
  `split`/`bucket`/`bins`). Le shell ne voit aucune différence de forme
  entre les deux sources.
- **Cache TTL en mémoire** (~20 s, clé = URL + paramètres traduits) : dict
  module-level avec expiration par horodatage, pas de nouvelle dépendance.
  Limite connue et acceptée : non partagé entre workers/replicas — réduit
  le martèlement au sein d'un worker, en complément (pas en remplacement)
  du debounce déjà côté shell (SP-14b, ~500 ms sur emprise/URL).
- Toutes les requêtes sortantes passent par `build_guarded_client()`
  (`core/app/harvest/egress.py`, déjà utilisé par `ArcgisConnector.fetch`)
  — aucune nouvelle surface d'egress à garder, le résiduel DNS-rebinding
  TOCTOU documenté reste inchangé et hors périmètre ici.

**Nouvelles routes** (`core/app/harvest/routes.py`, à côté de
`/harvest/layers`) :

- `GET /datasets/{itemId}/arcgis/items` (features) — mêmes query params que
  `/collections/{id}/items` (`limit`, `offset`, `bbox`, filtres en query
  string).
- `POST /datasets/{itemId}/arcgis/aggregate` — même corps
  (`AggregateRequestBody`) que `/collections/{id}/aggregate`, avec
  `bucket`/`split`/`bins` rejetés si renseignés.

**Pourquoi pas généraliser `/collections/{id}/*` directement** (option
écartée) : le module `features/routes.py` se déclare explicitement
« PostGIS-only » en tête de fichier, et `aggregate.py` est câblé sur
DuckDB/GeoParquet — y injecter une branche ArcGIS toucherait le chemin
chaud de tous les widgets existants pour un bénéfice nul, puisque le shell
distingue de toute façon la source au niveau de `resolveDataset()` (§5).
Rester additif, comme 14a→14j.

## 5. Shell — câblage

- `DatasetEditPage` gagne un sélecteur de type de source
  (« Collection » / « ArcGIS Feature Service »). Pour `arcgis`, une liste
  déroulante alimentée par un nouveau hook `useFeatureLayers()` (miroir de
  `useLayerSources`), listant les couches déjà moissonnées via
  `GET /harvest/feature-layers`. Pas de nouveau flux de gestion des sources
  de moissonnage — un lien renvoie vers l'écran d'admin existant si aucune
  couche n'apparaît.
- `resolveDataset()` (`itemClient.ts:187-210`) inchangé dans sa forme :
  résout toujours le `DatasetConfig` complet, avec son nouveau champ
  `source`.
- `queryDataSource`/`featuresUrl` (`itemClient.ts:651-682`) branchent sur
  `resolveDataset().source` : `"collection"` → chemin actuel inchangé (aucun
  widget existant ne change de comportement) ; `"arcgis"` → nouveau chemin
  vers `/datasets/{arcgisItemId}/arcgis/items|aggregate`. Un seul point de
  branchement, pas de duplication dans chaque widget consommateur
  (chart/table/indicator/pivot/carte réutilisent tous `queryDataSource`).
- Contexte analytique global (SP-14b) : `timeField`/`reactsToExtent`
  s'appliquent tels quels — `derivePatch` produit le même
  `{champ__gte/__lte}`/`{bbox}` indépendamment de la source, traduits par
  `translate_features_query`/`translate_aggregate_query` côté cœur. Aucun
  changement à `AnalyticsContext.tsx`.

## 6. Permissions

Même double vérification que SP-14a §5 (lire le *dataset* est indépendant
de lire les *données*), transposée : lire le dataset passe par `can()`
comme tout item ; **avant** de résoudre `arcgisItemId` en `external_url`,
`resolve_arcgis_source` revérifie indépendamment que l'item `external`
sous-jacent est lisible par l'utilisateur (même pattern que
`get_readable_collection` pour une source `collection`). Un dataset partagé
plus largement que l'item moissonné qu'il référence ne donne donc jamais
accès aux données distantes, seulement à la référence.

## 7. Compatibilité & tests

Compatibilité : `source` déjà requis sans défaut depuis SP-14a → aucune
config existante affectée par l'ajout du littéral `"arcgis"`. Nouveau champ
`arcgisItemId` additif optionnel.

**Core (unitaires)** :
- `translate_features_query` : mapping filtre `__gte/__lte/__in` → `where`,
  bbox → `geometry`/`geometryType`, pagination → `resultOffset`/
  `resultRecordCount`.
- `translate_aggregate_query` : mapping `groupBy` (simple et multiple) +
  `measures` → `groupByFieldsForStatistics`/`outStatistics` ; `bucket`/
  `split`/`bins` → 400 explicite.
- Cache : hit/miss selon clé et expiration TTL (horloge injectée en test).
- Permissions : dataset lisible mais item `external` sous-jacent non
  lisible → 403, pas de fuite de l'`external_url`.
- Egress : cible bloquée (interne/privée) → erreur propre, pas de requête
  sortante (réutilise les tests existants du garde SP-12d comme patron).

**Shell (unitaires)** : `DatasetEditPage` bascule de source (rendu
conditionnel du picker) ; `queryDataSource`/`featuresUrl` routent vers le
bon chemin selon `resolveDataset().source` (mock des deux résolutions).

**E2E nouvelle** (calquée sur les specs `harvest`/`datasets-shared`
existantes, ArcGIS distant mocké via un serveur HTTP local de test comme
dans les tests du connecteur SP-12d) : créer une source de moissonnage
`arcgis` en mode référence → la couche apparaît dans le picker
`DatasetEditPage` → créer un dataset `source: "arcgis"` → un widget table
lié via `datasetId` affiche les entités distantes → un widget indicateur
avec `groupBy` affiche une statistique agrégée traduite.

## 8. Risques

| Risque | Garde-fou |
|---|---|
| Traduction de filtre approximative (les valeurs sont quotées génériquement sans connaître le type réel de colonne, faute de schéma stocké côté harvest) | Couvre le cas majoritaire (la couche de coercition SQL d'Esri accepte un littéral quoté même sur un champ numérique sur la quasi-totalité des back-ends) ; échec propre (erreur amont, pas de crash) sur un serveur exotique — même sévérité qu'un filtre invalide aujourd'hui |
| `bucket`/`split`/`bins` demandés sur une source `arcgis` | 400 explicite plutôt qu'un résultat silencieusement incomplet |
| Cache TTL non partagé entre workers/replicas | Fraîcheur bornée à ~20 s par worker au pire cas, pas un risque de martèlement au-delà du debounce shell déjà en place (SP-14b) |
| Couche ArcGIS renommée/supprimée côté distant entre deux cycles de moissonnage | Le job planifié SP-12 rafraîchit périodiquement `external_url`/`layer_kind` ; entre deux cycles, la requête live échoue proprement (état `error` du widget, comme un `timeField` invalide en 14b) — pas de nouveau mode de panne |
| DNS-rebinding TOCTOU résiduel sur l'egress guard | Déjà documenté (`CLAUDE.md`), non spécifique à SP-14k, hors périmètre ici |
| Sur-ingénierie prématurée (auth token, cache partagé, parité `bucket`/`split`) | Explicitement hors périmètre (§1) ; le modèle reste additif pour une sous-partie ultérieure si le besoin émerge |
