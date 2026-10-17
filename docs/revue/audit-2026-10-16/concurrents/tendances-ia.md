# Tendances IA et standards émergents (SIG/BI) — cartographie concurrentielle vs GeoStudio

Date : 2026-10-16. Lecture seule sur le code. Preuves = code réel (chemins relatifs à la racine du dépôt).
Limites de la veille web : plusieurs pages éditeur (esri.com, sparkgeo.com) ont répondu 403 à WebFetch ; les
faits ci-dessous viennent des résumés de WebSearch et de la page GeoParquet. Chaque ligne porte un niveau de
confiance. Les points marqués « à vérifier » n'ont pas été confirmés par une source primaire.

## 1. Tableau des capacités

Maturité : GA / beta / preview / expérimental / standard (OGC adopté) / draft. Parité : oui / partiel / non / dépassé.

| # | Capacité (acteur) | Description | Maturité | Licence / coût | Source | Parité | Preuve GeoStudio |
|---|---|---|---|---|---|---|---|
| 1 | Esri Location Platform MCP | Géocodage, routage, cartes statiques, altitude via MCP | beta (29/06/2026), GA visée fin 2026 | sans surcoût MCP (selon source) | https://www.esri.com/arcgis-blog/products/platform/developers/mcp-support-beta-and-arcgis-static-maps-service-in-arcgis-location-platform-release | dépassé sur géocodage/routage, partiel sur carte statique | `core/app/mcp/tools/geocode.py` (geocode, geocode_batch), `core/app/mcp/tools/routing.py:44` (route), `:51` (isochrone) ; pas d'outil MCP de rendu de carte statique (rendu PDF via worker d'export, hors MCP) |
| 2 | MCP for ArcGIS Enterprise (MCP Services) | Serveur MCP sur Enterprise 11.x/12.x, natif sur K8s 12.2 | annoncé, sortie attendue nov. 2026 (à vérifier) | licence Enterprise | https://blueraster.com/stories/mcp-for-arcgis-enterprise-webinar-recap/ | dépassé (déjà livré) | `core/app/mcp/server.py:15` (FastMCP, OAuth `AuthSettings` l.23, mode sans état `CORE_MCP_STATELESS` l.21), 43 outils déclarés dans `core/app/mcp/tools/` |
| 3 | Serveurs MCP communautaires ArcGIS Portal / ArcGIS Pro | Pilotage d'un portail ou d'un projet Pro par un assistant | communautaire | OSS variée | https://community.esri.com/t5/developers-questions/arcgis-portal-mcp-connect-ai-assistants-to-your/td-p/1712083 | partiel | catalogue/partage via MCP : `core/app/mcp/tools/catalog.py:105`, `sharing.py`; pas de pilotage d'un client desktop (hors périmètre) |
| 4 | Plugins QGIS MCP (nkarasiak 100+ outils, QGIS Agent MCP 0.4.3, WAI QGIS MCP 0.2.1, AI GIS Agent) | Assistant externe pilote QGIS Desktop (couches, Processing, PyQGIS, rendu) | expérimental à stable selon plugin | OSS (GPL côté QGIS) | https://plugins.qgis.org/plugins/qgis_agent_mcp/ , https://plugins.qgis.org/plugins/qgis_mcp_plugin/ | partiel | outils de traitement côté cœur via pipelines : `core/app/mcp/tools/pipelines.py` (create_pipeline, run_pipeline, explain_pipeline) ; pas de PyQGIS (moteur QGIS retiré) mais 59 op DuckDB/Shapely |
| 5 | Felt MCP | Création/édition de projets, cartes, couches, éléments GeoJSON par agent (≈15 outils, source Composio, donc secondaire) | GA (à vérifier côté Felt) | SaaS payant | https://composio.dev/toolkits/felt | partiel | `core/app/mcp/tools/configs.py:227` (create_item), `:173` (save_app_config), `:160` (get_app_config) : création et édition de MapConfig/AppConfig déclaratives ; pas d'outil MCP dédié « ajouter des éléments GeoJSON » |
| 6 | Écosystème MCP géospatial (≈77 serveurs recensés par Sparkgeo) | Foisonnement : PostGIS, STAC, GeoServer, Mapbox, Earth Engine… | foisonnant | variée | https://sparkgeo.com/blog/geospatial-mcp-servers-mapped-and-categorized/ (403, vu via résumé de recherche seulement) | partiel | un seul serveur MCP, intégré au cœur et sous `can()` (`core/app/mcp/auth.py`, `server.py`) ; pas de client MCP vers des serveurs tiers hors op de pipeline `mcpCall` (voir `core/app/pipelines/ops/`) |
| 7 | Power BI MCP (serveur distant, lecture de modèles sémantiques ; serveur local d'écriture) | Requêtes DAX en lecture ; création de visuels limitée | preview (statut contradictoire selon sources) | licence Fabric/Power BI | https://www.knowi.com/blog/best-mcp-servers-for-analytics-bi-in-2026/ | dépassé sur la création de widgets | `core/app/mcp/tools/analytics.py:92` (run_analytics_query), `dataset.py` (create_dataset), `configs.py:286` (create_form_app), `save_app_config` écrit une AppConfig complète |
| 8 | Looker Conversational Analytics / Dashboard Agents / BI Agents | Questions en langage naturel ancrées dans la couche sémantique ; agents qui déclenchent des actions | GA (CA), preview (agents) | Google Cloud | https://cloud.google.com/blog/products/business-intelligence/looker-updates-for-agentic-bi-at-next26 | partiel | questions NL : `core/app/mcp/tools/query_generation.py:209` (generate_sql_query), `:260` (generate_visual_query) ; couche sémantique : métriques nommées de dataset (`resolve_metrics`, `core/app/analytics/`) ; pas de « dashboard agent » embarqué dans un rendu |
| 9 | Tableau Agent / Pulse | Résumés de métriques, agent d'analyse | à vérifier (aucune source 2026 trouvée) | Salesforce | https://omni.co/articles/best-conversational-analytics-tools-2026 | non évalué | — (aucune capacité équivalente de résumé automatique de métrique ; les alertes `core/app/alerts/` couvrent la surveillance seuil, pas la narration) |
| 10 | Copilote de construction de carte/dashboard (génération d'UI par LLM) | L'IA génère ou modifie la config d'une carte/dashboard dans l'éditeur | marché : GA/preview selon éditeur | variée | (synthèse des lignes 1 à 8) | oui | `core/app/copilot/routes.py:380` (POST /copilot/turn), allowlist 9 outils `core/app/copilot/tools_allowlist.py:14`, écritures confirmées par clic (`:COPILOT_WRITE_TOOL_NAMES`), brouillons appliqués côté client `shell/src/builder/copilot/visualQueryClientTools.ts` |
| 11 | Fournisseurs LLM interchangeables | Choix du modèle (OpenAI, Anthropic, local) par l'admin | standard de fait | — | — | partiel | `core/app/copilot/llm_provider.py:125` : un seul type réel (`openai`, API compatible), plus `fake` ; `CORE_LLM_API_URL` permet tout endpoint compatible OpenAI (pas de client Anthropic natif) |
| 12 | OGC API Features Part 4 (écriture) | CRUD transactionnel sur les features | standard (consultation publique 2024, adopté ; statut exact à vérifier sur ogc.org) | ouvert | https://www.ogc.org/requests/ogc-seeks-public-comment-on-ogc-api-features-parts-4-5/ | oui | `core/app/features/routes.py:112` (conf/create-replace-delete) |
| 13 | OGC API Features Part 2 (CRS) + Part 3 / CQL2 (filtres) | Reprojection par requête, filtrage CQL2 | standard | ouvert | https://docs.geoserver.org/main/en/user/services/features/status/ | oui (sous-ensemble) | `core/app/features/routes.py:111`, `:114-120` (CQL2 basic, spatial, temporel) ; sous-ensemble (`app/features/cql2.py`) |
| 14 | OGC API Features Part 5 (schémas) / Part 6 (sélection de propriétés) | Schémas logiques ; `properties=` | draft (Part 5) ; numérotation incohérente selon sources | ouvert | https://docs.geoserver.org/main/en/user/services/features/status/ | non | aucune classe de conformité Part 5/6 dans `CONFORMANCE_CLASSES` (`features/routes.py:106-121`) |
| 15 | OGC API Tiles / Maps / Processes / Records | Tuiles, cartes, exécution de traitements, catalogue | standards (statuts non vérifiés en 2026) | ouvert | non confirmé par la recherche | partiel | tuiles MVT propres au cœur (`core/app/features/tiles.py`, plafond `MAX_TILE_FEATURES = 5000` l.49, sous `rls_scope` l.31) ; aucune route `/processes` ni conformité Tiles (`grep` négatif sur `core/app`) ; WMS/WMTS/WFS via `core/app/ows/` ; catalogue = STAC/DCAT, pas Records |
| 16 | STAC 1.1 et STAC API | Catalogue d'actifs ; 1.1 annoncé (non confirmé) | standard, 1.1 à vérifier | ouvert | https://talks.osgeo.org/foss4g-europe-2024/talk/YQJFVK/ | partiel | API native `core/app/stac/` ; `STAC_VERSION = "1.0.0"` figé `core/app/stac/serializers.py:9`, conformité item-search l.15 ; moissonnage de STAC externe dans `core/app/harvest/` |
| 17 | GeoParquet 2.0 (types Parquet natifs GEOMETRY/GEOGRAPHY) | Géométrie native, CRS sur le type logique | v2.0.0-rc.1 (candidate) ; 1.1 reste la voie production | ouvert | https://geoparquet.org/releases/v2.0.0-rc.1/ | partiel | lecture : `core/app/ingestion/parsers.py:682` (`parse_geoparquet`, détection clé `geo` l.705, qui échouerait sur un 2.0 sans métadonnée `geo`) ; écriture GeoParquet 1.0 : `core/app/cdc/parquet_writer.py:2` ; pas d'écriture 2.0 native |
| 18 | PMTiles (v3, pas de v4 constaté) | Archive de tuiles en un fichier, lecture par range HTTP | stable v3, CLI merge 12/2025 | BSD-3 | https://protomaps.com/blog/pmtiles-v3-layout-compression | non | aucune occurrence de `pmtiles` dans `core/app`, `shell/src`, `deploy/` (recherche insensible à la casse) ; tuiles servies dynamiquement uniquement |
| 19 | COG (Cloud Optimized GeoTIFF) | Raster lisible par plages | standard OGC, stable | ouvert | https://www.ogc.org/ (non confirmé par la recherche) | oui | `core/app/raster/service.py:27` (ouverture COG via `/vsis3/`), proxy TiTiler sous `can()` (`core/app/raster/routes.py`), outil MCP `raster_zonal_stats` |
| 20 | Parquet feature layer cloud (ArcGIS Online beta) | Couche vecteur servie depuis Parquet | beta | Esri | https://www.esri.com/arcgis-blog/products/arcgis-online/announcements/scaling-your-gis-workflows-with-the-new-parquet-feature-layer-beta-in-arcgis-online | dépassé/équivalent | lac GeoParquet + DuckDB `core/app/cdc/`, `core/app/analytics/duckdb_conn.py`, `POST /collections/{id}/aggregate` |
| 21 | Gouvernance et audit des agents | Outils sous permissions de l'utilisateur, journalisés | pratique émergente | — | — | oui | `core/app/mcp/tools/harness.py:2` (audit `mcp.tool_call`), `core/app/copilot/routes.py:422` (audit tour de copilote), loopback sous jeton utilisateur `core/app/copilot/mcp_token.py`, garde d'egress `core/app/copilot/egress.py` |

## 2. Score de parité du domaine

Barème : oui = 1, dépassé = 1, partiel = 0,5, non = 0 ; lignes non évaluées (n° 9) exclues ; lignes de synthèse (n° 10) incluses.

- oui/dépassé : 1, 2, 7, 10, 12, 13, 19, 20, 21 = 9
- partiel : 3, 4, 5, 6, 8, 11, 15, 16, 17 = 9 (4,5 points)
- non : 14, 18 = 2
- exclue : 9

Score : (9 + 4,5) / 20 = **0,675, soit environ 68 %**. Ce score mesure la présence d'une capacité, pas sa qualité face à un éditeur : aucun rejeu face aux produits concurrents n'a été fait, et les lignes 1, 2, 5, 7 reposent sur des sources secondaires.

## 3. Dix écarts majeurs

1. **PMTiles absent** (ligne 18) : ni lecture ni export ; les fonds et couches importées dépendent d'un serveur de tuiles dynamique, ce qui exclut un hébergement statique sur S3 (aucune trace dans `core/app`, `shell/src`).
2. **Pas d'OGC API Processes** (ligne 15) : les 59 op de pipeline ne sont pas exposées comme processus standard ; un client OGC ne peut pas les invoquer.
3. **OGC API Features Part 5/6 absents** (ligne 14) : `features/routes.py:106-121` ne déclare ni schémas ni sélection de propriétés (Part 5 reste draft).
4. **STAC figé en 1.0.0** (ligne 16) : `stac/serializers.py:9` ; la 1.1 n'est pas supportée (statut de sortie à vérifier).
5. **GeoParquet 2.0 non écrit, lecture fragile** (ligne 17) : le détecteur s'appuie sur la clé `geo` (`parsers.py:705`) ; le 2.0 autorise à l'omettre.
6. **Un seul fournisseur LLM natif** (ligne 11) : `llm_provider.py:125` ne connaît que `openai`/`fake` ; pas de client Anthropic ni de local dédié, même si un endpoint compatible fonctionne.
7. **Pas de rendu de carte statique via MCP** (ligne 1) : Esri en fait un outil d'agent ; ici le rendu passe par le worker Playwright, hors MCP.
8. **Pas d'agent « embarqué » dans un dashboard publié** (ligne 8) : Looker Dashboard Agents répond dans le dashboard ; le copilote GeoStudio n'existe que dans le builder (`shell/src/builder/copilot/`).
9. **Pas de narration/résumé automatique de métriques** (ligne 9, non vérifiée côté Tableau) : les alertes déclenchent sur seuil mais ne génèrent pas de texte.
10. **OGC API Tiles/Maps/Records non déclarés** (ligne 15) : les tuiles MVT existent mais ne sont pas annoncées dans une classe de conformité OGC ; le catalogue passe par STAC/DCAT.

## 4. Cinq avantages réels de GeoStudio

1. **Un seul MCP sous `can()`, audité** : tous les outils héritent des permissions de l'utilisateur et laissent une ligne d'audit (`core/app/mcp/tools/harness.py:2`) ; les plugins QGIS et serveurs communautaires ArcGIS n'offrent pas cette garantie de bout en bout.
2. **Écriture sûre par le copilote** : outils d'écriture jamais exécutés sans clic humain, brouillons SQL/requête/CEL appliqués côté client (`copilot/tools_allowlist.py`, `shell/src/builder/copilot/visualQueryClientTools.ts`) ; Power BI MCP ne crée pas de visuels.
3. **Génération de config déclaratives complètes** : `create_item`, `create_form_app`, `save_app_config` (`mcp/tools/configs.py:227`, `:286`, `:173`) produisent des objets schématisés ; l'agent construit une app, pas seulement des éléments GeoJSON comme Felt.
4. **Standards d'écriture OGC réellement implémentés** : Part 4 + CQL2 + CRS (`features/routes.py:106-121`) avec RLS et masquage de colonne, là où GeoServer liste Part 4 comme non implémenté (https://docs.geoserver.org/main/en/user/services/features/status/).
5. **Outils d'analyse pour agents au-delà de l'écriture de cartes** : routage/isochrones (`mcp/tools/routing.py`), zonal stats raster, impact de lineage (`get_item_impact`), profilage (`profile_dataset`), pipelines ; le tout en open-source Apache-2.0, auto-hébergeable.

## 5. Réserves

- Tous les statuts 2026 sont issus de WebSearch (résumés) ; sources primaires Esri/Sparkgeo inaccessibles (403). Les lignes 1-9 et 16 doivent être revérifiées avant d'être citées hors du dépôt.
- Aucun test n'a été exécuté ; la parité s'appuie sur la lecture du code (absence confirmée par `grep` sur `core/app`, `shell/src`, `deploy/`).
- Non vérifié par lecture ligne à ligne : le contenu exact de `core/app/features/cql2.py` et de `core/app/pipelines/ops/` pour `mcpCall`.
