# Comparatif GeoStudio vs FME (Form/Flow/Hub) et ArcGIS Enterprise

Date : 2026-10-11. Branche `dev`. Document d'analyse, non commité.
Point de départ : §6-§7 de `docs/revue/2026-10-11-campagne-test-multi-angles.md`, approfondi et revérifié dans le code.

Conventions : chemins relatifs à `core/app/` sauf mention `shell/` ou `docs/`. Les références `[Sn]` renvoient à la table des sources (§7).
Côté FME, une capacité marquée « non vérifié » n'a pas pu être sourcée : son verdict repose sur la connaissance générale du produit. Côté ArcGIS Enterprise (§3), les lignes ont été reprises à partir de 7 jeux de notes de recherche web sourcées puis d'un second passage ciblé (2026-10-11) ; chaque ligne porte un niveau de confiance (S page officielle lue, R résumé de recherche, D déduit, NV non vérifié) et les derniers états du produit (12.0/12.1) sont en §3.8. Les lignes R, D et NV doivent être revalidées avant toute communication externe.

---

## 1. Résumé exécutif et positionnement

### 1.1 Message en trois phrases

1. GeoStudio est une plateforme **d'applications et de données** (catalogue, carte, builder no-code, API OGC, MCP/IA, gouvernance) dont le pipeline no-code est un module parmi d'autres. FME est un **moteur de transformation** de très grande largeur (formats, transformers) ; ArcGIS Enterprise est une **suite SIG complète** (géodatabase, services, analyse, mobile, 3D, réseau).
2. Face à FME, GeoStudio est nettement derrière sur la largeur (110 transformers `implemented` sur 290 recensés, 61 op brutes, aucun format GDAL en pipeline) et sur la robustesse d'exécution (pas d'upsert, de port Rejected, d'incrémental, de retry), mais devant sur la gouvernance (RLS, audit, secrets, SSRF), le pilotage IA et la déclarativité versionnée.
3. Face à ArcGIS Enterprise, GeoStudio couvre l'essentiel d'un usage « collectivité sans géodatabase d'entreprise » (catalogue, cartes, tableaux de bord, formulaires, sites, OGC API, STAC/DCAT, RGPD) à coût de licence nul, mais est absent sur l'édition avancée (versioning, relations, domaines), le raster/imagerie, l'analyse réseau, le terrain hors ligne, la haute disponibilité et l'écosystème mobile. Plusieurs écarts supposés n'en sont pas (état au 12.0/12.1, §3.8) : Insights et GeoAnalytics Server sont retirés, GeoEvent est déprécié au profit de Velocity, Hub dans Enterprise se réduit à « Enterprise Sites » (ni initiatives, ni événements, ni open data API, ni DCAT) ; Esri n'a ni audit dédié, ni anonymisation RGPD, ni RLS par utilisateur.

### 1.2 Chiffres (voir méthode §1.3)

Les chiffres du tableau ci-dessous sont calculés mécaniquement sur les lignes des matrices du §2 et §3 (colonne verdict). Ils mesurent la couverture des **lignes que j'ai choisi d'écrire**, pas un volume de fonctionnalités pondéré : un biais de sélection existe (j'ai davantage détaillé les domaines où l'écart est instructif).

| Produit | Lignes | ISO | MOINS BIEN | MIEUX | ABSENT | ISO+MIEUX | dont lignes sourcées (concurrent) |
|---|---|---|---|---|---|---|---|
| FME (§2.1, 2.2, 2.4, 2.5) | 62 | 12 (19 %) | 24 (39 %) | 7 (11 %) | 19 (31 %) | 19 (31 %) | 42 lignes ; ISO+MIEUX 6 (14 %) |
| ArcGIS Enterprise (§3, avant reprise) | 112 | 41 (37 %) | 28 (25 %) | 20 (18 %) | 23 (21 %) | 61 (54 %) | 25 lignes non « non vérifié » ; ISO+MIEUX 10 (40 %) |
| ArcGIS Enterprise (§3, après reprise sourcée) | 131 | 51 (39 %) | 30 (23 %) | 22 (17 %) | 28 (21 %) | 73 (56 %) | **69 lignes S (53 %)** ; ISO+MIEUX 40 (58 %) |

Lecture : « équivalence ou mieux » = ISO + MIEUX. Le catalogue de transformers (§2.3) est décompté à part : 110/290 `implemented` (37,9 %). Esri après reprise : 131 lignes = 69 S (53 %), 37 R (28 %), 9 D (7 %), 16 NV (12 %) ; 115 lignes sont désormais sourcées au sens large (S+R+D, contre 25 avant) et 61 d'entre elles sont ISO ou MIEUX (53 %). Le passage de 112 à 131 lignes vient de capacités ajoutées par les sources (Workforce, QuickCapture, Data Reviewer, Data Pipelines, Hub open data, effets visuels, statut de contenu, web tools, etc.) et de lignes scindées (Dashboards périodiques/temps réel, 3D Tiles/I3S) ; les écarts de pourcentage ne sont donc pas uniquement des changements de verdict. Les lignes FME restent à 42/62 sourcées : seuls les pourcentages Esri ont été recalculés dans cette reprise.

### 1.3 Méthode de décompte

- Chaque ligne de matrice porte un verdict unique parmi : ISO (capacité équivalente pour l'usage visé), MOINS BIEN (existe mais plus étroite ou moins robuste), MIEUX (GeoStudio fait plus ou plus sûr), ABSENT (aucune capacité équivalente dans le code).
- Le pourcentage = lignes du verdict / lignes totales du produit, sans pondération. Un second pourcentage restreint aux lignes de confiance S (page officielle lue) pour Esri ; pour FME, aux lignes dont la colonne concurrent ne contient pas « non vérifié ». Une capacité retirée chez Esri (Insights, GeoAnalytics) ou non offerte sur Enterprise (initiatives Hub, feeds DCAT) est notée ISO si GeoStudio ne l'a pas non plus, MIEUX s'il l'offre, avec une mention en colonne « Statut Esri ».
- Pour les transformers FME, un décompte séparé et **exact** est donné à partir de `docs/revue/matrice-couverture-fme.jsonl` (290 lignes) : il ne dépend pas de mon jugement mais de la méthode de catégorisation de la matrice (match 1:1 exigé).
- Les verdicts de GeoStudio s'appuient sur un `chemin:ligne` lu dans le code. Là où le récit (CLAUDE.md, matrice) diverge du code, le code prime et l'écart est signalé (§6).

### 1.4 Positionnement synthétique

| Axe | vs FME | vs ArcGIS Enterprise |
|---|---|---|
| Largeur fonctionnelle | très inférieur (transformation) | inférieur (SIG complet), proche sur la couche « web » |
| Gouvernance / sécurité | supérieur (RLS, audit, SSRF, secrets) | proche (rôles/privilèges, SSO, MFA), supérieur sur RLS par utilisateur, audit dédié et RGPD (Esri : filtres de vue seulement, journaux de portail, pas d'anonymisation) |
| Ouverture / standards | supérieur (OGC Part 4, STAC, DCAT, MCP) | supérieur sur STAC/DCAT (Hub Enterprise Sites n'expose pas de feed DCAT-AP, §3.1), inférieur sur OWS (WMS/WFS/WMTS/WCS : support officiel confirmé [S17]) |
| Coût / licence | Apache-2.0 vs licence commerciale | Apache-2.0 vs licences par type d'utilisateur [S12] |
| Exploitation | inférieur (HA, retry, rétention) | très inférieur (HA, fédération) ; Esri : HA limitée à un datacenter, Kubernetes x86_64 seulement (GeoStudio publie arm64) |

---

## 2. FME (Form, Flow, Flow Hosted, Hub)

Périmètre FME retenu : Form (poste, auteur de workspaces), Flow (serveur : jobs, schedules, automations, apps), Flow Hosted, Hub (échange de transformers/formats). Source générale : revendications de ~400+ transformers et 300 à 450+ formats [S2][S3] ; aucun décompte officiel daté n'a pu être récupéré, donc la matrice du dépôt (290 transformers) est un **sous-ensemble recensé**, pas le catalogue complet.

### 2.1 Readers (sources de données)

Réalité GeoStudio : 10 readers dans `OPERATIONS` (`pipelines/ops/contracts.py:158` : `reader.collection`, `.file`, `.connector.rest/postgres/snowflake/bigquery/mssql/oracle/databricks/blob`). Les formats fichiers (GeoJSON, CSV, XLSX, GPKG, SHP zip, KML/KMZ, GML, JSONL, XML, Parquet) passent par l'**ingestion** (`ingestion/importer.py:82-103`), pas par un reader de pipeline ; `reader.file` (DuckDB spatial) est gardé par `CORE_PIPELINE_FILE_IO_ENABLED`, défaut off (`pipelines/ops/contracts.py:612`).

| Capacité | Chez FME | Chez GeoStudio | Verdict | Effort | Priorité |
|---|---|---|---|---|---|
| Reader PostGIS / PostgreSQL | Reader PostGIS (non vérifié, connaissance générale) | `reader.connector.postgres` (`pipelines/ops/contracts.py:295`) | ISO | n/a | n/a |
| Reader Snowflake / BigQuery / MSSQL / Oracle / Databricks | Readers dédiés (non vérifié) | `reader.connector.snowflake/bigquery/mssql/oracle/databricks` (`pipelines/ops/contracts.py:300-320`) | ISO | n/a | n/a |
| Redshift | Reader (non vérifié) ; la matrice le classe `implemented` | via connecteur Postgres/ODBC : à confirmer (`docs/revue/matrice-couverture-fme.jsonl`) | ISO | S | basse |
| REST/HTTP en lecture paginée | HTTPCaller [S1] | `reader.connector.rest` via dlt (`pipelines/connector_runtime.py:442`) et `transform.httpCall` (`pipelines/ops/contracts.py:624`) | ISO | n/a | n/a |
| Stockage objet (S3, Azure Blob, GCS) | S3Connector, AzureBlobStorageConnector, GoogleCloudStorageConnector (matrice) | `reader.connector.blob` lié à un bucket par secret (`pipelines/ops/contracts.py:325`) | ISO | n/a | n/a |
| Fichier local / uploadé en pipeline | Reader de n'importe quel format | `reader.file` hors périmètre serveur par défaut (`pipelines/ops/contracts.py:612`) | MOINS BIEN | M | moyenne |
| Shapefile / GeoJSON / GPKG / KML / GML en reader de pipeline | Natif (matrice : `planned_gdal`) | absent en op ; présent en import (`ingestion/importer.py:82-103`) | MOINS BIEN | M | haute |
| FileGDB, DXF, DGN, MapInfo TAB/MIF, OSM, CityGML, CityJSON | Natif (matrice) | absent (aucun parser : `ingestion/parsers.py`) | ABSENT | L | moyenne |
| WFS / WMS / WCS comme source | Readers (matrice : `planned_gdal`) | aucun reader ; le moissonnage lit GetCapabilities mais ne lit pas les features en pipeline (`harvest/connectors/__init__.py:13-20`) | ABSENT | M | moyenne |
| LAS/LAZ, EPT, E57 (nuage de points) | Readers (matrice : `planned_pdal`) | absent | ABSENT | L | basse |
| Rasters (GeoTIFF, NetCDF, JPEG2000, GRIB) | Readers (matrice) | absent côté pipeline ; TiTiler/Martin en infra (`docker-compose.yml:114,168`) | ABSENT | L | moyenne |
| Excel multi-feuilles | Reader Excel (matrice : `planned_duckdb`) | import XLSX seulement (`ingestion/importer.py:88`) | MOINS BIEN | S | moyenne |
| MongoDB, Google Sheets, Salesforce, LDAP | Readers (matrice) | absent | ABSENT | M | basse |
| Sources ArcGIS (Feature Service) | Readers Esri (matrice, liste Esri [S9]) | connecteur de moissonnage `arcgis` + `source: "arcgis"` d'un dataset (`harvest/connectors/__init__.py:14`, `configs/schemas.py:87`) | ISO | n/a | n/a |
| Connecteurs SaaS (Box, Dropbox, OneDrive, SharePoint, Slack, Trello, Kinesis, RabbitMQ…) | ~24 connecteurs (matrice : `planned_duckdb`) | absent | ABSENT | L | basse |
| Lecture CDC (réplication logique) vers lac | non vérifié | worker `wal2json` → GeoParquet (`cdc/consumer.py:3`) | MIEUX | n/a | n/a |

### 2.2 Writers

| Capacité | Chez FME | Chez GeoStudio | Verdict | Effort | Priorité |
|---|---|---|---|---|---|
| Écriture en collection (insert) | Writers base de données | `writer.collection` mode `append`/`replace` (`pipelines/ops/schemas.py:55`) | ISO | n/a | n/a |
| Upsert / update / delete par clé | Feature operation par feature (Insert/Update/Delete) : non vérifié dans les sources collectées | absent ; `detectChanges` produit le statut mais rien ne l'applique (`pipelines/ops/contracts.py:541`, `pipelines/ops/schemas.py:55`) | ABSENT | M | haute |
| Écriture transactionnelle par lots | non vérifié | `insert_features` par lots, abandon du run à la 1re ligne invalide (`pipelines/runtime.py:1033`) | MOINS BIEN | M | haute |
| Export fichier (GeoJSON, CSV) | Writers 300+ formats [S2] | `writer.export` geojson/csv seulement (`pipelines/ops/schemas.py:66`) | MOINS BIEN | M | moyenne |
| Export GPKG / XLSX | Writers | présent hors pipeline : `analytics/export.py:40`, `dataexport/routes.py:102` | MOINS BIEN | S | moyenne |
| Écriture dataset (objet de plateforme) | n/a | `writer.dataset` (`pipelines/ops/contracts.py:285`) | MIEUX | n/a | n/a |
| Écriture fichier local | tous formats | `writer.file` derrière flag (`pipelines/ops/contracts.py:618`) | MOINS BIEN | M | basse |
| Écriture Shapefile / FileGDB / DXF / KML / GML | Natif | absent | ABSENT | L | moyenne |
| Écriture Parquet / GeoParquet | Reader/Writer Parquet (matrice `implemented`) | écriture du lac par le CDC (`cdc/parquet_writer.py`), pas de writer de pipeline | MOINS BIEN | S | moyenne |
| Écriture bases distantes (Snowflake, BigQuery, Oracle…) | Writers symétriques | absent : readers seulement | ABSENT | L | moyenne |
| Écriture vers services (ArcGIS FS, WFS-T, REST POST) | Writers / HTTPCaller | `transform.httpCall` POST par ligne, pas de writer ArcGIS (`pipelines/ops/contracts.py:624`) | MOINS BIEN | M | moyenne |

### 2.3 Catalogue des transformers par famille (compte exact)

Décompte exact depuis `docs/revue/matrice-couverture-fme.jsonl` (290 transformers FME recensés ; `implemented` = match 1:1 avec une op existante).
Registre actuel : **61 op** dans `OPERATIONS` (47 `transform`, 10 `reader`, 4 `writer` ; mesure par import le 2026-10-11, `pipelines/ops/contracts.py:158`). Plusieurs transformers FME partagent une même op (les 5 `*Reprojector` -> `transform.reproject`), d'où 110 `implemented` pour 47 op de transformation.
Note : le brut est 61 mais le catalogue exposé par `GET /v1/pipelines/ops` (`pipelines/routes.py:73`) en filtre certaines selon des flags ; le récit parle de 59 exposées.

| Famille FME | Recensés | `implemented` | Non couverts, principaux manques | Verdict famille | Effort | Priorité |
|---|---|---|---|---|---|---|
| Attribute | 21 | 17 (81 %) | AttributeManager (composition), DatabaseJoiner, Matcher, AggregateFilter | ISO | S | basse |
| Coordinate System | 28 | 20 (71 %) | MGRS, CoordinateSystemRemover, georeferencement raster (GCP) | ISO | S | basse |
| Database | 10 | 0 | DatabaseQuerier/Updater/Deleter, SQLCreator, SQLExecutor, InlineQuerier | ABSENT | M | haute |
| Filtering & Routing | 12 | 5 (42 %) | TestFilter, GeometryFilter, AttributeRangeFilter, Sampler, SpatialRelator, NeighborFinder | MOINS BIEN | M | haute |
| Geometry | 35 | 19 (54 %) | Triangulator (déjà TIN via `triangulate`), VertexRemover, SpikeRemover, AreaGapAndOverlapCleaner, AreaBuilder, Intersector, LineOnAreaOverlayer, Chopper, GeometryCoercer, RubberSheeter, AffineWarper | MOINS BIEN | M | moyenne |
| Integrations | 41 | 3 (7 %) | 24 connecteurs SaaS/queues, Emailer, Slack, Geocoder, MCPCaller, FTPCaller, CKANConnector | ABSENT | L | moyenne |
| Point Cloud | 16 | 1 | 13 transformers PDAL | ABSENT | L | basse |
| Raster | 22 | 0 | 5 retirés par décision (`capability_removed`), 13 `planned_gdal`, 3 OTB | ABSENT | L | moyenne |
| Readers/Writers (formats) | 52 | 11 (21 %) | 23 formats GDAL, 6 bloqués par licence (DWG, ECW, MrSID, Revit, ArcSDE, RDB) | MOINS BIEN | L | haute |
| Schema/Feature Type | 9 | 8 (89 %) | FeatureTypeFilter | ISO | S | basse |
| String/Text | 28 | 22 (79 %) | TextEncoder/Decoder, HTMLExtractor, NLP | ISO | S | basse |
| Workflow / Logic | 16 | 4 (25 %) | Terminator, ParameterFetcher, PythonCaller ; 9 hors périmètre (FeatureHolder, Logger, Inspector, VariableSetter…) | MOINS BIEN | M | moyenne |
| **Total** | **290** | **110 (37,9 %)** | | | | |

Autres statuts (total 290) : `planned_duckdb` 50, `planned_gdal` 55, `planned_pdal` 16, `planned_otb` 3, `planned_rust` 2, `license_blocked` 10, `out_of_scope` 25, `capability_removed` 7, `unknown` 12.

Observations vérifiées :

- Les lignes `implemented` des familles Attribute/String/Coordinate System sont presque toutes des **expressions SQL DuckDB** dans `transform.derive`/`select`/`filter` (`pipelines/ops/contracts.py:164-188`) : couverture réelle mais ergonomie différente (un nœud d'expression au lieu d'un transformer dédié par action).
- Plusieurs transformers `planned_duckdb` (AttributeManager, DatabaseJoiner, AggregateFilter) sont atteignables **aujourd'hui** par composition de 2 op ; la matrice les classe volontairement `planned` (match 1:1 exigé) : la couverture fonctionnelle réelle est donc supérieure à 37,9 %, de façon non chiffrée.
- Le catalogue FME est estimé à plus de 400 transformers [S2] : rapportées à ce total non daté, les 110 `implemented` représentent au plus 27 %. Chiffre à ne pas citer sans mention de la source.
- Aucune op de **réseau** (isochrones, routage), de **géocodage en lot**, de **déduplication floue** (Matcher), de **raster** : cf. matrice.

### 2.4 Exécution et exploitation (FME Form + Flow)

| Capacité | Chez FME | Chez GeoStudio | Verdict | Effort | Priorité |
|---|---|---|---|---|---|
| Ports Rejected (sortie des features invalides) | Nombreux transformers ont un port `<Rejected>` ; paramètre de workspace pour stopper au 1er rejet [S4] | aucun : une ligne invalide fait échouer tout le run (`pipelines/runtime.py:1033`) | ABSENT | M | haute |
| Mode incrémental / delta | non vérifié (patron « dernier run » à gérer par l'utilisateur d'après [S8]) ; ChangeDetector présent | `detectChanges` en transformation (`pipelines/ops/contracts.py:541`) ; pas d'état par nœud reader (`pipelines/connector_runtime.py:442`) | MOINS BIEN | M | haute |
| Retry automatique d'un job | Resubmission après perte de moteur, défaut 3 [S7] ; retry des actions d'automation avec backoff [S5-S6] | aucun retry de run (`pipelines/jobs.py:209`) ; reprise des runs bloqués seulement (`pipelines/jobs.py:302`) | MOINS BIEN | M | moyenne |
| Paramètres publiés | Paramètres publiés / visibles demandés au lancement, par API [S8] | pas de paramètres de run (`pipelines/routes.py:94`) ; variables CEL côté App, pas côté pipeline | ABSENT | M | haute |
| Planification | Basic, intervalle, CRON, fuseau du serveur, « skip if job in progress », expiry de job [S6] | cron validé par `croniter`, évaluation en UTC (`configs/schemas.py:281`, `pipelines/repository.py` list_due_pipelines), un seul run actif par pipeline (`pipelines/jobs.py:316`) | MOINS BIEN | S | moyenne |
| Déclencheurs | Schedule, manuel, email IMAP, dossier/S3/FTP, événements système, webhooks [S5][S1] | cron + déclenchement manuel + jeton webhook entrant (`pipelines/routes.py:198-240`) ; pas de déclencheur sur fichier/S3/événement | MOINS BIEN | M | moyenne |
| Chaînage (sortie succès/échec vers action) | Ports de succès et d'échec par composant d'automation [S5] | chaînage par notification seulement (`pipelines/jobs.py:73`) ; webhook sortant uniquement côté alertes (`alerts/notify.py:52`) | MOINS BIEN | M | moyenne |
| Webhooks sortants génériques | créer et consommer des webhooks [S1] | `send_webhook` réservé aux alertes (`alerts/notify.py:52`) | MOINS BIEN | M | moyenne |
| Annulation d'un run | non vérifié | `POST /pipelines/{id}/runs/{run}/cancel` + vérif entre lots (`pipelines/routes.py:116`, `pipelines/runtime.py:1040`) | ISO | n/a | n/a |
| Aperçu d'un nœud | Data Inspector / feature caching (non vérifié) | `POST /pipelines/{id}/preview`, autorisation `write` (`pipelines/routes.py:171`) | ISO | n/a | n/a |
| Lineage / traçabilité des données | Lineage et Feature Counts (non vérifié) ; Flow Job history | champ `lineage` texte libre par collection (`collections/models.py:72`) ; pas de graphe amont/aval | ABSENT | M | moyenne |
| Journal d'exécution / logs | Log de job complet (non vérifié) | statistiques par nœud (`pipelines/jobs.py:129`), liste de runs (`pipelines/routes.py:154`), audit des runs planifiés (`pipelines/jobs.py:316-330`) | MOINS BIEN | S | moyenne |
| Rétention des jobs / requeue en un clic | Rétention et requeue configurables [S7] | non configuré (`docker-compose.yml:518` worker) ; pas de bouton de rejeu | MOINS BIEN | M | moyenne |
| Modèles / galerie de templates de pipeline | FME Hub (échange de transformers, templates) (non vérifié) | 4 gabarits d'App seulement (`shell/src/builder/templates.ts:232`) ; aucun gabarit de pipeline | ABSENT | M | basse |
| Transformer personnalisé (custom transformer / PythonCaller) | PythonCaller, custom transformers (matrice : `planned_duckdb`) | aucune extension de pipeline ; extensions widgets seulement (`extensions/routes.py:32`) | ABSENT | L | moyenne |
| Pipeline déclaratif, versionné, diffable | Workspace binaire/XML (non vérifié) | JSON schématisé (`configs/schemas.py:246`), historique + rollback (`configs/routes.py:263,276`), `If-Match` 412 (`configs/routes.py:61`) | MIEUX | n/a | n/a |
| Validation de topologie à l'écriture | non vérifié | `config_validation.py` + modèle (`configs/schemas.py:312-314`) | ISO | n/a | n/a |
| Secrets et connexions | Connexions partagées de FME Flow (non vérifié) | coffre AES-GCM, liaison à `baseUrl`/`bucketUrl`, rotation (`secrets/routes.py:42`, `secrets/rotation.py:28`) | MIEUX | n/a | n/a |
| Garde SSRF / egress | non vérifié | garde dédiée + épinglage DNS (`pipelines/egress.py:51`, `net_pin.py`) | MIEUX | n/a | n/a |
| Pilotage par IA / MCP | non vérifié (aucune source collectée) | outils `create_pipeline`, `run_pipeline`, `explain_pipeline` (`mcp/tools/pipelines.py:46`) | MIEUX | n/a | n/a |
| FME Flow : moteurs multiples, files, haute dispo | Engines multiples, files, clusters (non vérifié) | file procrastinate `etl`, worker unique dans le compose (`docker-compose.yml:501`) | MOINS BIEN | L | basse |
| Apps / workspace apps FME Flow | Workspace Apps, Streams, Notifications (non vérifié) | Apps, dashboards et sites via builder (`configs/schemas.py:469`) | ISO | n/a | n/a |
| API d'exécution (REST) | REST API v3 de soumission de jobs [S-REST: https://support.safe.com/hc/en-us/articles/25407519073165-Submitting-a-Job-through-the-FME-Flow-REST-API-V3] | `POST /v1/pipelines/{id}/run` + `/trigger` (`pipelines/routes.py:94,240`) | ISO | n/a | n/a |
| Échelle : lecture/écriture volumétrique (moteur) | Moteur propriétaire multi-cœur | DuckDB en process avec plafonds (`analytics/aggregate.py`, `pipelines/runtime.py`) | MOINS BIEN | L | basse |
| Géocodage en pipeline | Geocoder (matrice : `planned_duckdb`) | BAN en REST/MCP seulement (`geocoding/routes.py:22`, `geocoding/provider.py:46`) | ABSENT | S | moyenne |
| Licences / coût | Licences commerciales Form/Flow (non vérifié, aucun tarif collecté) | Apache-2.0 | MIEUX | n/a | n/a |

### 2.5 Formats (vue consolidée)

| Famille de formats | FME | GeoStudio (import / export / pipeline) | Verdict |
|---|---|---|---|
| Vecteur courant (SHP, GeoJSON, GPKG, KML, GML, CSV, XLSX, JSONL, Parquet) | natif lecture + écriture | import : tous (`ingestion/importer.py:82-103`) ; export : csv/xlsx/geojson/gpkg (`analytics/export.py:40`) ; pipeline : csv/geojson seulement | MOINS BIEN |
| CAO / BIM (DWG, DXF, DGN, IFC, Revit) | natif ; IFC ajouté en 2025.2 [S9] | absent | ABSENT |
| Bases géodatabase Esri (FileGDB, ArcSDE) | natif (matrice : FileGDB `planned_gdal`, ArcSDE `license_blocked`) | absent (lecture via FeatureServer moissonné seulement) | ABSENT |
| Raster / MNT / imagerie | natif | absent en pipeline ; TiTiler en infra ; terrain RGB via `terrain3d` (`terrain3d/routes.py:157`) | ABSENT |
| 3D (CityGML, CityJSON, 3D Tiles, IFC) | natif (matrice) | 3D Tiles hébergés (`tileset3d/routes.py:238`), pas de conversion | MOINS BIEN |
| Nuage de points | natif | absent | ABSENT |
| Delta Lake / formats lac | Delta Lake reader 2025.2 [S9] | GeoParquet maison (`cdc/parquet_writer.py`) ; Iceberg différé | MOINS BIEN |
| Services web OGC (WFS/WMS/WCS) | readers | uniquement moissonnage de métadonnées | MOINS BIEN |
| Total annoncé | « 450+ » (source commerciale non datée) [S2][S3] | ~10 formats d'import | MOINS BIEN |

### 2.6 Verdict FME en une phrase

GeoStudio n'est **pas** un remplaçant de FME : il couvre le noyau « transformer des données tabulaires/vecteur, les charger dans le lac ou une collection, sur planning », avec une gouvernance supérieure, mais il manque la largeur formats, les fonctions d'exploitation d'ETL (rejected, incrémental, upsert, paramètres, retry) et tout le raster/nuage de points.

---

## 3. ArcGIS Enterprise (Portal, Server, Data Store, Notebooks, Hub/Enterprise Sites, mobile)

Architecture de référence : Portal for ArcGIS + ArcGIS Server (rôles hosting, image, GeoEvent, notebook, workflow manager, knowledge, vidéo ; GeoAnalytics retiré) + Data Stores (relationnel, objet, spatiotemporel, graphe) [S10][S34]. Licences par type d'utilisateur (Viewer, Contributor, Mobile Worker, Creator, Professional, Professional Plus) [S12][S62]. Versions de référence au 2026-10-11 : 11.5 (LTS), 12.0 (STS, 18 novembre 2025), 12.1 (premier LTS 12.x) : voir §3.8.

Lecture des tableaux : colonne **Statut Esri** = état de la capacité chez l'éditeur (« actif » sauf mention : retiré, déprécié, bêta, extension payante) ; colonne **Conf.** = niveau de confiance de la ligne : **S** page officielle lue ; **R** résumé de résultat de recherche sur page officielle non relue (ou miroir) ; **D** déduit ; **NV** non vérifié (connaissance générale). Règle de verdict : une capacité **retirée** chez Esri (Insights, GeoAnalytics, Web AppBuilder) ou **non offerte sur Enterprise** (initiatives Hub, feeds DCAT) ne compte pas comme écart : verdict ISO si GeoStudio ne l'a pas non plus, MIEUX s'il l'offre.

### 3.1 Données et services

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Feature Services (REST édition/requête) | Capacités Query, Create/Update/Delete, Editing, Sync, Extract, ChangeTracking (11.0) ; pagination `resultOffset`, plafond `maxRecordCount` ; formats json/geojson/pbf [S19][S20] | OGC API Features Part 1+4 : lecture, création, remplacement, suppression (`features/routes.py:228,732,784,842`) | MOINS BIEN | M | haute | actif | S |
| Requêtes : where libre, tri, statistiques, plein texte | `where` SQL-92 ; `orderByFields` ; `outStatistics` count/sum/min/max/avg/stddev/var + percentiles (10.8), `groupBy`, `having` ; `fullText` (11.4) ; `time` ; `outSR` WKT2 (11.2) [S20] | filtres égalité/`__in`/`__gte`/`__lte`, bbox, geom_intersects, pas de `sortby`, tri par PK seule (`features/repository.py:102,115,204`) ; agrégats via `POST /collections/{id}/aggregate` (`features/routes.py:308`) | MOINS BIEN | M | haute | actif | S |
| CQL2 / datetime / CRS en sortie | `time` (instant ou intervalle) et `outSR` natifs [S20] ; CQL2 : non vérifié | absents (`features/routes.py:228`, conformité limitée `features/routes.py:84-90`) | ABSENT | M | moyenne | actif | S |
| Services OGC OWS (WMS, WMTS, WFS, WCS, WPS) | WMS, WMTS, WFS, WCS, WPS et OGC API Features, à activer explicitement par service ; sécurité héritée du service parent [S17]. CSW, OGC API Tiles/Maps, KML : non mentionnés par la page | absents ; tuiles MVT propres (`features/tiles.py:241`) | ABSENT | L | moyenne | actif | S |
| Vector Tile Services | Hosted vector tile layers depuis 10.4, pbf 512 px, Export Tiles, upload `.vtpk`, éditeur de style sans régénération des tuiles [S21] | MVT dynamiques `ST_AsMVT`, plafond 5000 entités/tuile, RLS appliquée (`features/tiles.py:47,241`) | ISO | n/a | n/a | actif | S |
| Tuiles agrégées / clustering serveur | Clustering (11.3) et binning points/lignes/polygones (11.5) côté Map Viewer [S38] ; GeoAnalytics (retiré) | absent côté serveur ; `HexagonLayer` client (`shell/src/map/mapDeckTerrain.ts:24`) ; aucun clustering dans la carte | MOINS BIEN | S | moyenne | actif | R |
| Image Services / raster | Image Server : mosaic datasets, services dynamiques (WMS/WCS/WMTS/KML), raster analytics, fonctions Python custom, Deep Learning Studio [S53] | absent ; TiTiler non exposé aux utilisateurs (`docker-compose.yml:168`) | ABSENT | L | moyenne | actif (rôle serveur sous licence dédiée) | S |
| OGC API : Features lecture | Service `OGCFeatureServer`, page de 3000 par collection par défaut, listé depuis 11.1 [S18][S17] | oui (`features/routes.py:93,118`) | ISO | n/a | n/a | actif | S |
| OGC API Features Part 4 (écriture) | Non vérifié : les pages lues ne décrivent que la lecture ; l'édition passe par le Feature Service REST [S18] | oui : `conf/create-replace-delete` (`features/routes.py:85-90`) | MIEUX | n/a | n/a | actif | D |
| STAC | Aucun service STAC trouvé dans les pages Esri lues | API STAC native + search GET/POST (`stac/routes.py:111,457,490`) | MIEUX | n/a | n/a | non trouvé | D |
| DCAT-AP / feeds de catalogue | Feeds DCAT US 1.1, DCAT-AP 2.1.1/3.0.0, RSS, OGC API Records : Hub Online seulement, la page porte « not relevant for Hub in ArcGIS Enterprise » ; Enterprise Sites sans API/téléchargements open data [S49] | export DCAT-AP (`dcat/routes.py:122,161`) | MIEUX | n/a | n/a | absent d'Enterprise (Hub Online seulement) | S |
| Moissonnage / fédération de catalogues | Fédération Portal/Server = rattachement de serveurs, pas moissonnage de catalogues tiers ; le moissonnage Hub est Online : non vérifié pour Enterprise | 7 connecteurs : STAC, ArcGIS FS, WMS, WFS, WMTS, CSW, OGC Records, CKAN (`harvest/connectors/__init__.py:13-20`) | MIEUX | n/a | n/a | actif | D |
| Géodatabase d'entreprise (schémas, topologies) | Enterprise geodatabase : sous-types, domaines, relationship classes, topologies (en feature service : données enregistrées en branch versioning), jeux de données d'entités [S26][S28] | PostGIS direct avec registre de collections (`collections/routes.py:421,625`) | ABSENT | L | basse | actif | R |
| Formats d'import / interopérabilité | L'import avancé passe par l'extension serveur Data Interoperability = FME embarqué (FME 2025.1.2 en 12.0, FME 2026.1 en 12.1), payante ; voir §2 [S58] | 10 formats (`ingestion/importer.py:82-103`) | MOINS BIEN | M | moyenne | actif (extension payante) | S |
| Export de données | Capacité Extract du Feature Service ; action « Export data » d'Experience Builder (Shapefile/FGDB/KML) depuis 12.0 [S19][S46] | CSV/XLSX/GeoJSON/GPKG asynchrones (`dataexport/routes.py:102`, `export/routes.py:69`) | ISO | n/a | n/a | actif | R |
| Scene layers (I3S) | Scene service I3S depuis 10.3.1, 6 types (objet 3D, bâtiment, maillage intégré, points, nuage de points, voxel) ; caches de scene layers hébergés vers l'object store dès 11.4 ; tile cache data store retiré en 12.0 [S22][S34] | 3D Tiles hébergés + proxy authentifié (`tileset3d/routes.py:92,238`) | MOINS BIEN | M | basse | tile cache store retiré (12.0) | S |
| OGC 3D Tiles | 3D Tiles 1.1 partiel (extensions 1.0 seulement) : `.b3dm` oui, `.i3dm`/`.pnt`, implicit tiling, multiple contents non ; seul l'integrated mesh est visualisable dans Scene Viewer ; service 3D Tiles publiable depuis Enterprise 11.5 [S43] | `Tile3DLayer` deck.gl + hébergement de tilesets (`shell/src/map/mapDeckTerrain.ts:47`, `tileset3d/routes.py:238`) ; aucune matrice de support par extension établie | ISO | n/a | n/a | 3D Tiles 1.1 partiel côté Esri | S |
| Interrogation SQL analytique | Pas de SQL libre natif trouvé (Insights : requête SQL non trouvée) | SQL Lab sandboxé DuckDB (`features/routes.py:595`, `analytics/sql_sandbox.py`) | MIEUX | n/a | n/a | actif | D |
| Lac de données / CDC | Big data store spatiotemporel : au moins 3 machines, 2 copies [S68] ; GeoAnalytics retiré | CDC logique -> GeoParquet, compaction, `asOf` (`cdc/consumer.py`, `analytics/snapshot.py`) | ISO | n/a | n/a | actif | S |
| Jointures hébergées / vues jointes | Vue jointe hébergée (left/inner, 1-1 ou 1-N), lecture seule, définition non modifiable, inutilisable hors ligne ; outil Join Features du Map Viewer (sortie couche ou table hébergée) [S24] | `transform.join` en pipeline et jointure de requête visuelle (`pipelines/ops/contracts.py:196`) ; pas de vue jointe persistante servie en tuiles | ISO | n/a | n/a | actif | R |

### 3.2 Édition

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Édition multi-utilisateurs avec versioning de branche | Branch versioning : parent Default uniquement, reconcile puis post, conflits traités par ligne sur plusieurs sessions, archivage temporel natif, sync service à service (11.3), webhooks de service [S28][S19] | absent : écriture directe sans version (`features/repository.py:303,407,446`) | ABSENT | L | basse | actif | S |
| Historique d'entités / time travel | `ChangeTracking` (capacité 11.0) [S19] ; archivage de géodatabase : non lu en détail | `asOf` sur le lac seulement (`analytics/snapshot.py`) ; pas de journal avant/après par entité (`features/routes.py:784`) | ABSENT | M | haute | actif | R |
| Domaines et sous-types d'attributs | Domaines de liste et de plage (terminologie 12.0), sous-types portant valeurs par défaut et domaines propres [S26][S36] | enum / types simples (`collections/introspection.py:13`) ; formulaires générés | MOINS BIEN | M | moyenne | actif | R |
| Validation à l'écriture / règles d'attributs | Attribute rules : calcul et contrainte immédiats, calcul batch et validation différés ; sur couches web, validation et batch exigent l'extension Advanced Editing (11.2+) [S27] | validateur de type/obligatoire seulement (`features/validation.py:1-25`) ; ni règle de calcul ni contrainte métier | MOINS BIEN | M | moyenne | actif (extension payante) | R |
| Relations / classes de relations | Relationship classes 1-1, 1-N, N-N ; ressource Relationships sur services hébergés (11.1), related records [S26][S19] | jointure de requête visuelle (`pipelines/ops/contracts.py:196`), pas de relations 1-N en édition | ABSENT | L | moyenne | actif | S |
| Pièces jointes | Attachments : `addAttachment` (depuis 10.0), `hasAttachments`, 10 Mo sur ArcGIS Online, jusqu'à 2 Go via le répertoire REST [S23] | S3 présigné, proxy authentifié, 25 Mo (`attachments/routes.py:171,277,298`) | ISO | n/a | n/a | actif | R |
| Contrôle de concurrence | Conflits via versions de branche [S28] | `If-Match` sur configs, aucun sur features (`configs/routes.py:61`) | MOINS BIEN | S | moyenne | actif | R |
| Édition hors ligne | Offline areas : Enterprise geodatabase obligatoire, Global IDs, sync à activer, 16 zones max par carte, échec au-delà de 4 Go, éditions refusées si contrôle d'accès par propriétaire [S29][S30] | absent ; seule une bannière de connectivité (`shell/src/shell/ConnectivityBanner.tsx`) | ABSENT | L | moyenne | actif | S |
| Collecte terrain (Field Maps) | Field Maps depuis Enterprise 10.8.1 ; édition réservée à Mobile Worker/Creator/Professional ; hors ligne exige une géodatabase d'entreprise [S30] | formulaire d'App en ligne (`shell/src/builder/widgets/form.tsx`) | MOINS BIEN | L | moyenne | actif | S |
| Enquêtes (Survey123) | Depuis 10.9.1 ; XLSForm ; site web 3.26 exige 11.5 ; app terrain 3.x en correctifs seulement, nouvelle app en préversion [S31] | générateur d'App formulaire `create_form_app` (`mcp/form_app.py`) | MOINS BIEN | M | moyenne | app terrain en maintenance | S |
| Soumission citoyenne publique avec modération | Survey123 anonyme (11.4+) : web et terrain, sondages publics sans compte, résultats anonymes seulement si partagés publiquement [S31] | écriture OGC authentifiée seulement (`features/routes.py:732`) | ABSENT | M | haute | actif | S |
| Tracking GPS / Mobile Worker | Location Sharing inclus dans Mobile Worker (11.0+) ; suivi de position dans le widget Map d'Experience Builder 12.1 [S30][S46] | absent | ABSENT | L | basse | actif | S |
| Affectation de tâches (Workforce) | Workforce déprécié, retrait d'Enterprise prévu avec 12.2 ; remplacé par Tasks dans Field Maps (11.5+) [S32] | absent | ABSENT | L | basse | déprécié (retrait 12.2) | R |
| Capture rapide (QuickCapture) | Enterprise 10.8.1+ ; app pour Creator/Pro/Pro Plus, Mobile Worker app seule [S30] | absent | ABSENT | L | basse | actif | R |
| Contrôle qualité des données (Data Reviewer) | Extension Pro et Enterprise ; revue automatisée par attribute rules (11.3) ; endpoint Write Errors (11.4) ; statut 12.0 non trouvé [S33] | `GET /collections/{id}/profile` (profilage, pas de règles de qualité) (`features/routes.py:362`) | ABSENT | M | basse | actif (extension) | R |
| Géocodage / recherche d'adresse | Locator partagé depuis Pro -> service de géocodage fédéré ; locators composites ; géocodage par lot générique non confirmé hors locator Business Analyst [S61] | BAN en recherche, un résultat à la fois, pas de lot ni de reverse (`geocoding/routes.py:22`, `geocoding/provider.py:46`) ; MCP `geocode` (`mcp/tools/geocode.py:23`) | MOINS BIEN | S | moyenne | actif | R |
| Limites géographiques d'édition (périmètre par rôle) | Vue de couche hébergée filtrée par emprise (AOI) : par vue, pas par utilisateur [S25] | geo-limits par utilisateur/groupe, RLS restrictive (`collections/geo_limits_routes.py:85`) | MIEUX | n/a | n/a | actif | S |

### 3.3 Cartographie, symbologie, 3D

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Map Viewer (couches, style, popups) | Map Viewer ; Map Viewer Classic déprécié (11.5 dernière version le supportant), retiré en 12.0 [S37][S34] | éditeur de carte MapLibre (`shell/src/pages/MapEditorPage.tsx`, `shell/src/map/MapView.tsx`) | ISO | n/a | n/a | Classic retiré (12.0) | S |
| Types de couches | feature, tuiles vectorielles, imagerie, scène, 3D tiles, vidéo time-enabled (12.0) [S37] | `vector`, `raster`, `feature`, `deck`, `tiles3d` (`configs/schemas.py:126`) | ISO | n/a | n/a | actif | R |
| Symbologie data-driven (catégoriel, classé, continu) | Styles Counts and Amounts, Dot Density, Color and Size, Compare A to B, Predominant category, Relationship, Charts, bivarié, spike ; normalisation, rotation et transparence par attribut ; Arcade dans le style [S37] | catégoriel, classé, continu, partagé éditeur/widget (`shell/src/builder/widgets/mapSymbology.ts:138-160`) ; aucun dot density, prédominance, relationship, bivarié (grep négatif sur `shell/src/map`) | MOINS BIEN | M | basse | actif | S |
| Symbologie avancée : icônes, étiquettes CEL, contour data-driven | Étiquettes champ/texte/Arcade, halo, placement automatique ; symboles animés (11.5) [S37][S38] | bibliothèque d'icônes par tenant (`mapicons/routes.py:101`), étiquettes CEL multi-champs, contour data-driven | ISO | n/a | n/a | actif | S |
| Effets visuels (bloom, ombre, modes de fusion) | Bloom, drop shadow, brightness/contrast ; 30+ modes de fusion (11.1+) [S39] | absent (aucune occurrence `blend`/`bloom` dans `shell/src/map`) | ABSENT | S | basse | actif | R |
| Popups configurables | Popups : expressions Arcade, graphiques, images, enregistrements liés, pièces jointes [S37] | gabarit CEL (`configs/schemas.py:109`, `shell/src/map/popupTemplate.ts`), pièces jointes (`attachments/routes.py`) | ISO | n/a | n/a | actif | S |
| Expressions de style (Arcade) | Arcade : langage portable, 26 profils (popups, labels, visualisation, règles d'attributs, dashboards, data pipelines…) [S45] | CEL (spike validé, `expr_validation.py`) ; moins de profils | ISO | n/a | n/a | actif | S |
| Légende | légende automatique : non vérifié | `MapLegend`, `MapSymbologyLegend` (`shell/src/map/MapLegend.tsx`) | ISO | n/a | n/a | actif | NV |
| Clustering de points | Regroupement de points proches, étiquettes et popups de cluster personnalisables (11.3) ; binning 11.5 [S38] | absent (aucune occurrence `cluster` dans `shell/src/map`) | ABSENT | S | moyenne | actif | R |
| Heatmap / hexbin | Style Heat map (points), incompatible avec le clustering ; binning (11.5) [S38] | deck.gl `HeatmapLayer`, `HexagonLayer` (`shell/src/map/mapDeckTerrain.ts:21-24`) | ISO | n/a | n/a | actif | R |
| Time slider / animation temporelle | Time slider (couche time-enabled, lecture, vitesse, intervalles) ; animation configurable par Arcade [S40] | widget `timePlayer` (`shell/src/builder/widgets/timePlayer.tsx`), non persisté dans la carte (`configs/schemas.py:122`) | MOINS BIEN | S | basse | actif | S |
| Mesure et croquis | Outil Measurement distance/aire (calcul géodésique sur ellipsoïde, Alt+Shift+M) ; Sketch avec courbes et galerie de symboles [S41][S36] | oui, haversine sphérique (`shell/src/map/measureSketch.ts:1-4`), écart d'ellipsoïde non quantifié | ISO | n/a | n/a | actif | S |
| Fonds de carte | Galerie alimentée par ArcGIS Online par défaut, remplaçable par groupe admin (10.9.1) [S37] | quelques fonds publics MapLibre/Carto (`shell/src/map/basemaps.ts:5-12`) ; pas de galerie d'organisation | MOINS BIEN | S | basse | actif | R |
| Terrain 3D / élévation | Couches d'élévation dans « Ground » ; service d'élévation par défaut sur ArcGIS Online (~30 m), remplaçable par un service d'image publié ; portail hors ligne : service par défaut à configurer [S42] | `MapTerrain` raster-dem terrarium (`configs/schemas.py:47`) + tuiles d'élévation hébergées (`terrain3d/routes.py:157`) | ISO | n/a | n/a | actif | R |
| Scènes 3D (Scene Viewer, bâtiments) | Scene Viewer 12.0 : couches scene et 3D Tiles fusionnées en « 3D layer », slices ; 12.1 : Gaussian splats [S37][S36] | 3D Tiles + deck.gl (`shell/src/map/LayersPanel.tsx`) ; pas de vue Scène dédiée | MOINS BIEN | L | basse | actif | R |
| Impression / export cartographique | Service PrintingTools (Export Web Map) : PDF, PNG, JPG, SVG, TIFF…, mises en page A3/A4/Letter/Tabloid, layouts custom publiés depuis Pro [S44] | `printLayout` + worker Playwright (`configs/schemas.py:498`, `export/rendering.py`) ; pas de layouts avancés type Pro (§5.2 B10) | MOINS BIEN | M | moyenne | actif | S |
| Portabilité de style (SLD, mapbox) | Éditeur de style de tuiles vectorielles, `.vtpk` ; pas d'export SLD trouvé [S21] | absent (style interne JSON) | ABSENT | M | basse | actif | R |
| Couches vidéo | Couches vidéo time-enabled ajoutables au Map Viewer (12.0) [S37] | absent | ABSENT | L | basse | actif | R |
| Recherche d'adresse dans la carte | Search widget : non vérifié | `AddressSearch` (`shell/src/map/AddressSearch.tsx`) | ISO | n/a | n/a | actif | NV |
| Tuiles raster/COG servies | Image/tile layers : non vérifié (cf. Image Server §3.1) | couches `raster` par URL de tuiles ; pas d'ingestion raster | MOINS BIEN | L | moyenne | actif | NV |

### 3.4 Applications

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Builder no-code d'apps | Experience Builder : 12.0 (Display Order, Document Explorer, templates Harbor/Beacon) ; 12.1 (Branch Version Editing, Date Filter, Login, Theme Mode Switcher, templates Concourse/Compass, 7 thèmes) [S46] | `AppRenderer` unique (modes edit/preview/runtime), 25 types de widgets (`core/app/configs/builtin_widget_types.json`, `shell/src/builder/AppRenderer.tsx`) | ISO | n/a | n/a | actif | S |
| Widgets analytiques (graphiques, indicateurs, pivot, filtres) | Dashboards : éléments liste, indicateur, table (11.0), axe secondaire (11.5), types date/time-only (12.0) [S47] | chart (15 types ECharts, `shell/src/builder/widgets/chartOption.ts:11`), indicator, pivot, filtres (select/slider/date) | ISO | n/a | n/a | actif | S |
| Widgets d'édition / formulaires | Widget Edit (édition par lot et Split/Merge en 12.1) ; widget Survey [S46] | widget `form` généré depuis le schéma | ISO | n/a | n/a | actif | S |
| Analyse embarquée dans l'app | Widget Analysis : 25 outils (miroir tiers) à 64 (doc Experience Builder [S15]) selon source [S56] | requête visuelle Filtrer->Joindre->Résumer, SQL Lab ; pas d'outils spatiaux dans l'app | MOINS BIEN | M | moyenne | actif | R |
| Widgets Print, Directions, Swipe, Basemap gallery, Feature Report | présents [S15] | print par export ; pas de directions/swipe/rapport de feature | MOINS BIEN | M | basse | actif | R |
| Gabarits d'apps | Templates Experience Builder (Harbor, Beacon, Concourse, Compass), StoryMaps (GA 12.0), Instant Apps (Gallery 12.1) [S46][S48][S50] | 4 gabarits (`shell/src/builder/templates.ts:232`) | MOINS BIEN | M | moyenne | actif | S |
| Interactions inter-widgets | Dashboards : actions filter/zoom/flash/pan/follow/show-hide ; Experience Builder : Experience state, actions Open view/Toggle widget (12.0) [S47][S46] | bus d'actions + cross-filter spatial/attribut (`shell/src/builder/ActionBus.ts`, `configs/schemas.py:67-77`) | ISO | n/a | n/a | actif | S |
| Liaison à des expressions | Arcade : sources de données Arcade, mise en forme avancée (12.0), data expressions de Dashboards (10.9.1) [S46][S47] | CEL généralisé + variables typées (`visibleWhen`, colonnes calculées) | ISO | n/a | n/a | actif | S |
| Annuler/rétablir, historique | non vérifié | undo/redo 50 niveaux (`shell/src/builder/useUndoableDraft.ts`), historique + rollback (`configs/routes.py:263,276`) | MIEUX | n/a | n/a | actif | NV |
| Dashboards à rafraîchissement périodique | Intervalle de rafraîchissement sur la couche, la couche de la web map ou l'expression de données ; pas de push ; hors vue mobile [S47] | sondage côté App | ISO | n/a | n/a | actif | R |
| Flux temps réel (GeoEvent / Velocity) | GeoEvent Server : 12.3 = dernière version, transition vers Velocity ; Velocity for Enterprise (12.1) : mono-machine, flux Kafka/gRPC, licence par cœurs [S57] | sondage seulement ; décision produit Q10 ouverte (`docs/revue/2026-09-04-backlog.md`) | ABSENT | L | moyenne | GeoEvent déprécié au profit de Velocity | S |
| StoryMaps | StoryMaps Enterprise : disponible, certaines capacités d'Online non supportées ; charts 11.5, briefings 11.3, templates GA 12.0, infographies 12.0 [S48] | mode narratif `story` de `PageManager` (`shell/src/builder/PageManager.tsx`) | MOINS BIEN | M | basse | actif | S |
| Hub : sites et portails de données | « ArcGIS Enterprise Sites » = équivalent Hub Basic sur site ; domaines et branding personnalisés ; Workspaces (12.0) [S49] | sites `/sites/{slug}`, catalogue public, sitemap, aperçus sociaux (`public/routes.py:94,122,151,197`) | ISO | n/a | n/a | appelé Enterprise Sites | S |
| Hub : engagement citoyen (initiatives, événements, discussions) | Enterprise Sites : pas d'initiatives, d'événements, de discussions ni de comptes communautaires ; Hub Premium indisponible sur Enterprise [S49] | absent | ISO | n/a | n/a | non offert sur Enterprise | S |
| Hub : open data (API, téléchargements, DCAT) | Enterprise Sites : open data via API et téléchargements NON ; feeds DCAT-AP/OGC API Records = Hub Online [S49] | catalogue public, DCAT-AP, STAC, sitemap (`public/routes.py:94,122,151,197`, `dcat/routes.py:122`) | MIEUX | n/a | n/a | non offert sur Enterprise | S |
| Embarquement (iframe) d'apps | Dashboards en iframe, anonyme si dashboard, web map et couches partagés Everyone ; Experience Builder 12.0 : app imbriquée demande un jeton au parent [S47][S46] | `/embed/:token`, jeton recoupé avec droits (`shell/src/pages/EmbedPage.tsx`, `items/routes.py:293`) | ISO | n/a | n/a | actif | R |
| Export d'app autonome (hors plateforme) | Experience Builder Developer Edition (versions alignées 1.8 à 1.20 sur Enterprise 11.0 à 12.1), auto-hébergée [S46] | 3 modes d'export : statique, connecté, autoporté (`appexport/routes.py:65`, `shell/src/staticExport/entry.tsx`) | MIEUX | n/a | n/a | actif | R |
| SDK d'extension | Custom widgets dans Enterprise depuis 11.0 ; widgets basés sur les « JS widgets » du Maps SDK retirés dès Q1 2027, viser les Web Components [S46][S50] | widgets Web Components + registre d'extensions (`shell/src/builder/wc/registerWcWidget.ts`, `extensions/routes.py:32`) | ISO | n/a | n/a | actif | S |
| Applications historiques (Web AppBuilder, Configurable Apps) | Web AppBuilder, Configurable Apps retirés en 12.0, les apps WAB ne fonctionnent plus après la mise à niveau ; Instant Apps remplace [S34][S50] | sans objet | ISO | n/a | n/a | retiré (12.0) | S |
| Application desktop / hors-ligne | Pro (hors Enterprise) | embryon `DesktopApp` (`shell/src/desktop/DesktopApp.tsx`) | MOINS BIEN | L | basse | actif | NV |
| Génération d'app par IA | non vérifié (aucune source) | `create_form_app`, copilote builder 9 outils (`copilot/tools_allowlist.py:14`) | MIEUX | n/a | n/a | actif | NV |
| Rapports planifiés (PDF) | Survey123 reports, rapports planifiés d'administration (12.1) : périmètre non lu | `ReportSchedule` -> PDF cron (`reports/routes.py:53`, `export/jobs.py`) | ISO | n/a | n/a | actif | D |
| Alertes sur seuil | non vérifié (GeoEvent/Velocity/Dashboards) | `AlertRule`, transition d'état, webhook/email (`alerts/routes.py:83`, `alerts/notify.py:52`) | ISO | n/a | n/a | actif | NV |

### 3.5 Analyse

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Analyse visuelle de données (Insights) | Insights retiré en 12.0 ; dernière version 2025.1, compatible Enterprise 11.5 ; retraite finale planifiée juin 2026 ; aucun remplaçant nommé [S51][S34] | requête visuelle + datasets + pivot + cross-filter (`shell/src/builder/visualQuery`, `configs/schemas.py:86`) | MIEUX | n/a | n/a | retiré (12.0) | S |
| Agrégats statistiques | `outStatistics` count/sum/min/max/avg/stddev/var, percentiles, groupBy, having [S20] | count, sum, avg, countDistinct, median, percentile, stddev, 6 grains temporels (`analytics/aggregate.py:195-223`) | ISO | n/a | n/a | actif | S |
| Profilage exploratoire | non vérifié | `GET /collections/{id}/profile` (`features/routes.py:362`) | ISO | n/a | n/a | actif | NV |
| GeoAnalytics (calcul distribué) | GeoAnalytics Server retiré à 11.4 (dernière version livrée avec 11.3) [S52][S34] | DuckDB mono-process | ISO | n/a | n/a | retiré (11.4) | S |
| Outils géospatiaux (buffer, overlay, jointure spatiale…) | Outils d'analyse du portail (25 à 64 selon source) + web tools / GP services [S56][S55] | 47 op de transformation dont buffer, intersection, countWithin, simplify, convexHull (`pipelines/ops/contracts.py:205-232`) | MOINS BIEN | M | moyenne | actif | R |
| Web tools / services de géotraitement | Web tool = item portail adossé à un GP service ; publié depuis Pro/ModelBuilder/Python ; planification dans la doc 12.1 ; journaux d'audit couvrant les GP services en 12.0 [S55][S34] | pipelines exécutables par `POST /v1/pipelines/{id}/run` et webhook entrant (`pipelines/routes.py:94,198-240`) | ISO | n/a | n/a | actif | S |
| Interopérabilité ETL (Data Interoperability) | Extension serveur = FME embarqué (2025.1.2 en 12.0, 2026.1 en 12.1), pooling jusqu'à 16 cœurs en 12.1 ; web tools issus de Workbench [S58] | 59 op exposées / 61 brutes, aucun format GDAL en pipeline (§2.3) | MOINS BIEN | L | moyenne | actif (extension payante) | S |
| Data Pipelines (no-code) | Éditeur visuel : sources S3, Azure, BigQuery, Snowflake, URL, feature layers ; sortie hosted layer ; bêta en 12.0 sans support technique, GA annoncée en 12.1 (résumé de recherche) [S59] | canvas DAG de pipelines no-code (`configs/schemas.py:246`) | ISO | n/a | n/a | bêta (12.0) | R |
| Analyse raster / imagerie | Image Server, raster analytics, fonctions raster chaînables, `arcpy.ia`, Deep Learning Studio [S53] | absent | ABSENT | L | moyenne | actif | S |
| Analyse réseau (routage, isochrones, zones de service) | Network analysis services : closest facility, route, location-allocation, matrice OD, service areas (page 10.7) [S56] | absent (`pipelines/ops/contracts.py:205`) | ABSENT | L | moyenne | actif | R |
| Notebooks Python | Notebook Server 12.0 : Python 3.13, runtime 13.0, templates low-code, tâches planifiées, webhooks, TensorFlow déprécié [S54] | absent ; SQL Lab seulement | ABSENT | L | basse | actif | S |
| Enrichissement de données (GeoEnrichment) | Enrich Layer requiert GeoEnrichment [S56] | absent | ABSENT | L | basse | actif | R |
| Gestion de workflows (Workflow Manager) | Workflow Manager Server (rôle) ; version Classic dépréciée, inaccessible après 11.5 [S60][S34] | absent | ABSENT | L | basse | Classic déprécié | R |
| Génération de requêtes en langage naturel | non vérifié | NL->SQL et NL->requête visuelle avec revue humaine (`analytics/query_generation.py:195-335`) | MIEUX | n/a | n/a | actif | NV |
| Alertes et rapports | cf. §3.4 | cf. §3.4 | ISO | n/a | n/a | actif | D |
| Moteur d'expressions | Arcade, 26 profils [S45] | CEL + `generate_cel_expression` (`mcp/tools/query_generation.py`) | ISO | n/a | n/a | actif | S |

### 3.6 Sécurité et gouvernance

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Authentification SSO | SAML 2.0, OpenID Connect, IWA, LDAP, PKI, comptes built-in [S63][S11] | OIDC délégué à Keycloak (`auth/dependency.py:162-231`), Keycloak peut fédérer SAML/LDAP en amont (non vérifié côté Keycloak) | ISO | S | basse | actif | S |
| MFA / politique de mots de passe | TOTP pour comptes built-in seulement (SAML/OIDC : MFA côté IdP) ; imposable à toute l'organisation en 12.0 ; mot de passe et verrouillage (5 échecs/15 min) réglables, built-in seulement [S63][S36] | délégués à Keycloak (aucun mot de passe dans le cœur) | ISO | n/a | n/a | actif | S |
| Groupes externes -> groupes portail | claim `groups` / assertion SAML, résolu à la connexion [S11] | groupes gérés par le cœur, pas synchronisés depuis l'IdP (`sharing/routes.py:57-203`) | MOINS BIEN | M | moyenne | actif | S |
| Modèle de rôles / privilèges | 6 types d'utilisateur ; 5 rôles par défaut (Viewer, Data Editor, User, Publisher, Administrator) + rôles personnalisés limités par le type [S62][S12] | 20 privilèges, 4 rôles prédéfinis + sur mesure (`roles/privileges.py:5-25`, `roles/routes.py:59-157`) | ISO | n/a | n/a | actif | S |
| Point d'autorisation unique | non vérifié | `can()` / `decide()` (`sharing/authorization.py:33,101`) | MIEUX | n/a | n/a | actif | NV |
| Partage (privé, groupes, organisation, public) | Privé par défaut ; partage avec organisation, public, groupes ; Shared update ; option interdisant aux non-admins le partage public [S63][S16] | rôles viewer/editor/manager, publication, liens à échéance (`items/routes.py:260-342`) | ISO | n/a | n/a | actif | S |
| Privilège de publication séparé | rôle Publisher dédié [S62] | rattaché à d'autres privilèges (`items/routes.py:165`) | MOINS BIEN | S | basse | actif | S |
| Sécurité au niveau ligne | Pas de RLS par utilisateur ni d'ABAC trouvés : vues de couches hébergées avec filtre de définition (expressions, emprise), valable par vue y compris via REST et exports [S25] | RLS PostGIS par collection (`features/rls.py`) | MIEUX | n/a | n/a | vues filtrées seulement | S |
| Sécurité au niveau colonne | Champs masqués dans une vue de couche (par vue, non par utilisateur) [S25] | champs sensibles : RLS par colonne, exclusion du lac (`collections/models.py:57`, `features/routes.py:228`) | MIEUX | n/a | n/a | actif | S |
| Audit des actions | Pas de fonction d'audit dédiée : journaux du portail (connexions, actions admin, partage, CRUD d'items, publication ; sans requêtes edit/query REST) ; 12.0 ajoute des journaux d'audit d'accès aux services map/feature/GP/image [S64][S34] | `audit_log` sur toute écriture dès la 1re migration (`audit/writer.py:7`) + page d'usage (`usage/routes.py:34,93`) | MIEUX | n/a | n/a | pas d'audit dédié (12.0 : accès services) | S |
| Rapports d'usage | Activity Dashboard intégré (items vus, contributeurs, membres, groupes) [S64] | page d'usage `UsagePage` (`usage/routes.py:34,93`) | ISO | n/a | n/a | actif | R |
| RGPD : anonymisation, purge | Pas d'anonymisation ni de tombstone : suppression de membre avec transfert de contenu ; DPA/CCT et suppression sous 60 j limités à ArcGIS Online, rien d'Enterprise [S67] | `POST /users/{id}/erase`, `POST /tenants/{id}/purge` (`compliance/routes.py:32,88`) | MIEUX | n/a | n/a | actif | R |
| Multi-tenant | Un portail = une organisation ; pas de multi-tenance native trouvée (thread communautaire) [S67] | colonne `tenant_id` partout mais un seul tenant en pratique : `get_or_create_default_tenant` (`auth/dependency.py:181`) | ISO | n/a | n/a | actif | D |
| Quotas | non vérifié | quotas items/collections/stockage (`quotas/routes.py:44`) | ISO | n/a | n/a | actif | NV |
| Rate limiting | non vérifié | en mémoire par process (`ratelimit/limiter.py:2`) | MOINS BIEN | S | moyenne | actif | NV |
| CORS, proxy, HTTPS, passerelle admin | HTTPS-only par défaut ; liste Allow origins (100 max, sans wildcard), trusted servers ; proxy du portail limité par défaut à une liste d'hôtes approuvés (12.0) [S63][S36] | CSP enforcing + passerelle `/admin/*` (SP-32/48) ; coffre AES-GCM | ISO | n/a | n/a | actif | S |
| Coffre de secrets | aucune doc Esri sur un coffre de secrets du portail [S67] | coffre AES-GCM, liaison à `baseUrl`/`bucketUrl`, rotation (`secrets/routes.py:42`, `secrets/rotation.py:28`) | MIEUX | n/a | n/a | non trouvé | D |
| Jetons de sécurité / clés d'API | Developer credentials : API keys et OAuth2 (Enterprise 11.4+), clé valide 1 an, 2 clés par credential [S65] | jetons OIDC, liens de partage ; pas de clés d'API de service | MOINS BIEN | S | moyenne | actif | R |
| Statut de contenu (authoritative/deprecated) et catégories | Badges authoritative/deprecated, protection contre la suppression, boost de recherche ; catégories d'organisation (10.6.1+) [S66] | absent (aucune occurrence `authoritative` dans `core/app/items`) | ABSENT | S | basse | actif | R |
| Conformité (certifications, FIPS…) | FedRAMP Moderate et ISO 27001 cités pour ArcGIS Online ; Enterprise : non trouvé [S67] | aucune certification | ABSENT | L | basse | non trouvé | D |

### 3.7 Administration, HA, déploiement, coût

| Capacité | Chez ArcGIS Enterprise | Chez GeoStudio | Verdict | Effort | Priorité | Statut Esri | Conf. |
|---|---|---|---|---|---|---|---|
| Haute disponibilité | 2 portails + LB + répertoire partagé ; pool ArcGIS Server ; data stores relationnel primaire/standby, objet et spatiotemporel >= 3 machines ; conçue pour un seul datacenter, multi-DC = reprise après sinistre ; GeoEvent non supporté [S68] | monolithe `core` unique, pgbouncer, pas de réplicas (`docker-compose.yml:47,226`) | ABSENT | L | moyenne | actif (HA mono-datacenter) | S |
| Fédération de serveurs | ArcGIS Server fédéré au portail ; un serveur ne fédère qu'avec un seul portail [S10][S67] | aucune ; moissonnage de catalogues externes à la place | ABSENT | L | basse | actif | S |
| Sauvegarde / restauration | WebGISDR : portail, services, webhooks, stores relationnel/objet/graphe, Notebook Server ; exclut caches de tuiles et spatiotemporel ; restauration même version, mêmes URL [S69] | script `deploy/backup/backup.sh:106`, `restore.sh` ; restauration non vérifiée automatiquement | MOINS BIEN | M | haute | actif | S |
| Observabilité | 12.0 : métriques Prometheus (bêta), journaux d'audit d'accès aux services ; 12.1 : metrics API ; ArcGIS Monitor = produit séparé [S34][S70] | OTel + `otel-lgtm`, dashboards et SLO (`docker-compose.yml:777`) | ISO | n/a | n/a | Prometheus en bêta (12.0) | R |
| Gestion de rôles de serveur | Rôles : GIS, Image, GeoAnalytics (retiré), GeoEvent, Notebook, Workflow Manager, Knowledge, Video ; niveaux Basic/Standard/Advanced [S34][S14] | services Docker dédiés : titiler, martin, export-worker, cdc-worker (`docker-compose.yml:114,168,691,741`) | ISO | n/a | n/a | GeoAnalytics retiré | S |
| Mise à jour / migrations | Mise à niveau directe 11.0 à 11.5 -> 12.0 ; prérequis : object store et migration des caches ; PostgreSQL 13 et SQL Server 2017 non supportés ; nouveau fichier de licence [S34][S35] | `alembic upgrade head` au démarrage ; migrations testées | ISO | n/a | n/a | actif | S |
| Rotation de secrets | non vérifié | rotation atomique 2 passes (`secrets/rotation.py:28`) | MIEUX | n/a | n/a | actif | NV |
| Déploiement | Installeurs Windows/Linux ; Kubernetes (OpenShift, EKS, GKE, AKS, Tanzu, RKE2) ; Chef, PowerShell DSC, arcgis-gitops (Apache-2.0, Terraform/Ansible/Packer, AWS et Azure) ; pas de Docker Compose officiel trouvé [S71][S72] | Docker Compose, Ansible Proxmox/OCI, OpenTofu OCI (`deploy/ansible`, `deploy/oci`) ; pas de Helm | MOINS BIEN | M | moyenne | actif | S |
| Multi-architecture | Kubernetes : workers Linux x86_64 seulement ; Data Store : x86-64 seulement [S71] | images amd64 + arm64 (8/9) | MIEUX | n/a | n/a | x86_64 seulement | S |
| Automatisation / API d'administration | REST API (toute tâche admin), ArcGIS API for Python, utilitaires CLI [S72] | API REST OpenAPI + MCP audité (`mcp/server.py`) | ISO | n/a | n/a | actif | S |
| Licence / coût | Licence annuelle par type d'utilisateur ; extensions serveur et rôles vendus séparément ; tarifs non publics (devis), repères indirects en §3.8 [S73][S12] | Apache-2.0, aucun coût de licence | MIEUX | n/a | n/a | actif | S |
| Support et écosystème | support éditeur, communauté, Marketplace (non vérifié) | projet mono-mainteneur piloté par Claude ; aucun support contractuel | ABSENT | L | haute | actif | NV |
| Administration unifiée (utilisateurs, rôles, usage, extensions) | Portail admin ; 12.0 : MFA d'organisation, catégories de membres ; 12.1 : transfert complet d'un membre, tableau de bord et rapports planifiés [S34][S35] | pages `/admin/users`, `/admin/roles`, extensions, harvest, collections (`shell/src/pages/*AdminPage.tsx`) | ISO | n/a | n/a | actif | S |
| Notifications | non vérifié | cloche in-app + préférence (`notifications/routes.py:45-118`) | ISO | n/a | n/a | actif | NV |
| MCP / IA agentique | non vérifié (aucune source) | MCP OAuth 2.1 (`mcp/server.py`), ~35 outils (`mcp/tools/*.py`), audités | MIEUX | n/a | n/a | actif | NV |

### 3.8 Dernier état du produit (12.0 / 12.1, retraits, cycle de vie, licences et tarifs indicatifs)

**Versions et cycle de vie** (confiance R : la page officielle du cycle de vie renvoie 403, dates reprises de résumés de recherche, à revérifier avant citation) : 11.5 = LTS, sortie 22 mai 2025, support général jusqu'au 31 mai 2027, étendu jusqu'au 31 mai 2029, mature jusqu'au 31 mai 2031, retraite le 1er juin 2031 ; 12.0 = STS, sortie le 18 novembre 2025, retraite le 1er décembre 2026 ; 12.1 = premier LTS de la série 12.x (~4 ans, date exacte non trouvée). Nouvelle politique depuis 12.0 : LTS ~4 ans, STS ~1 an ; Enterprise on Kubernetes a un cycle distinct (12.0 publié le 11 décembre 2025) [S74][S71]. Mise à niveau directe de 11.0 à 11.5 vers 12.0 ; 12.1 est le dernier à supporter PostgreSQL 14 [S34][S35].

**Retraits et dépréciations connus** (impact sur les verdicts) :

| Composant | Statut chez Esri | Source | Conf. | Effet sur le comparatif |
|---|---|---|---|---|
| Insights | retiré en 12.0 ; 2025.1 = dernière version, compatible 11.5 ; retraite finale planifiée juin 2026 | [S51][S34] | S | « Analyse visuelle » : MOINS BIEN -> MIEUX (§3.5) |
| GeoAnalytics Server | retiré à 11.4 (dernière version livrée avec 11.3) | [S52][S34] | S | ABSENT -> ISO (absent des deux) |
| Web AppBuilder, Configurable Apps, Map Viewer Classic | retirés en 12.0 | [S34] | S | ligne dédiée, pas un écart |
| Tile cache data store | retiré en 12.0 (caches de scene layers vers l'object store dès 11.4) | [S34][S22] | S | scene layers : mention de statut |
| GeoEvent Server | déprécié, 12.3 = dernière version, transition vers Velocity for Enterprise (12.1) | [S57] | S | temps réel : reste ABSENT chez nous, mais l'offre Esri se déplace |
| Workforce | déprécié, retrait d'Enterprise prévu avec 12.2 ; remplacé par Tasks (Field Maps, 11.5+) | [S32] | R | écart conservé, priorité basse |
| Workflow Manager Classic | déprécié, inaccessible après 11.5 | [S60] | R | écart conservé, priorité basse |
| Hub dans Enterprise | « Enterprise Sites » seulement : ni initiatives, ni événements, ni discussions, ni open data API/téléchargements, ni feeds DCAT-AP ; Hub Premium indisponible | [S49] | S | engagement citoyen : ABSENT -> ISO ; DCAT-AP : ISO -> MIEUX |
| Data Pipelines | bêta en 12.0 (sans support technique) ; GA annoncée en 12.1 (résumé de recherche) | [S59] | S (statut 12.0) / R (12.1) | ligne ISO, confiance R |
| Data Interoperability | extension payante embarquant FME 2025.1.2 (12.0) / FME 2026.1 (12.1) | [S58] | S | l'ETL d'Esri est FME : renvoie à §2 |
| Prometheus (métriques ArcGIS Server) | bêta en 12.0 | [S34] | S | observabilité : mention de statut |
| Maps SDK for JavaScript | 5.0 = Enterprise 12.1 ; widgets dépréciés dès 5.0, retirés en 6.0 (début 2027) ; widgets Experience Builder basés sur les « JS widgets » retirés dès Q1 2027 | [S50][S46] | R | SDK d'extension : trajectoire Web Components |
| Plateforme x86_64 | Kubernetes et Data Store : x86_64 seulement | [S71] | R | arm64 : MIEUX côté GeoStudio |
| Haute disponibilité | conçue pour un seul datacenter, multi-DC = reprise après sinistre | [S68] | S | HA : ABSENT chez nous, mais périmètre Esri borné |

**Modèle de licence** [S73] (S) : logiciel auto-hébergé, licence annuelle par type d'utilisateur (un type = une personne) : Creator, Professional, Professional Plus (cœur) ; Mobile Worker, Contributor, Viewer (collaborateurs) ; applications essentielles et terrain incluses dans les types ; add-ons par membre (AllSource, Business Analyst Advanced). Kubernetes : trois options (Standard, Advanced, Kubernetes) incluant chacune un nombre de Creator et Viewer. Rôles serveur sous licence dédiée (Image, GeoEvent, Notebook, Workflow Manager, Knowledge, Video) ; extensions vendues séparément (Network Analyst, Spatial Analyst, Data Reviewer, Data Interoperability, Advanced Editing, Location Sharing…). Niveaux GIS Server Basic/Standard/Advanced : Basic = géodatabases d'entreprise seulement, ne peut pas héberger un déploiement de base (doc 11.0, non reconfirmé en 12.0).

**Tarifs indicatifs** (R, **non officiels**, ne pas citer sans devis) : les tarifs ne sont pas publics (devis via les ventes Esri). Repères indirects : revendeur Systematics sur AWS Marketplace, Contributor 12 mois = 580 USD, Professional 12 mois = 4 640 USD ; accord d'entreprise d'un comté américain (2023) : 240 000 à 280 000 USD/an pour 55 à 100 Creators (total, pas un prix unitaire) ; remises ONG et éducation. Ces ordres de grandeur ne comptent ni les extensions ni l'infrastructure.

---

## 4. Avantages nets de GeoStudio (avec preuve)

1. **Pilotage IA natif** : serveur MCP dans le cœur (~35 outils `@server.tool`, `mcp/tools/*.py`), copilote builder limité à 9 outils allowlistés (`copilot/tools_allowlist.py:14`), NL->SQL/requête visuelle/CEL avec revue humaine (`analytics/query_generation.py:195-335`). Aucune capacité équivalente sourcée chez FME ou Esri dans cette session.
2. **Écriture OGC API Features Part 4** (`features/routes.py:85-90`) : create/replace/delete standard sur toute collection.
3. **STAC et DCAT-AP natifs** (`stac/routes.py:111-490`, `dcat/routes.py:122`) plus moissonnage de 7 types de sources (`harvest/connectors/__init__.py:13-20`). Face à Esri, l'avantage est confirmé par les sources : les feeds DCAT-AP et OGC API Records sont réservés à Hub Online, Enterprise Sites n'offre ni API open data ni téléchargements (§3.1, §3.4 ; [S49]).
4. **Objets de plateforme déclaratifs, versionnés, diffables** (11 kinds, `configs/schemas.py:469` ; historique et rollback `configs/routes.py:263,276` ; `If-Match` `configs/routes.py:61`).
5. **Sécurité des données plus fine** : RLS PostGIS par collection (`features/rls.py`), masquage de colonnes sensibles, limites géographiques par groupe (`collections/geo_limits_routes.py:85`), audit systématique (`audit/writer.py:7`). Esri n'offre que des vues de couches filtrées (par vue, pas par utilisateur) et des journaux de portail sans fonction d'audit dédiée (§3.6, S) ; l'ABAC n'est pas documenté.
6. **RGPD** : anonymisation utilisateur et purge complète d'un tenant (`compliance/routes.py:32,88`), privilège exclu même de l'Administrateur. Esri Enterprise : suppression de membre avec transfert de contenu, pas d'anonymisation trouvée (R) ; DPA et suppression sous 60 jours limités à ArcGIS Online.
7. **Export d'app autonome** (statique, connecté, autoporté ; `appexport/routes.py:65`) et embed par jeton recoupé avec les droits du créateur (`items/routes.py:293`).
8. **Coût** : Apache-2.0, deux architectures CPU (Esri : Kubernetes et Data Store en x86_64 seulement, S), déploiement scripté Proxmox/OCI.
9. **Coffre de secrets et egress SSRF** (`secrets/routes.py:42`, `pipelines/egress.py:51`) : liaison d'un secret à un `baseUrl`/`bucketUrl`, absente des ETL courants (comparaison non sourcée).
10. **Cross-filter spatial et contexte temps x emprise** entre datasets (`configs/schemas.py:67-77`). Nuance après sources : les actions inter-éléments de Dashboards/Experience Builder existent côté Esri, le verdict de l'interaction générale passe donc de MIEUX à ISO (§3.4) ; l'avantage tient à l'emprise opt-in par dataset.
11. **Pas de dette de retrait** : GeoStudio n'a pas à migrer hors d'Insights (retiré en 12.0), de GeoAnalytics Server (retiré à 11.4), de Web AppBuilder/Configurable Apps (retirés en 12.0) ni de GeoEvent (déprécié) ; un client Esri doit planifier ces migrations (§3.8).

---

## 5. Écarts bloquants pour un remplacement, par persona

### 5.1 Collectivité (SIG territorial, 10-200 agents, catalogue ouvert)

Remplaçable pour : catalogue, cartes, tableaux de bord, sites de données ouvertes, formulaires d'agents, partage par groupes, RGPD.

Bloquants vs ArcGIS Enterprise :
- B1. Pas de services OGC OWS (WMS/WFS/WMTS/WCS) : les partenaires (DDT, SDIS, SIG départemental) consomment souvent du WMS/WFS. Absent (`features/routes.py:85-90`) ; Esri les publie par service, à activer explicitement (S, [S17]).
- B2. Pas d'édition hors ligne ni de collecte mobile (absent ; `ConnectivityBanner.tsx` seulement).
- B3. Pas de soumission citoyenne publique avec modération (`features/routes.py:732` exige l'authentification) ; Esri couvre le besoin par Survey123 anonyme (11.4+, sondages publics) et non par Hub Enterprise Sites (S, §3.2).
- B4. Pas de HA ni de support contractuel (§3.7) ; la HA d'Esri est elle-même limitée à un datacenter (S).
- B5. Pas de gestion des relations/domaines d'une base métier existante (réseaux, cadastre).
- B6. Géocodage en lot absent (`geocoding/provider.py:46`).
Atténuation : INSPIRE/DCAT/STAC couverts ; BAN intégrée. Plan de rattrapage détaillé : §6.1.

### 5.2 Bureau d'études (traitements ponctuels, livrables clients)

Bloquants :
- B7. Largeur de formats (DWG, DXF, FileGDB, IFC, LAS/LAZ) : absente (§2.1, §2.5).
- B8. Pas de raster/MNT/orthophoto (§3.1, §3.5).
- B9. Pas d'analyse réseau ni de notebooks Python (Notebook Server 12.0 côté Esri). Pas de bloquant « Insights » ni « GeoAnalytics » : les deux sont retirés chez Esri (§3.5).
- B10. Sorties cartographiques : impression Playwright seulement (`export/rendering.py`) ; pas de mise en page cartographique avancée (type Pro layouts).

### 5.3 Intégrateur / éditeur ETL (remplacer FME Flow)

Bloquants :
- B11. Aucun upsert/update/delete en écriture (`pipelines/ops/schemas.py:55`).
- B12. Aucun port Rejected (`pipelines/runtime.py:1033`), aucun incrémental, aucun retry, aucun paramètre publié.
- B13. 37,9 % de la matrice des 290 transformers (110/290), 10 formats d'import contre « 300 à 450+ » annoncés [S2][S3].
- B14. Pas de transformers personnalisés (PythonCaller / SDK de pipeline).
- B15. Pas de déclencheurs fichier/S3/événement.
Atténuation : la gouvernance (secrets, RLS, audit) est plus sûre que celle d'un ETL classique ; la piste « DuckDB + GDAL » est déjà modélisée (`docs/vision/2026-08-30-etl-generaliste-triptyque-sql-lab-notebook-fme.md`).

---

## 6. Feuille de route de rattrapage proposée (valeur / effort)

Cette table est centrée FME/ETL ; la feuille de route de rattrapage ArcGIS Enterprise (ARC-01 à ARC-35, vagues, chemin critique) est en §6.1.

Ordre = valeur décroissante, effort croissant. Reliée à la campagne (`2026-10-11-campagne-test-multi-angles.md` §7, numéros #) et aux SP/REV existants quand identifiés ; les autres entrées sont **nouvelles**.

| Rang | Chantier | Comble | Effort | Lien existant |
|---|---|---|---|---|
| 1 | Mode `upsert`/`update`/`delete` du `writer.collection` appliquant le statut de `detectChanges` | B11, FME écriture | M | campagne #2 ; nouveau SP |
| 2 | Port Rejected + collection de quarantaine + rapport de qualité (réutilise `analytics/profile.py`) | B12 | M | campagne #4 |
| 3 | Paramètres de run publiés (schéma de paramètres dans le pipeline, saisie au `POST /run`, MCP) | B12 | M | nouveau |
| 4 | Incrémental via dlt (état par reader) | B12 | M | campagne #3 |
| 5 | Retry de run + reprise par nœud + bouton « rejouer » dans `/tasks` | B12 | M | campagne #14 |
| 6 | Webhooks sortants génériques (outbox, egress) + déclencheurs fichier/S3 | B15 | M | campagne #6 |
| 7 | Reader de pipeline pour formats GDAL vecteur (SHP, GPKG, GeoJSON, KML, GML, WFS) via DuckDB `ST_Read` | B13 | M | matrice FME `planned_gdal` ; `reader.file` existe déjà |
| 8 | Familles Filtering/Database de la matrice (TestFilter, Sampler, SQLExecutor, NeighborFinder) | B13 | M | matrice FME `planned_duckdb` (50 lignes) |
| 9 | Jeton de soumission public par collection + file de modération (référence Esri : Survey123 anonyme) | B3 | M | campagne #7 |
| 10 | Journal avant/après dans `audit_log` + `asOf` sur les items | historique d'entités | M | campagne #5 |
| 11 | `transform.geocode` BAN en lot et à l'import CSV | B6 | S | campagne #9 |
| 12 | Clustering de points (couche vectorielle + MVT agrégé) | carto | S/M | campagne §6.3 |
| 13 | Tri `sortby`, CQL2 de base, `datetime` et `crs` sur `/items` | Feature Services | M | campagne §6.3 |
| 14 | Services OWS minimaux (WFS lecture, WMTS depuis MVT/raster) ou passerelle GeoServer documentée ; référence Esri : WMS/WMTS/WFS/WCS/OGC API Features activables par service (S) | B1 | L | nouveau ADR |
| 15 | Lineage dérivé des configs et vue d'impact avant suppression | gouvernance | M | campagne #8 |
| 16 | HA : réplicas `core`/`worker`, readiness `/health`, rétention de jobs, sauvegarde vérifiée | B4 | L | REV-164 partiel, rapports de rejeu |
| 17 | Synchronisation de groupes depuis l'IdP (claim `groups`) | SSO | M | nouveau |
| 18 | PWA hors ligne pour la collecte (rouvre Q11) | B2 | L | campagne #17, REV-120 (fermé par décision, à rouvrir) |
| 19 | Raster : ingestion COG + TiTiler exposé + 1 outil (zonal stats) | B8 | L | matrice FME raster ; ADR à écrire |
| 20 | SDK de transformer personnalisé (Python sandboxé) | B14 | L | nouveau |
| 21 | Notebooks (JupyterLite ou SQL Lab étendu) | B9 | L | nouveau |
| 22 | Analyse réseau (pgRouting/valhalla en service externe) | B9 | L | nouveau |

Séquencement conseillé : lot « ETL robuste » (1 à 5, environ 5 SP moyens) puis lot « ouverture » (6, 7, 9, 11) puis lot « exploitation » (16). Les chantiers 14, 18 à 22 sont des décisions produit (positionnement horizontal acté en Q2, parité de couverture de connecteurs comme différenciateur) à arbitrer, pas à lancer sans ADR.

### 6.1 Feuille de route de rattrapage ArcGIS Enterprise

Complète la table ci-dessus (centrée FME/ETL) sans la dupliquer : les chantiers 9 (soumission publique), 11 (géocodage lot), 12 (clustering), 13 (tri/CQL2/CRS), 14 (OWS), 16 (HA), 17 (groupes IdP) et 10 (journal d'entité) y figurent déjà ; ils sont **repris ici sous un identifiant ARC-nn** avec le détail demandé pour le remplacement d'ArcGIS Enterprise. Base : verdicts, colonnes « Statut Esri » et « Conf. » (S/R/D/NV) de §3, avantages §4, bloquants §5. Date de rédaction : 2026-10-11. Hypothèse de capacité : 1 flux d'exécution (Claude en SDD) ≈ 20 j-h/mois ; deux flux en parallèle sur des périmètres disjoints sont possibles (cœur/shell), jamais deux sur `features/routes.py`.

Échelle d'effort : **S** ≤ 3 j, **M** ≤ 10 j (2 semaines), **L** > 10 j. Valeur : C = collectivité, B = bureau d'études, I = intégrateur ; ●●● bloquant pour le remplacement, ●● fort, ● utile, – nul. « ADR » = décision produit à trancher avant lancement.

#### 6.1.1 Écarts qu'il ne faut PAS combler (capacité retirée, dépréciée ou non offerte sur Enterprise)

| Capacité Esri | Statut Esri (§3.8) | Raison de ne pas la rattraper | Réf. |
|---|---|---|---|
| Insights | retiré en 12.0 | Aucun remplaçant nommé chez Esri ; la requête visuelle + pivot de GeoStudio est déjà au-dessus (ligne §3.5 : MIEUX) | [S51] |
| GeoAnalytics Server | retiré à 11.4 | Calcul distribué abandonné par l'éditeur ; DuckDB mono-process suffit (A18) | [S52] |
| Web AppBuilder, Configurable Apps, Map Viewer Classic | retirés en 12.0 | Les clients Esri doivent migrer ; pas de parité à construire (§4 point 11) | [S34] |
| GeoEvent Server | déprécié, transition vers Velocity (licence par cœurs) | Ne pas cloner un produit en fin de vie ; seule la question « push temps réel » reste, traitée en ARC-35 (décision) | [S57] |
| Workforce | déprécié, retrait prévu avec 12.2 (R) | Remplacé par Tasks de Field Maps ; la collecte passe par ARC-27 | [S32] |
| Workflow Manager Classic | déprécié, inaccessible après 11.5 (R) | Pas de remplaçant clair ; les pipelines + `AlertRule` couvrent l'usage automatisable | [S60] |
| Tile cache data store | retiré en 12.0 | Détail d'architecture Esri | [S34] |
| Hub : initiatives, événements, discussions, open data API/téléchargements, feeds DCAT-AP | non offerts sur Enterprise (Enterprise Sites seulement) | Pas d'écart (ISO/MIEUX) ; l'engagement citoyen communautaire est de toute façon différé (A38) | [S49] |
| « JS widgets » du Maps SDK (retrait Q1 2027) | trajectoire Web Components | GeoStudio est déjà sur Web Components (A10) | [S46][S50] |
| Data Pipelines (bêta 12.0, GA 12.1 en R) | bêta | Ligne ISO ; ne pas sur-investir avant de connaître le périmètre GA | [S59] |

#### 6.1.2 Chantiers par vague

Les lignes `chemin:ligne` ont été relues dans le code le 2026-10-11. Les numéros `§3.x` désignent la ligne de la matrice ; `campagne #n` renvoie à `2026-10-11-campagne-test-multi-angles.md` §7. **Constat nouveau** : la matrice §3.1 note le clustering/binning « absent côté serveur » ; or `features/tiles.py:138-148,293` agrège déjà les tuiles denses (grille de 16 cellules, `CORE_TILE_AGG_MAX_ZOOM`, REV-283a). ARC-01/ARC-22 s'appuient dessus ; le verdict « ABSENT côté serveur » est à nuancer en « MOINS BIEN ».

##### Vague 0 : quick wins (≤ 1 mois, jusqu'à 2026-11-11, 26 j-h)

> **Statut d'exécution (2026-10-12)** : ARC-01, 02, 04, 05, 06, 07, 08 livrés ; ARC-03 livré **partiellement** (lot synchrone, sans job de reprise ; `transform.geocode` reporté) ; ARC-09 livré **partiellement** (REV-356 fermé, lecteur temps selon C3, **fonds de carte par tenant non livrés** : table + migration requises). Reliquats : REV-366/367. Les compteurs ISO+MIEUX de §3 ne sont pas recalculés ici ; la ligne « clustering absent côté serveur » de §3.1 reste à nuancer (ARC-01 livre le clustering client des couches GeoJSON, les tuiles denses étaient déjà agrégées côté serveur).

| ID | Capacité ArcGIS visée (réf., ligne §3) | État GeoStudio vérifié | Livrable | Critères d'acceptation | Dépendances | Effort | Valeur C/B/I | Risque / arbitrage |
|---|---|---|---|---|---|---|---|---|
| ARC-01 | Clustering de points avec étiquettes/popups de cluster, 11.3 [S38] (§3.3 « Clustering de points », ABSENT) | aucune occurrence `cluster` dans `shell/src/map` ; sources GeoJSON simples (`shell/src/map/MapView.tsx:356`) | option `cluster: {radius, maxZoom, label}` sur couche `feature`/GeoJSON (MapLibre natif), calques cercle+compte, clic = zoom ; champ ajouté à `MapLayer` **et** à `toFrontLayer()` (piège n°5) | 1) 10 000 points GeoJSON : 1 cluster à z4, points individuels à z14 (Vitest + E2E) ; 2) rechargement de la page conserve l'option ; 3) incompatible heatmap signalé dans l'éditeur | SP-25/27 (symbologie), REV-283a | S, 3 j | C ●● B ● I – | aucun ; MVT non couvert (ARC-22) |
| ARC-02 | Requêtes `orderByFields`, `time`, `outSR` [S20] (§3.1 « Requêtes », MOINS BIEN) | tri par PK seule : `ORDER BY {pk}` (`features/repository.py:231`) ; pas de `datetime`/`crs` (`features/routes.py:228`) | paramètres OGC `sortby=±champ` (allowlist de colonnes, `quote_ident`), `datetime=` (instant/intervalle sur colonne temporelle déclarée), `crs`/`bbox-crs` (4326, 3857, 2154 minimum) ; `conformsTo` mis à jour (`features/routes.py:118-120`) | 1) `sortby=-nom` ordonne, colonne inconnue = 400 RFC 7807 ; 2) `datetime=2025-01-01/..` filtre ; 3) `crs=EPSG:2154` renvoie des coordonnées Lambert-93 vérifiées contre `ST_Transform` ; 4) la pagination curseur (`__after` sur PK) reste correcte sous tri personnalisé (offset forcé) | REV-353 (bbox), campagne #13, A4/ADR 0004 | S, 3 j | C ●● B ●● I ● | pagination par curseur à restreindre quand `sortby` ≠ PK |
| ARC-03 | Géocodage par lot et reverse (locator fédéré) [S61] (§3.2 « Géocodage », MOINS BIEN) | BAN : un résultat, pas de lot ni reverse (`geocoding/provider.py:43-53`, `geocoding/routes.py:22`) ; MCP `geocode` (`mcp/tools/geocode.py:23`) | `POST /v1/geocode/batch` (≤ 500 adresses, job procrastinate, garde d'egress existante `geocoding/egress.py`), `GET /v1/geocode/reverse`, op pipeline `transform.geocode` | 1) lot de 500 adresses < 60 s avec rapport `non_trouvé` ; 2) reverse renvoie une adresse BAN ; 3) outil MCP `geocode_batch` audité | campagne #9, REV-102/183 (BAN), SP-6 jobs | S, 3 j | C ●●● B ●● I ● | quotas de l'API BAN publique ; prévoir fournisseur hébergé local (hors périmètre) |
| ARC-04 | Contrôle de concurrence par version de branche [S28] (§3.2 « Contrôle de concurrence », MOINS BIEN) | `If-Match` sur configs seulement (`configs/routes.py:61`) ; aucune garde sur `PUT /items/{fid}` (`features/routes.py:784`) | ETag par entité (hash de ligne ou colonne `_version`), `If-Match` optionnel puis recommandé sur PUT/DELETE, 412 RFC 7807 ; formulaire shell gère le conflit | 1) deux PUT concurrents : le 2e reçoit 412 ; 2) sans en-tête, comportement inchangé (rétro-compatible) ; 3) test sur base non vide (piège n°8) | SP-54/REV-271 (If-Match), REV-343 | S, 3 j | C ●● B ● I ● | OpenAPI + types à régénérer (piège n°1) |
| ARC-05 | Statut de contenu authoritative/deprecated + catégories [S66] (§3.6, ABSENT) | aucune occurrence `authoritative` dans `core/app/items` | champs `content_status` (`none/authoritative/deprecated`) et `categories[]` sur `Item`, migration 0052+, badge catalogue, filtre `GET /items?status=`, privilège `catalog.manage` | 1) item « Référence » apparaît en tête (boost) ; 2) déprécié = bandeau + exclu du catalogue public par défaut ; 3) facette dans `GET /items/facets` | SP-55 (facettes), SP-41 | S, 3 j | C ●● B ● I ● | migration testée sur base non vide |
| ARC-06 | Clés d'API / Developer credentials [S65] (§3.6, MOINS BIEN) | jetons OIDC et liens de partage seulement | clé d'API de service par utilisateur/rôle (hash stocké, préfixe visible, expiration ≤ 1 an, révocation), vérifiée par la **même** porte `can()` ; UI dans Paramètres | 1) clé expirée = 401 ; 2) clé n'élève jamais au-delà des privilèges du créateur (test d'invariant) ; 3) usage tracé dans `audit_log` | ADR 0001 (`can()`), SP-31 (rôles), REV-336 | S, 3 j | C ● B ●● I ●●● | **ADR court** : ajoute un mode d'authentification ; aucun mot de passe dans le cœur reste vrai (clé = secret machine, pas mot de passe) |
| ARC-07 | Rôle Publisher séparé [S62] (§3.6, MOINS BIEN) | publication rattachée à d'autres privilèges (`items/routes.py:165`) ; 20 privilèges (`roles/privileges.py:5-25`) | privilège `items.publish` distinct, prédéfinis (Créateur l'a, Lecteur non), migration de rôles | 1) un rôle sur mesure sans `items.publish` ne peut pas passer un item en public (REST + MCP) ; 2) 4 rôles prédéfinis inchangés en comportement | REV-335 (éditeur publie à l'anonyme), SP-31 | S, 2 j | C ●● B ● I ●● | rôles prédéfinis immuables : migration de données, pas de modification de rôle prédéfini |
| ARC-08 | Prérequis de fiabilité des écritures et de l'OGC (aucun équivalent Esri : condition de sérieux de ARC-10/11/12) | REV-335, 352, 353, 359 ouverts (campagne) | correctifs : publication anonyme via PATCH, collection `GEOMETRY` mixte/Polygon→MultiPolygon, bbox hors bornes/NaN, 401 tuiles 3D/icônes sur item public | tests de non-régression de chaque REV ; `bbox=999,0,0,0` = 400 ; Polygon accepté sur couche MultiPolygon | REV-335, 352, 353, 359 | S, 3 j | C ●●● B ●● I ●● | jumelles de garde à lister avant clôture (piège n°14) |
| ARC-09 | Time slider persisté, galerie de fonds de carte d'organisation, légende [S40][S37] (§3.3 « Time slider » MOINS BIEN, « Fonds de carte » MOINS BIEN) | `timePlayer` non persisté dans la carte (`shell/src/builder/widgets/timePlayer.tsx`) ; `PUT` carte avec `timeField` rejeté (REV-356) ; 4-5 fonds publics (`shell/src/map/basemaps.ts:5-12`) | `MapLayer.timeField` accepté (REV-356), lecteur temps dans l'éditeur de carte, collection de fonds de carte par tenant (admin), légende exportée | 1) PUT carte avec `timeField` = 200 et relecture identique ; 2) un admin ajoute un fond WMTS/XYZ, visible par tous ; 3) lecteur temps pilote le filtre `datetime` d'ARC-02 | REV-356, ARC-02, SP-14 | S, 3 j | C ●● B ● I – | fonds tiers : CSP `img-src` (SP-48, allowlist dynamique) |

##### Vague 1 : bloquants collectivité (1-3 mois, jusqu'à 2027-01-11, 86 j-h)

| ID | Capacité ArcGIS visée (réf., ligne §3) | État GeoStudio vérifié | Livrable | Critères d'acceptation | Dépendances | Effort | Valeur C/B/I | Risque / arbitrage |
|---|---|---|---|---|---|---|---|---|
| ARC-10 | Survey123 anonyme / sondages publics (11.4+) [S31] (§3.2 « Soumission citoyenne publique », ABSENT ; §5.1 B3) | écriture OGC authentifiée seulement : `Depends(get_current_user)` (`features/routes.py:738`) | jeton de soumission public par collection (`SubmissionToken`, quota, expiration), route `POST /v1/public/submit/{token}`, **file de modération** (statut `pending/approved/rejected` ; invisible sans validation), captcha/honeypot, rate limit dédié, notifications aux modérateurs | 1) soumission anonyme crée une ligne `pending` invisible dans `list_features` et tuiles ; 2) 101e requête/h/IP = 429 ; 3) approbation → visible, `audit_log` trace modérateur ; 4) pièce jointe ≤ 25 Mo scannée par type ; 5) aucune lecture anonyme élargie (test d'invariant RLS) | campagne #7, ARC-08, REV-336/358, SP-40, SP-39, SP-58, `GuestActor` (`features/routes.py:238`, GAP-19) | M, 8 j | C ●●● B ● I ● | **ADR obligatoire** (modèle de menace anonyme) : contourne « écriture authentifiée » (A4) mais reste derrière `can()` (A1) via un acteur invité borné ; RGPD : données personnelles anonymes à purger (SP-58) |
| ARC-11 | OWS : WFS 2.0 lecture (GetCapabilities, DescribeFeatureType, GetFeature GML 3.2/GeoJSON) + OGC API Tiles (MVT) [S17] (§3.1 « Services OGC OWS », ABSENT ; §5.1 B1) | absents ; tuiles MVT propres (`features/tiles.py:241`) ; conformité limitée (`features/routes.py:84-90,118`) | module `app/ows/` (couche `features` → `ows`), routes `/v1/ows/wfs`, `/v1/collections/{id}/tiles/{tms}/{z}/{x}/{y}` ; **mêmes `rls_scope` et `can()`** que l'API Features ; activation par collection (comme Esri : « à activer explicitement ») | 1) QGIS Desktop charge la couche via WFS (E2E manuel + fixtures XML validées contre le schéma OGC) ; 2) utilisateur sans droit = 403, masquage de champs sensibles respecté ; 3) `lint-imports` vert ; 4) capacité absente du compose quand le flag est éteint | ARC-08, ARC-02, REV-352, A4/ADR 0004, ADR 0012 (connecteurs : GeoStudio moissonne déjà WFS en lecture) | M, 10 j | C ●●● B ●● I ●● | **ADR OWS** (avec ARC-20) ; GML/XML = nouvelle surface de sérialisation (XXE inapplicable en écriture, vérifier à la lecture) |
| ARC-12 | `where` / CQL2 [S20] (§3.1 « CQL2 / datetime / CRS en sortie », ABSENT) | filtres égalité/`__in`/`__gte`/`__lte` (`features/routes.py:210`) | OGC API Features Part 3 : `filter`/`filter-lang=cql2-text` (sous-ensemble : comparaison, AND/OR/NOT, LIKE, IN, BETWEEN, `S_INTERSECTS`, `T_*`) compilé en SQL paramétré (aucune interpolation) | 1) 40 expressions de la suite de référence passent ; 2) `filter=1=1; DROP` = 400 ; 3) `S_INTERSECTS` réutilise la validation `geom_intersects` (`features/routes.py:182`) | ARC-02, ARC-08, A4 | M, 6 j | C ● B ●● I ●● | MIEUX potentiel : Esri non vérifié sur CQL2 (NV §7.1) |
| ARC-13 | Domaines et sous-types d'attributs [S26][S36] (§3.2, MOINS BIEN) | types simples/enum (`collections/introspection.py:13`), validateur type/obligatoire (`features/validation.py:42`) | domaines `list`/`range` déclarés sur le schéma de collection, sous-types portant défauts et domaines, appliqués **à l'écriture** (REST, import, pipeline `writer.collection`) et dans les formulaires générés | 1) valeur hors domaine = 400 `field/code` ; 2) formulaire affiche une liste déroulante filtrée par sous-type ; 3) import CSV : lignes hors domaine rejetées dans le rapport ; 4) migration test base non vide | SP-4 (formulaires, A9), ARC-04, REV-337 | M, 8 j | C ●●● B ●● I ●● | pas de rétro-application sur données existantes (rapport seulement) |
| ARC-14 | Règles d'attributs (calcul/contrainte immédiats, batch différé) [S27] (§3.2, MOINS BIEN) | validateur sans règle métier (`features/validation.py:1-25`) ; CEL disponible (`expr_validation.py`) | règles CEL par collection : `calculation` (valeur par défaut/dérivée), `constraint` (message FR), `batch` (job de validation produisant un rapport de qualité, réutilise le port Rejected FME §6 rang 2) | 1) contrainte `surface > 0` rejette avec le message ; 2) calcul alimente un champ à l'insertion ; 3) batch sur 50 000 entités < 60 s ; 4) génération NL→règle CEL par MCP avec revue humaine | SP-5 (CEL, A8), ARC-13, campagne #4, REV-337 | M, 10 j | C ●●● B ●● I ●●● | **MIEUX visé** : Esri exige l'extension payante Advanced Editing pour validation/batch [S27] ; CEL ≠ Arcade (pas de portage) |
| ARC-15 | `ChangeTracking` / historique d'entité [S19] (§3.2, ABSENT) | `asOf` sur le lac seulement (`analytics/snapshot.py`) ; pas de journal avant/après (`features/routes.py:784`) ; `audit_log` sans diff (`audit/writer.py:7`) | journal d'entité `before/after` (JSON) écrit dans la même transaction que l'écriture ; `GET /collections/{id}/items/{fid}/history`, `GET /collections/{id}/changes?since=` ; restauration d'une version ; shell : onglet Historique | 1) PUT puis historique : 2 versions avec auteur ; 2) `changes?since=` ne renvoie que le delta ; 3) un champ masqué reste masqué dans l'historique ; 4) l'anonymisation (SP-58) efface l'auteur du journal | campagne #5, SP-58/ADR 0015, SP-11 (asOf), ARC-04 | M, 10 j | C ●●● B ●● I ●● | stockage croissant : quotas (SP-58) + purge ; sert de socle à ARC-31 |
| ARC-16 | PrintingTools : A3/A4/Tabloid, mises en page, formats PDF/PNG/SVG [S44] (§3.3 « Impression », MOINS BIEN ; §5.2 B10) | `printLayout` + worker Playwright (`configs/schemas.py:456-498`, `export/rendering.py`) ; pas de gabarits | gabarits de mise en page (A4/A3 portrait/paysage, cartouche, légende, échelle graphique, flèche du nord, texte libre, logo), export PDF/PNG/SVG ; éditeur de gabarit dans le builder | 1) PDF A3 paysage avec échelle exacte à ±1 % (mesure sur capture) ; 2) légende reflète la symbologie courante ; 3) job en worker, timeout 120 s, annulable ; 4) E2E du rendu | SP-17 (A25), REV-358 (export en démo), REV-363 (mesure clavier) | M, 10 j | C ●●● B ●●● I ● | **A25 respecté** (Playwright, pas de QGIS Server) ; mise en page « Pro » complète (atlas) reportée à ARC-30 |
| ARC-17 | Styles Dot Density, Predominant, bivarié, Compare A to B, effets visuels [S37][S39] (§3.3 « Symbologie data-driven » MOINS BIEN ; « Effets visuels » ABSENT) | catégoriel/classé/continu (`shell/src/builder/widgets/mapSymbology.ts:138-160`) ; aucun dot density/bivarié | 4 nouveaux modes dans `mapSymbology.ts` + `MapSymbologyEditor`, légende associée, effets (bloom, ombre, fusion) | 1) chaque mode round-trippe après rechargement (`toFrontLayer()`, piège n°5) ; 2) légende correcte ; 3) identiques éditeur et widget carte (SP-25) | SP-25/27, ARC-01 (légende) | M, 8 j | C ●● B ●● I – | périmètre ouvert : borner à 4 modes |
| ARC-18 | HA : 2 portails + LB, data stores en réplication [S68] (§3.7, ABSENT ; §5.1 B4) | monolithe `core`, pgbouncer, pas de réplicas (`docker-compose.yml:47,226`) ; limiteur en mémoire par process (`ratelimit/limiter.py:2`) | **HA documentée et testée** : runbook (2 instances `core` derrière Traefik, Postgres primaire/standby streaming, MinIO distribué, RPO/RTO annoncés), test de bascule scripté, vérification des invariants avec 2 réplicas (jobs, limiteur, CSP) ; correctifs REV-354/355/345 | 1) `docker compose up --scale core=2` passe la suite de fumée ; 2) arrêt d'un réplica : < 5 s d'indisponibilité mesurée ; 3) document RPO/RTO relu ; 4) limiteur : écart documenté | REV-164 (partiel), REV-354/355/345, SP-49, SP-59, ARC-19 | M, 8 j | C ●●● B ● I ●● | périmètre Esri borné à un datacenter [S68] ; la HA **réelle** (limiteur partagé, élection CDC, Helm) est ARC-32 (décision) |
| ARC-19 | WebGISDR : sauvegarde/restauration complète [S69] (§3.7, MOINS BIEN) | `deploy/backup/backup.sh:106`, `restore.sh` ; restauration non vérifiée automatiquement ; reconnexion OIDC jamais vérifiée (REV-164) | « drill » de restauration automatisé (CI hebdomadaire : sauvegarde → `down -v` → restauration → fumée OIDC) + sonde de fraîcheur | 1) job CI vert sur stack réelle ; 2) échec si buckets/realm manquent ; 3) temps de restauration publié | REV-164, SP-59, `scripts/replay/restore-oidc.sh` | M, 8 j | C ●●● B ● I ●● | exige `down -v` : jamais sur la base de référence partagée (piège SP-49) |

##### Vague 2 : consolidation (3-6 mois, jusqu'à 2027-04-11, 54 j-h)

| ID | Capacité ArcGIS visée (réf., ligne §3) | État GeoStudio vérifié | Livrable | Critères d'acceptation | Dépendances | Effort | Valeur C/B/I | Risque / arbitrage |
|---|---|---|---|---|---|---|---|---|
| ARC-22 | Binning points/lignes/polygones (11.5) [S38] (§3.1 « Tuiles agrégées », MOINS BIEN) | agrégation de tuiles denses déjà présente (`features/tiles.py:138-148,293`) ; `HexagonLayer` client (`shell/src/map/mapDeckTerrain.ts:24`) | binning hexagonal/carré côté tuile avec statistique (count/sum/avg) et symbologie continue | tuile à z6 sur 1 M de points < 1 s, comptes exacts vs `count(*)` | ARC-01, REV-283a | M, 6 j | C ●● B ●● I – | plafond 5000 entités/tuile (SP-24) à ne pas contourner |
| ARC-23 | Data Interoperability (FME embarqué, payant) pour import avancé [S58] (§3.1 « Formats d'import », MOINS BIEN ; §5.2 B7) | 10 formats d'import (`ingestion/importer.py:82-103`) ; `reader.file` DuckDB `ST_Read` existe | import FileGDB (lecture OpenFileGDB), DXF, GML complexe, MapInfo/TAB via GDAL de DuckDB ; mêmes bornes que SP-56 | 1) FileGDB de 3 couches importé avec géométries valides ; 2) VRT refusé (REV-333) ; 3) matrice FME `planned_gdal` : ≥ 10 lignes `implemented` | REV-333 (VRT), SP-56, matrice FME, §6 rang 7 | M, 8 j | C ●● B ●●● I ●● | **MIEUX visé** : Esri facture l'extension ; GDAL (MIT) compatible Apache-2.0 ; DWG exclu (licence) |
| ARC-24 | Groupes externes → groupes portail (claim/assertion) [S11] (§3.6, MOINS BIEN) | groupes gérés par le cœur, non synchronisés (`sharing/routes.py:57-203`) ; claims lus dans `auth/dependency.py:162-231` | table de mapping `claim groups → groupe du cœur` (admin), appliquée à la connexion de façon **additive** | 1) utilisateur du groupe Keycloak « SIG » rejoint le groupe cœur mappé ; 2) retrait côté IdP retire l'appartenance au prochain login ; 3) groupes manuels intacts | A2/ADR 0002, §6 rang 17 | M, 6 j | C ●● B ● I ●●● | **A2 signalé** : groupes restent « gérés par le cœur », seul l'appartenance est alimentée ; sinon ADR amendant A2 |
| ARC-25 | Widget Analysis (25 à 64 outils [S56][S15]) (§3.4 « Analyse embarquée », MOINS BIEN ; §3.5 « Outils géospatiaux ») | requête visuelle Filtrer→Joindre→Résumer (SP-14o) ; 47+ op de pipeline dont buffer/intersection (`pipelines/ops/contracts.py:205-232`) | widget « Analyse » exécutant un sous-ensemble d'op de pipeline (buffer, intersection, jointure spatiale, count within, dissolve) sur un dataset, sortie = dataset éphémère ou collection | 1) buffer 500 m sur 10 000 points < 10 s, résultat affiché ; 2) RLS/masquage respectés (même chemin que `/aggregate`) ; 3) 8 outils minimum avec schéma et aide | SP-14o, A18/A19, OperationContract | M, 10 j | C ●● B ●●● I ●● | périmètre Esri flou (25 vs 64, §7.1) : viser 8-12 outils utiles, pas la parité numérique |
| ARC-26 | Templates, widgets Print/Swipe/Basemap gallery/Feature Report [S46][S15] (§3.4, MOINS BIEN ×2) | 4 gabarits (`shell/src/builder/templates.ts:232`) ; pas de swipe | 8 gabarits supplémentaires (portail données ouvertes, tableau de bord territorial, suivi de chantier, enquête…), widgets Swipe, Galerie de fonds de carte, Fiche d'entité imprimable (PDF) | 1) chaque gabarit s'instancie depuis le catalogue et passe le schéma `AppConfig` ; 2) a11y axe vert ; 3) `create_item` MCP accepte `template` | SP-13, A31/A36, ARC-16, ARC-09 | M, 8 j | C ●● B ● I ● | gabarits = données déclaratives (règle 2) |
| ARC-27 | Field Maps / Survey123 en ligne : XLSForm, capture GPS, photo [S30][S31] (§3.2 « Collecte terrain » MOINS BIEN, « Enquêtes » MOINS BIEN ; §5.1 B2 partiel) | widget `form` en ligne (`shell/src/builder/widgets/form.tsx`), `create_form_app` (`mcp/form_app.py`), pièces jointes (SP-40) | import XLSForm → App formulaire, mode mobile-first avec capture géolocalisée + photo, liste « mes saisies » | 1) XLSForm de 30 questions importé sans perte (types, listes, `relevant` → `visibleWhen` CEL) ; 2) saisie sur mobile Chrome émulé avec GPS ; 3) soumission via ARC-10 pour le public | ARC-10, ARC-13, SP-4, SP-40 | M, 10 j | C ●●● B ●● I ● | hors ligne explicitement exclu (ARC-31) ; Survey123 app terrain en maintenance chez Esri |
| ARC-28 | Éditeur de style de tuiles vectorielles, `.vtpk`, portabilité [S21] (§3.3 « Portabilité de style », ABSENT) | style interne JSON (symbologie déclarative) | export **SLD 1.1** et **Mapbox/MapLibre style JSON** depuis la symbologie ; import MapLibre style | 1) export SLD validé par XSD sur 6 symbologies types ; 2) style MapLibre rechargé donne un rendu identique (capture) | campagne #11, ARC-17, ARC-20 (prérequis du rendu WMS) | M, 6 j | C ● B ●● I ●● | MIEUX potentiel : Esri n'exporte pas de SLD (R) |

##### Vague 3 : parité avancée (6-12 mois, jusqu'à 2027-10-11, 61 j-h)

| ID | Capacité ArcGIS visée (réf., ligne §3) | État GeoStudio vérifié | Livrable | Critères d'acceptation | Dépendances | Effort | Valeur C/B/I | Risque / arbitrage |
|---|---|---|---|---|---|---|---|---|
| ARC-20 | WMS 1.3.0 / WMTS 1.0.0 [S17] (§3.1 « OWS », reste après ARC-11 ; §5.1 B1) | absents (`features/routes.py:85-90`) | `GetCapabilities/GetMap/GetFeatureInfo` WMS et WMTS **rendus par le cœur** (renderer Python sur la symbologie déclarative d'ARC-28) ; WMTS raster depuis MVT impossible tel quel | 1) QGIS/ArcGIS Pro consomment la couche en WMS 1.3.0 ; 2) RLS identique à l'API Features (test croisé) ; 3) rendu 256×256 < 300 ms p95 | ARC-11, ARC-28, ARC-17, A3 (RLS), A12 | L, 25 j | C ●●● B ●● I ●● | **ADR OWS : contradiction possible avec A12/A3** si le rendu passe par un sidecar GPL (GeoServer, GPL-2.0) ou qui lit PostGIS hors `rls_scope` ; précédent : retrait de `transform.qgis` (GPL) ; options : renderer interne (recommandé), MapServer (MIT) derrière proxy authentifié sans accès direct à la base |
| ARC-21 | Relationship classes 1-1/1-N/N-N, related records [S26][S19] (§3.2, ABSENT ; §5.1 B5) | jointure de requête visuelle seulement (`pipelines/ops/contracts.py:196`) | relation déclarée entre deux collections (clé étrangère logique ou réelle), enregistrements liés dans popup/formulaire (maître-détail), suppression en cascade optionnelle | 1) maître-détail : parcelle → propriétaires ; 2) suppression restreinte si enfants ; 3) RLS appliquée aux deux côtés | ARC-13, ARC-04, ARC-15, SP-3/4 | L, 18 j | C ●● B ●● I ●● | **ADR** modèle de données ; pas de géodatabase d'entreprise (hors périmètre) |
| ARC-29 | Déploiement Kubernetes/Helm, arcgis-gitops [S71][S72] (§3.7 « Déploiement », MOINS BIEN) | Docker Compose, Ansible Proxmox/OCI, OpenTofu OCI ; pas de Helm | chart Helm (core, worker, cdc, shell, export, observabilité optionnelle), images amd64+arm64 | 1) `helm install` sur kind passe la fumée ; 2) valeurs documentées ; 3) `test_deployability`-équivalent pour le chart | ARC-18, release arm64 | L, 12 j | C ● B ● I ●●● | MIEUX : Esri K8s x86_64 seulement [S71] ; ne pas lancer sans ARC-18 |
| ARC-30 | Mise en page Pro, atlas / pages de série [S44] (§5.2 B10) | gabarits d'ARC-16 | atlas : une page par entité d'une couche, champs dynamiques CEL | 1) atlas de 50 communes → PDF de 50 pages ; 2) annulation en cours de job | ARC-16, ARC-26 | M, 6 j | C ●● B ●●● I – | **A25** : si la demande exige du print « pro », la bascule QGIS Server reste conditionnelle à une demande réelle |

##### Hors périmètre / décisions à trancher (ADR requis avant tout lancement)

| ID | Capacité ArcGIS visée (réf., ligne §3) | État GeoStudio vérifié | Livrable potentiel | Critères d'acceptation | Dépendances | Effort | Valeur C/B/I | Risque / arbitrage |
|---|---|---|---|---|---|---|---|---|
| ARC-31 | Offline areas, édition hors ligne [S29][S30] (§3.2, ABSENT ; §5.1 B2) | bannière de connectivité seulement (`shell/src/shell/ConnectivityBanner.tsx:36`) | PWA de collecte : cache de zone (MVT/raster), file d'écritures, synchronisation avec résolution de conflits | 1) saisie hors ligne puis synchro sans perte ; 2) conflit 412 résolu côté utilisateur | ARC-04, ARC-15, ARC-27 ; **REV-120 / Q11 fermée par décision 2026-10-10 à rouvrir** | L, 25 j | C ●● B ●● I – | **contredit la décision de clôture de REV-120** ; Esri impose une géodatabase d'entreprise : la barre est haute (§3.2) |
| ARC-32 | HA réelle multi-réplicas (§3.7) | limiteur en mémoire (`ratelimit/limiter.py:2`), CDC mono-writer | limiteur partagé (Postgres), élection du `cdc-worker`, `core` sans état, Postgres/MinIO répliqués, support contractuel externe | bascule < 30 s sous charge, aucune perte d'écriture | ARC-18, ARC-29, REV-164 | L, 25 j | C ●●● I ●● | support « contractuel » = offre de service, pas du code (ligne §3.7 « Support », NV) |
| ARC-33 | Image Server, raster analytics [S53] (§3.1/§3.5, ABSENT) | TiTiler non exposé (`docker-compose.yml:168`), `deploy/titiler` | ingestion COG, proxy TiTiler authentifié par `can()`, zonal stats, `reader.raster` | COG 1 Go servi en tuiles ; RLS par item ; 1 outil d'analyse | matrice FME raster, §6 rang 19 | L, 30 j | B ●●● C ●● | **ADR positionnement** (Q2 : produit horizontal) ; licences GDAL/rasterio OK |
| ARC-34 | Network analysis (routage, isochrones, zones de service) [S56] (§3.5, ABSENT) | absent (`pipelines/ops/contracts.py:205`) | service externe Valhalla/OSRM (MIT/BSD) appelé par le cœur sous egress, ops de pipeline + widget Directions | isochrone 10 min < 2 s ; audit des appels | §6 rang 22 | L, 20 j | B ●●● C ●● | pgRouting (GPL-2) à éviter (précédent QGIS) ; données de réseau non fournies |
| ARC-35 | Flux temps réel (GeoEvent → Velocity) [S57] (§3.4, ABSENT) | sondage ; Q10 ouverte (REV-114, fermé par décision) | push SSE/WebSocket pour widgets et alertes | latence < 2 s sur 50 abonnés | REV-114 | L, 12 j | I ● C ● | **à ne pas cloner** : GeoEvent déprécié ; contredit la décision REV-114 |
| H1 | Versioning de branche [S28] ; géodatabase d'entreprise complète [S26] | écriture directe | aucun | n/a | ARC-04/15/21 couvrent 80 % du besoin | L, > 40 j | – | hors périmètre : coût disproportionné |
| H2 | Scene layers I3S, Gaussian splats, couches vidéo, tracking GPS, QuickCapture, Notebooks, GeoEnrichment, certifications FedRAMP/ISO | absent | aucun | n/a | n/a | L | – | hors périmètre (valeur faible, §3, ou données/certification externes) ; domaine personnalisé et communauté déjà différés (A33, A38) |

#### 6.1.3 Chemin critique et graphe de dépendances

Chemin critique « remplacement collectivité » (séquentiel ≈ 47 j-h) : ARC-08 → ARC-02 → ARC-11 → ARC-12 → ARC-20 (WMS/WMTS). En parallèle : ARC-08 → ARC-10 (soumission publique) ; ARC-04 → ARC-13 → ARC-14 → ARC-21 (édition avancée) ; ARC-16 (impression) indépendant ; ARC-18 → ARC-19 → (ARC-29, ARC-32).

```text
ARC-08 --+--> ARC-02 --> ARC-09
         |        \--> ARC-12 --> ARC-11 --> ARC-20 (WMS/WMTS) <-- ARC-28 <-- ARC-17
         +--> ARC-10 --> ARC-27 --> ARC-31 (hors ligne, décision)
ARC-04 --> ARC-13 --> ARC-14 --> ARC-21
ARC-04 --> ARC-15 --> ARC-31
ARC-01 --> ARC-22 ;  ARC-01 --> ARC-17
ARC-16 --> ARC-26 --> ARC-30 ;  ARC-16 --> ARC-30
ARC-18 --> ARC-19 --> ARC-29 --> ARC-32 (décision)
ARC-06, ARC-07, ARC-03, ARC-05, ARC-23, ARC-24, ARC-25 : indépendants (feuilles)
```

(ARC-11 dépend d'ARC-02 ; ARC-12 est livré avant ARC-11 si le WFS doit exposer `filter`, sinon en parallèle : ordre libre, effort identique.)

#### 6.1.4 Tableau récapitulatif triable

Verdict visé = verdict de la ou des lignes §3 une fois le chantier livré. Valeur = somme C+B+I (●=1, max 9).

| ID | Titre | Vague | Effort | Valeur C/B/I | Verdict visé |
|---|---|---|---|---|---|
| ARC-01 | Clustering de points | 0 | S, 3 j | 2/1/0 | ISO |
| ARC-02 | `sortby`, `datetime`, `crs` | 0 | S, 3 j | 2/2/1 | ISO |
| ARC-03 | Géocodage lot et reverse | 0 | S, 3 j | 3/2/1 | ISO |
| ARC-04 | Concurrence optimiste sur entités | 0 | S, 3 j | 2/1/1 | ISO |
| ARC-05 | Statut de contenu et catégories | 0 | S, 3 j | 2/1/1 | ISO |
| ARC-06 | Clés d'API de service | 0 | S, 3 j | 1/2/3 | ISO |
| ARC-07 | Privilège de publication séparé | 0 | S, 2 j | 2/1/2 | ISO |
| ARC-08 | Prérequis fiabilité OGC/écriture | 0 | S, 3 j | 3/2/2 | (prérequis) |
| ARC-09 | Time slider persisté, fonds de carte, légende | 0 | S, 3 j | 2/1/0 | ISO |
| ARC-10 | Soumission citoyenne publique modérée | 1 | M, 8 j | 3/1/1 | ISO |
| ARC-11 | WFS 2.0 lecture + OGC API Tiles | 1 | M, 10 j | 3/2/2 | MOINS BIEN (ISO avec ARC-20) |
| ARC-12 | CQL2 (Part 3) | 1 | M, 6 j | 1/2/2 | ISO (MIEUX si Esri sans CQL2) |
| ARC-13 | Domaines et sous-types | 1 | M, 8 j | 3/2/2 | ISO |
| ARC-14 | Règles d'attributs CEL | 1 | M, 10 j | 3/2/3 | MIEUX |
| ARC-15 | Historique d'entité / change tracking | 1 | M, 10 j | 3/2/2 | ISO |
| ARC-16 | Impression : gabarits de mise en page | 1 | M, 10 j | 3/3/1 | ISO |
| ARC-17 | Symbologie : dot density, prédominance, bivarié, effets | 1 | M, 8 j | 2/2/0 | ISO |
| ARC-18 | HA documentée et testée | 1 | M, 8 j | 3/1/2 | MOINS BIEN (périmètre Esri borné) |
| ARC-19 | Drill de restauration automatisé | 1 | M, 8 j | 3/1/2 | ISO |
| ARC-20 | WMS/WMTS rendus par le cœur | 3 | L, 25 j | 3/2/2 | ISO |
| ARC-21 | Relations 1-N et enregistrements liés | 3 | L, 18 j | 2/2/2 | ISO |
| ARC-22 | Binning serveur | 2 | M, 6 j | 2/2/0 | ISO |
| ARC-23 | Import GDAL : FileGDB, DXF, TAB | 2 | M, 8 j | 2/3/2 | MIEUX (Esri payant) |
| ARC-24 | Mapping des groupes IdP | 2 | M, 6 j | 2/1/3 | ISO |
| ARC-25 | Widget Analyse spatiale | 2 | M, 10 j | 2/3/2 | ISO |
| ARC-26 | Gabarits et widgets d'app | 2 | M, 8 j | 2/1/1 | ISO |
| ARC-27 | Collecte terrain en ligne + XLSForm | 2 | M, 10 j | 3/2/1 | ISO |
| ARC-28 | Export SLD / Mapbox style | 2 | M, 6 j | 1/2/2 | MIEUX |
| ARC-29 | Helm / Kubernetes | 3 | L, 12 j | 1/1/3 | MIEUX (arm64) |
| ARC-30 | Atlas d'impression | 3 | M, 6 j | 2/3/0 | ISO |
| ARC-31 | Hors ligne (PWA) | décision | L, 25 j | 2/2/0 | ISO (conditionnel) |
| ARC-32 | HA réelle multi-réplicas | décision | L, 25 j | 3/0/2 | ISO |
| ARC-33 | Raster COG + TiTiler + zonal | décision | L, 30 j | 2/3/0 | MOINS BIEN → ISO |
| ARC-34 | Routage / isochrones | décision | L, 20 j | 2/3/0 | ISO |
| ARC-35 | Push temps réel | décision | L, 12 j | 1/0/1 | non cible (déprécié) |

Total : 35 chantiers (V0 : 9, V1 : 10, V2 : 7, V3 : 4, décision : 5) + 2 lignes hors périmètre (H1, H2) ; effort engagé V0-V3 = 227 j-h, décisions = 112 j-h.

#### 6.1.5 Cinq paris stratégiques (viser MIEUX plutôt qu'ISO)

1. **IA agentique sur l'édition** (ARC-14, ARC-27) : règles CEL, XLSForm et formulaires générés par MCP/copilote avec revue humaine ; Esri n'a aucune source équivalente (ligne NV, §3.7).
2. **Participation citoyenne modérée et conforme RGPD** (ARC-10 + SP-58) : Survey123 anonyme existe, mais sans anonymisation/purge ni audit dédié chez Esri (§3.6).
3. **OGC moderne complet** (ARC-11/12 + Part 4 + STAC/DCAT + moissonnage) : être le seul à offrir écriture standard, CQL2, Tiles et catalogue ouvert sans extension.
4. **Qualité et traçabilité incluses** (ARC-14/15) : règles d'attributs et historique sans l'extension payante Advanced Editing [S27].
5. **Zéro verrou et déploiement léger** (ARC-23, ARC-28, ARC-29) : GDAL/FileGDB, SLD/Mapbox, Helm arm64 sous Apache-2.0 ; coût de licence nul (§3.7 « Licence »).

#### 6.1.6 Indicateurs de succès

Recalcul mécanique du verdict (bloc §3 : lignes 181-345) :

```bash
sed -n '/^## 3\. ArcGIS/,/^## 4\./p' docs/revue/2026-10-11-comparatif-fme-arcgis-enterprise.md | awk -F'|' 'NF>9 && $2!~/Capacité|---/ {gsub(/^ +| +$/,"",$5); c[$5]++; n++} END{for(k in c)print k,c[k]; print n}'
```

| Jalon | Lignes qui passent ISO/MIEUX (cumul) | ISO+MIEUX cible sur 131 lignes |
|---|---|---|
| Aujourd'hui | 0 | 73 (55,7 %) |
| Fin vague 0 (2026-11-11) | 9 | 82 (62,6 %) |
| Fin vague 1 (2027-01-11) | 18 | 91 (69,5 %) |
| Fin vague 2 (2027-04-11) | 28 | 101 (77,1 %) |
| Fin vague 3 (2027-10-11) | 31 | 104 (79,4 %) |
| Avec les 5 décisions | 38 | 111 (84,7 %) |

Autres indicateurs : bloquants collectivité B1-B6 (§5.1) fermés (cible : B1, B3, B4, B6 en fin de vague 3) ; nombre de lignes ABSENT (28 → ≤ 14 hors décisions) ; `feature_health_cli.py --check` sans régression de la santé médiane ; REV `ouvert` de la campagne (REV-332 à 365) ≤ 10 avant le début de la vague 1 ; essai pilote : une collectivité test migre un périmètre réel (catalogue + 3 cartes + 1 formulaire public) sans recours à ArcGIS en fin de vague 1.

#### 6.1.7 Risques et hypothèses

- **Lignes NV (16, §7.1)** : si Esri offre réellement légende automatique, recherche d'adresse, tuiles raster, alertes ou quotas, les verdicts ISO restent ; si Esri offre CQL2 ou écriture OGC API Features Part 4 sur Enterprise (non lu), le MIEUX d'ARC-12 et de §4 point 2 s'effondre en ISO. « Support et écosystème » (NV, ABSENT, priorité haute §3.7) n'est pas un chantier de code mais pèse sur tout achat collectivité : hors feuille de route technique.
- **Contradictions de sources (§7.1)** : domaines personnalisés d'Enterprise Sites (page développeurs vs pages de prix) : s'ils sont confirmés, **A33 (domaine personnalisé différé) devrait être rouvert** ; fin de GeoEvent (12.3 vs « eventual deprecation ») conditionne ARC-35 ; taille du widget Analysis (25 vs 64) borne ARC-25 ; GA de Data Pipelines en 12.1 (R) pourrait relever la barre côté pipelines (§2).
- **Lignes R/D** : ~60 % des verdicts de ce plan reposent sur S ; les lignes R (Image Server, relations, historique, géodatabase) doivent être revalidées avant communication externe.
- **Capacité** : 227 j-h engagés sur 12 mois supposent 1 flux ≈ 20 j-h/mois et zéro régression ; chaque chantier suit TDD + revue par tâche + revue finale (piège n°4), ce qui ajoute ~30 % non compté.
- **Arbitrages potentiellement contredits** : A2 (ARC-24, groupes alimentés par l'IdP), A4/A1 (ARC-10, écriture anonyme et nouvelle surface OWS ARC-11/20), A12/A3 (ARC-20, rendu WMS par sidecar GPL ou hors RLS), A25 (ARC-16/30, si print « pro » exigé), A33 (si Esri confirme les domaines personnalisés). Décisions de clôture rouvertes : REV-114 (ARC-35) et REV-120/Q11 (ARC-31). ADR à écrire : ARC-06 (court), ARC-10, ARC-11/20, ARC-21, ARC-31 à ARC-35.
- **Piège de périmètre** : ne pas confondre rattrapage et dérive vers une géodatabase d'entreprise (H1) ; chaque chantier doit rester un document déclaratif (règle 2) et passer par `can()` (règle 1 de la table des décisions).

---

## 7. Limites, points non vérifiés et sources

### 7.1 Limites de l'analyse

- **Biais de sélection des lignes** : les pourcentages de §1.2 mesurent mes lignes de matrice, pas un volume fonctionnel. Le chiffre exact et robuste est celui de la matrice FME : 110/290 (37,9 %).
- **Matrice FME sous-ensemble** : 290 transformers recensés contre « 400+ » annoncés [S2] ; l'année de ce chiffre est inconnue. La matrice date d'avant certaines clôtures (elle peut ne pas refléter `transform.httpCall` partout ; vérifié : HTTPCaller est `implemented`).
- **Écart 59/60/61 op** : le récit dit 59 exposées / 61 brutes ; mesuré par import : 61 brutes. Le nombre exposé dépend de flags d'exécution, non remesuré ici.
- **Capacités FME non sourcées** : les lignes FME dont la colonne concurrent contient « non vérifié » reposent sur la connaissance générale (writer modes, lineage, tarification, nombre exact de transformers).
- **ArcGIS Enterprise, état de la vérification (2026-10-11)** : 131 lignes dont 69 S, 37 R, 9 D, 16 NV. Reprise à partir de 7 jeux de notes (données, édition, cartographie, applications, analyse, sécurité, administration) et de 7 recherches ciblées supplémentaires (OGC, pièces jointes, géodatabase, jointures hébergées, mesure, terrain, OGC API Features). Les lignes R reposent sur des extraits de résultats de recherche ou des miroirs institutionnels de la doc Esri, non relus sur la page officielle.
- **Pages inaccessibles** : `support.esri.com` (cycle de vie), les blogs `esri.com/arcgis-blog` (403 au fetch), plusieurs pages `enterprise.arcgis.com` (ECONNRESET, p. ex. « what's new » 12.1 du portail), `developers.arcgis.com` (404 sur les URL OGC API). Les dates de cycle de vie et les nouveautés 12.1 viennent donc de résumés (R) et sont à revérifier.
- **Toujours non vérifié côté Esri** : CQL2 et écriture OGC API Features d'Enterprise (la page OGC ne décrit que la lecture) ; STAC ; moissonnage de catalogues tiers ; SQL libre ; CSW, OGC API Tiles/Maps ; utility network ; limites actuelles du Network Analysis (page 10.7 seulement) ; géocodage par lot générique ; Experience Builder (Edit/Survey123 en détail, comportement anonyme des formulaires) ; archivage et change tracking en détail ; statut de Data Reviewer en 12.0 ; ABAC ; chiffrement au repos natif et certifications d'Enterprise ; GeoEvent/Velocity alertes ; CPU/RAM minimaux Portal/Server ; statut de Cloud Builder ; date de fin de support de 12.1 ; tarifs officiels ; et les 16 lignes NV (légende, recherche d'adresse, quotas, rate limiting, MCP/IA, notifications, rotation de secrets, point d'autorisation, annuler/rétablir, génération d'app par IA, alertes, profilage, NL->SQL, support/écosystème, application desktop, tuiles raster).
- **Contradictions de sources non tranchées** : verrouillage de compte built-in (5 échecs/15 min modifiable selon `configure-security`, non modifiable selon `about authentication`) ; Enterprise Sites et domaines personnalisés (page développeurs contre page de prix) ; fin de GeoEvent (12.3 selon la page GeoEvent 12.1, « eventual deprecation » selon la FAQ Velocity 12.1) ; nombre d'outils du widget Analysis (25 selon un miroir, 64 selon [S15]) ; Workforce (retrait 12.2, trimestre divergent selon les sources) ; GA de Data Pipelines en 12.1 (résumé de recherche seulement).
- **Tarification** : aucun prix FME n'a été collecté. Chez Esri la structure par type d'utilisateur est sourcée (S), les tarifs sont non publics ; seuls des repères indirects non officiels figurent en §3.8 (R). Ne pas chiffrer le gain de licence sans devis.
- **Version** : Esri 11.5, 12.0 et 12.1 coexistent dans les sources ; la page 12.0 ne liste aucun changement propre aux types d'utilisateurs, contrairement à ce que laissait entendre une version antérieure de ce document. Plusieurs faits sont datés d'une version ancienne (Network Analysis 10.7, GeoAnalytics 10.7/11.3, Notebook 10.9) et signalés comme tels. FME : documentation 2025.x et 2026.x mélangées.
- **Capacités GeoStudio non rejouées** : les verdicts s'appuient sur la lecture du code ; l'exécution sur stack réelle de ces surfaces n'a pas été refaite dans cette session (cf. `docs/revue/2026-10-10-rapport-rejeu-stack-reelle.md`).
- **Redshift** : classé `implemented` par la matrice sans op dédiée visible ; à confirmer.

### 7.2 Divergences récit/code relevées

- Récit : copilote « 8 outils » ; code : 9 outils (`copilot/tools_allowlist.py:14-24`).
- Récit : 18 privilèges ; code : 20 entrées d'enum (`roles/privileges.py:5-25`).
- Récit : « 9e kind » `ReportSchedule` ; code : 11 kinds dans `BuilderConfig` (`configs/schemas.py:469`).
- Récit : « SP-14 requête visuelle ... catalogue 12 types » ; code : 25 types de widgets natifs (`builtin_widget_types.json`).
- Récit : multi-tenant ; code : tenant par défaut unique (`auth/dependency.py:181`).

### 7.3 Sources

- [S1] FME, Web data services et webhooks : https://support.safe.com/hc/en-us/articles/25407390010381-Working-with-FME-and-Web-Data-Services-and-Protocols
- [S2] Teradata, page partenaire Safe Software (« 300+ formats, 400+ transformers », non daté) : https://www.teradata.com/partners/safe-software
- [S3] 1Spatial, FME Form (« 450+ formats », non daté) : https://1spatial.com/products/fme/fme-form/ ; Wikipedia FME : https://en.wikipedia.org/wiki/FME_(software)
- [S4] FME, rejected features : https://docs.safe.com/fme/html/FME-Form-Documentation/FME-Form/Workbench/Viewing_Rejected_Features.htm ; FeatureReader : https://docs.safe.com/fme/2023.1/html/FME-Form-Documentation/FME-Transformers/Transformers/featurereader.htm
- [S5] FME Flow Automations : https://docs.safe.com/fme/html/FME-Flow/WebUI/Automations-General/Automations.htm ; déclencheur Schedule : https://docs.safe.com/fme/html/FME-Flow/WebUI/Automations-Triggers/Trigger-Schedule.htm ; Run a Workspace : https://docs.safe.com/fme/html/FME-Flow/WebUI/Automations-Actions/Action-Run-Workspace.htm
- [S6] FME Flow Schedules (fuseau, skip if job in progress, expiry) : https://docs.safe.com/fme/html/FME-Flow/WebUI/schedules.htm
- [S7] Job recovery (resubmission, défaut 3) : https://docs.safe.com/fme/2017.1/html/FME_Server_Documentation/Content/AdminGuide/Job_Recovery.htm (ancienne version ; config 2024 : https://docs.safe.com/fme/2024.0/html/FME-Flow/ReferenceManual/ConfigFileRef.htm)
- [S8] Paramètres publiés/privés : https://docs.safe.com/fme/2025.0/html/FME-Form-Documentation/FME-Form/Workbench/published_private_parameters.htm
- [S9] Nouveaux formats 2025.0 : https://docs.safe.com/fme/2025.0/html/FME-Form-Documentation/FME-ReadersWriters/New-Formats-2025.htm ; 2025.2 : https://databuilders.ie/whats-new-in-fme-2025-2-flow-and-form-updates/ ; formats Esri : https://docs.safe.com/fme/html/FME-Form-Documentation/FME-ReadersWriters/esri-format-list.htm
- [S10] ArcGIS Enterprise HA : https://enterprise.arcgis.com/en/portal/latest/administer/windows/ha-scenarios-web-gis.htm ; https://enterprise.arcgis.com/en/portal/latest/administer/windows/configuring-a-highly-available-portal.htm
- [S11] SAML : https://enterprise.arcgis.com/en/portal/latest/administer/windows/configuring-a-saml-compliant-identity-provider-with-your-portal.htm ; OIDC : https://enterprise.arcgis.com/en/portal/latest/administer/windows/openid-connect-logins.htm
- [S12] Types d'utilisateurs : https://enterprise-k8s.arcgis.com/en/11.5/administer/license-user-type-extensions.htm ; mises à jour 2025 : https://www.esri.com/en-us/c/product/2025-user-type-updates ; nouveautés 11.5 : https://www.esri.com/arcgis-blog/products/arcgis-enterprise/announcements/whats-new-in-arcgis-enterprise-11-5
- [S13] Branch versioning : https://pro.arcgis.com/en/pro-app/3.3/help/data/geodatabases/overview/branch-version-scenarios.htm
- [S14] Notebook Server : https://enterprise.arcgis.com/en/notebook/10.9/use/windows/perform-analysis-using-notebooks.htm ; GeoAnalytics (10.7) : https://enterprise.arcgis.com/en/server/10.7/get-started/windows/what-is-arcgis-geoanalytics-server-.htm (versions anciennes)
- [S15] Experience Builder widgets : https://doc.arcgis.com/en/experience-builder/latest/build-apps/add-widgets.htm ; https://doc.arcgis.com/en/experience-builder/11.4/configure-widgets/widgets-overview.htm
- [S16] Groupes du portail : https://enterprise.arcgis.com/en/portal/latest/use/create-groups.htm
- [S-REST] FME Flow REST API v3 : https://support.safe.com/hc/en-us/articles/25407519073165-Submitting-a-Job-through-the-FME-Flow-REST-API-V3
- [S17] Esri, OGC support in ArcGIS Enterprise (latest/12.1) : https://doc.esri.com/en/arcgis-enterprise/latest/administer/ogc-support-in-arcgis-server.html
- [S18] Esri, Work with OGC Features services (Server 11.5) : https://enterprise.arcgis.com/en/server/11.5/publish-services/linux/ogc-features-service.htm ; OGC dans le portail 11.4 : https://enterprise.arcgis.com/en/portal/11.4/use/ogc.htm ; OGC Server 11.1 : https://enterprise.arcgis.com/en/server/11.1/publish-services/windows/ogc-support-in-arcgis-server.htm
- [S19] Esri REST, Feature Service (enterprise) : https://developers.arcgis.com/rest/services-reference/enterprise/feature-service/
- [S20] Esri REST, Query (Feature Service/Layer) : https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/
- [S21] Esri REST, Vector Tile Service ; style de tuiles vectorielles : https://developers.arcgis.com/rest/services-reference/enterprise/vector-tile-service/ ; https://developers.arcgis.com/documentation/mapping-apis-and-services/data-hosting/tutorials/tools/style-a-vector-tile-layer/
- [S22] Esri REST, Scene Service (I3S) : https://developers.arcgis.com/rest/services-reference/enterprise/scene-service/
- [S23] Esri REST, Add Attachment (miroir de la référence) ; KB pièces jointes volumineuses : https://kgs.uky.edu/arcgis/help/en/rest/services-reference/enterprise/add-attachment.htm ; https://support.esri.com/en/technical-article/000029873
- [S24] Portal for ArcGIS, Create hosted feature layer views (latest/11.4) ; Join Features (Map Viewer, 12.0) : https://enterprise.arcgis.com/en/portal/latest/use/create-hosted-views.htm ; https://enterprise.arcgis.com/en/portal/12.0/use/join-features-mv.htm
- [S25] Portal for ArcGIS, Set hosted feature layer view definition (11.5) : https://enterprise.arcgis.com/en/portal/11.5/use/set-view-definition.htm
- [S26] ArcGIS Pro, sous-types et relationship classes ; préparer des données pour un feature service : https://pro.arcgis.com/en/pro-app/latest/help/data/geodatabases/overview/an-overview-of-subtypes.htm ; https://pro.arcgis.com/en/pro-app/3.4/help/data/relationships/relationship-class-usage-tips.htm ; https://enterprise.arcgis.com/en/server/latest/publish-services/windows/prepare-data-for-feature-services.htm
- [S27] ArcGIS Pro, Evaluate attribute rules (licence Advanced Editing pour couches web) : https://pro.arcgis.com/en/pro-app/latest/help/data/geodatabases/overview/evaluate-attribute-rules.htm
- [S28] Esri blog, Branch versioning ; sync service à service ; [S13] : https://www.esri.com/arcgis-blog/products/arcgis-enterprise/data-management/branch-versioning-editing-administration ; https://www.esri.com/arcgis-blog/products/arcgis-enterprise/data-management/one-way-feature-service-to-feature-service-sync (403 au fetch, résumés de recherche)
- [S29] Esri, Prepare data for offline use (Server 12.0) ; Take maps offline (Portal 11.4) : https://enterprise.arcgis.com/en/server/12.0/publish-services/windows/prepare-data-for-offline-use.htm ; https://enterprise.arcgis.com/en/portal/11.4/use/take-maps-offline.htm
- [S30] Esri, Field Maps requirements ; QuickCapture requirements : https://doc.arcgis.com/en/field-maps/get-started/requirements.htm ; https://doc.arcgis.com/en/quickcapture/faq/requirements.htm
- [S31] Esri, Survey123 avec ArcGIS Enterprise ; nouveautés mars 2026 : https://doc.arcgis.com/en/survey123/get-started/survey123withenterprise.htm ; https://community.esri.com/t5/arcgis-survey123-blog/what-s-new-in-arcgis-survey123-march-2026/ba-p/1694701
- [S32] Esri blog, Deprecation notice for ArcGIS Workforce : https://www.esri.com/arcgis-blog/products/workforce/field-mobility/deprecation-notice-for-arcgis-workforce
- [S33] Esri blog, What's new in ArcGIS Data Reviewer (nov. 2024) : https://www.esri.com/arcgis-blog/products/data-reviewer/data-management/whats-new-in-arcgis-data-reviewer-november-2024
- [S34] Esri, What's new in ArcGIS Enterprise 12.0 (get-started) : https://enterprise.arcgis.com/en/get-started/12.0/linux/what-s-new-in-arcgis-enterprise.htm ; mise à niveau : https://enterprise.arcgis.com/en/get-started/12.0/windows/upgrade-arcgis-enterprise.htm
- [S35] Esri, What's new in ArcGIS Enterprise 12.1 (doc.esri.com) : https://doc.esri.com/en/arcgis-enterprise/12.1/introduction/what-s-new-in-arcgis-enterprise.html
- [S36] Esri, What's new in Portal for ArcGIS 12.0 : https://enterprise.arcgis.com/en/portal/12.0/administer/linux/what-s-new-in-portal-for-arcgis.htm
- [S37] Portal 11.5/12.0 : styles numériques, popups, étiquettes, Map Viewer Classic : https://enterprise.arcgis.com/en/portal/12.0/use/style-numbers-mv.htm ; https://enterprise.arcgis.com/en/portal/12.0/use/configure-pop-ups-mv.htm ; https://enterprise.arcgis.com/en/portal/11.5/use/create-labels.htm
- [S38] Portal 11.3 clustering ; 11.5 binning, symboles animés ; styling reference 11.5 : https://enterprise.arcgis.com/en/portal/11.3/use/configure-clustering-mv.htm ; https://enterprise.arcgis.com/en/portal/11.5/use/styling-reference.htm ; https://arcgis.water.nv.gov/imagery/help/en/portal/11.5/administer/windows/what-s-new-in-portal-for-arcgis.htm (miroir 11.5)
- [S39] Portal, effets et modes de fusion : https://enterprise.arcgis.com/en/portal/latest/use/use-effects.htm ; https://enterprise.arcgis.com/en/portal/11.1/use/use-blend-modes-mv.htm
- [S40] Portal 12.0, Time slider (Map Viewer) : https://enterprise.arcgis.com/en/portal/12.0/use/view-time-maps-mv.htm
- [S41] Portal 12.0, Measure distance or area (Map Viewer) : https://enterprise.arcgis.com/en/portal/12.0/use/measure-mv.htm
- [S42] Portal, Configure ground (Scene Viewer) ; publier un service d'élévation : https://enterprise.arcgis.com/en/portal/latest/use/configure-ground-in-scene.htm ; https://enterprise.arcgis.com/en/server/latest/publish-services/windows/publish-elevation-service.htm
- [S43] ArcGIS Pro 3.5, Work with 3D tiles layers : https://pro.arcgis.com/en/pro-app/3.5/help/mapping/layer-properties/work-with-3d-tiles-layers.htm
- [S44] Server 12.0, Printing in web applications : https://enterprise.arcgis.com/en/server/12.0/publish-services/linux/printing-in-web-applications.htm
- [S45] Arcade, profils : https://developers.arcgis.com/arcade/profiles/
- [S46] Experience Builder : nouveautés 12.0, 12.1 ; FAQ ; versions Developer Edition : https://doc.arcgis.com/en/experience-builder/12.0/get-started/whats-new.htm ; https://doc.arcgis.com/en/experience-builder/12.1/get-started/whats-new.htm ; https://doc.arcgis.com/de/experience-builder/latest/get-started/faq.htm ; https://developers.arcgis.com/experience-builder/guide/release-versions/
- [S47] Dashboards : historique des versions ; Arcade ; FAQ : https://doc.arcgis.com/en/dashboards/12.1/reference/previous-releases.htm ; https://doc.arcgis.com/en/dashboards/11.5/get-started/use-arcade-in-dashboards.htm ; https://doc.arcgis.com/en/dashboards/reference/faqs.htm
- [S48] StoryMaps dans Enterprise : https://doc.esri.com/en/arcgis-storymaps/latest/reference/enterprise-features.html
- [S49] Hub : FAQ Enterprise Sites ; options d'achat ; feeds de catalogue ; tarifs : https://doc.arcgis.com/it/hub/get-started/frequently-asked-questions.htm ; https://www.esri.com/en-us/arcgis/products/arcgis-hub/purchase-options ; https://doc.esri.com/en/arcgis-hub/latest/build/federate-data.html ; https://www.esri.com/en-us/arcgis/products/arcgis-hub/pricing
- [S50] Instant Apps, Maps SDK for JavaScript (matrice de versions) : https://developers.arcgis.com/javascript/latest/version-matrix/ ; miroir Instant Apps 12.0 : gis.ices.dk/gis/help/en/instant-apps/12.0/get-started/whats-new.htm
- [S51] Esri, Insights deprecation : https://doc.arcgis.com/en/insights/latest/get-started/insights-deprecation.htm ; cycle de vie : https://support.esri.com/en-us/products/arcgis-insights/life-cycle
- [S52] GeoAnalytics Server (retrait 11.4, doc 11.3) : https://enterprise.arcgis.com/en/geoanalytics/11.3/install/windows/what-is-arcgis-geoanalytics-server-.htm
- [S53] Image Server 12.0 : https://enterprise.arcgis.com/en/image/12.0/get-started/windows/what-is-arcgis-image-server-.htm
- [S54] Notebook Server 12.0 ; tâches planifiées : https://enterprise.arcgis.com/en/notebook/12.0/administer/linux/what-s-new-in-arcgis-notebook-server.htm ; https://enterprise.arcgis.com/en/notebook/12.0/administer/windows/automate-notebook-execution.htm
- [S55] Web tools / GP services (11.5, latest) : https://enterprise.arcgis.com/en/server/11.5/publish-services/linux/what-is-a-web-tool.htm ; https://doc.esri.com/en/arcgis-enterprise/latest/share/what-is-a-web-tool.html
- [S56] Network analysis services (10.7, page ancienne) ; widget Analysis (miroir tiers) : https://enterprise.arcgis.com/en/server/10.7/publish-services/windows/network-analysis-services.htm ; https://arcportal.sbcounty.gov/arcgis/help/en/portal/latest/use/widget-analysis.htm
- [S57] GeoEvent Server 12.1 ; Velocity for Enterprise FAQ 12.1 : https://geopub.epa.gov/ArcGIS/help/en/geoevent/12.1/get-started/whats-new-in-geoevent-server.htm ; https://doc.arcgis.com/es/velocity/12.1/reference/faq.htm
- [S58] Data Interoperability server extension 12.0/12.1 : https://enterprise.arcgis.com/en/data-interoperability/12.0/help/what-s-new-in-the-arcgis-data-interoperability-server-extension.htm ; https://doc.esri.com/en/arcgis-data-interoperability/latest/help/what-s-new-in-the-arcgis-data-interoperability-server-extension.html
- [S59] Data Pipelines 12.0 (bêta) : https://doc.esri.com/en/arcgis-data-pipelines/12.0/get-started/about-data-pipelines.html ; https://www.esri.com/arcgis-blog/products/arcgis-enterprise/data-management/introducing-arcgis-data-pipelines-beta-in-arcgis-enterprise-12-0
- [S60] Workflow Manager Classic, dépréciation : https://www.esri.com/arcgis-blog/products/workflow-manager/announcements/announcement-deprecation-of-arcgis-workflow-manager-classic
- [S61] Locators et géocodage (Pro 3.6 ; portail 12.0) : https://pro.arcgis.com/en/pro-app/3.6/help/data/geocoding/share-a-locator.htm ; https://imagery.geoplatform.gov/iipp/help/en/12.0/administer/configure-portal-to-geocode-addresses.htm
- [S62] Portal 12.0, user types ; member roles : https://enterprise.arcgis.com/en/portal/12.0/administer/windows/user-types-orgs.htm ; https://enterprise-k8s.arcgis.com/en/12.0/administer/member-roles.htm
- [S63] Portal 11.5, about authentication / configure security (MFA, verrouillage, CORS, proxy, HTTPS) : https://enterprise.arcgis.com/en/portal/11.5/administer/windows/about-configuring-portal-authentication.htm ; https://enterprise.arcgis.com/en/portal/11.5/administer/windows/configure-security.htm ; https://enterprise.arcgis.com/en/portal/11.5/administer/windows/restrict-cross-domain-requests-to-your-portal.htm
- [S64] Portal 11.5, about portal logs ; rapports d'usage 11.3 : https://enterprise.arcgis.com/en/portal/11.5/administer/windows/about-portal-logs.htm ; https://enterprise.arcgis.com/en/portal/11.3/administer/windows/about-usage-reports.htm
- [S65] Esri, API key credentials (Enterprise 11.4+) : https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/api-key-credentials/enterprise/
- [S66] Statut de contenu authoritative/deprecated (10.6.1+) : https://enterprise.arcgis.com/en/portal/10.6/use/what-s-new-in-portal-for-arcgis.htm ; https://www.esri.com/arcgis-blog/products/arcgis-online/uncategorized/improving-content-quality/
- [S67] Esri Trust Center, GDPR ; conformité ; Hardening guide ; gestion des membres 12.0 : https://trust.arcgis.com/en/compliance/gdpr.htm ; https://trust.arcgis.com/en/compliance/compliance.htm ; https://downloads.esri.com/RESOURCES/ENTERPRISEGIS/ArcGIS_Enterprise_Hardening_Guide.PDF ; https://enterprise.arcgis.com/en/portal/12.0/administer/linux/manage-members.htm
- [S68] Esri, Configure a highly available system (latest) : https://doc.esri.com/en/arcgis-enterprise/latest/plan/configure-highly-available-system.html
- [S69] WebGISDR (12.1, 12.0) : https://doc.esri.com/en/arcgis-enterprise/12.1/administer/overview-backup-restore-web-gis.html ; https://enterprise.arcgis.com/en/portal/12.0/administer/linux/restore-web-gis.htm
- [S70] Observabilité d'ArcGIS Enterprise : https://architecture.arcgis.com/en/framework/architecture-pillars/observability/arcgis-enterprise-observability-features.html
- [S71] Enterprise on Kubernetes 12.0 : prérequis ; Data Store 12.0 ; release : https://enterprise-k8s.arcgis.com/en/12.0/deploy/system-requirements.htm ; https://enterprise.arcgis.com/en/system-requirements/12.0/windows/arcgis-data-store-system-requirements.htm ; https://www.esri.com/arcgis-blog/products/arcgis-enterprise/announcements/whats-new-in-arcgis-enterprise-12-0-on-kubernetes
- [S72] Scripting/automatisation ; arcgis-gitops : https://doc.esri.com/en/arcgis-enterprise/latest/plan/scripting-and-automation-for-your-portal.html ; https://github.com/Esri/arcgis-gitops
- [S73] Esri, tarification ArcGIS Enterprise ; extensions serveur ; applications premium ; repères indirects : https://www.esri.com/en-us/arcgis/products/arcgis-enterprise/pricing ; https://doc.esri.com/en/arcgis-enterprise/latest/plan/server-extensions.html ; https://enterprise.arcgis.com/en/portal/12.0/administer/linux/license-premium-apps.htm ; https://aws.amazon.com/marketplace/pp/prodview-du7vn6deoom3q ; https://mcatlas.org/filetransfer/Misc/Christemp/ELA_v1_MC_2023.pdf
- [S74] Esri, cycle de vie ArcGIS Enterprise (403 au fetch : résumés) : https://support.esri.com/en-us/products/arcgis-enterprise/life-cycle ; https://www.esri.com/arcgis-blog/products/arcgis-enterprise/announcements/update-to-arcgis-enterprise-product-lifecycle-2
