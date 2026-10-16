# Cartographie concurrentielle : QGIS Server, GeoNode, GeoServer, MapStore, Kepler.gl, Felt, Carto, Mapbox, Foursquare

Date : 2026-10-16. Lecture seule. Preuves GeoStudio = code relu (`core/app`, `shell/src`), pas CLAUDE.md.
Les routes `/ows/*` ne sont montées que si `CORE_OWS_ENABLED` / `CORE_OWS_WMS_ENABLED` valent `true`
(`core/app/ows/routes.py:46-49`, `core/app/ows/wms_routes.py:52-53`, `core/app/main.py:463-466`).

## Limites de la recherche

WebSearch/WebFetch ont donné des résultats minces sur plusieurs points. Marqué **(non confirmé)** quand je n'ai pas pu ouvrir la source primaire.
- Pas de notes de version QGIS Server 4.x trouvées : jeu de protocoles lu sur le manuel serveur 4.2 (résumé de recherche).
- GeoNode 5.0 (16/12/2025) : liste officielle complète non ouverte.
- Felt : la page `felt.com/ai-information` a répondu 404 en fetch ; prix = seulement le billet du 13/10/2026 et Capterra (périmé probable).
- Mapbox : tarifs issus de pages tierces ; seule la page officielle fait foi.
- Foursquare Studio : pas de changelog 2026 trouvé ; capacités = doc `keplergl-vs-studio`.

## Tableau des capacités

Légende parité : oui / partiel / non / dépassé. Maturité : GA = produit stable, Comm. = module communautaire, Beta.

| # | Capacité (concurrent) | Description | Maturité | Licence / coût | Source | Parité | Preuve GeoStudio |
|---|---|---|---|---|---|---|---|
| 1 | WMS 1.3.0 (QGIS Server, GeoServer, GeoNode) | GetCapabilities/GetMap/GetFeatureInfo | GA | GPL-2 / GPL-2 / GPL | [QGIS 4.2 server](https://docs.qgis.org/4.2/de/docs/server_manual/services.html) | partiel | `core/app/ows/wms.py:23` (GetMap `image/png` seul), `wms.py:66`, `wms_routes.py:244-258` ; pas de GetLegendGraphic (grep négatif) |
| 2 | WMTS 1.0.0 (QGIS, GeoServer) | Tuiles raster standard | GA | idem | idem | oui | `core/app/ows/wms_routes.py:405-465` |
| 3 | WFS (lecture) (QGIS, GeoServer) | GetFeature/DescribeFeatureType, GML 3.2 + JSON | GA | idem | idem | oui | `core/app/ows/routes.py:130`, `ows/wfs.py:21-23,100-103` |
| 4 | WFS-T transactions (GeoServer, QGIS 1.x/1.1) | Écriture via WFS | GA | idem | idem | partiel | Pas de Transaction WFS (`ows/routes.py:159` n'accepte que 3 opérations) ; écriture par OGC API Features Part 4 `features/routes.py:904,970,1145` |
| 5 | WCS 1.0/1.1 (QGIS, GeoServer) | Servir des couvertures raster | GA | idem | idem | non | Aucune route WCS (grep `WCS` : uniquement connecteurs de moissonnage) |
| 6 | OGC API Features 1/2/3/4 (QGIS Server, GeoServer) | REST, CQL2, CRS, écriture | GA | idem | idem | dépassé | `features/routes.py:105-118` (Part 1, 2, 3, 4, CQL2-text) ; RLS + masquage colonne dans les mêmes routes |
| 7 | OGC API Tiles / MVT (GeoServer, Mapbox) | Tuiles vectorielles | GA | – | [GeoServer 2.28](https://geoserver.org/announcements/vulnerability/2025/10/14/geoserver-2-28-0-released.html) | oui | `core/app/features/tiles.py:366` (`ST_AsMVT` sous RLS), `ows/routes.py:263-300` |
| 8 | OGC API Maps/Coverages/Processes, WPS (GeoServer) | Traitements standardisés | GA | – | idem (WPS Excel, ZonalStatistics) | partiel | Pas de WPS/Processes ; équivalents propriétaires : `pipelines/analysis_routes.py:40`, `raster/routes.py:258` (zonal-stats) |
| 9 | Style SLD / SE (GeoServer, QGIS) | Import/export de styles OGC | GA | – | idem (legend + Recode/Interpolate) | partiel | Export seul : `core/app/styles/sld.py:2,85` ; pas d'import SLD |
| 10 | Import/export style MapLibre (Mapbox Studio, Felt) | Interop style GL | GA | – | [Mapbox](https://docs.mapbox.com/help/getting-started/maps/) | oui | `shell/src/map/mapLibreStyle.ts:35,104`, `map/MapStyleTransfer.tsx` |
| 11 | Éditeur de style visuel (GeoServer CSS/YSLD, Mapbox Studio, Felt) | Symbologie catégorielle/continue/classée | GA | – | idem | oui | `shell/src/map/MapSymbologyEditor.tsx`, `AdvancedSymbologyEditor.tsx` |
| 12 | Catalogue CSW serveur (GeoNode/pycsw) | Exposition CSW | GA | GPL | [GeoNode 5](https://geosolutionsgroup.com/blog/geonode-5-is-out/) | partiel | Pas de serveur CSW ; STAC `stac/routes.py:112-486` + DCAT-AP `dcat/routes.py:122-161` ; CSW seulement en lecture `harvest/connectors/csw.py:107-132` |
| 13 | Éditeur de métadonnées ISO/INSPIRE (GeoNode 5, JSON Schema) | Schémas de validation configurables | GA | GPL | idem | partiel | Métadonnées DCAT/STAC (10 champs) en `collections` ; aucun ISO 19115 sortant (grep négatif `MD_Metadata` hors moissonnage) |
| 14 | Moissonnage de catalogues (GeoNode 5, MapStore) | Harvesting distant | GA | – | idem | dépassé | `core/app/harvest/connectors/` (STAC, ArcGIS, OWS, CSW, CKAN, WFS) |
| 15 | Groupes/permissions fins, OIDC (GeoNode, GeoServer sec-oidc) | AuthZ + SSO | GA | – | GeoServer 2.28 | dépassé | `auth/dependency.py:12` (sync claims→groupes), `shell/src/pages/GroupClaimMappingsSection.tsx`, RLS `features/rls.py` ; LDAP/SAML natifs : non (Keycloak seul, `deploy/keycloak/geostudio-realm.json`) |
| 16 | Dashboards + onglets (MapStore 2026.01) | Widgets groupés par onglets | GA | GPL-3 | [MapStore 2026.01](https://geosolutionsgroup.com/blog/mapstore-2026-01-release/) | oui | `shell/src/builder/widgets/tabs.tsx:18`, `builder/PageManager.tsx` |
| 17 | Constructeur de filtres dynamiques (MapStore) | Filtres runtime croisés | GA | idem | idem | dépassé | `widgets/filter.tsx:8`, `selectFilter.tsx`, `sliderFilter.tsx`, `dateRangeFilter.tsx`, `CrossFilterLinkEditor.tsx` |
| 18 | Geostories / storytelling (MapStore, Felt) | Récit narratif | GA | – | MapStore (non confirmé 2026.01) | oui | mode `story` : `shell/src/builder/pages.ts`, `PageManager.tsx` |
| 19 | Table attributaire éditable avec restrictions (MapStore + GeoServer GSIP-234) | Édition contrainte | GA | – | MapStore 2026.01 / GeoServer 2.28 | oui | `features/validation.py`, `widgets/form.tsx`, `features/rules.py` |
| 20 | Point de vue sauvegardé / CameraPosition (MapStore) | Viewpoints | GA | – | MapStore 2026.01 | oui | `shell/src/map/CameraControls.tsx`, bookmarks `mcp/tools/bookmark.py` |
| 21 | 3D Tiles + terrain + COG en 3D (MapStore/Cesium, Mapbox, Foursquare globe) | Rendu 3D | GA | – | idem | oui | `shell/src/map/mapDeckTerrain.ts:6,47`, `core/app/tileset3d/routes.py:91`, `terrain3d/routes.py:57` |
| 22 | Google Photorealistic 3D Tiles (CARTO Q2 2026) | Basemap 3D photoréaliste | GA | clé Google payante | [CARTO Q2 2026](https://carto.com/blog/whats-new-in-carto-q2-2026/) | non | Aucune référence (grep négatif `photorealistic`) ; 3D Tiles tiers possibles via `tiles3d` |
| 23 | Raster COG (Foursquare Studio, Felt, GeoServer) | Hébergement/tuilage COG | GA | – | [Studio vs kepler](https://docs.foursquare.com/studio/docs/keplergl-vs-studio) | oui | `core/app/raster/routes.py:101-258` (proxy TiTiler sous `can()`), derrière `CORE_RASTER_ENABLED` |
| 24 | Clustering / hexbin / binning (kepler, Studio, Carto spatial index) | Agrégation spatiale | GA | MIT (kepler) | idem | partiel | `shell/src/map/mapLayerBuild.ts:81`, `mapDeckTerrain.ts:23` (HexagonLayer) ; pas d'index H3/Quadbin natif |
| 25 | Animation temporelle (kepler, Studio, MapStore) | Lecteur de temps | GA | – | idem | partiel | `shell/src/map/MapTimePlayer.tsx`, `widgets/timePlayer.tsx` ; un seul timeline (Studio : plusieurs liés) non vérifié |
| 26 | Comparaison swipe (MapStore, Felt) | Curseur avant/après | GA | – | – | oui | `shell/src/builder/widgets/swipe.tsx:29` |
| 27 | Export vidéo/GIF (Studio 1440p, kepler 3) | Rendu animation | GA | Studio Pro payant | Studio vs kepler | non | grep négatif (`gif|webm|MediaRecorder`) |
| 28 | Mise en page d'impression / atlas (QGIS, MapStore) | PDF paginé | GA | – | QGIS 4.2 manual | oui | `shell/src/builder/print/PrintLayoutPanel.tsx:20`, `AtlasPages.tsx`, worker Playwright |
| 29 | Analyses spatiales no-code (Carto Workflows, Studio cluster/outlier/suitability) | Chaîne d'analyse + hotspot Gi* | GA | Carto payant | CARTO Q2 2026 | partiel | `core/app/pipelines/analysis.py:165-251`, `pipelines/ops/` (23 modules, ~150 op) ; Getis-Ord/suitability : non vérifié |
| 30 | Versionnage de workflows (Carto Q2 2026) | Historique + restauration | GA | – | CARTO Q2 2026 | oui | `shell/src/builder/ConfigHistoryPanel.tsx:24`, historique de features `FeatureHistoryPanel.tsx:17` |
| 31 | Connecteurs entrepôt (Carto, Studio) | BigQuery/Snowflake/Databricks/Postgres | GA | – | idem | oui | `core/app/pipelines/ops/contracts.py:261-292,738-742` (flag expérimental `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED`, jamais rejoué) |
| 32 | Requête live sur entrepôt sans copie (Carto) | Push-down SQL | GA | – | CARTO | non | Moissonnage = copie/référence ; DuckDB local `analytics`, pas de push-down vers l'entrepôt |
| 33 | Serveur MCP / agents IA (Carto for Agents) | MCP hébergé + traçabilité | GA | inclus | CARTO Q2 2026 | oui | `core/app/mcp/server.py:5`, 43 outils (`mcp/tools/*.py`), audit `mcp.tool_call` ; `core/app/copilot/` |
| 34 | Quotas/contrôles IA par groupe (Carto) | Gouvernance IA | GA | – | CARTO Q2 2026 | partiel | Allowlist copilote `copilot/tools_allowlist.py`, `quotas/` ; pas de quota par groupe/modèle |
| 35 | Clés/jetons d'API à périmètre (Carto, Mapbox) | Tokens à droits | GA | – | – | oui | `core/app/apikeys/routes.py:43` |
| 36 | Embed + SDK (Felt Platform 1 000 $/mois, Mapbox GL JS) | Intégration tierce | GA | Felt payant | [Felt blog](https://felt.com/blog/build-maps-into-your-product) | oui | `core/app/items/routes.py:285-289` (`/embed/:token`), `shell/src/pages/EmbedPage.tsx`, SDK Web Components `builder/wc/` |
| 37 | Hébergement de tilesets vectoriels (Mapbox Tiling Service) | Traitement + hébergement | GA | payant au job | [MTS pricing](https://docs.mapbox.com/mapbox-tiling-service/ja/guides/pricing) | partiel | MVT dynamique `features/tiles.py:366` (plafond 5000 lignes) ; pas de tuilage pré-généré ni PMTiles (grep négatif) |
| 38 | Geocoding + routage + isochrones (Mapbox) | APIs géo | GA | payant | Mapbox | partiel | `core/app/geocoding/routes.py:28-160`, `routing/routes.py:107-152` ; fournisseurs externes, pas de moteur propre |
| 39 | Collecte terrain mobile (Felt app, QField) | Saisie terrain | GA | – | Felt (annuaire) | partiel | `core/app/xlsform/routes.py:39`, `public_submit/routes.py:61` ; pas d'app mobile offline |
| 40 | Commentaires/annotations collaboratifs et co-édition temps réel (Felt) | Collaboration | GA | Felt payant | Felt | non | Aucun modèle de commentaire ni WebSocket (grep négatif) ; croquis local `shell/src/map/measureSketch.ts` |
| 41 | Plugin QGIS / projet QGIS publié (Felt, QGIS Server) | Publier un .qgs | GA | – | Felt, QGIS | non | Aucune route ; QGIS retiré (GPL) |
| 42 | Cache de tuiles (GeoWebCache) (GeoServer) | Seeding/invalidations | GA | GPL | GeoServer 2.28.3 | non | Aucun cache de tuiles côté cœur (grep négatif `seed`) |
| 43 | Lignage/impact + webhooks (Carto, GeoNode async) | Gouvernance | GA | – | GeoNode 5 | dépassé | `core/app/lineage/routes.py:68`, `webhooks/delivery.py` |
| 44 | Datastore PMTiles / SingleStore (GeoServer 2.28 comm.) | Formats additionnels | Comm. | GPL | GeoServer 2.28 | non | Aucune lecture PMTiles |

Décompte (44 lignes) : dépassé 5 (6, 14, 15, 17, 43), oui 18, partiel 13, non 8.

## Score de parité du domaine

Barème : dépassé = 1,0 ; oui = 1,0 ; partiel = 0,5 ; non = 0.
(5 + 18 + 13 x 0,5) / 44 = **29,5 / 44 = 67 %**.
Lecture : forte parité sur l'analytique, le builder et la fédération ; faiblesse sur les standards OGC « serveur » complets (WCS, WFS-T, WPS, CSW, légende SLD) et sur la collaboration.

## 10 écarts majeurs

1. **Pas de collaboration** (commentaires, co-édition) : cœur de Felt, absent (ligne 40).
2. **WCS absent** (QGIS Server, GeoServer) (ligne 5) ; seul un proxy COG propriétaire existe (`raster/routes.py:215`).
3. **WFS en lecture seule** ; pas de Transaction (ligne 4, `ows/routes.py:159`) : les clients desktop (QGIS) doivent passer par OGC API Features.
4. **Pas de CSW serveur ni d'ISO 19115 sortant** (lignes 12-13) : bloquant pour l'INSPIRE institutionnel que GeoNode 5 adresse.
5. **WMS minimal** : GetMap `image/png` seul, pas de GetLegendGraphic ni autres formats (`ows/wms.py:23`).
6. **Pas de WPS / OGC API Processes** (ligne 8) : interopérabilité de traitements impossible.
7. **Pas de push-down vers l'entrepôt** (Carto) (ligne 32) ; connecteurs entrepôt en copie et expérimentaux (`contracts.py:738-742`).
8. **Pas d'export vidéo/GIF** ni plusieurs timelines liés (lignes 25, 27).
9. **Pas de tuilage pré-généré ni PMTiles/cache** (lignes 37, 42, 44) : tuiles dynamiques plafonnées à 5000 lignes, risque de passage à l'échelle.
10. **Pas de plugin QGIS ni d'import SLD** (lignes 9, 41) : le pont avec l'écosystème desktop est unidirectionnel.

Mention secondaire : pas d'index H3/Quadbin, pas de 3D photoréaliste Google, LDAP/SAML uniquement via Keycloak.

## 5 avantages réels de GeoStudio

1. **Un seul garde d'autorisation sur toutes les surfaces** : WFS, MVT, STAC, WMS et exports passent par `rls_scope` + masquage colonne (`ows/routes.py:1-8`, `features/rls.py`) ; GeoServer/QGIS Server n'ont pas de RLS PostGIS par tenant ni de masquage par colonne équivalent.
2. **Builder no-code déclaratif + runtime unique** (apps, dashboards, sites) avec CEL, variables, cross-filter : `shell/src/builder/AppRenderer.tsx`, `widgets/` (~40 widgets). MapStore n'a pas de langage d'expression ni de config schématisée pour l'IA.
3. **MCP natif de 43 outils + copilote sous `can()`** (`core/app/mcp/tools/`, `copilot/tools_allowlist.py`), auto-hébergé ; Carto l'offre en SaaS payant, GeoServer/GeoNode/QGIS non.
4. **ETL géospatial intégré** (~150 op DuckDB, lignage, webhooks, rejeu, CDC→lac) : `core/app/pipelines/ops/`, `lineage/routes.py:68` ; aucun des OSS cités ne l'embarque (Carto Workflows est payant et lié à l'entrepôt).
5. **Fédération et licence** : 6 connecteurs de moissonnage + STAC/DCAT natifs (`harvest/connectors/`, `stac/routes.py`, `dcat/routes.py`) en Apache-2.0, sans la contrainte GPL de GeoServer/QGIS/GeoNode/MapStore ni coût par chargement (Mapbox) ou par siège (Felt, Carto, Studio Pro).

## Sources

- GeoServer : https://geoserver.org/announcements/vulnerability/2025/10/14/geoserver-2-28-0-released.html ; https://geoserver.org/announcements/vulnerability/2026/08/14/geoserver-2-28-5-released.html
- QGIS Server 4.2 : https://docs.qgis.org/4.2/de/docs/server_manual/services.html
- GeoNode 5 : https://geosolutionsgroup.com/blog/geonode-5-is-out/ ; https://wiki.osgeo.org/wiki/GeoNode_Report_2025
- MapStore : https://geosolutionsgroup.com/blog/mapstore-2026-01-release/
- CARTO : https://carto.com/blog/whats-new-in-carto-q2-2026/ ; https://carto.com/blog/whats-new-in-carto-q1-2026/
- Foursquare / kepler.gl : https://docs.foursquare.com/studio/docs/keplergl-vs-studio ; https://foursquare.com/resources/blog/capabilities/introducing-kepler-gl-3-0/
- Felt : https://felt.com/blog/build-maps-into-your-product ; https://www.capterra.com/p/10035247/Felt/
- Mapbox : https://docs.mapbox.com/help/getting-started/maps/ ; https://docs.mapbox.com/mapbox-tiling-service/ja/guides/pricing ; https://www.woosmap.com/blog/mapbox-pricing
