# Cartographie concurrentielle FME (Safe Software) vs GeoStudio — 2026-10-16

Méthode : sources web FME actuelles (releases 2026.1/2026.2/2026.3, liste officielle des formats, catégorie « Data Quality » des transformers), croisées avec le **code** GeoStudio (preuves `fichier:ligne`, lecture seule). CLAUDE.md et les specs ne servent pas de preuve (piège 12). Registre d'opérations mesuré par exécution : `OPERATIONS` = **152 op brutes** (`core/app/pipelines/ops/contracts.py`), dont **32 `experimental`** (derrière `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED`, `operation_contract.py:88`).

Légende parité : oui / partiel / non / dépassé. « exp. » = op expérimentale (jamais rejouée contre le service tiers réel).

## Limites de l'enquête
- Pas de prix officiel 2026 trouvé : FME Form = licence perpétuelle + maintenance annuelle, abonnement entreprise forfaitaire ; Flow Hosted facturé à l'heure/instance (sources 25, 26). Chiffres anecdotiques non retenus.
- Pas de décompte officiel actuel de la FME Hub : la présentation Safe 2022 parle de « plus de 1000 transformers » avec la Hub (source 12). Chiffre ancien.
- Le fetch de la page 2026.2 a échoué ; son contenu vient du résumé de recherche (source 3, 4).

## Sources
1. https://docs.safe.com/fme/html/FME-Form-Documentation/FME-ReadersWriters/Format-List-All.htm (≈375 R/W courants, + obsolètes + packages)
2. https://community.safe.com/product-updates/fme-2026-3-feature-highlights-40901
3. https://community.safe.com/product-updates/fme-2026-2-feature-highlights-40528 (via recherche : boucles natives, JSON destination, Flow serveur MCP)
4. https://community.safe.com/product-updates/fme-2026-1-feature-highlights-40103
5. https://docs.safe.com/fme/html/FME-Form-Documentation/FME-Transformers/Categories/data_quality.htm (35 transformers)
6. https://fme.safe.com/blog/2026/06/how-to-validate-data-at-scale-geometry-schema-attributes-and-ai/
7. https://support.safe.com/hc/en-us/articles/25407588693901-Working-with-BIM-Data-and-FME
8. https://docs.safe.com/fme/html/FME-Form-Documentation/FME-ReadersWriters/revitnative/revitnative.htm
9. https://support.safe.com/hc/en-us/articles/25407679266829-Validate-your-Data-s-Attributes-with-the-AttributeValidator-Transformer
10. https://docs.safe.com/fme/html/fpkg-sdk/ (packages .fpkg)
11. https://support.safe.com/hc/en-us/articles/25407602187661-FME-Hub-FAQ
12. https://engage.safe.com/presentations/introducing-new-package-sdk-create-share-python-based-transformers/
13. https://hub.safe.com/browse
14. https://fme.udot.utah.gov/fmeserver/help/WebUI/Flow-Apps.htm (Flow 2025.1 : Workspace/Gallery/Automation Apps)
25. https://support.safe.com/hc/en-us/articles/29728097481229 (Flow Hosted pricing)
26. https://community.safe.com/integration-8/views-on-recent-fme-price-changes-34403

## Tableau des capacités

Maturité FME : GA sauf mention. Licence FME : propriétaire (Form perpétuelle + maintenance ; Flow sur abonnement/instance).

### A. Formats — vecteur, tabulaire, entrepôts

| # | Capacité FME | Maturité / licence | Src | Parité | Preuve GeoStudio |
|---|---|---|---|---|---|
| A1 | Lecture SHP, GeoJSON, GPKG, CSV, Excel, KML/KMZ, GML, JSON Lines, XML | GA | 1 | oui | `core/app/ingestion/importer.py:96-120` (dispatch par extension) ; parseurs `ingestion/parsers.py:158-786` |
| A2 | Écriture multi-format (≈375 R/W, ~tous bidirectionnels) | GA | 1 | partiel | écriture limitée à csv/xlsx/geojson/gpkg `core/app/analytics/export.py:197-207` ; `writer.topojson` `pipelines/ops/reliquats.py:452` ; `writer.file` derrière flag `contracts.py:580`. Pas d'écriture SHP/KML/GML/DXF |
| A3 | Esri File Geodatabase R/W (nouveau lecteur GDAL 2026.1) | GA, limites connues | 4 | partiel | lecture `.gdb.zip` `importer.py:104` / `parsers.py:512` ; pas d'écriture |
| A4 | CAD : DXF, DGN (MicroStation, ODA en tech preview), DWG/Civil 3D/RealDWG | GA / TP | 1,4 | partiel | DXF/DGN lecture seule `importer.py:108-110`, `parsers.py:521-531` ; **DWG absent** (aucune occurrence dans `core/app`) |
| A5 | GeoParquet, Parquet R/W | GA | 1 | oui | lecture `parsers.py:682,730` ; GeoParquet plat du lac (CDC) |
| A6 | Delta Lake (GA 2026.1), Iceberg (reader 2026.3), Databricks, Fabric Warehouse | GA / TP | 2,4 | partiel | `reader.connector.databricks` exp. (liste `OPERATIONS`) ; Delta/Iceberg/Fabric : aucune occurrence → non |
| A7 | Snowflake, BigQuery, SQL Server, Oracle, PostGIS, MongoDB, Google Sheets, Airtable | GA | 1 | partiel | postgres/rest GA `contracts.py:~255` ; snowflake/bigquery/mssql/oracle/mongodb/googlesheets **exp.** (registre) ; `writer.connector.postgres.update/delete` GA |
| A8 | PMTiles (R/W), MBTiles, FlatGeobuf, TPKX | GA | 1,4 | non | grep `pmtiles\|mbtiles\|flatgeobuf` dans `core/app` + `shell/src` : 0 |
| A9 | Lecteurs OGC WFS/WMS/WMTS/WCS/OGC API Features | GA | 1 | partiel | `reader.wfs` `contracts.py:618` exp. ; `reader.wms/wcs` exp. ; GeoStudio **sert** WMS/WMTS/OGC Features (`core/app/ows/`) |
| A10 | OSM, NetCDF, GRIB, ERDAS, JPEG2000, Sentinel-2, Landsat-8, CityJSON | GA | 1 | oui | `pipelines/ops/readers2.py:471-495,716,816,941` (GA, hors exp.) |
| A11 | CityGML / CityGML 3, IMDF | GA | 1 | non | seul CityJSON `readers2.py:941` ; pas de CityGML |
| A12 | Lecteurs d'objet / cloud (S3, Azure, GCS, FTP, SharePoint) | GA | 1 | partiel | `reader.cloudfile`, `reader.ftp` exp. `cloudfiles.py:582` |
| A13 | Rejected port sur FeatureWriter (2026.3) | GA | 2 | dépassé | `writer.collection` upsert/update/delete + quarantaine `<cible>__rejected` `pipelines/collection_writer.py:13,60-61` |

### B. Raster

| # | Capacité | Src | Parité | Preuve |
|---|---|---|---|---|
| B1 | GeoTIFF/COG R/W + autres rasters | 1 | partiel | ingestion **GeoTIFF/COG uniquement**, magic TIFF vérifié `raster/ingest.py:37-41`, conversion COG `terrain3d/conversion.py` |
| B2 | Transformers raster (calculatrice, convolution, mosaïque, pyramides, bandes, géoréférencement, GCP) | 1 | oui | `pipelines/ops/raster2.py:477` (`rasterCalc`) et le registre (`rasterConvolve…rasterGcpExtract`) |
| B3 | Statistiques zonales / vecteur sur raster | 1 | oui | `transform.zonalStats`, `transform.vectorOnRaster` (registre) ; `raster/zonal.py` |
| B4 | Diffusion de tuiles raster | — | dépassé | proxy TiTiler sous `can()` `core/app/raster/routes.py` (FME : pas de serveur de tuiles natif) |
| B5 | Orthomosaïque drone (WebODM, Hub) | 2 | non | aucune occurrence |

### C. 3D / nuages de points / BIM

| # | Capacité | Src | Parité | Preuve |
|---|---|---|---|---|
| C1 | Cesium 3D Tiles writer 1.1 (glTF, attributs) | 2 | partiel | GeoStudio **héberge et affiche** un tileset déjà produit (zip avec `tileset.json` validé) `tileset3d/storage.py:102-112` ; aucun producteur/convertisseur |
| C2 | glTF, OBJ, FBX, COLLADA, STL, PLY, USD, 3DS | 1,2 | non | seule occurrence : un type MIME `.gltf` `tileset3d/routes.py:45` |
| C3 | Nuages de points LAS/LAZ/COPC/E57/PCD | 1,4 | non | aucune occurrence (`.pnts` 3D Tiles servi tel quel `routes.py:48`) |
| C4 | BIM : IFC (IFC_API), Revit natif, BCF, Navisworks | 1,7,8 | non | aucune occurrence `ifc`/`rvt` dans `core/app`, `shell/src` |
| C5 | MNT/terrain, drapage, triangulation | 1 | oui | `terrain3d/` (COG DEM → raster-dem), `transform.surfaceDrape`, `transform.triangulate` `contracts.py:549` |

### D. Qualité de données (35 transformers de la catégorie FME, src 5)

| # | Capacité FME | Parité | Preuve |
|---|---|---|---|
| D1 | AttributeValidator (type, unicité, null, plage, regex ; règle fautive tracée) | oui | `transform.validateAttributes` `contracts.py:486` ; plus règles CEL `constraint`/`batch` par collection `core/app/quality/runner.py:20-45`, route `quality/routes.py:49` |
| D2 | Tester / TestFilter / AttributeRangeFilter / Sampler / DuplicateFilter / Matcher | oui | `contracts.py:639,646` ; `attrs.py:145,204,295` |
| D3 | GeometryFilter / PlanarityFilter / SpatialRelator / FeatureTypeFilter | oui | `attrs.py:219,240,384,760` |
| D4 | **GeometryValidator** (règles + réparation) | non | aucun op de validation/réparation de géométrie dans le registre ; `ST_MakeValid` n'apparaît que dans `core/app/sharing/geo_limits.py:197` |
| D5 | AreaGapAndOverlapCleaner, SpikeRemover, Snapper | oui | `geom2.py:290,368` ; `snapToLayer` `contracts.py:532` |
| D6 | ChangeDetector | oui | `contracts.py:502` |
| D7 | JSONValidator / XMLValidator (schéma externe) | non | aucun op |
| D8 | HTMLReportGenerator (rapport + carte des erreurs) | partiel | rapport persistant par collection (`quality/routes.py:91-107`), pas de carte des erreurs ni PDF dédié |
| D9 | Validation en continu à l'arrivée de données (Flow) | partiel | déclencheurs webhook/S3/cron + `quality-checks` à la demande ; pas de chaîne schéma→attributs→mail packagée |

### E. Hub, extensibilité, plateforme (Form/Flow)

| # | Capacité | Src | Parité | Preuve |
|---|---|---|---|---|
| E1 | FME Hub : packages `.fpkg` (transformers, formats, connexions), >1000 transformers avec la Hub | 10-13 | non | `Extension` = module UI de widgets (`core/app/extensions/models.py:29` `module_url`) ; aucun packaging d'op de pipeline, aucune place de marché |
| E2 | Custom transformers réutilisables (sous-graphes) | 12 | non | grep `subgraph\|custom transformer\|macro` dans `core/app/pipelines` : 0 |
| E3 | PythonCaller / SDK Python | 12 | non | aucun op d'exécution de code utilisateur (volontaire : sandbox) |
| E4 | Boucles natives sur le canevas (2026.2) | 3 | non | aucune notion de boucle dans le registre d'op |
| E5 | Workspace Apps / Gallery Apps (Flow) | 14 | dépassé | builder d'apps config-driven + gabarits `core/app/configs/builder_templates.py:1-22` |
| E6 | Automations, planification, déclencheurs | 14 | oui | cron `pipelines/routes.py:11,99` ; `PipelineWebhookToken` `pipelines/models.py:62` ; webhooks sortants `webhooks/routes.py:127` |
| E7 | MCPCaller (2026.1) | 4 | oui | `transform.mcpCall` `pipelines/ops/messaging.py:1206`, exp. |
| E8 | Flow comme serveur MCP, jobs en MCP (2026.2/3) | 2,3 | dépassé | `/mcp` natif, permissions de l'utilisateur, audité `core/app/mcp/server.py:11` |
| E9 | AI Assist (plugin) | 2 | oui | copilote `core/app/copilot/` (outils allowlistés) |
| E10 | Géocodage, routage | 2 | partiel | `transform.geocode`, `isochrone`, `route` exp. |
| E11 | Messagerie (SNS, Kinesis, RabbitMQ, Service Bus, Slack, email) | 1 | partiel | `writer.*` / `reader.kinesis` exp. (registre) |
| E12 | Data caching / débogage canevas | 4 | partiel | aperçu tableau dans le builder (non relu ligne à ligne) |

## Score de parité du domaine

Pondération : oui = dépassé = 1, partiel = 0,5, non = 0. 44 lignes : **oui 14, dépassé 4 (A13, B4, E5, E8), partiel 14, non 12**.

Score = (14 + 4 + 14×0,5) / 44 = 25 / 44 = **≈ 57 %**

Si l'on retire les 32 op expérimentales (jamais rejouées sur service réel), les lignes A7, A9, A12, E10, E11 retombent vers « non » en production : score plancher ≈ **52 %**. La couverture est forte sur le moteur de transformation (vecteur/attributs/raster) et faible sur formats d'échange 3D/CAD/BIM/nuages de points et sur l'écosystème de distribution.

## 10 écarts majeurs (par priorité estimée)

1. **BIM/IFC/Revit absents** (C4) : aucun lecteur ; FME a IFC_API, Revit natif, BCF. Fermé seulement si un convertisseur IFC→glTF/3D Tiles est ajouté.
2. **Nuages de points LAS/LAZ/COPC/E57** (C3) : rien, alors que FME les R/W et 2026.1 améliore LAS/LAZ.
3. **Pas de producteur 3D** (C1, C2) : GeoStudio n'affiche que des tilesets pré-faits ; glTF/OBJ/FBX/USD/PLY/STL non lisibles.
4. **DWG** (A4) : lecture DXF/DGN seulement ; DWG est le format CAD dominant.
5. **Pas de Hub / packaging d'opérations / custom transformers** (E1, E2) : verrou d'écosystème majeur de FME ; l'extension GeoStudio ne couvre que les widgets UI.
6. **Écriture de formats limitée** (A2) : pas de SHP, KML, GML, DXF, FileGDB, PMTiles en sortie, alors que l'interopérabilité bidirectionnelle est le cœur de FME.
7. **Formats lakehouse/tuiles modernes** (A6, A8) : Iceberg, Delta, PMTiles, MBTiles, FlatGeobuf absents.
8. **GeometryValidator/réparation et validateurs JSON/XML** (D4, D7) : le trou le plus visible de la catégorie qualité.
9. **Connecteurs entrepôt/BDD/messagerie non rejoués** (A7, A9, E11) : 32 op `experimental` ; maturité réelle non prouvée face aux connecteurs FME éprouvés.
10. **Boucles et PythonCaller** (E3, E4) : pas de flux itératif natif ni de code utilisateur dans un pipeline.

## 5 avantages réels de GeoStudio

1. **Ouvert et gratuit** (Apache-2.0, moteurs MIT/BSD : DuckDB, GDAL/pyogrio) face à une licence FME perpétuelle + maintenance annuelle ou abonnement par instance (src 25-26). Contrainte de licence vérifiable dans `OperationContract.engine_license`.
2. **Autorisation et sécurité à la lecture/écriture intégrées au pipeline** : RLS, masquage de colonnes, `can()` sur les readers/runs (ex. `quality/runner.py:3-4` : masquage GAP-22 jamais contourné), là où FME délègue à la couche Flow.
3. **Rejets natifs et upsert transactionnel** vers collections avec quarantaine `__rejected` (`collection_writer.py:13`), alors que FME ne propose le port Rejected qu'en 2026.3 pour trois formats seulement (src 2).
4. **Chaîne complète donnée → carte → app dans un seul produit** : builder d'apps config-driven, tuiles servies sous `can()`, OGC Features/WMS/WMTS/STAC/DCAT, TiTiler (B4, E5) ; FME s'arrête à l'ETL et à des Flow Apps de formulaires.
5. **IA opérable de façon native et gouvernée** : serveur MCP du cœur, mêmes permissions que l'utilisateur, audité (`mcp/server.py:11`), copilote à outils allowlistés ; FME a rattrapé en 2026.2-2026.3 (MCP Flow en technical preview, AI Assist via MCP).
