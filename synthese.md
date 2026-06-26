# Synthèse : Stack Open-Source équivalente à ArcGIS Enterprise

## 1. Analyse de la stack ArcGIS Enterprise

ArcGIS Enterprise est une plateforme SIG propriétaire d'Esri composée de plusieurs modules interdépendants :

| Composant ArcGIS | Rôle |
|---|---|
| ArcGIS Server | Serveur de services cartographiques (WMS, WFS, REST) |
| ArcGIS Portal | Portail web, gestion des utilisateurs, partage de données |
| ArcGIS Data Store | Stockage des données (relationnel, tuiles, big data) |
| ArcGIS Web Adaptor | Reverse proxy / intégration IIS/Apache |
| Enterprise Geodatabase | Base spatiale (Oracle, SQL Server, PostgreSQL + ST_Geometry) |
| ArcGIS Pro | Client desktop d'analyse et de publication |
| ArcGIS Dashboards | Tableaux de bord opérationnels temps réel |
| ArcGIS GeoAnalytics Server | Analyse spatiale distribuée à grande échelle |
| ArcGIS Image Server | Services raster, mosaïques, COG |
| ArcGIS Insights | BI spatiale, exploration de données |
| ArcGIS StoryMaps | Narration cartographique |
| GeoEvent Server | Streaming géospatial temps réel |

**Coût estimé ArcGIS Enterprise :** 100 000 € – 500 000 €/an selon niveau.

---

## 2. Stack Open-Source Équivalente — Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────┐
│                   DASHBOARDS & PORTAIL                        │
│   Grafana · Apache Superset · GeoNode · MapStore2            │
├──────────────────────────────────────────────────────────────┤
│                  SERVICES CARTOGRAPHIQUES                     │
│   GeoServer · pg_tileserv · pg_featureserv · Martin          │
│   TiTiler (raster) · STAC API                                │
├──────────────────────────────────────────────────────────────┤
│              ETL / ANALYSE / TRAITEMENT                       │
│   Apache Sedona (Spark) · DuckDB/Spatial · GDAL/OGR          │
│   Apache Airflow · GRASS GIS · WhiteboxTools                  │
├──────────────────────────────────────────────────────────────┤
│                   STOCKAGE SPATIAL                            │
│   PostgreSQL 16 + PostGIS 3.x · TimescaleDB · MinIO          │
│   Redis · PgBouncer                                          │
├──────────────────────────────────────────────────────────────┤
│              INFRASTRUCTURE & PERFORMANCE                     │
│   Kubernetes · Nginx · GeoWebCache · MapProxy                │
│   Prometheus · Loki · Grafana (monitoring)                   │
├──────────────────────────────────────────────────────────────┤
│                  SÉCURITÉ & AUTH                              │
│   Keycloak · GeoServer Security · SSL/TLS                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Correspondance Composant par Composant

### 3.1 Base de données spatiale — *remplace Enterprise Geodatabase*

**PostgreSQL 16 + PostGIS 3.4**
- Support complet des géométries 2D/3D/4D, topologie, raster
- Fonctions spatiales : ST_Intersects, ST_Buffer, ST_DWithin, etc.
- Index GIST/BRIN pour les requêtes spatiales hautes performances
- Compatible avec tous les standards OGC

**TimescaleDB** (extension PostgreSQL)
- Séries temporelles géospatiales (IoT, capteurs, tracking)
- Compression automatique, continuous aggregates
- Équivalent partiel du Data Store "big data" d'ArcGIS

**Extensions recommandées :**
```sql
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_raster;
CREATE EXTENSION postgis_topology;
CREATE EXTENSION timescaledb;
CREATE EXTENSION h3;         -- grilles hexagonales Uber
CREATE EXTENSION pg_stat_statements;
```

---

### 3.2 Serveur de services géospatiaux — *remplace ArcGIS Server*

**GeoServer 2.25**
- WMS, WFS, WCS, WMTS, WPS, OGC API Features
- Styles SLD/CSS, rendu avancé, labellisation
- Plugin ImageMosaic pour les rasters tuilés
- Clustering natif avec GeoServer Cluster + JMS

**pg_tileserv** (Rust/Go — PostGIS natif)
- Génération de tuiles vectorielles MVT directement depuis PostGIS
- Latence < 5ms pour les requêtes simples
- Idéal pour les layers dynamiques

**pg_featureserv** (Go)
- OGC API Features (successor to WFS)
- Interface REST légère sur PostGIS

**Martin** (Rust)
- Serveur de tuiles vectorielles très haute performance
- Supporte PostGIS et MBTiles/PMTiles
- ~3x plus rapide que pg_tileserv pour les charges élevées

**TiTiler** (Python/FastAPI)
- Serveur de tuiles raster dynamiques
- Support Cloud Optimized GeoTIFF (COG), STAC
- Équivalent ArcGIS Image Server

---

### 3.3 Portail web — *remplace ArcGIS Portal*

**GeoNode 4.x**
- Portail complet : catalogue de données, métadonnées INSPIRE/ISO 19115
- Gestion des droits (public/privé/groupes)
- Visualisation cartographique intégrée (MapLibre)
- API REST, OGC CSW, OGC API Records

**MapStore2** (alternative légère)
- Application cartographique web avancée
- Gestion de contextes, annotations, impression
- Intégration GeoServer native

---

### 3.4 Dashboards avancés — *remplace ArcGIS Dashboards*

#### Grafana 10+ (recommandé principal)

Grafana offre la couverture fonctionnelle la plus proche d'ArcGIS Dashboards pour un contexte opérationnel :

**Plugins géospatiaux clés :**

| Plugin | Usage |
|---|---|
| `grafana-worldmap-panel` | Carte choroplèthe, points |
| `Geomap panel` (natif) | Carte vectorielle intégrée, couches multiples |
| `GeoJSON / PostGIS datasource` | Connexion directe à PostGIS |
| `Flowcharting` | Schémas réseau avec données temps réel |
| `AG Charts` | Graphiques haute performance |

**Datasources pour GIS :**
```yaml
# grafana.ini
[datasources]
# PostgreSQL/PostGIS direct
- type: postgres
  url: postgis-host:5432
  database: gis_db

# Prometheus pour métriques infra
- type: prometheus
  url: http://prometheus:9090

# Loki pour logs
- type: loki
  url: http://loki:3100
```

**Dashboard types couverts :**
- Suivi de flottes / tracking temps réel (via MQTT → Telegraf → InfluxDB → Grafana)
- Indicateurs KPI territoriaux (agrégats PostGIS + Grafana)
- Alertes géographiques (Grafana Alerting + géofencing PostGIS)
- Tableaux de bord opérationnels IoT

#### Apache Superset 3.x (BI spatiale)

- Visualisations riches : cartes choroplèthes, scatter geo, flow maps
- Connexion directe à PostGIS via SQLAlchemy
- Support Deck.gl pour visualisations 3D avancées
- Équivalent ArcGIS Insights pour l'exploration de données

```python
# Exemple requête spatiale dans Superset
SELECT
    commune,
    ST_AsGeoJSON(geom) AS geojson,
    count(*) AS incidents,
    avg(valeur) AS valeur_moy
FROM incidents
WHERE date_event > NOW() - INTERVAL '7 days'
GROUP BY commune, geom
```

---

### 3.5 Analyse spatiale distribuée — *remplace GeoAnalytics Server*

**Apache Sedona (ex-GeoSpark) sur Spark**
- Analyse spatiale distribuée à l'échelle du Big Data
- Jointures spatiales distribuées, agrégations, interpolation
- Intégration Python (PySedona), Scala, SQL

```python
from sedona.spark import SedonaContext
from pyspark.sql import SparkSession

spark = SedonaContext.create(SparkSession.builder
    .config("spark.driver.memory", "8g")
    .getOrCreate())

# Jointure spatiale distribuée
result = spark.sql("""
    SELECT a.id, b.commune, ST_Distance(a.geom, b.centroid) AS dist
    FROM points a, communes b
    WHERE ST_Within(a.geom, b.geom)
""")
```

**DuckDB + extension spatial** (analytique ad-hoc)
- Requêtes spatiales instantanées sur fichiers GeoParquet/GeoJSON
- Idéal pour l'exploration et prototypage
- Supporte H3, GeoArrow

```sql
INSTALL spatial;
LOAD spatial;

SELECT commune, ST_Area(geom) AS surface_ha
FROM ST_Read('communes.gpkg')
WHERE ST_Intersects(geom, ST_GeomFromText('POLYGON((...))'));
```

---

### 3.6 ETL & Orchestration — *remplace ArcGIS Data Interoperability*

**GDAL/OGR 3.8+**
- Conversion entre 200+ formats vecteur/raster
- Reprojection, découpage, fusion
- CLI et API Python/C++

**Apache Airflow 2.x**
- Orchestration de pipelines ETL géospatiaux
- DAGs Python, retry, monitoring, alertes
- Intégration S3 (MinIO), PostgreSQL, Spark

```python
# Exemple DAG Airflow pour import données géo
from airflow.providers.postgres.operators.postgres import PostgresOperator

dag = DAG('import_cadastre', schedule='@daily')

import_task = BashOperator(
    task_id='ogr2ogr_import',
    bash_command="""
        ogr2ogr -f PostgreSQL PG:"host=postgis dbname=gis" \
        /data/cadastre.gpkg -nlt PROMOTE_TO_MULTI -overwrite
    """,
    dag=dag
)
```

---

### 3.7 Streaming temps réel — *remplace GeoEvent Server*

**Stack recommandée :**
```
Capteurs/IoT → MQTT (Mosquitto) → Apache Kafka → 
  Flink (traitement) → PostGIS (persistance) → 
    Grafana (visualisation temps réel)
```

- **Mosquitto** : broker MQTT léger
- **Apache Kafka** : bus de messages haute performance
- **Apache Flink** : traitement de flux avec opérateurs spatiaux
- **Telegraf** : collecte de métriques (alternative légère à Kafka pour petits volumes)

---

### 3.8 Client Desktop — *remplace ArcGIS Pro*

**QGIS 3.36 LTR**
- Analyse vecteur/raster complète
- Connexion native à PostGIS, GeoServer, WMS/WFS
- PyQGIS pour l'automatisation
- Plugins : GRASS, WhiteboxTools, Processing

---

### 3.9 Stockage objets — *remplace ArcGIS Data Store (fichiers)*

**MinIO**
- S3-compatible, déployable on-premise
- Stockage COG, MBTiles, PMTiles, GeoParquet
- Haute disponibilité avec mode distributed

---

## 4. Gestion des performances

### 4.1 Base de données

```sql
-- Index spatial sur table volumineuse
CREATE INDEX CONCURRENTLY idx_incidents_geom
ON incidents USING GIST(geom);

-- Partitionnement temporel (TimescaleDB)
SELECT create_hypertable('mesures', 'timestamp',
    chunk_time_interval => INTERVAL '1 month');

-- Clustering physique par localisation
CLUSTER incidents USING idx_incidents_geom;

-- Tuning PostgreSQL (postgresql.conf)
-- shared_buffers = 25% RAM
-- effective_cache_size = 75% RAM
-- work_mem = 64MB
-- max_parallel_workers_per_gather = 4
-- random_page_cost = 1.1  (SSD)
```

**PgBouncer** : connection pooling (évite la surcharge PostgreSQL)
```ini
[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 50
```

### 4.2 Cache de tuiles

**GeoWebCache** (intégré GeoServer)
- Cache WMTS, TMS, Google Maps
- Seeding automatique, invalidation par région

**MapProxy**
- Proxy/cache multi-sources (WMS, WMTS, TMS)
- Cache disque, Redis, S3
- Reprojection à la volée

```yaml
# mapproxy.yaml
caches:
  communes_cache:
    grids: [GLOBAL_WEBMERCATOR]
    sources: [communes_wms]
    cache:
      type: redis
      host: redis
      port: 6379
      prefix: gis_tiles
```

### 4.3 Tuiles vectorielles pré-générées

**PMTiles** (format recommandé)
- Fichier unique auto-indexé (range requests HTTP)
- Déployable sur MinIO/S3 sans serveur
- Régénération via `tippecanoe` :

```bash
tippecanoe \
  -o communes.pmtiles \
  --maximum-zoom=14 \
  --minimum-zoom=0 \
  --drop-densest-as-needed \
  communes.geojson
```

### 4.4 Monitoring & observabilité

**Stack Prometheus + Grafana + Loki :**

```yaml
# docker-compose monitoring
services:
  prometheus:
    image: prom/prometheus
    # Scrape GeoServer, PostGIS, Nginx, applicatifs

  grafana:
    image: grafana/grafana
    # Dashboards : latence tuiles, requêtes/s, saturation DB

  loki:
    image: grafana/loki
    # Centralisation logs GeoServer, Airflow, applicatifs

  postgres_exporter:
    image: prometheuscommunity/postgres-exporter
    # Métriques PostGIS : connexions, locks, slow queries

  nginx_exporter:
    image: nginx/nginx-prometheus-exporter
```

**Alertes critiques à configurer :**
- Latence tuile > 500ms
- Connexions PostgreSQL > 80% du max
- Espace disque tuile-cache > 85%
- Lag Kafka > 10k messages

---

## 5. Architecture de déploiement recommandée

```
                    ┌──────────────┐
                    │   Nginx LB   │  ← SSL termination, rate limiting
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌────────────┐ ┌────────────┐
    │  GeoServer  │ │  Grafana   │ │  GeoNode   │
    │  (x2-3)     │ │  Superset  │ │  MapStore  │
    └──────┬──────┘ └─────┬──────┘ └─────┬──────┘
           └──────────────┼──────────────┘
                          ▼
           ┌──────────────────────────────┐
           │     PostgreSQL + PostGIS     │
           │     (Primary + Replica)      │
           │     PgBouncer (pooling)      │
           └──────────────┬───────────────┘
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
      ┌─────────┐   ┌──────────┐   ┌─────────┐
      │  Redis  │   │  MinIO   │   │  Kafka  │
      │ (cache) │   │ (objets) │   │(stream) │
      └─────────┘   └──────────┘   └─────────┘
```

**Kubernetes recommandé** pour production :
- HPA (Horizontal Pod Autoscaler) sur GeoServer et pg_tileserv
- PersistentVolumes pour PostGIS et MinIO
- Helm charts disponibles pour tous les composants

---

## 6. Tableau de correspondance final

| ArcGIS Enterprise | Open-Source | Maturité |
|---|---|---|
| Enterprise Geodatabase | PostgreSQL + PostGIS | ⭐⭐⭐⭐⭐ |
| ArcGIS Server (WMS/WFS) | GeoServer | ⭐⭐⭐⭐⭐ |
| ArcGIS Server (tuiles vecteur) | Martin / pg_tileserv | ⭐⭐⭐⭐ |
| ArcGIS Image Server | TiTiler + STAC | ⭐⭐⭐⭐ |
| ArcGIS Portal | GeoNode | ⭐⭐⭐⭐ |
| ArcGIS Dashboards | Grafana + Superset | ⭐⭐⭐⭐⭐ |
| ArcGIS GeoAnalytics | Apache Sedona | ⭐⭐⭐⭐ |
| ArcGIS Insights | Apache Superset | ⭐⭐⭐⭐ |
| GeoEvent Server | Kafka + Flink | ⭐⭐⭐⭐ |
| Data Interoperability | GDAL/OGR + Airflow | ⭐⭐⭐⭐⭐ |
| ArcGIS Pro | QGIS | ⭐⭐⭐⭐⭐ |
| Web Adaptor | Nginx | ⭐⭐⭐⭐⭐ |
| Cache de tuiles | GeoWebCache / MapProxy | ⭐⭐⭐⭐⭐ |
| Monitoring | Prometheus + Grafana | ⭐⭐⭐⭐⭐ |
| SSO / Auth | Keycloak | ⭐⭐⭐⭐⭐ |

---

## 7. Coûts et gains

| | ArcGIS Enterprise | Stack Open-Source |
|---|---|---|
| Licences logicielles | 100k–500k €/an | 0 € |
| Infrastructure | Identique | Identique |
| Formation / expertise | Élevée | Élevée (différente) |
| Communauté & support | Esri uniquement | Large communauté + support commercial disponible |
| Indépendance vendor | Zéro | Totale |
| Interopérabilité standards OGC | Bonne | Excellente (natif) |
| Scalabilité | Licences par core | Illimitée |

**Économie estimée : 80-95% sur les coûts logiciels.**

---

## 8. Recommandations de démarrage

1. **Socle minimal MVP** : PostgreSQL/PostGIS + GeoServer + Grafana + QGIS
2. **Ajouter le portail** : GeoNode pour le catalogue et le partage
3. **Optimiser les performances** : Martin (tuiles vecteur) + MapProxy (cache) + PgBouncer
4. **Monitoring** : Prometheus + Grafana dès le début (pas après)
5. **Streaming** : Kafka + Telegraf si besoin de données temps réel
6. **Big Data spatial** : Apache Sedona si volumes > 100M features

> **Note :** La stack complète peut être déployée en moins d'une semaine avec Docker Compose, et en production sur Kubernetes en 2-4 semaines selon le niveau d'expertise DevOps.
