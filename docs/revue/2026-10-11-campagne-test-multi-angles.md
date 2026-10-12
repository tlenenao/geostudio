# Campagne de test multi-angles GeoStudio (2026-10-11)

Source : 24 lentilles (L01 à L24), constats vérifiés par un second passage, tests reproducteurs écrits dans `core/tests/audit/` et `shell/src/audit/` (non commités). Les numéros de ligne sont ceux de l'arbre `dev` au 2026-10-11.

## 1. Synthèse chiffrée

Comptage estimé, non recalculé mécaniquement : environ 190 constats bruts, environ 165 après déduplication (la galerie `/internal/kit-gallery` apparaît 6 fois, le profil hors limite géographique 3 fois, CQL2/datetime 5 fois, raster 3 fois, upsert 2 fois, incrémental 2 fois). 1 constat réfuté.

| Lentille | Thème | Bruts |
|---|---|---|
| L01 | autorisation | 10 |
| L02 | RLS / colonnes sensibles | 4 |
| L03 | SSRF / secrets | 7 |
| L04 | injection | 4 |
| L05 | concurrence | 6 |
| L06 | jobs orphelins | 6 |
| L07 | migrations | 8 |
| L08 | fuzz / limites | 8 |
| L09 | récit vs code | 16 |
| L10 | câblage | 3 |
| L11 | surfaces orphelines | 6 |
| L12 | aller-retour de config | 7 |
| L13 | tests tautologiques | 8 |
| L14 | couverture critique | 13 |
| L15 | parcours persona | 7 |
| L16 | états UX | 5 |
| L17 | a11y | 5 |
| L18 | i18n / cohérence | 8 |
| L19 | contrats API | 8 |
| L20 | perf / exploitation | 6 |
| L21 à L23 | parité ArcGIS / FME / autres | 30 |
| L24 | manques créatifs | 14 |

Par famille (ordre de grandeur) : carte-données-OGC ~70, admin-exploitation ~45, pipelines ~35, apps-analytics ~30, transverse ~25.

Par gravité après vérification : 3 critiques (secret S3 lisible via SQL, VRT déguisé à l'import, `timeField` dans les cartes, ce dernier rétrogradé important par le vérificateur), ~45 importants, le reste mineurs.

Par genre : bugs ~85, manques ~35, sous-développé ~6, à revoir ~35, parité marché ~29.

## 2. Top 15 à traiter en premier

1. **Secret S3 du lac lisible par SQL Lab** (`core/app/analytics/duckdb_conn.py:39`, `sql_sandbox.py:118-120`) : `current_setting('s3_secret_access_key')` renvoie la clé couvrant tous les tenants. Critique, reproduit.
2. **Import GPKG/ZIP/KML/GML : un fichier VRT déguisé lit des fichiers du serveur** (`core/app/ingestion/parsers.py:415`, `:389`, `:791`). Restreindre `drivers=` et vérifier la signature.
3. **Profil de collection ignore les limites géographiques** (`core/app/features/routes.py:362-398`) et l'outil MCP jumeau (`core/app/mcp/tools/analytics.py:181-224`). Piège n°14.
4. **Un éditeur publie un item à l'anonyme via PATCH** (`core/app/items/routes.py:165-177`). La garde existe sur collections (`collections/routes.py:788`).
5. **Coffre SMTP sans garde d'egress**, ouvert au Créateur (`core/app/alerts/notify.py:142`).
6. **`writer.collection` en mode replace met à NULL les colonnes sensibles** (`core/app/pipelines/runtime.py:1014`).
7. **Le jeton d'export Playwright est un jeton utilisateur complet** (`core/app/auth/dependency.py:196`), rejouable en écriture par un widget d'extension.
8. **`timeField` et `attachmentField` rejetés en 422** (`core/app/configs/schemas.py:122`, `:113`) : la config carte ne s'enregistre pas. Filet de parité TS aveugle aux champs en trop (`shell/src/api/builderSchemaParity.types.ts:18`).
9. **Import CSV/XLSX : en-tête avec espace, `id` ou Z fait échouer le job** (`core/app/ingestion/importer.py:304`, `parsers.py:464`, `importer.py:322`).
10. **Prod : le worker garde `CORE_BASE_URL=http://localhost:8200`** (`docker-compose.prod.yml:253`, `docker-compose.yml:613`) ; `install.sh:248` n'active pas `CORE_EXPORT_ENABLED` ni `CORE_APPEXPORT_ENABLED`.
11. **Fuite de clé API par redirection** dans `reader.connector.rest` (`core/app/pipelines/connector_runtime.py:569`) ; hôtes Azure/GCS/BigQuery hors garde (`:906`, `:918`).
12. **Purge de tenant** : S3 supprimé avant commit (`core/app/compliance/purge.py:179`), pas de gel ni d'idempotence (`compliance/routes.py:105`), pas de statut d'échec (`compliance/jobs.py:30`).
13. **Jobs zombies** terrain3d/tileset3d (`core/app/terrain3d/jobs.py:59`, `core/app/tileset3d/jobs.py:54`), embeddings (`core/app/items/repository.py:231`).
14. **Bombe gzip dans le moissonnage** (`core/app/harvest/egress.py:97`) ; agrégats/profil sans rate limit (`core/app/ratelimit/limiter.py:99-130`).
15. **Écriture pipeline : pas d'upsert, pas de sortie Rejected, pas d'incrémental, pas de retry** (`core/app/pipelines/ops/schemas.py:55`, `runtime.py:1033`, `connector_runtime.py:442`, `pipelines/jobs.py:273`). C'est le premier écart face à FME.

## 3. Bugs

| fichier:ligne | gravité | lentille | repro | test reproducteur |
|---|---|---|---|---|
| analytics/duckdb_conn.py:39 | critique | L04 | SQL Lab `SELECT current_setting('s3_secret_access_key')` | audit/test_audit_lot2.py `test_s3_secret_not_readable_after_lock_down` |
| ingestion/parsers.py:415 | critique | L04 | .gpkg contenant un VRT vers un fichier local | lot1 `test_gpkg_import_rejects_vrt_disguised_file` |
| features/routes.py:362 | important | L01/L02 | geo-limit puis GET `/profile` renvoie 200, `/aggregate` 403 | lot0 (2 tests) |
| mcp/tools/analytics.py:181 | important | L02 | `profile_dataset` sans `refuse_geo_limited` | lot0 |
| items/routes.py:165 | important | L01 | éditeur PATCH `isPublished:true` | lot0 `test_editor_cannot_publish_item_via_patch` |
| ratelimit/limiter.py:99 | important | L01 | boucle sur `/aggregate` sans 429 | lot0 |
| pipelines/runtime.py:1014 | important | L02 | replace par utilisateur masqué | lot0 |
| alerts/notify.py:142 | important | L03 | secret SMTP vers hôte interne | lot1 |
| pipelines/connector_runtime.py:569 | important | L03 | 302 vers autre hôte, clé API suivie | lot1 |
| harvest/egress.py:97 | important | L03 | gzip 48 Ko vers 50 Mo | lot1 |
| pipelines/connector_runtime.py:906/918 | important | L03 | accountName ou token_uri libre | lot1 (schéma seulement) |
| alerts/notify.py:44 | important | L03 | éditeur cite le secret du propriétaire | lot1 (placeholder xfail) |
| configs/repository.py:312 | important | L05 | rollback concurrent d'un PUT | lot2 |
| compliance/routes.py:105 | important | L05 | double POST purge | lot2 |
| compliance/jobs.py:30 | important | L06 | purge avec S3 coupé, 202 infini | lot2 |
| terrain3d/jobs.py:59, tileset3d/jobs.py:54 | important | L06 | worker tué pendant conversion | lot2 |
| items/repository.py:231 | important | L06 | defer avant commit | lot3 |
| harvest/models.py:76 | important | L07 | DELETE collection moissonnée, 500 FK | lot3 |
| alembic/versions/0012_pgvector_embeddings.py:43 | important | L07 | ivfflat sur table vide | lot3 (XPASS strict à revoir) |
| ingestion/importer.py:304 | important | L08 | CSV `Code postal` | lot3 |
| ingestion/parsers.py:464 | important | L08 | propriété `id` | lot3 |
| ingestion/importer.py:322 | important | L08 | GeoJSON avec Z | lot3 |
| features/validation.py:85 | important | L08 | POST Point sur collection mixte, 422 | lot4 |
| features/routes.py:169 | important | L09 | bbox hors bornes ou NaN, 500 | lot4 |
| docker-compose.prod.yml:253 | important | L10 | worker localhost | lot4 |
| scripts/install.sh:248 | important | L10 | profil export sans flag | lot4 |
| configs/schemas.py:122, :113 | important | L12 | PUT carte avec `timeField` ou `attachmentField` | lot4 |
| configs/schemas.py:248, :273 | important | L12 | position de nœud fractionnaire | lot5 |
| shell/pages/ComplianceAdminPage.tsx:57 | important | L16 | anonymisation sans confirmation | shell audit-lot5 |
| shell/shell/ShareForm.tsx:105 | important | L16 | révocation de lien sans erreur | shell audit-lot5 |
| shell/pages/ReportEditPage.tsx:36 | important | L15 | rapport créé sans bookmark | shell audit-lot5 (statique) |
| shell/map/MapMeasureSketchToolbar.tsx:334 | important | L17 | mesure sans clavier | shell audit-lot5 (statique) |
| features/routes.py:169 (bbox) et features/repository.py:155 | mineur | L09 | antiméridien vide | non écrit |
| features/routes.py:104 | mineur | L09 | conformance oas30 vs doc 3.1.0 | non écrit |
| main.py:275 | important | L09 | mode démo laisse passer les exports | non écrit |
| items/repository.py:709 | mineur | L05 | If-Match sans verrou (TOCTOU) | non écrit |
| mapicons/routes.py:101 | mineur | L01 | POST sans privilège ni quota | non écrit |
| tileset3d/routes.py:238, terrain3d/routes.py:157 | important (manque) | L01 | 401 en anonyme sur 3D et icônes | non écrit |
| harvest/routes.py:441 | mineur | L01 | `numberMatched` faux | non écrit |
| compliance/routes.py:140 | mineur | L19 | 202 problem+json, `completedAt=""` | non écrit |
| main.py:521 | mineur | L20 | `/health` 200 base morte | non écrit |
| cdc/main.py:188 | mineur | L14 | requête DB par message WAL | non écrit |
| shell/api/domains/datasets.ts:231 | mineur | L12 | dataset arcgis sans `baseVersion` | non écrit |
| shell/map/measureSketch.ts:144 | mineur | L09 | cercle en ovale | non écrit |
| shell/builder/pipeline/PipelineWebhookTrigger.tsx:46 | mineur | L16 | révocation sans confirmation | non écrit |
| shell/pages/UsagePage.tsx:173 (+ 3 autres) | mineur | L18 | dates ISO brutes | non écrit |
| shell/ui/kit/MetadataForm.tsx:95 | mineur | L18 | chaînes FR en dur | non écrit |
| shell/ui/kit/Splitter.tsx:39 | mineur | L17 | séparateur sans clavier | non écrit |
| shell/builder/widgets/form.tsx:71 | mineur | L17 | `dragIndex` local au rendu | non écrit |

Constat réfuté : voir section 8.

## 4. Manques et fonctionnalités sous-développées

| fichier:ligne | gravité | Manque |
|---|---|---|
| core/app/features/routes.py:82-90 | important | OGC Features : ni `datetime`, `sortby`, CQL2, `crs`, ni queryables ; 4 classes de conformité |
| core/app/pipelines/ops/schemas.py:55 | important | pas d'upsert/update/delete par clé alors que `detectChanges` existe (schemas.py:569) |
| core/app/pipelines/connector_runtime.py:442 | important | pas d'import incrémental ni de watermark |
| core/app/pipelines/jobs.py:273 | important | pas de retry de run ni de reprise depuis un nœud |
| core/app/pipelines/routes.py:92 | important | pas de paramètres de run |
| core/app/pipelines/runtime.py:1033 | important | une ligne invalide fait échouer tout le run, pas de port Rejected |
| core/app/pipelines/ops/contracts.py:159 | important | ni raster ni nuage de points ni lineage |
| core/app/pipelines/ops/contracts.py:275 | important | 3 writers actifs seulement, aucun vers base externe, WFS-T ou ArcGIS |
| core/app/configs/schemas.py:279 | important | cron en UTC sans fuseau, granularité réelle 5 min, pas d'événement ni de chaînage |
| core/app/reports/routes.py:53 | important | pas d'exécution à la demande d'un rapport |
| core/app/mcp/tools/secrets.py:21 | important | parité REST/MCP rompue (secrets, rapports, moissonnage, jetons webhook) |
| core/app/main.py:300 | important | plafond de 5 Mo contourné par MCP |
| core/app/alembic/versions/0037_items_bbox.py:23 | important | backfill de l'emprise manuel, jamais câblé |
| docker-compose.yml:518 | important | pas de purge des jobs procrastinate |
| core/app/audit/models.py:20 | important | pas de rétention de `audit_log` |
| docker-compose.yml:509 | important | pas de rotation des logs ni de `mem_limit` hors worker |
| core/app/cdc/main.py:114 | critique | boucle de production du worker CDC jamais testée (54 lignes sur 97 à 0 hit) |
| core/app/cdc/backfill.py:142 | important | backfill complet en mémoire à chaque redémarrage |
| core/app/geocoding/routes.py:22 | important | pas de géocodage en lot, pas d'op pipeline, pas de reverse |
| core/app/features/routes.py:784 | important | pas de versionnage ni d'historique des entités |
| core/app/features/routes.py:732 | important | pas de collecte publique (écriture anonyme avec modération) |
| shell/src/shell/ConnectivityBanner.tsx:36 | important | pas de hors-ligne ni de PWA |
| core/app/alerts/notify.py:52 | important | pas de webhooks sortants génériques |
| core/app/analytics/export.py:40 | important | export limité à csv, xlsx, geojson, gpkg |
| core/app/features/tiles.py:47 | mineur | tuiles plafonnées à 5000 entités, pas de clustering ni de généralisation |
| shell/src/map/mapLayerBuild.ts:30 | mineur | pas de clustering de points |
| shell/src/builder/pipeline/SecretParamSelect.tsx:43 | mineur | pas de page de gestion des secrets ni d'usage |
| core/app/collections/models.py:72 | mineur | lineage réduit à une chaîne libre |
| core/app/pipelines/ops/schemas.py:547 | mineur | qualité de données basique |
| shell/src/pages/MapEditorPage.tsx:70 | mineur | pas d'undo/redo sur la carte |
| core/app/configs/routes.py:276 | mineur | pas de diff entre révisions |
| (aucun module) | mineur | pas de commentaires collaboratifs, pas de marketplace de templates |
| shell/src/shell/routes.tsx (profil) | mineur | profil de collection (REST + MCP) sans écran : `shell/src/api/domains/datasets.ts:365` |
| core/app/pipelines/ops/schemas.py:66 | mineur | formats de sortie pipeline limités |

## 5. À revoir (cohérence, UX, a11y, dette)

- **Sécurité de conception** : jeton d'export plein droit (`auth/dependency.py:196`) ; webhook de pipeline exécuté avec les droits du propriétaire courant, sans expiration (`pipelines/service.py:180`) ; jeton de passerelle admin rejouable 60 s (`admin_tools/routes.py:61`) ; `GET /instance` anonyme (`instance/routes.py:44`) ; oracle de nom de secret (`secrets/routes.py:53`) ; NAT64 jugé global dans 6 copies de la garde (`pipelines/egress.py:51`) ; `reader.file` sans racine (`pipelines/runtime.py:730`) ; confused deputy du coffre sur les alertes (`alerts/notify.py:44`).
- **Intégrité** : rotation de clé maître sans verrou (`secrets/rotation.py:29`) ; quota de stockage vérifié après coup (`quotas/service.py:243`) ; `ingestion_jobs.collection_id` sans FK (`ingestion/models.py:33`) ; migrations 0028 et 0030 couplées au code vivant (`alembic/versions/0030_roles.py:38`) ; 0050 promeut les éditeurs en managers (`0050_share_role_manager.py:39`) ; 0045 ignore un index INVALID (`0045_p24_indexes.py:33`) ; configs relues sans tolérance aux validateurs durcis (`configs/repository.py:40`).
- **UX** : pages publiques et runtime affichent « introuvable » pour toute erreur (`shell/src/pages/PublicItemPage.tsx:47`, `AppRuntimePage.tsx:169`) ; fiche d'item sans éditeur pour report/alert (`ItemDetailPage.tsx:133`) ; tous les rapports portent le même titre (`ReportEditPage.tsx:124`) ; requête visuelle sans garde de brouillon (`VisualQueryWizardPage.tsx:419`) ; suppressions sans confirmation (`map/LayersPanel.tsx:420`, `builder/VariablesPanel.tsx:177`) ; `/internal/kit-gallery` en prod sans garde (`shell/src/shell/routes.tsx:366`).
- **i18n** : défauts de widgets persistés en français (`builder/pages.ts:10`, `widgets/tabs.tsx:20`, `templates.ts:30`) ; « Retirer/Supprimer » incohérents (`i18n/domains/widgets.ts:587`) ; « Export standalone » vs « Autoporté » (`widgets.ts:40`) ; libellés « Enregistrer » dupliqués.
- **Contrats API** : `limit` sans `le=` dans OpenAPI (`features/routes.py:232`) ; 400 sans `errors[]` (`usage/routes.py:105`) ; 429 à `Retry-After` fixe de 60 s, clé = en-tête brut (`main.py:342`) ; aucune idempotence sur les POST de jobs (`pipelines/routes.py:94`) ; If-Match optionnel par défaut (`configs/routes.py:60`).
- **Tests** : mutants survivants sur le routage `llm` (`ratelimit/limiter.py:107`) et les budgets `jobs` et `collections_empty` (`limiter.py:66`) ; assertions larges (`tests/test_features_collections_manage_read.py:73`, `tests/test_p14_sharing_guards.py:233`) ; ~185 tests PostGIS skippés sans `CORE_TEST_DATABASE_URL` (`tests/test_features_rls.py:1`) ; `restore.sh` testé avec de faux binaires (`tests/test_restore_script.py:1`) ; mypy bloquant sur 7 modules seulement (`.github/workflows/ci.yml:90`).
- **Récit vs code** : copilote à 9 outils (`copilot/tools_allowlist.py:17`), 20 privilèges (`roles/privileges.py:6`) ; multi-tenant dormant, tout est `default` (`auth/dependency.py:181`) ; `CORE_PIPELINE_FILE_IO_ENABLED` non câblé sur `core` (`docker-compose.yml:566`).
- **Exploitation** : sauvegarde en 3 copies sur disque (`deploy/backup/backup.sh:106`) ; restauration jamais vérifiée automatiquement ; `/health` sans readiness.

## 6. Comparatif marché

### 6.1 ArcGIS Enterprise

| Capacité | Verdict | Preuve | Effort |
|---|---|---|---|
| Requêtes de features (where, tri, stats, offset) | moins bien | features/routes.py:82-90, `:308` compense en partie | M |
| Filtre de sécurité appliqué aux statistiques | moins bien | features/routes.py:362 | S |
| Édition avancée (versioning, relations, domaines, tracking) | absent | features/repository.py:368 | L |
| Historique temporel et archivage | absent | features/routes.py:784 | M |
| Raster / imagerie / analyse | absent | admin_tools/routes.py:33 | L |
| Analyse réseau, isochrones | absent | pipelines/ops/contracts.py:205 | L |
| Géocodage lot et reverse | moins bien | geocoding/provider.py:43 | S |
| Experience Builder : filtres, cross-filter, formulaires, time slider | iso | shell/src/builder/widgets/index.tsx | n/a |
| Gabarits d'apps, légende, table d'attributs | moins bien | shell/src/builder/widgets/index.tsx:1 | M |
| Copilote IA, bindings CEL | mieux | core/app/copilot, tools_allowlist.py:17 | n/a |
| Collecte terrain hors ligne (Field Maps, Survey123) | absent | docs/revue/2026-09-04-backlog.md:1310 | L |
| Sites et catalogue ouvert (Hub) | iso | public/routes.py:1 | n/a |
| DCAT-AP et STAC natifs | mieux | core/app/dcat/routes.py, stac/routes.py | n/a |
| Engagement citoyen (Hub) | absent | public/routes.py:1 | L |
| Notebooks / Insights Python | moins bien | features/routes.py:595 | L |
| NL vers SQL avec revue humaine | mieux | analytics/query_generation.py:195-335 | n/a |
| Rôles et privilèges fins, audit | iso | roles/privileges.py:1 | n/a |
| Purge de tenant et RGPD | mieux | compliance/purge.py:179 | n/a |
| Fédération multi-serveurs, haute disponibilité | absent | docker-compose.yml | L |
| Privilège de publication séparé | moins bien | items/routes.py:165 | S |
| Rate limit par service / jeton | moins bien | ratelimit/limiter.py:99 | S |
| Quota de stockage compté à l'écriture | moins bien | quotas/service.py:243 | S |
| Time slider persisté dans la carte | moins bien | configs/schemas.py:122 | S |
| Verrouillage optimiste obligatoire | moins bien | configs/routes.py:60 | S |

### 6.2 FME

| Capacité | Verdict | Preuve | Effort |
|---|---|---|---|
| Transformers : 110/290 `implemented` de la matrice, 59 op exposées | moins bien | docs/revue/matrice-couverture-fme.jsonl, pipelines/ops/contracts.py:158 | L |
| Écriture : upsert, update, delete | moins bien | pipelines/ops/schemas.py:55 | M |
| Ports Rejected | absent | pipelines/runtime.py:1033 | M |
| Mode incrémental | absent | pipelines/connector_runtime.py:442 | M |
| Retry de job | absent | pipelines/jobs.py:273 | M |
| Paramètres publiés | absent | pipelines/routes.py:92 | M |
| Formats lecture/écriture (~450) | moins bien | ops/schemas.py:66, analytics/export.py:40 | L |
| Raster, nuage de points | absent | ops/contracts.py:159 | L |
| Déduplication, appariement flou | absent | ops/contracts.py:158 | M |
| Géocodage en pipeline | absent | geocoding/routes.py:22 | S |
| Déclencheurs : cron + webhook | moins bien | pipelines/jobs.py:300, routes.py:240 | M |
| Cron avec fuseau | moins bien | configs/schemas.py:279 | S |
| Audit, RLS par ligne, secrets, garde SSRF | mieux | runtime.py:1049, egress.py:51 | n/a |
| Pilotage par MCP et copilote | mieux | mcp/tools/pipelines.py:46 | n/a |
| Pipeline déclaratif versionné en JSON | mieux | configs/schemas.py:248 | n/a |
| Redirections avec identifiants (HTTPCaller) | moins bien (reader REST) | connector_runtime.py:569, http_call_runtime.py:329 | S |
| Rétention des jobs, requeue en un clic | moins bien | docker-compose.yml:518 | M |
| Lineage | absent | collections/models.py:72 | M |

### 6.3 Autres outils

| Outil | Capacité | Verdict | Preuve | Effort |
|---|---|---|---|---|
| GeoServer / pygeoapi | CQL2, datetime, sortby, crs | moins bien | features/routes.py:228 | M |
| GeoServer / pygeoapi | WMS, WFS, WMTS, SLD, Tiles, Styles | absent | features/routes.py:85-90 | L |
| GeoServer / pygeoapi | Écriture OGC Part 4 | mieux | features/routes.py:85-90 | n/a |
| Martin, Tippecanoe, CARTO | Tuiles agrégées | moins bien | features/tiles.py:47 | M |
| QGIS | Portabilité de style (SLD, QML) | absent | shell/src/map/MapSymbologyEditor.tsx:1 | M |
| QGIS | Traitement raster | absent | ops/contracts.py:205 | L |
| Superset / Metabase | Variété de visualisations | moins bien | shell/src/builder/widgets/chartOption.ts:117 | M |
| Superset / Metabase | Cross-filter spatial, emprise globale | mieux | shell/src/builder/widgets/timePlayer.tsx | n/a |
| Kepler | Time player | iso | timePlayer.tsx | n/a |
| Kepler | 3D, arcs, trips | moins bien | shell/src/map/LayersPanel.tsx:431 | M |
| CKAN / GeoNetwork | CSW serveur, API CKAN | absent | harvest/connectors/__init__.py:20 | M |
| CKAN / GeoNetwork | DCAT-AP, STAC natif | iso / mieux | dcat/routes.py, stac/routes.py | n/a |
| Felt | Commentaires sur carte | absent | (aucun module) | M |
| Felt | Clustering | absent | shell/src/map/mapLayerBuild.ts:30 | S |
| Debezium | Snapshot incrémental CDC | moins bien | cdc/backfill.py:142 | M |
| Vault / KMS | Clés versionnées | moins bien | secrets/rotation.py:28 | M |

### 6.4 Synthèse

- **Mieux** : écriture OGC Part 4, STAC et DCAT-AP natifs, pilotage IA (MCP, copilote, NL vers SQL avec revue), CEL, RGPD (anonymisation, purge de tenant), audit et RLS par ligne, pipelines versionnés en JSON, cross-filter spatial.
- **Iso** : filtres et formulaires du builder, sites et catalogue, rôles et audit, time player.
- **En retard** : requêtes OGC avancées, écriture et incrémental des pipelines, raster et 3D, formats, hors-ligne, versioning et historique d'entités, serveurs OWS, tuiles agrégées, HA et fédération, exploitation (rétention, readiness).

## 7. Idées créatives priorisées (valeur / effort)

| # | Idée | Valeur | Effort | Appui |
|---|---|---|---|---|
| 1 | Garde unique `refuse_geo_limited` dans `run_collection_profile` pour fermer REST et MCP d'un coup | haute | S | features/routes.py:362 |
| 2 | Mode `upsert` du `writer.collection` appliquant le statut de `detectChanges` | haute | M | schemas.py:55, :569 |
| 3 | Incrémental via dlt (état par nœud reader), déjà natif côté bibliothèque | haute | M | connector_runtime.py:442 |
| 4 | Port Rejected avec collection de quarantaine et rapport de qualité réutilisant `profile` | haute | M | runtime.py:1033, analytics/profile.py |
| 5 | Journal avant/après dans `audit_log` puis `asOf` sur les items (time travel du lac) | haute | M | features/routes.py:784, analytics/snapshot.py:1 |
| 6 | Webhooks sortants génériques via outbox, en réutilisant `send_webhook` et l'egress | haute | M | alerts/notify.py:52 |
| 7 | Jeton de soumission public par collection + file de modération (consultation citoyenne) | haute | M | features/routes.py:732 |
| 8 | Index d'usage dérivé des configs : lineage et vue d'impact avant suppression | moyenne | M | collections/models.py:72, configs/bbox.py:58 |
| 9 | `transform.geocode` BAN en lot, et à l'import CSV | moyenne | S | geocoding/provider.py:43 |
| 10 | Diff de configs en JSON Patch (RFC 6902), possible car documents déclaratifs | moyenne | S | configs/routes.py:276 |
| 11 | Export de styles SLD / Mapbox depuis la symbologie déclarative | moyenne | M | map/MapSymbologyEditor.tsx:1 |
| 12 | Page « Secrets » avec usages et rotation | moyenne | S | pipelines/SecretParamSelect.tsx:43 |
| 13 | Module unique d'egress (6 copies) avec NAT64 et IPv4-mapped décodés dans `net_pin.py` | moyenne | S | pipelines/egress.py:51 |
| 14 | Retry de run et reprise par nœud ; bouton « rejouer » dans `/tasks` | moyenne | M | pipelines/jobs.py:273 |
| 15 | Annotations géolocalisées commentées, réutilisant `notifications/` | basse | M | attachments/, notifications/ |
| 16 | Bundle d'items exportable (zip de configs) comme galerie de modèles | basse | M | extensions/ |
| 17 | PWA hors-ligne pour la collecte (rouvrir Q11) | haute | L | ConnectivityBanner.tsx:36 |

## 8. Méthode et limites

- **Méthode** : 24 lentilles indépendantes (autorisation, RLS, SSRF, injection, concurrence, jobs, migrations, fuzz, récit vs code, câblage, surfaces, aller-retour de config, tests, couverture, parcours, UX, a11y, i18n, contrats, exploitation, parité ArcGIS, FME et autres, manques créatifs). Chaque constat a été revérifié par un second passage qui a lu le code et pu corriger la gravité. Ceux dont `correctedSeverity` diffère ont été classés selon la valeur corrigée.
- **Tests** : 6 lots de tests reproducteurs `xfail(strict=True)` côté cœur (lot0 à lot5, soit une trentaine de cas) et 4 `it.fails` côté shell. Chaque test a été rejoué avec `--runxfail` pour confirmer qu'il échoue pour la bonne raison. Rien n'a été commité.
- **Non exécuté** : confused deputy des alertes (placeholder), tests Azure et GCS au niveau schéma seulement, pas de 500 réel sur `ST_Transform`, pas de rejeu sur stack réelle, pas de test de concurrence à deux sessions, tests shell 5 et 6 statiques. Un conteneur PostGIS jetable a servi aux tests postgis et a été supprimé.
- **Biais de couverture** : `coverage.xml` daté du 10/10 sans PostGIS, donc les lignes « non couvertes » sont une borne haute.
- **Constat réfuté** : « budget `jobs` à 15000 dans l'arbre de travail » (`ratelimit/limiter.py:66`) : la valeur est 15 dans HEAD, `git diff` vide. Il reste cependant un mutant survivant sur ce budget (section 5).
- **À nettoyer** : `test_vector_index_is_not_ivfflat_built_on_empty_table` (lot3) sort en XPASS strict dans un des runs, donc son critère est à revoir.
- **Nombres** : les totaux de la section 1 sont des estimations (~190 bruts, ~165 dédupliqués), à recompter par script avant toute communication externe.
