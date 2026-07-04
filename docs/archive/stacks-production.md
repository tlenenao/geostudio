# 5 Stacks Production pour remplacer — et dépasser — ArcGIS Enterprise

> Chaque stack est opinionée, complète, déployable, et surpasse ArcGIS Enterprise
> sur au moins un axe structurel : performance, temps réel, coût, scalabilité, modernité.

---

## Stack 1 — Sovereign GIS
### "Souveraineté totale, conformité INSPIRE, on-premise"

**Ce qu'elle dépasse :** ArcGIS Portal + ArcGIS Server + Enterprise Geodatabase
**Avantage clé :** Zéro dépendance cloud Esri, conformité RGPD/INSPIRE native, coût licences = 0.

```
┌─────────────────────────────────────────────────────────┐
│                    ACCÈS UTILISATEURS                    │
│          Nginx (SSL, rate limiting, load balancing)      │
│                   Keycloak (SSO OIDC)                    │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
  ┌──────────┐    ┌───────────┐    ┌───────────┐
  │ GeoNode  │    │ GeoServer │    │  Grafana  │
  │  Portail │    │WMS/WFS/   │    │Dashboards │
  │catalogue │    │WMTS/WPS   │    │opérationn.│
  └────┬─────┘    └─────┬─────┘    └─────┬─────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
          ┌─────────────────────────────┐
          │   PostgreSQL 16 + PostGIS   │
          │   PgBouncer (pooling)       │
          │   Streaming Replication     │
          └─────────────┬───────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
          MinIO       Redis      Airflow
         (COG/       (cache     (ETL/
         fichiers)    tuiles)   pipelines)
```

| Composant | Version | Rôle |
|---|---|---|
| GeoServer | 2.25 | Services OGC (WMS, WFS, WMTS, WPS, OGC API) |
| GeoWebCache | 1.23 | Cache tuiles intégré |
| PostGIS | 3.4 | Base spatiale principale |
| PgBouncer | 1.22 | Connection pooling |
| GeoNode | 4.x | Portail, catalogue ISO 19115, partage |
| Grafana | 10.x | Dashboards opérationnels, alertes |
| Keycloak | 24.x | SSO, OAuth2/OIDC, rôles |
| MinIO | AGPL | Stockage objet S3 (COG, fichiers) |
| Redis | 7.x | Cache sessions et tuiles |
| Airflow | 2.x | Orchestration ETL |
| QGIS Server | 3.36 | Services WMS desktop-grade |
| Nginx | 1.25 | Reverse proxy, SSL termination |

**Infrastructure minimale :**
```
Serveur 1 (app)   : 16 vCPU / 32 GB RAM / 500 GB SSD
Serveur 2 (DB)    : 16 vCPU / 64 GB RAM / 2 TB NVMe
Serveur 3 (cache) : 8 vCPU / 16 GB RAM / 1 TB SSD
```

**Déploiement :** Docker Compose (dev) → Ansible (prod)

**Points forts vs ArcGIS :**
- Catalogue INSPIRE/ISO 19115 meilleur que ArcGIS Portal (GeoNetwork en option)
- WPS natif pour geoprocessing serveur (ArcGIS nécessite extension payante)
- Réplication PostgreSQL standard, pas de vendor lock-in sur le format de données

---

## Stack 2 — Real-Time GIS Platform
### "Streaming géospatial < 500ms, IoT, tracking, alertes"

**Ce qu'elle dépasse :** ArcGIS GeoEvent Server (70k€/an) + ArcGIS Dashboards
**Avantage clé :** Latence bout-en-bout < 500ms, 100k+ événements/s, alertes géospatiales complexes.

```
Capteurs / GPS / IoT / Webhooks
              │
              ▼
     Mosquitto (MQTT broker)
              │
              ▼
     Apache Kafka (bus événements)
     ─ Partitions par zone géo
     ─ Rétention configurable
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 Apache    Telegraf   Kafka
  Flink    (métriques) Connect
(CEP geo)             (sink)
    │                   │
    ▼                   ▼
PostGIS          TimescaleDB
(géofences,      (séries temp.
 alertes)         IoT, tracks)
    │                   │
    └─────────┬─────────┘
              ▼
   ┌──────────────────────┐
   │       Grafana        │
   │  Refresh < 1 seconde │
   │  Geomap temps réel   │
   │  Alerting géo        │
   └──────────────────────┘
              │
   Martin / pg_tileserv
   (tuiles positions live)
              │
   MapLibre GL JS (front)
```

**Pipeline Flink — géofencing temps réel :**
```java
// Alerte si véhicule entre dans zone interdite
DataStream<Alert> alerts = vehicleStream
    .keyBy(Vehicle::getId)
    .process(new GeoFenceFunction(forbiddenZones))
    .filter(alert -> alert.getSeverity() > 2);

alerts.addSink(new KafkaSink<>("alerts-topic"));
alerts.addSink(new PostgresSink("INSERT INTO alerts ..."));
```

| Composant | Rôle |
|---|---|
| Mosquitto | Broker MQTT (IoT, GPS) |
| Apache Kafka | Bus haute performance (100k+ msg/s) |
| Apache Flink | CEP spatial — géofencing, détection patterns |
| TimescaleDB | Séries temporelles géospatiales |
| PostGIS | Géofences, zones, référentiels |
| Telegraf | Collecte métriques systèmes |
| Grafana | Dashboards live (streaming datasource) |
| Martin | Tuiles positions en temps réel |
| MapLibre GL JS | Rendu WebGL client |

**Infrastructure :**
```
Kafka cluster  : 3 nœuds × (8 vCPU / 16 GB / 500 GB)
Flink cluster  : 1 master + 3 workers (8 vCPU / 16 GB)
DB             : 16 vCPU / 64 GB / NVMe (TimescaleDB)
App            : 8 vCPU / 16 GB
```

**Performances mesurées (benchmarks open-source) :**
- Ingestion : 150 000 positions GPS/seconde
- Latence géofence : < 50ms
- Refresh dashboard : 500ms

---

## Stack 3 — Modern Web GIS
### "Expérience utilisateur web sans égale, 3D, mobile-first"

**Ce qu'elle dépasse :** ArcGIS Experience Builder + ArcGIS Dashboards + ArcGIS StoryMaps
**Avantage clé :** WebGL natif, tuiles vectorielles, 3D, mobile, offline-capable — ArcGIS JS SDK ne peut pas rivaliser en performance brute.

```
┌─────────────────────────────────────────────┐
│              FRONT-END WEB                   │
│                                             │
│  MapLibre GL JS  ──  Deck.gl (3D/WebGL)     │
│  Observable Framework (dashboards)          │
│  Apache Superset  (BI spatiale)             │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Martin     TiTiler    pg_featureserv
(MVT Rust) (COG raster)(OGC API Feat.)
 < 3ms      dynamique   REST/JSON
    │
    ▼
PostgreSQL + PostGIS
    │
    ├── PMTiles sur MinIO  (tuiles statiques CDN)
    ├── GeoParquet          (export analytique)
    └── Redis               (cache chaud)
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Keycloak  Traefik    GeoNode
 (auth)   (ingress)  (catalogue)
```

**Rendu Deck.gl — visualisation 3D bâtiments + données :**
```javascript
// Carte 3D avec données temps réel
const layers = [
  new Tile3DLayer({
    data: 'http://minio/3dtiles/tileset.json',  // CesiumJS 3D Tiles
  }),
  new ScatterplotLayer({
    data: fetchGeoJSON('/api/incidents'),
    getPosition: d => d.geometry.coordinates,
    getColor: d => riskColor(d.properties.score),
    radiusScale: 50,
  }),
  new HeatmapLayer({
    data: fetchGeoJSON('/api/densite'),
    getWeight: d => d.properties.count,
    intensity: 1,
    threshold: 0.03,
  }),
];
```

**PMTiles — zéro serveur de tuiles :**
```bash
# Génération depuis PostGIS → PMTiles (une seule fois)
ogr2ogr -f GeoJSON /vsistdout/ PG:"host=db dbname=gis" communes \
  | tippecanoe -o communes.pmtiles \
      --maximum-zoom=14 \
      --drop-densest-as-needed \
      --force

# Upload MinIO → accessible via range requests HTTP
mc cp communes.pmtiles minio/tiles/communes.pmtiles
# Consommé directement par MapLibre, SANS SERVEUR
```

| Composant | Rôle |
|---|---|
| MapLibre GL JS | Rendu vectoriel WebGL |
| Deck.gl | Visualisations 3D avancées |
| Martin (Rust) | MVT dynamiques < 3ms |
| TiTiler | COG dynamiques (NDVI, raster) |
| PMTiles | Tuiles statiques sans serveur |
| Apache Superset | BI + Deck.gl intégré |
| Observable Framework | Dashboards code-driven |
| pg_featureserv | OGC API Features |
| Traefik | Ingress cloud-native |

**Points forts vs ArcGIS :**
- Tuiles MVT 3–5x plus rapides que ArcGIS Feature Services
- 3D natif WebGL sans plugin (ArcGIS 3D nécessite CityEngine)
- Mode offline avec PMTiles + Service Worker

---

## Stack 4 — Spatial Analytics Platform
### "BI spatiale et data science, dépasse ArcGIS Insights + GeoAnalytics"

**Ce qu'elle dépasse :** ArcGIS Insights (15k€/an) + ArcGIS GeoAnalytics Server (50k€/an)
**Avantage clé :** SQL spatial sur milliards de lignes, Python natif, notebook intégré, Spark distribué.

```
Data Sources
(PostGIS, COG, GeoParquet, APIs, Shapefiles)
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 DuckDB    Apache    Apache
 Spatial    Spark    Airflow
(ad-hoc)  +Sedona   (pipelines)
(< 1s)    (distrib)
    │         │
    └────┬────┘
         ▼
   GeoParquet / Delta Lake
   (résultats persistés)
         │
    ┌────┼────┐
    ▼    ▼    ▼
PostGIS Superset Jupyter
(résult) (dashb.) (notebooks)
         │
         ▼
   Grafana (métriques)
   Evidence (rapports)
```

**DuckDB — analytique instantanée :**
```sql
-- Analyse sur 50M points en < 2 secondes, sans cluster
INSTALL spatial; LOAD spatial;

SELECT
    h3_cell_to_parent(h3_latlng_to_cell(lat, lon, 7), 5) AS zone,
    COUNT(*)                   AS nb_incidents,
    AVG(severity)              AS gravite_moy,
    PERCENTILE_CONT(0.95)
      WITHIN GROUP (ORDER BY response_time) AS p95_response
FROM incidents
WHERE date_incident > CURRENT_DATE - INTERVAL '90 days'
GROUP BY zone
ORDER BY nb_incidents DESC;
```

**Sedona — jointure spatiale sur 500M features :**
```python
from sedona.spark import SedonaContext

spark = SedonaContext.create(SparkSession.builder
    .config("spark.executor.memory", "16g")
    .config("spark.executor.cores", "4")
    .getOrCreate())

# Jointure spatiale distribuée : points dans polygones
spark.sql("""
    SELECT
        c.nom_commune,
        COUNT(p.id)              AS nb_points,
        ST_AsText(c.geom)        AS geom_wkt,
        AVG(p.valeur)            AS valeur_moy
    FROM communes c
    JOIN points p ON ST_Within(p.geom, c.geom)
    GROUP BY c.nom_commune, c.geom
""").write.format("geoparquet").save("s3://minio/results/communes_stats")
```

**Superset — dashboard BI spatiale :**
```python
# Connexion PostGIS dans Superset
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://user:pass@postgis:5432/gis"
)
# Viz disponibles : choroplèthe, scatter geo, flow map,
# heatmap, deck.gl 3D column, H3 hexbin
```

| Composant | Rôle |
|---|---|
| DuckDB + Spatial | Analytique fichiers ultra-rapide |
| Apache Sedona | Spatial distribué sur Spark |
| Apache Airflow | Pipelines ETL orchestrés |
| GeoParquet | Format colonne géo haute perf |
| H3 (Uber) | Indexation hexagonale multi-résolution |
| Apache Superset | BI + Deck.gl (cartes 3D) |
| Jupyter + GeoPandas | Data science Python |
| Evidence | Rapports SQL → site statique |
| PostGIS | Persistance et requêtes finales |

**Points forts vs ArcGIS :**
- DuckDB: requêtes spatiales ad-hoc sans serveur, sans licence
- Sedona: scale horizontal illimité (Spark autoscaling)
- Notebooks Jupyter intégrés (ArcGIS Notebooks = add-on payant)
- H3 hexbins natifs (ArcGIS ne supporte pas H3 nativement)

---

## Stack 5 — Full Enterprise Cloud-Native
### "La stack complète, scalable, observable — tout ce que fait ArcGIS, mieux"

**Ce qu'elle dépasse :** L'intégralité d'ArcGIS Enterprise (Server + Portal + GeoEvent + GeoAnalytics + Insights + Image Server)
**Avantage clé :** Auto-scaling, zéro downtime, observabilité totale, multi-tenant, GitOps.

```
                    ╔══════════════════╗
                    ║  INTERNET / VPN  ║
                    ╚════════╤═════════╝
                             │
                    ┌────────▼────────┐
                    │  Traefik Ingress │
                    │  SSL + Rate Limit│
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  ┌──────────┐        ┌──────────┐        ┌──────────┐
  │ GeoServer│        │  Martin  │        │ TiTiler  │
  │ ×3 pods  │        │ ×2 pods  │        │ ×2 pods  │
  │  HPA     │        │  HPA     │        │  HPA     │
  └────┬─────┘        └────┬─────┘        └────┬─────┘
       │                   │                   │
  ┌────▼───────────────────▼───────────────────▼─────┐
  │                  Service Mesh (Istio)             │
  │              mTLS inter-services                  │
  └────────────────────────┬──────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │  GeoNode │      │ Superset │      │  Grafana │
  │  Portail │      │  BI Geo  │      │ Dashbds  │
  └────┬─────┘      └────┬─────┘      └────┬─────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
          ┌──────────────────────────────┐
          │   CloudNativePG (PostgreSQL) │
          │   Primary + 2 Replicas       │
          │   PostGIS 3.4                │
          │   PgBouncer (pooling)        │
          └──────────────┬───────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │  Redis   │   │  MinIO   │   │  Kafka   │
   │ Sentinel │   │Distributed│  │ Cluster  │
   │ Cluster  │   │  (HA S3) │   │ 3 nodes  │
   └──────────┘   └──────────┘   └────┬─────┘
                                       │
                                ┌──────▼──────┐
                                │Apache Flink │
                                │(streaming)  │
                                └─────────────┘

         ┌─────────────────────────────────────┐
         │         OBSERVABILITÉ               │
         │  Prometheus → Grafana (métriques)   │
         │  Loki → Grafana (logs centralisés)  │
         │  Tempo → Grafana (tracing distribué)│
         │  AlertManager (PagerDuty/Slack)      │
         └─────────────────────────────────────┘

         ┌─────────────────────────────────────┐
         │         GITOPS / CI-CD              │
         │  ArgoCD (déploiement K8s)           │
         │  Helm Charts (packaging)            │
         │  GitHub Actions / GitLab CI         │
         └─────────────────────────────────────┘
```

**Helm Charts utilisés :**
```yaml
dependencies:
  - name: geoserver        # camptocamp/geoserver
  - name: postgresql-ha    # bitnami/postgresql-ha
  - name: redis            # bitnami/redis
  - name: minio            # bitnami/minio
  - name: kafka            # bitnami/kafka
  - name: grafana          # grafana/grafana
  - name: prometheus       # prometheus-community/kube-prometheus-stack
  - name: loki             # grafana/loki
  - name: keycloak         # bitnami/keycloak
  - name: airflow          # apache/airflow
  - name: superset         # apache/superset
```

**Autoscaling — GeoServer sous charge :**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: geoserver-hpa
spec:
  scaleTargetRef:
    name: geoserver
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: geoserver_wms_requests_per_second
      target:
        type: AverageValue
        averageValue: "100"
```

**Dashboards Grafana — SLA GIS :**

| Métrique | Seuil alerte | Seuil critique |
|---|---|---|
| Latence tuile WMS P95 | > 300ms | > 1000ms |
| Latence tuile MVT P95 | > 50ms | > 200ms |
| Requêtes PostGIS P99 | > 500ms | > 2000ms |
| Connexions PgBouncer | > 80% | > 95% |
| Lag Kafka consumer | > 5000 msg | > 50000 msg |
| Disk MinIO | > 75% | > 90% |

**Infrastructure K8s :**
```
Masters   : 3 × (4 vCPU / 8 GB)
Workers   : 5 × (16 vCPU / 64 GB / NVMe)
DB nodes  : 3 × (16 vCPU / 128 GB / 4 TB NVMe)
Storage   : Ceph / Longhorn (persistent volumes)
```

**Coût infrastructure vs ArcGIS Enterprise :**
```
ArcGIS Enterprise (licences seules) : ~150 000 €/an
Stack 5 infrastructure cloud        : ~40 000 €/an
Stack 5 on-premise amorti 3 ans     : ~15 000 €/an
Économie nette                      : 75–90%
```

---

## Synthèse comparative

| | Stack 1 | Stack 2 | Stack 3 | Stack 4 | Stack 5 |
|---|---|---|---|---|---|
| **Nom** | Sovereign GIS | Real-Time GIS | Modern Web GIS | Spatial Analytics | Full Enterprise |
| **Remplace** | Server+Portal+DB | GeoEvent+Dashboards | Experience Builder | Insights+GeoAnalytics | Tout ArcGIS |
| **Complexité deploy** | Faible | Élevée | Moyenne | Moyenne | Très élevée |
| **Temps réel** | ❌ | ⭐⭐⭐⭐⭐ | ❌ | ❌ | ⭐⭐⭐⭐ |
| **Scalabilité** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Perf. web** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Analytics** | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Profil cible** | Collectivités | IoT/Smart city | Startups/Web | Data science | Grandes orgs |
| **Équipe requise** | 1–2 devops | 2–3 devops | 1–2 devops | 1–2 data eng | 3–5 devops |

---

## Trajectoire recommandée

```
Semaine 1–2   →  Stack 1  (base fonctionnelle)
Mois 2–3      →  Stack 3  (modernisation front)
Mois 4–6      →  Stack 4  (analytics avancée)
Mois 6–12     →  Stack 5  (passage enterprise grade)
Sur besoin    →  Stack 2  (si IoT/temps réel requis)
```
