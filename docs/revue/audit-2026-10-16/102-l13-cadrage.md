# Lot L13 « Parité long terme » — cadrage (2026-10-19)

Source : `99-synthese.md` §4/§5/§8 (D1 à D12 tranchées conformément à la recommandation). Chaque ligne
a été revérifiée dans le code courant (piège n°12). Classes : (a) faisable maintenant, (b) arbitrage de
Tanguy requis, (c) hors périmètre actuel. Aucune décision figée de `CLAUDE.md` n'est contredite.

| AUD | État réel du code | Effort | Décisions liées | Classe |
|---|---|---|---|---|
| 063 modèle sémantique | `AggregateRequestBody` : pas de top-N/tri par mesure, filtres limités à `=`/`__in`/`__gte`/`__lte`, aucun cache de résultat ; `DatasetPayload.metrics` = champ+agrégat nommés sans CEL (REV-119) | L | A28 | (a) tranche 1 : top-N (`orderBy`/`limit`), opérateurs `__ne`/`__gt`/`__lt`/`__contains`, cache TTL de résultat. Mesure calculée -> (b) |
| 062 SQL Lab | aucune requête sauvegardée côté serveur ; `_materialize` copie toute la collection en table TEMP (barrière nécessaire : `enable_external_access=false` interdit la lecture paresseuse) | M | `analytics.sql` | (a) requêtes sauvegardées par utilisateur (migration 0172, `tenant_id`, audit) ; projection des colonnes réellement lues = reste |
| 131 temps réel | aucun `refetchInterval` de widget, aucun flux SSE ; webhooks entrants de pipeline déjà livrés (SP-53) | M | D7 | (a) rafraîchissement planifié par widget (`refreshSeconds`) ; SSE sur alertes -> tranche 2 si fenêtre |
| 142 raster | tuiles PNG à 3 paramètres + info + zonal ; pas d'identify | M | — | (a) `GET /v1/raster/{id}/point` (identify) via TiTiler `/cog/point`, mêmes gardes que les tuiles |
| 143 formats/FeatureServer | import : geojson/csv/xlsx/gpkg/shp/gdb/dxf/dgn/kml/gml/parquet…, export csv/xlsx/geojson/gpkg ; ni FlatGeobuf, ni PMTiles/MBTiles, ni 3D/BIM | L | D10 (ne pas imiter FeatureServer), A22 | (a) import FlatGeobuf (`.fgb`, GDAL déjà présent). Le reste -> (b)/(c) |
| 144 custom transformers/PythonCaller/boucles | registre `OPERATIONS` fermé ; pas de sous-pipeline, pas de code utilisateur | L | licences, sécurité | (b) |
| 145 notebooks/Spark | absent | L | D1 (« ne pas courir après GeoAnalytics ») | (c) |
| 146 RGAA/RGS/SecNumCloud/ProConnect | RGAA audité = action humaine ; RGS/SecNumCloud = hébergeur (D12) ; ProConnect/FranceConnect = brokering Keycloak, habilitation DINUM | L | D12 | (b)/(c) |
| 147 collaboration/GIF/focus/iframe | rien de livré ; commentaires = nouvel objet de plateforme (table + `can()` + MCP) | L | D1 | (b) |
| 148 SaaS connectors/backfill/assets/lac transactionnel | backfill = paramètres de run existants ; catalogue Airbyte/Iceberg absents (Iceberg différé par décision figée) | L | A27 | (b) Airbyte ; (c) lac transactionnel |
| 032 HA/PITR base | chart Helm sans Postgres managé ; `deploy/ha/docker-compose.ha-test.yml` ne couvre que les réplicas applicatifs ; slot logique CDC non répliqué en PG16 | L | D3 | (b) |

## Classe (a) — exécutée, par valeur décroissante

1. AUD-063 tranche 1 — analytique (top-N, opérateurs, cache).
2. AUD-062 — requêtes SQL sauvegardées.
3. AUD-131 — rafraîchissement planifié de widget (D7).
4. AUD-142 — identify raster.
5. AUD-143 — import FlatGeobuf.

## Classe (b) — questions pour Tanguy

- **AUD-063 mesure calculée** : autoriser une mesure dérivée (ratio/différence de deux métriques nommées, arithmétique bornée sans CEL libre) ? Reco : oui, `DatasetMetric.kind="ratio"` ; CEL libre refusé (REV-119).
- **AUD-144** : (1) custom transformer = sous-pipeline paramétré réutilisable (op `transform.subpipeline`) — reco oui, SP dédié ; (2) PythonCaller : reco **non** (exécution de code arbitraire, surface d'évasion) ; couvert par `sqlExecutor`/`httpCall`/CEL ; (3) boucles : reco via itération par ligne de `subpipeline`.
- **AUD-146** : commander l'audit RGAA tiers (D12) et publier la déclaration d'accessibilité ; ProConnect : reco runbook Keycloak (IdP brokering) une fois l'habilitation DINUM obtenue.
- **AUD-147** : commentaires de carte = objet de plateforme (table + `can()` + MCP + notifications) ; reco SP dédié après arbitrage des 3 verticales (D1). Focus mode/iframe/GIF : reco report (iframe = élargit `frame-src`).
- **AUD-148** : connecteurs SaaS via Airbyte ? Reco : non (dépendance lourde) ; étendre `reader.connector.*` à la demande. Backfill : documenter les paramètres de run existants.
- **AUD-032** : choix HA Postgres pour l'instance dédiée Helm : reco CloudNativePG (PITR WAL vers S3, failover slots logiques à valider) ; jamais de HA applicative seule.
- **AUD-143** : export FlatGeobuf/Shapefile et PMTiles/MBTiles : reco export FlatGeobuf+Shapefile seulement si demande client ; pas de FeatureServer (D10).

## Classe (c) — hors périmètre

AUD-145 (notebooks/Spark), lac transactionnel Iceberg/DuckLake (A27 : différé), SaaS multi-tenant avant L4/D3 (instance dédiée Helm seulement), 3D/BIM/nuages de points et DWG (licences GDAL/PDAL, ADR 0028).
