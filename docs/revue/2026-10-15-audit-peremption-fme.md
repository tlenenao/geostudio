# Audit de péremption de la matrice FME — 2026-10-15

> Tâche 0.1 du plan `docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md`.
> Périmètre : les 120 lignes `planned_*`/`unknown` de `docs/revue/matrice-couverture-fme.jsonl`,
> confrontées au registre réel (`core/app/pipelines/ops/contracts.py::OPERATIONS`, 71 ops
> brutes / 67 exposées en CI) et aux capacités hors pipeline (import `core/app/ingestion`,
> hébergement raster `core/app/raster`, export sec `core/app/dataexport`) — le code fait foi,
> pas les documents (piège n°12).

## Méthode

- Une ligne passe `implemented` seulement si un équivalent **1:1 existe dans le code** :
  une op unique, ou, pour la catégorie *Readers/Writers*, l'import/export de fichiers (règle
  déjà appliquée par ARC-23 à Shapefile, DXF, FileGDB…). Les **compositions de plusieurs
  ops** restent `planned_*`, comme la matrice l'a déjà tranché (AttributeManager,
  DatabaseJoiner, AggregateFilter).
- Les capacités livrées mais seulement voisines sont listées comme **périmètre rétréci** :
  la ligne reste `planned_*`, la voie a moins à construire.
- Décisions de Tanguy du 2026-10-15 appliquées : D2 (TCPIP/JMS) et D4 (PDAL) passent en
  `out_of_scope` motivé. Lignes OTB (voie H) et voie I non touchées (D1).

## Reclassées en `implemented` (4)

| Voie | Ligne FME | Équivalent réel | Preuve dans le code |
|---|---|---|---|
| A | ParameterFetcher | `transform.derive` avec `expr: "{{param.nom}}"` | `core/app/configs/pipeline_params.py` (paramètres de run ARC-K2/F3 ; `expr` ∈ `_EXPR_KEYS`, substitution en littéral SQL typé) |
| B | Microsoft Excel | `ingestion:xlsx` (lecture) + export sec XLSX (écriture) | `core/app/ingestion/importer.py` (`.xlsx`), `parsers.py::parse_xlsx_sheet` ; `core/app/dataexport/jobs.py` (xlsx) |
| B | SQLCreator | `reader.connector.postgres` (+ jumeaux mssql/oracle/snowflake/bigquery/databricks) | `ops/schemas.py::ReaderConnectorPostgresParams.query` (SELECT seul, secret de connexion) |
| F2 | GeoTIFF | hébergement raster (GeoTIFF/BigTIFF → COG) + `reader.raster` | `core/app/raster/ingest.py::require_tiff`/`to_cog`, `ops/raster.py::ReaderRasterParams` (gardée par `CORE_RASTER_ENABLED`) |

Limites consignées dans les `notes` de chaque ligne : pas d'écriture GeoTIFF depuis un
pipeline (aucune sortie raster) ; SQLCreator sans DDL/DML ni `{{param.x}}` dans `query`.

## Reclassées en `out_of_scope` (20, décision Tanguy 2026-10-15)

| Voie | Lignes | Motif |
|---|---|---|
| E | TCPIPReceiver, TCPIPSender, JMSReceiver, JMSSender (4, ex-`unknown`) | D2 : sockets arbitraires / API Java hors garde d'egress ; déclencheurs entrants déjà couverts (webhook entrant, déclencheur S3, ADR 0027) |
| G | 13 `PointCloud*` + LAS/LAZ, EPT, E57 (16, ex-`planned_pdal`) | D4 : pas de PDAL ni de sidecar nuage de points |

## Périmètre rétréci (ligne maintenue `planned_*`)

| Voie | Ligne FME | Ce qui existe déjà | Ce qui reste à construire |
|---|---|---|---|
| A | GeometryFilter, AttributeRangeFilter | `transform.filter`/`transform.testFilter` par catégorie ou par plage | une seule op avec priorité de port (ordre, exclusivité) |
| A | AttributeManager, AggregateFilter, DatabaseJoiner | compositions select+derive, aggregate+filter, connecteur+join | matérialiser l'op unique (aucun moteur nouveau) |
| A | SpatialRelator | `transform.countWithin` (`intersects`/`contains`), `transform.intersection` | prédicats OGC restants + colonne de relation |
| A | Terminator | `transform.testFilter` (conditions bornées validées par `validate_bounded_expr`) | échec du run avec message si une ligne échoue |
| B | Google Sheets | `reader.connector.rest` (pagination, secret) | OAuth via le coffre, mise en forme des feuilles |
| C | GeometryCoercer | `transform.explodeGeometry` (multi → simples), `transform.boundingGeometry` | polygone→ligne, ligne→point, etc. |
| C | Triangulator | `transform.triangulate` (Delaunay sur points, Shapely) | triangulation de l'intérieur d'un polygone (maillage contraint) |
| D | CKANConnector, ArcGISOnlineConnector | `reader.connector.rest` (CKAN Action API, `f=geojson` d'un FeatureServer) ; moissonnage CKAN/ArcGIS FS (métadonnées) | résolution multi-étapes (jeu de données → ressource → fichier), jetons Esri |
| E | SlackConnector, TrelloConnector | `transform.httpCall` (POST vers un webhook entrant Slack/l'API Trello, secret scopé REV-294) | API bot (canaux, fichiers), forme de message dédiée |
| E | Emailer | SMTP TLS des alertes (`core/app/alerts`) | writer générique de pipeline (réutiliser le SMTP existant) |
| F1 | RasterPyramider | overviews COG construites à l'import (`rio_cogeo.cog_translate`, `core/app/terrain3d/conversion.py`) | niveaux paramétrables — sans objet tant qu'aucun pipeline ne produit de raster |
| F1 | RasterStatisticsCalculator | statistiques approchées par bande à l'import (`app/raster/ingest.py::read_metadata`) | statistiques exactes en sortie d'op |
| F1 | WebMapTiler | tuiles XYZ dynamiques depuis le COG (proxy TiTiler sous `can()`, ARC-33) | pyramide de tuiles statiques exportée |
| F1 | SurfaceDraper | `transform.zonalStats` (statistiques de bande sous polygones) | échantillonnage d'altitude aux sommets |
| F2 | CityGML | import `.gml` via le driver GML générique de GDAL (ARC-23, lecture partielle non sémantique) | modèle CityGML complet (LOD, sémantique) |
| F2 | WMS | WMS 1.3.0 **servi** par le cœur (ARC-20) et moissonnage WMS (SP-12) | **lecteur** WMS dans un pipeline (egress + plafond de pixels) |

Aucun reclassement pour la voie C (géométrie) : aucune des 15 opérations topologiques n'a
d'équivalent 1:1 dans `OPERATIONS`. OSM XML/PBF, TopoJSON, NetCDF, ERDAS, JPEG 2000, GRIB,
Sentinel-2, Landsat-8, WCS, CityJSON : aucune extension acceptée par l'import
(`importer.py`, `parsers.py`), et l'hébergement raster n'accepte que le TIFF.

## Effectif restant par voie

| Voie | Avant | → implemented | → out_of_scope | Reste à implémenter |
|---|---|---|---|---|
| A | 19 | 1 | 0 | **18** |
| B | 7 | 2 | 0 | **5** |
| C | 15 | 0 | 0 | **15** |
| D | 10 | 0 | 0 | **10** |
| E | 14 | 0 | 4 | **10** |
| F1 | 17 | 0 | 0 | **17** |
| F2 | 12 | 1 | 0 | **11** (spike des drivers GDAL amd64/arm64 encore requis, D5) |
| G | 16 | 0 | 16 | 0 (voie abandonnée) |
| H | 3 | — | — | 3 (différée, D1) |
| I | 7 | — | — | 7 (différée, D1) |
| **Total** | **120** | **4** | **20** | **86 implémentables + 10 différées** |

Matrice après audit (290 lignes) : 132 `implemented`, 45 `out_of_scope`, 43 `planned_gdal`,
40 `planned_duckdb`, 8 `unknown`, 3 `planned_otb`, 2 `planned_rust`, 10 `license_blocked`,
7 `capability_removed`. Rendu régénéré par
`cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --write --check`
(aucune erreur).
