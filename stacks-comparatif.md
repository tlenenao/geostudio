# 8 Stacks Open-Source complètes — Alternatives à ArcGIS Enterprise

> Chaque option est une stack autonome et cohérente, déployable en production.

---

## Stack 1 — FOSS4G Classique (La Valeur Sûre)

**Philosophie :** Combinaison éprouvée depuis 15 ans, documentation abondante, communauté massive.

```
QGIS Desktop
    │
    ▼
GeoServer 2.x  ──→  GeoWebCache (tuiles)
    │
    ▼
PostgreSQL 16 + PostGIS 3.4
    │
    ▼
GeoNode 4.x (portail)       Grafana (dashboards)
    │
    ▼
Nginx + Keycloak (proxy / auth)
```

| Composant | Rôle |
|---|---|
| **GeoServer** | WMS, WFS, WCS, WMTS, OGC API |
| **PostGIS** | Base spatiale principale |
| **GeoWebCache** | Cache de tuiles intégré |
| **GeoNode** | Portail, catalogue, partage |
| **Grafana** | Dashboards opérationnels |
| **QGIS** | Client desktop |
| **Keycloak** | SSO / OAuth2 |
| **Nginx** | Reverse proxy, load balancer |

**Pour :** Organisations publiques, collectivités, tout profil métier GIS.
**Contre :** Architecture monolithique, scalabilité verticale principalement.
**Coût infra :** 2–4 serveurs dédiés ou VMs.
**Maturité :** ⭐⭐⭐⭐⭐

---

## Stack 2 — Vector-First Moderne (La Stack Légère Haute Performance)

**Philosophie :** Pas de serveur WMS lourd — tout en tuiles vectorielles MVT, rendu côté client.

```
QGIS Desktop / MapLibre Studio
    │
    ▼
Martin (Rust) ──→ PMTiles sur MinIO
pg_tileserv     ──→ CDN (Cloudflare / nginx)
pg_featureserv  ──→ OGC API Features
    │
    ▼
PostgreSQL 16 + PostGIS 3.4 + PgBouncer
    │
    ▼
MapLibre GL JS (front-end)    Apache Superset (dashboards)
    │
    ▼
Keycloak + Traefik
```

| Composant | Rôle |
|---|---|
| **Martin** | Serveur tuiles vectorielles Rust (< 5ms) |
| **pg_tileserv** | MVT direct depuis PostGIS |
| **pg_featureserv** | API REST features |
| **PMTiles** | Tuiles statiques auto-indexées (S3/MinIO) |
| **MapLibre GL JS** | Rendu WebGL côté client |
| **MinIO** | Stockage objet S3-compatible |
| **Superset** | BI spatiale + Deck.gl |
| **Traefik** | Reverse proxy cloud-native |

**Pour :** Applications web modernes, forte charge utilisateurs, mobile.
**Contre :** WMS/WCS non couverts nativement, rasters complexes nécessitent TiTiler.
**Coût infra :** 1–2 serveurs + CDN.
**Maturité :** ⭐⭐⭐⭐

---

## Stack 3 — Cloud Native Kubernetes (La Stack Enterprise Scalable)

**Philosophie :** Microservices, auto-scaling, résilience, observabilité complète.

```
                   Ingress NGINX / Traefik
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   GeoServer          Martin            GeoNode
  (x3 pods HPA)    (x2 pods HPA)     (x2 pods)
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
              PostgreSQL HA (CloudNativePG)
              PostGIS + PgBouncer + Replica
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
            Redis       MinIO       Kafka
           (cache)    (objets)    (stream)
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
           Grafana   Prometheus      Loki
          (dashboards) (métriques) (logs)
```

| Composant | Rôle |
|---|---|
| **CloudNativePG** | PostgreSQL HA géré sur K8s |
| **GeoServer** | Services OGC avec HPA |
| **Martin** | Tuiles vectorielles avec HPA |
| **Redis Cluster** | Cache distribué |
| **MinIO Distributed** | Stockage objet HA |
| **Kafka** | Bus de messages |
| **Prometheus + Grafana + Loki** | Observabilité complète |
| **Keycloak** | SSO OIDC |

**Helm charts disponibles :** GeoServer, PostGIS, Grafana, Keycloak, MinIO, Kafka, Prometheus.

**Pour :** Grandes organisations, SLA élevé (99.9%+), équipes DevOps.
**Contre :** Complexité opérationnelle, courbe d'apprentissage K8s.
**Coût infra :** Cluster K8s (3 masters + 5+ workers).
**Maturité :** ⭐⭐⭐⭐⭐

---

## Stack 4 — Big Data Spatial (La Stack Analytique Massive)

**Philosophie :** Traitement de centaines de millions de features, analyses distribuées.

```
Sources de données
(Shapefiles, COG, API, IoT)
        │
        ▼
  Apache Airflow (orchestration ETL)
        │
        ▼
  Apache Spark + Sedona (GeoSpark)
  ─── analyses spatiales distribuées
        │
    ┌───┴───┐
    ▼       ▼
 DeltaLake  GeoParquet
 (stockage) (export)
    │
    ▼
PostgreSQL + PostGIS   ──→  GeoServer / Martin
(résultats agrégés)              │
                                 ▼
                     Apache Superset + Grafana
                         (dashboards BI)
```

| Composant | Rôle |
|---|---|
| **Apache Spark + Sedona** | Analyse spatiale distribuée (jointures, buffers, krigeage) |
| **Apache Airflow** | Orchestration pipelines ETL |
| **Delta Lake** | Stockage données géo versionné |
| **GeoParquet** | Format colonne géospatial haute performance |
| **DuckDB + Spatial** | Analytique ad-hoc sans cluster |
| **PostGIS** | Persistance des résultats |
| **Superset** | Exploration et dashboards |

**Exemples de workloads :**
```python
# Sédona : jointure spatiale sur 500M points
spark.sql("""
    SELECT p.id, c.nom_commune, COUNT(*) as nb
    FROM points p JOIN communes c
    ON ST_Within(p.geom, c.geom)
    GROUP BY p.id, c.nom_commune
""")
```

**Pour :** Smart cities, télédétection, données LiDAR massives, mobilité urbaine.
**Contre :** Sur-dimensionné pour < 10M features.
**Coût infra :** Cluster Spark (5–20 nœuds) ou Databricks/EMR.
**Maturité :** ⭐⭐⭐⭐

---

## Stack 5 — Temps Réel Streaming (La Stack Event-Driven)

**Philosophie :** Données géospatiales en mouvement — capteurs, véhicules, alertes.

```
Capteurs / GPS / IoT / API externes
        │
        ▼
  MQTT (Mosquitto)  ──→  Apache Kafka
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              Apache Flink  Telegraf  Kafka Connect
              (CEP spatial) (métriques) (sink DB)
                    │
                    ▼
         PostgreSQL + PostGIS + TimescaleDB
         (persistance + séries temporelles)
                    │
            ┌───────┼───────┐
            ▼       ▼       ▼
         Grafana  Martin  GeoServer
         (temps  (tuiles) (WMS)
          réel)
```

| Composant | Rôle |
|---|---|
| **Mosquitto** | Broker MQTT |
| **Apache Kafka** | Bus de messages haute performance |
| **Apache Flink** | Traitement de flux avec opérateurs spatiaux |
| **TimescaleDB** | Séries temporelles géospatiales |
| **Telegraf** | Agent de collecte métriques |
| **Grafana** | Dashboards temps réel (< 1s refresh) |

**Cas d'usage :** Tracking flottes, réseaux de capteurs environnementaux, gestion de crises, trafic routier.

**Pour :** Applications nécessitant < 1s de latence bout en bout.
**Contre :** Complexité opérationnelle élevée, maintenance Kafka.
**Coût infra :** 3–6 serveurs dédiés.
**Maturité :** ⭐⭐⭐⭐

---

## Stack 6 — Raster & Télédétection (La Stack Image Server)

**Philosophie :** Traitement et diffusion d'images satellite, orthos, LiDAR, MNT.

```
Images sources
(Sentinel, Landsat, Ortho, LiDAR)
        │
        ▼
  GDAL / GRASS GIS / WhiteboxTools
  (prétraitement, reprojection, découpage)
        │
        ▼
  COG (Cloud Optimized GeoTIFF) sur MinIO
  STAC API (catalogue d'assets raster)
        │
        ▼
  TiTiler (serveur tuiles raster dynamiques)
  GeoServer ImageMosaic (mosaïques)
        │
        ▼
  OpenLayers / MapLibre (client web)
  Jupyter + Rasterio (analyse)
  Grafana + Superset (dashboards)
```

| Composant | Rôle |
|---|---|
| **GDAL 3.8+** | Conversion et traitement raster universel |
| **GRASS GIS** | Analyse raster avancée (hydrologie, morphologie) |
| **WhiteboxTools** | 500+ algorithmes géomorphométrie |
| **TiTiler** | Serveur COG dynamique (NDVI à la volée, etc.) |
| **STAC API** | Catalogue assets spatio-temporels |
| **Rasterio / Xarray** | Analyse Python |
| **MinIO** | Stockage COG |

```bash
# Génération COG optimisé
gdal_translate input.tif output_cog.tif \
  -of COG \
  -co COMPRESS=DEFLATE \
  -co OVERVIEW_RESAMPLING=AVERAGE \
  -co BIGTIFF=YES
```

**Pour :** Agences cartographiques, agriculture de précision, environnement, urbanisme.
**Contre :** Volumes importants (stockage + bande passante).
**Coût infra :** Stockage objet conséquent + serveurs CPU/GPU pour traitements.
**Maturité :** ⭐⭐⭐⭐

---

## Stack 7 — Python-Centric Developer-First (La Stack Dev Moderne)

**Philosophie :** Tout en Python, APIs REST modernes, déploiement rapide, idéal pour équipes data/dev.

```
QGIS / Jupyter Lab (desktop/analyse)
        │
        ▼
FastAPI + GeoPandas + Shapely
(API REST géospatiale custom)
        │
        ▼
pg_featureserv / OGC API (standards)
        │
        ▼
PostgreSQL + PostGIS
        │
        ▼
TiTiler (raster)    Martin (vecteur)
        │
        ▼
Evidence / Observable (dashboards code-driven)
Streamlit / Panel (apps géo interactives)
```

| Composant | Rôle |
|---|---|
| **FastAPI + GeoPandas** | API REST géospatiale sur-mesure |
| **Shapely / Fiona** | Manipulation géométries Python |
| **Rasterio / Xarray** | Traitement raster Python |
| **Streamlit / Panel** | Apps web géo interactives sans JS |
| **Evidence** | Dashboards SQL → site statique |
| **Jupyter + Folium** | Exploration interactive |
| **DuckDB Spatial** | Analytique fichiers sans serveur |

```python
# API géospatiale FastAPI en 10 lignes
from fastapi import FastAPI
from geopandas import read_postgis
from sqlalchemy import create_engine

app = FastAPI()
engine = create_engine("postgresql://user:pass@postgis/gis")

@app.get("/communes/{id}/voisines")
def voisines(id: int, distance_km: float = 10):
    gdf = read_postgis(f"""
        SELECT b.* FROM communes a, communes b
        WHERE a.id = {id}
        AND ST_DWithin(a.geom::geography, b.geom::geography, {distance_km * 1000})
        AND b.id != {id}
    """, engine, geom_col="geom")
    return gdf.to_json()
```

**Pour :** Équipes data science, startups, prototypage rapide, APIs custom.
**Contre :** Moins adapté aux utilisateurs non-techniques, pas de portail clé-en-main.
**Coût infra :** 1–2 serveurs suffisent.
**Maturité :** ⭐⭐⭐⭐

---

## Stack 8 — Full Elastic (La Stack Search & Maps)

**Philosophie :** Elasticsearch comme moteur central — recherche géospatiale + analytics + maps.

```
GDAL / Logstash / Beats (ingest)
        │
        ▼
Elasticsearch 8.x
(index géospatiaux : geo_point, geo_shape)
        │
        ▼
Kibana + Elastic Maps
(dashboards, cartes interactives)
        │
        ▼
PostGIS (données authoritatives)
GeoServer (services OGC)
        │
        ▼
Keycloak + Nginx
```

| Composant | Rôle |
|---|---|
| **Elasticsearch** | Moteur de recherche + index géospatiaux |
| **Kibana + Elastic Maps** | Dashboards + cartes vectorielles avancées |
| **Logstash** | Ingestion et transformation données |
| **Beats** | Agents collecte légère |
| **PostGIS** | Source authoritaire données spatiales |

```json
// Requête geo_distance Elasticsearch
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": { "lat": 48.85, "lon": 2.35 }
    }
  }
}
```

**Pour :** Applications search-heavy (adresses, POI, patrimoine), SIEM géo, portails publics avec recherche plein-texte géolocalisée.
**Contre :** Licence BSL (pas 100% open-source depuis v7.11), RAM importante requise.
**Coût infra :** 3+ nœuds Elastic (mémoire-intensif).
**Maturité :** ⭐⭐⭐⭐

---

## Tableau de décision

| Stack | Scalabilité | Complexité | Temps réel | Raster | Analytique | Idéal pour |
|---|---|---|---|---|---|---|
| **1 FOSS4G Classique** | ⭐⭐⭐ | Faible | ❌ | Partiel | ⭐⭐⭐ | Collectivités, EPCI |
| **2 Vector-First** | ⭐⭐⭐⭐ | Faible | ❌ | TiTiler | ⭐⭐⭐ | Apps web modernes |
| **3 Cloud Native K8s** | ⭐⭐⭐⭐⭐ | Élevée | Partiel | ✅ | ⭐⭐⭐⭐ | Grandes organisations |
| **4 Big Data Spatial** | ⭐⭐⭐⭐⭐ | Élevée | ❌ | ✅ | ⭐⭐⭐⭐⭐ | Smart city, mobilité |
| **5 Streaming Temps Réel** | ⭐⭐⭐⭐ | Très élevée | ✅ | ❌ | ⭐⭐⭐ | IoT, tracking, crises |
| **6 Raster & Télédétection** | ⭐⭐⭐ | Moyenne | ❌ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Agences carto, env. |
| **7 Python-Centric** | ⭐⭐⭐ | Faible | Partiel | ✅ | ⭐⭐⭐⭐ | Équipes data/dev |
| **8 Full Elastic** | ⭐⭐⭐⭐ | Moyenne | ✅ | ❌ | ⭐⭐⭐⭐ | Search, SIEM, portails |

---

## Recommandation par profil

| Profil | Stack recommandée |
|---|---|
| Collectivité territoriale / EPCI | **Stack 1** + éléments **Stack 2** |
| DSI grande organisation | **Stack 3** (K8s) |
| Startup / équipe produit | **Stack 7** → migrer vers **Stack 2** |
| Analyse données massives | **Stack 4** + **Stack 6** |
| Applications IoT / smart city | **Stack 5** + **Stack 3** |
| Portail public avec recherche | **Stack 8** + **Stack 1** |
| Télédétection / satellite | **Stack 6** |
| Besoin universel complet | **Stack 3** (intègre tout) |

---

> **Note :** Les stacks ne sont pas mutuellement exclusives. La trajectoire naturelle est souvent :
> **Stack 1** (démarrage) → **Stack 2** (modernisation web) → **Stack 3** (passage à l'échelle) → **Stack 4/5** (besoins analytiques avancés).
