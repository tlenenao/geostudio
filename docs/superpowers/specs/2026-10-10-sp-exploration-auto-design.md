# SP « exploration automatique d'une collection » — design

Date : 2026-10-10. Ferme `REV-117` / `GAP-23` (résumé exploratoire en un clic, façon
Metabase X-rays). Référence vision : brainstorm analytics 2026-07-09 §« X-rays »
(version GeoStudio : découverte automatique depuis le schéma — ici le **profil**, brique
de données ; l'« auto-dashboard » généré reste un prompt MCP/copilote, hors périmètre).

## 1. Périmètre minimal utile

Un **profil par colonne** d'une collection, calculé par DuckDB sur le lac GeoParquet
(état courant, même réduction `_dedup_cte` que `aggregate`) :

- Collection : `rowCount` exact, `sampled`, `asOf`, `pending` (lac pas alimenté).
- Par colonne : `name`, `type`, `nonNull`, `nulls`, `distinct`.
  - numériques (`integer`/`number`) : `min`, `max`, `mean`, `p25`, `median`, `p75`,
    `histogram` (10 classes, réutilise `_run_binned_histogram`) ;
  - `date`/`datetime` : `min`, `max` (texte ISO, cast `TIMESTAMPTZ` comme `aggregate`) ;
  - `string`/`enum`/`boolean`/`integer` : `topValues` (5 plus fréquentes, `{value, count}`) ;
  - `list`/`unsupported` : comptage de nulls seulement.
- Géométrie : `geometry = {column, bbox [minx,miny,maxx,maxy] | null, types: [{type, count}]}`.

Hors périmètre (assumé) : auto-dashboard généré, corrélations, détection d'anomalies,
profil filtré par bbox/filtres, profil des datasets ArcGIS live, mise en cache.

## 2. Architecture (réutilisation, pas de duplication)

- `core/app/analytics/profile.py` : `run_collection_profile(conn, base_uri, tenant_id,
  collection_id, table_info, masked_fields)`. Réutilise `_dedup_cte`, `_has_any_file`,
  `lake_as_of`, `_valid_column_names` (donc **masquage GAP-22 identique à `aggregate`** :
  une colonne masquée n'apparaît ni dans le profil, ni dans l'emprise), `_run_binned_histogram`,
  `statement_timeout`, `UnknownAggregateField`.
- Matérialisation unique de l'état courant dans une table temporaire `prof` (colonnes
  profilées seulement) ; toutes les statistiques lisent `prof` : un seul balayage du lac.
- REST : `GET /v1/collections/{id}/profile` dans `app/features/routes.py`
  (même autorisation que `aggregate` : `get_collection_for_read`, privilège
  `data.view_sensitive` pour lever le masquage).
- MCP : outil `profile_dataset(datasetId)` jumeau, même chemin que `run_analytics_query`
  source `collection` (`require_access` + `require_collection_read`) ; source `arcgis` refusée.
- Shell : `ItemClient.getCollectionProfile(collectionId)` (domaine `datasets`) + hook
  `useCollectionProfile` + composant `CollectionProfilePanel` (bouton « Explorer » sur la page
  publique de jeu de données `DatasetPage`, déplie le panneau ; requête déclenchée au clic).

## 3. Bornes

- Budget de temps : `statement_timeout` global (30 s, `CORE_DUCKDB_STATEMENT_TIMEOUT_S`)
  sur l'ensemble du profil, mémoire/threads : `open_connection`.
- `MAX_PROFILE_COLUMNS = 50` colonnes profilées (`truncatedColumns: true` au-delà).
- `PROFILE_SAMPLE_ROWS = 500 000` : au-delà, les statistiques portent sur un échantillon
  `USING SAMPLE` (`sampled: true`, `rowCount` reste exact).
- `topValues` ≤ 5, `histogram` ≤ 10 classes, valeurs texte tronquées à 200 caractères.
- Erreur de budget -> 400 `unknown_field`/`query` (même convention que `aggregate`).

## 4. Sécurité

`can()` via `get_collection_for_read` (404 si illisible, partage/public/lien comme
`aggregate`) ; le profil expose des **valeurs** (top, min/max) : le masquage de champs sensibles
s'applique avant toute construction SQL (la colonne n'existe pas pour la requête). La colonne
PK et `tenant_id` ne sont pas profilées. Pas de route ajoutée à la liste CORS d'export
Connecté (`_APPEXPORT_CORS_*`) ni à l'allowlist du copilote.

## 5. Décisions à valider

1. **Profil global uniquement** (pas de filtres/bbox) : conservateur ; extensible en
   `POST` avec `AggregateRequestBody.filters` plus tard.
2. **Échantillonnage au-delà de 500 000 lignes** plutôt qu'un 400 : le résumé reste utile,
   le drapeau `sampled` le dit.
3. **PK exclue du profil** (identifiant unique sans intérêt exploratoire).
4. **Pas d'entrée dans l'allowlist du copilote** ni de CORS Connecté : à décider séparément.
5. **Panneau placé sur la page publique `DatasetPage`** (la seule « fiche collection »
   côté shell qui ne soit pas un éditeur) ; pas encore sur `DatasetEditPage`.
6. **Pas de privilège dédié** : mêmes droits que la lecture/agrégation de la collection.
7. **Pas de limitation de débit spécifique** : le groupe par défaut s'applique ; le coût
   est borné par le budget de temps et l'échantillon (à revoir si abus constaté).
