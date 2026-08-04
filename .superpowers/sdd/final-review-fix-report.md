# Rapport — corrections review finale SP-14k (source arcgis, référencement live)

Deux findings de la review finale de branche ont été corrigés, chacun dans son
propre commit.

## Finding 1 (Critical) — mismatch shell↔core sur le paramètre de chemin

**Cause racine confirmée** : la route cœur `GET/POST
/datasets/{item_id}/arcgis/items|aggregate` (`core/app/harvest/routes.py`,
`_resolve_arcgis_dataset`) attend l'`item_id` **du dataset lui-même**
(`get_config_by_item(session, item_id)` puis lecture de
`config.dataset.arcgisItemId` pour retrouver la couche moissonnée). Le shell
construisait cette même URL avec l'`arcgisItemId` (item de la couche
moissonnée) au lieu de l'`item_id` du dataset — chemin garanti 404 en
production puisqu'un item de couche moissonnée (`resource_type="external"`)
n'a pas de `Config` de type `dataset`.

### Changements — `shell/src/api/itemClient.ts`

- `buildArcgisItemsUrl` (ligne ~167) : paramètre renommé
  `arcgisItemId: string` → `datasetItemId: string` (clarté seule, la fonction
  reçoit désormais toujours l'item id du dataset).
- `featuresUrl` (lignes ~706-715) : condition simplifiée en
  `cached?.source === "arcgis"` (plus besoin de vérifier `arcgisItemId`) et
  appel corrigé en `buildArcgisItemsUrl(coreUrl, source.datasetId, source.query)`.
- `queryDataSource` (lignes ~717-728) : condition changée en
  `cachedDataset?.source === "arcgis" && source.datasetId` (narrowing
  TypeScript sur `source.datasetId`) ; URL d'agrégat corrigée en
  `` `/datasets/${source.datasetId}/arcgis/aggregate` `` ; URL de features
  corrigée en `buildArcgisItemsUrl(coreUrl, source.datasetId, source.query)`.
- Aucun autre point du fichier touché : `ResolvedDataset.arcgisItemId`,
  `getDatasetConfig`, `saveDatasetConfig`, `createDatasetItem`,
  `listFeatureLayers` restent inchangés (l'`arcgisItemId` y reste pertinent
  pour l'affichage/la config).

### Changements — `shell/src/api/itemClient.test.ts`

- Test `featuresUrl routes an arcgis-sourced dataset to
  /datasets/{datasetItemId}/arcgis/items` (titre corrigé) : assertion
  `toBe(...)` mise à jour de `/datasets/layer-9/arcgis/items` vers
  `/datasets/ds-arcgis-1/arcgis/items`.
- Test `queryDataSource fetches features from the arcgis proxy...` : mock
  `http.get` déplacé de `/datasets/layer-10/arcgis/items` vers
  `/datasets/ds-arcgis-2/arcgis/items`.
- Test `queryDataSource posts aggregate queries to the arcgis proxy...` :
  mock `http.post` déplacé de `/datasets/layer-11/arcgis/aggregate` vers
  `/datasets/ds-arcgis-3/arcgis/aggregate`.
- **Nouveau test** `featuresUrl keys the arcgis proxy URL on the dataset item
  id, not the arcgis layer id` : dataset `ds-999` avec
  `arcgisItemId: "totally-different-layer-id"`, assertion que l'URL générée
  est bien keyée sur `ds-999` — régression exacte du bug corrigé.
- Les autres tests arcgis (`getDatasetConfig`, `createDatasetItem`,
  `listFeatureLayers`) non touchés (hors du chemin concerné).

### Changements — `shell/e2e/dataset-arcgis.spec.ts`

- `page.route("**/datasets/layer-1/arcgis/items*", ...)` → `**/datasets/dataset-1/arcgis/items*`.
- `page.route("**/datasets/layer-1/arcgis/aggregate", ...)` → `**/datasets/dataset-1/arcgis/aggregate`.
- Commentaire de la section « Runtime » mis à jour pour référencer
  `/datasets/dataset-1/arcgis/*` (au lieu de `layer-1`).
- Les autres occurrences de `layer-1` dans ce spec (id de couche ArcGIS lors
  du moissonnage, `arcgisItemId` dans le payload de création du dataset) sont
  restées inchangées — elles ne concernent pas l'URL du proxy.

## Finding 2 (Important) — noms de champs non validés dans l'agrégat arcgis

**Contexte** : une tâche précédente du même plan avait corrigé un finding
Critical où les *noms* de filtres arrivaient dans la clause `where=` ArcGIS
sans échappement (seules les *valeurs* étaient échappées), en ajoutant
`_FIELD_NAME_RE` validé dans `_build_where`. `translate_aggregate_query`
avait deux autres points où des noms de champs contrôlés par l'utilisateur
atteignaient les paramètres sortants ArcGIS sans passer par cette même
validation : `groupByFieldsForStatistics` (depuis `body.groupBy`) et
`onStatisticField` (depuis `body.field`/`body.measures[].field`).

### Changements — `core/app/harvest/live_query.py` (`translate_aggregate_query`)

- Chaque nom non-`None` dans la boucle `measures` est désormais validé contre
  `_FIELD_NAME_RE` avant utilisation comme `onStatisticField` ; sinon
  `ArcgisQueryError(field, f"invalid measure field name '{field}'")`.
- Chaque nom dans `group_by` est validé contre `_FIELD_NAME_RE` avant d'être
  joint dans `groupByFieldsForStatistics` ; sinon
  `ArcgisQueryError(field_name, f"invalid groupBy field name '{field_name}'")`.
- Aucun changement de route nécessaire : `get_dataset_arcgis_aggregate`
  (`core/app/harvest/routes.py`) attrapait déjà `live_query.ArcgisQueryError`
  autour de l'appel à `translate_aggregate_query` et la propage en 400.

### Tests ajoutés

- `core/tests/test_harvest_live_query.py` :
  `test_translate_aggregate_query_rejects_invalid_groupby_field_name`,
  `test_translate_aggregate_query_rejects_invalid_measure_field_name`.
- `core/tests/test_harvest_dataset_arcgis_routes.py` :
  `test_post_aggregate_invalid_groupby_field_name_rejected` (mirroring
  `test_post_aggregate_invalid_filter_field_name_rejected`, POST avec
  `groupBy: "1) OR (1=1--"` → 400).

## Résultats des tests (intégraux, avant chaque commit)

### Shell

- `npm run build` → OK (`tsc --noEmit && vite build`, build réussi, warnings
  de taille de chunk préexistants et hors périmètre).
- `npx vitest run` → **840 tests passés** (110 fichiers), 0 échec (les
  quelques logs `stderr` visibles dans la sortie sont des chemins d'erreur
  volontairement testés dans des tests existants, non liés à ce fix).
- `VITE_AUTH_MODE=mock npm run e2e` → **83 tests passés** (18 specs), y
  compris `dataset-arcgis.spec.ts` qui exerce directement le chemin corrigé
  (création dataset arcgis → Table + Indicateur liés → runtime consomme via
  `/datasets/dataset-1/arcgis/items` et `/datasets/dataset-1/arcgis/aggregate`).

### Cœur

- `uv run pytest` → **850 passés, 106 skipped** (skips = tests postgis
  nécessitant docker, préexistants), 0 échec.
- `uv run lint-imports` → `layered architecture KEPT`, `Contracts: 1 kept, 0
  broken`.

Tout est vert sur les deux stacks.

## Commits

- `8c2cba5` — `fix(shell): key the arcgis live proxy URL on the dataset item id (SP-14k)`
  (`shell/src/api/itemClient.ts`, `shell/src/api/itemClient.test.ts`,
  `shell/e2e/dataset-arcgis.spec.ts`)
- `9f4ef1b` — `fix(core): validate groupBy and measure field names in arcgis aggregate (SP-14k)`
  (`core/app/harvest/live_query.py`,
  `core/tests/test_harvest_live_query.py`,
  `core/tests/test_harvest_dataset_arcgis_routes.py`)

## Remarques / points de vigilance

- Périmètre strictement limité aux deux findings demandés ; les findings
  Minor listés dans la review (message 404 incohérent, croissance du cache,
  regex ASCII-only, etc.) n'ont pas été touchés, comme prescrit.
- Des fichiers `.superpowers/sdd/*.md` étaient déjà modifiés dans l'arbre de
  travail avant le début de cette tâche (non liés à ces deux findings) — ils
  n'ont pas été inclus dans les commits ci-dessus, volontairement laissés en
  l'état pour ne pas élargir le périmètre.
- Aucun problème ouvert identifié après vérification complète : les deux
  fixes sont couverts par des tests unitaires ciblés et validés de bout en
  bout par la suite E2E (en particulier `dataset-arcgis.spec.ts`, seul test
  qui prouve que l'URL réellement construite par le shell correspond bien à
  ce que le cœur attend).
