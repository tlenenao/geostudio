# Op de pipeline expérimentales (lot 9, release v0.2.0)

Décision de Tanguy : les vagues ARC/FME sont dans la release grand public, mais les op
qui parlent à un service tiers sans jamais avoir été rejouées contre le vrai service sont
**expérimentales** : `experimental: True` sur leur `OperationContract` (posé depuis
`EXPERIMENTAL_OPS`, `core/app/pipelines/ops/contracts.py`), derrière
`CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED` (défaut `false`).

## Critère

Une op est expérimentale quand **les deux** conditions sont vraies, relevées dans le code et
les tests, pas de mémoire :

1. elle appelle un service tiers à protocole ou API propre (messagerie, cloud, base ou
   entrepôt externe, serveur OGC/STAC, moteur de routage, géocodeur, serveur MCP) ;
2. aucun test d'intégration ne la rejoue contre ce service réel : les tests n'utilisent que
   des doubles (`monkeypatch` d'un client, `pytest-httpserver` imitant l'API, session HTTP
   factice), ou aucun appel réseau n'est exercé. L'ADR 0028 (« Conséquences ») le dit des
   connecteurs Trello, Service Bus, Kinesis, MCP, Dropbox/Box/Graph ; la matrice
   (`matrice-couverture-fme.jsonl`) le dit de Snowflake, Databricks et Google Drive.

Restent **stables** : les op DuckDB/Shapely/attributs/géométrie/raster fichier, les lecteurs de
fichiers locaux (`reader.file`, NetCDF, GRIB, OSM, CityJSON…), et les op qui ont un test
contre un vrai service local :

| Op stable | Preuve |
|---|---|
| `reader.connector.postgres`, `writer.connector.postgres.update/delete`, `transform.databaseJoin` | tests contre le vrai PostGIS de test (`CORE_TEST_DATABASE_URL`) : `test_pipeline_connector_runtime.py`, `test_pipeline_ops_dbio.py`, `test_pipeline_ops_reliquats.py` |
| `reader.connector.rest`, `transform.httpCall` | client HTTP générique, testé contre un vrai serveur HTTP local (`pytest-httpserver`) ; aucune API tierce spécifique |
| `transform.sqlExecutor` | DuckDB local |
| `reader.sentinel2`, `reader.landsat8`, `reader.netcdf`, `reader.osm`… | lisent un produit/fichier local (`CORE_PIPELINE_FILE_IO_ENABLED`), aucun service tiers |

## Liste (32 op)

| Op | Service | Raison / preuve |
|---|---|---|
| `writer.email` | SMTP | `test_pipeline_ops_messaging.py` : client SMTP remplacé, jamais de vrai serveur |
| `writer.slack` | Slack | idem, session HTTP factice (`http` fixture) |
| `writer.trello` | Trello | ADR 0028 : forme d'API testée contre un double |
| `writer.servicebus`, `writer.azurequeue`, `reader.azurequeue` | Azure Service Bus / Queue | ADR 0028 ; doubles HTTP |
| `writer.sns` | AWS SNS | double (`test_pipeline_ops_messaging.py`) |
| `writer.kinesis`, `reader.kinesis` | AWS Kinesis | ADR 0028 ; double |
| `writer.rabbitmq` | RabbitMQ | `pika` remplacé par un double (en-tête de `test_pipeline_ops_messaging.py`) |
| `transform.mcpCall` | serveur MCP tiers | ADR 0028 ; double |
| `reader.cloudfile` (Drive, Dropbox, Box, Graph, Azure Files, HDFS…) | API fichiers cloud | `test_pipeline_ops_cloudfiles.py` : `pytest-httpserver` redirigeant `cf._API` ; matrice : « non testé contre le v[rai service] » |
| `reader.ckan`, `reader.arcgisonline` | portails CKAN / ArcGIS Online | idem (`httpserver`) |
| `reader.ftp`, `writer.ftp` | serveur FTPS | `FakeFtp` substitué à `ftplib.FTP_TLS` |
| `reader.connector.googlesheets` | Google Sheets | `test_pipeline_ops_dbio.py` : `pytest-httpserver` imitant l'API v4 |
| `reader.connector.snowflake` | Snowflake | matrice : « round-trip réel non câblé en CI », test `@pytest.mark.snowflake` manuel |
| `reader.connector.databricks` | Databricks | matrice : « Non vérifié sur un workspace réel » ; `databricks_manual` |
| `reader.connector.bigquery`, `reader.connector.mssql`, `reader.connector.oracle` | BigQuery / SQL Server / Oracle | `test_pipeline_connector_runtime.py` : gardes (non-SELECT, type de secret, secret absent) et résolution du dialecte SQLAlchemy sans réseau ; aucun aller-retour contre un serveur |
| `reader.connector.blob` | S3/GCS/Azure Blob externes | `test_pipeline_connector_runtime.py` : internes de `duckdb`/credentials interceptés (`_patch_blob_internals`) |
| `reader.mongodb` | MongoDB | `test_pipeline_ops_secretkinds.py` ne valide que le schéma du secret ; aucun test de connexion |
| `reader.wms`, `reader.wcs`, `reader.wfs` | serveurs OGC | `pytest-httpserver` (WMS/WCS) et session HTTP factice (WFS) imitant la réponse, jamais GeoServer/MapServer |
| `transform.imageFetch`, `transform.webMapTiler` | serveurs d'images/tuiles | `test_pipeline_ops_raster2.py` : `_fetch` remplacé par un double |
| `transform.geocode` | BAN / Nominatim | `test_pipeline_ops_arc4m.py` : `_FakeGeocoder` |
| `transform.isochrone`, `transform.route` | Valhalla | `test_pipeline_ops_routing.py` : `httpx.MockTransport` (`fake_valhalla`), jamais de Valhalla réel |

(Le décompte exact et à jour est `len(EXPERIMENTAL_OPS)` ; `test_pipeline_experimental_ops.py`
vérifie que chaque nom existe dans `OPERATIONS`.)

## Comportement

| Surface | Flag éteint (défaut) | Flag allumé |
|---|---|---|
| `GET /v1/pipelines/ops` | op absentes | présentes, `experimental: true` (les autres : `false`) |
| écriture d'une config (REST `/configs`, MCP `create_pipeline`/`update_config`) | 422 RFC 7807 « Opération expérimentale désactivée : … » | acceptée |
| exécution (run manuel, cron, webhook, aperçu, sidecar) | échec lisible du run, même message, avant toute exécution | normale |
| palette du builder | op absente | op présente, badge « Expérimental » |
| `GET /v1/instance`, `GET /v1/me` | `experimentalOpsEnabled: false` | `true` |

Jumelles vérifiées (piège n°14) : toutes les écritures de config pipeline passent par
`validate_pipeline_payload` (REST create/update/restore, MCP `create_pipeline` et
`update_config`) ; toute exécution passe par `_prepare()` (`run_pipeline`, `preview_pipeline`,
tâches procrastinate, planification, webhook, sidecar). `explain_pipeline` (lecture seule) ne
filtre pas. Le copilote n'a aucun outil de pipeline dans son allowlist.

## Pour sortir une op de l'expérimental

Rejouer l'op contre le vrai service (test d'intégration ou rejeu manuel documenté), puis la
retirer de `EXPERIMENTAL_OPS` et de ce document, et mentionner la bascule dans `CHANGELOG.md`.
