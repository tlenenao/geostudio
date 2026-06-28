# Plan d'implémentation — Stack GIS Open-Source

> Objectif : déployer une alternative complète à ArcGIS Enterprise, en 8 phases progressives.
> Chaque phase est autonome et livrable. Les phases 1–5 constituent le MVP production.

---

## Vue d'ensemble des phases

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  Socle       Services    Portail &   Sécurité &   Perfs &
  données     OGC         BI          Auth          cache
  [Semaine 1] [Semaine 2] [Semaine 3] [Semaine 4]  [Semaine 5]
                                                        │
                                                        ▼
                                               Phase 6 ──► Phase 7 ──► Phase 8
                                                 ETL &      Monitoring   Streaming
                                                 Airflow    Grafana      temps réel
                                               [Sem. 6]   [Sem. 7]     [Sem. 8–10]
```

**Prérequis avant de commencer :**
- Serveur (ou VM) : 16 vCPU / 32 Go RAM / 500 Go SSD minimum
- Docker 24+ et Docker Compose 2.20+ installés
- Nom de domaine avec DNS configuré (pour le SSL Let's Encrypt)
- Accès SSH root ou utilisateur sudo

---

## Phase 1 — Socle de données (Semaine 1)

**Objectif :** Base spatiale opérationnelle + serveur de tuiles vectorielles + front cartographique minimal.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| PostgreSQL 16 + PostGIS 3.4 | `postgis/postgis:16-3.4` | Stockage spatial |
| PgBouncer 1.22 | `edoburu/pgbouncer:1.22` | Connection pooling |
| Martin 0.13 | `ghcr.io/maplibre/martin:v0.13` | Tuiles MVT (< 5ms) |
| Application web MapLibre | Nginx + JS bundle | Carte interactive |

### Fichiers à créer

```
sql/
├── init.sql              ✅ existant — extensions + schéma de base
├── 001_communes.sql      À créer — table communes + index
├── 002_functions.sql     À créer — fonctions MVT get_communes_tiles()
└── seeds/
    └── communes_test.sql À créer — jeu de données de test (10 communes)

web-app/
├── index.html            À créer — page principale
├── src/
│   ├── map.js            À créer — initialisation MapLibre GL JS
│   └── layers.js         À créer — définition des couches
├── styles/
│   └── style.json        À créer — style fond de carte (OSM)
└── package.json          À créer — dépendances (maplibre-gl, pmtiles)

docker-compose.yml        ✅ existant — à restreindre aux services phase 1
martin-config.yaml        ✅ existant — à configurer avec tables réelles
```

### Tâches détaillées

1. **PostGIS — schéma complet**
   - Créer `sql/001_communes.sql` : table `communes` (code_insee, nom, population, geom MULTIPOLYGON 4326)
   - Créer `sql/002_functions.sql` : `get_communes_tiles(z,x,y)` avec simplification adaptive par zoom
   - Créer `sql/seeds/communes_test.sql` : insérer 10 communes françaises réelles via WKT
   - Ajouter index `GIST` sur `geom`, index `btree` sur `code_insee`
   - Vérifier avec `SELECT ST_IsValid(geom) FROM communes` → 0 géométries invalides

2. **Martin — configuration des sources**
   - Mettre à jour `martin-config.yaml` : déclarer les tables `communes` et `points_interet`
   - Déclarer la fonction `get_communes_tiles` comme source MVT custom
   - Activer le cache Redis (TTL 3600s pour communes, 300s pour incidents)
   - Tester : `curl http://localhost:3000/communes/10/512/368` → réponse MVT valide

3. **Application web MapLibre**
   - Initialiser `web-app/` avec Vite + MapLibre GL JS 4.x
   - `map.js` : carte centrée sur la France, fond OSM raster en fallback
   - `layers.js` : couche `communes-fill` (choroplèthe population) + `communes-line`
   - `style.json` : fond de carte vecteur depuis OpenMapTiles (CDN public)
   - Ajouter popup au clic : nom commune + population
   - Servir via Nginx sur port 80

4. **Intégration et tests**
   - `docker compose up -d postgis pgbouncer redis martin web`
   - Vérifier rendu carte dans navigateur à zoom 6–14
   - Mesurer latence tuile MVT (objectif : P95 < 20ms à chaud)
   - Mesurer mémoire PostGIS au repos (< 4 Go RAM)

### Critères d'acceptation

- [ ] `curl http://localhost:3000/health` → HTTP 200
- [ ] Tuile Martin `communes/10/512/368` retourne un protobuf valide
- [ ] Carte affiche les communes avec choroplèthe population
- [ ] Clic sur commune → popup avec nom + population
- [ ] P95 latence tuile MVT < 20ms (mesurée avec `wrk` ou `k6`)
- [ ] Aucune requête SQL > 100ms dans `pg_stat_statements`

---

## Phase 2 — Services cartographiques OGC (Semaine 2)

**Objectif :** Exposer les données via les standards OGC pour interopérabilité avec QGIS, ArcGIS Pro, etc.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| GeoServer 2.25 | `kartoza/geoserver:2.25.0` | WMS, WFS, WCS, WMTS, WPS |
| GeoWebCache 1.23 | intégré GeoServer | Cache tuiles raster |
| TiTiler 0.18 | `developmentseed/titiler:0.18` | Raster COG dynamique |
| pg_featureserv 1.3 | `pramsey/pg_featureserv:latest` | OGC API Features (WFS3) |
| MinIO | `minio/minio` | Stockage COG et fichiers |

### Fichiers à créer

```
geoserver/
├── data/                 À créer — répertoire données GeoServer
│   └── workspaces/       À créer — workspace GIS initial
├── geoserver.env         À créer — variables d'environnement
└── web.xml               À créer — config sécurité servlet

titiler/
└── main.py               À créer — extensions custom (endpoint NDVI)

minio/
└── init-buckets.sh       À créer — création buckets au démarrage

nginx/
└── conf.d/
    └── geoserver.conf    À créer — reverse proxy GeoServer
```

### Tâches détaillées

1. **GeoServer — déploiement et configuration initiale**
   - Ajouter service `geoserver` dans `docker-compose.yml`
   - Configurer workspace `gis` et store PostGIS pointant sur `pgbouncer:6432`
   - Publier layers : `communes` (WMS + WFS), `points_interet` (WMS)
   - Activer GeoWebCache : seeder les tuiles de zoom 5 à 12 pour la France entière
   - Configurer styles SLD : choroplèthe population en 5 classes Jenks

2. **TiTiler — serveur raster COG**
   - Ajouter service `titiler` dans `docker-compose.yml`
   - Créer `titiler/main.py` : endpoint `/cog/ndvi/{z}/{x}/{y}.png` (calcul NDVI bandes NIR+Rouge)
   - Configurer accès MinIO via variables `AWS_*` pointant vers MinIO local
   - Tester avec un GeoTIFF de test uploadé dans MinIO

3. **pg_featureserv — OGC API Features**
   - Ajouter service `pg-featureserv` dans `docker-compose.yml`
   - Créer `pg-featureserv-config.toml` : URL base, pagination (100/5000), métadonnées
   - Vérifier endpoint `/features/collections/communes/items?limit=10&bbox=2,48,3,49`
   - Documenter les URLs dans le README

4. **MinIO — stockage objet**
   - Ajouter service `minio` dans `docker-compose.yml`
   - Créer `minio/init-buckets.sh` : créer buckets `tiles`, `rasters`, `exports` au démarrage
   - Configurer politique d'accès public en lecture sur bucket `tiles`
   - Uploader un COG de test (orthophoto IGN 100x100 km)

### Critères d'acceptation

- [ ] `http://localhost:8080/geoserver/wms?SERVICE=WMS&REQUEST=GetCapabilities` → XML valide
- [ ] QGIS peut ajouter une couche WMS GeoServer et l'afficher correctement
- [ ] `http://localhost:8000/healthz` → HTTP 200
- [ ] TiTiler retourne une tuile PNG pour le COG de test
- [ ] `http://localhost:9000/features/collections` → JSON listant les collections
- [ ] MinIO console accessible sur `http://localhost:9001`
- [ ] GeoWebCache sème les tuiles zoom 5–12 sans erreur

---

## Phase 3 — Portail et BI spatiale (Semaine 3)

**Objectif :** Portail de données géographiques avec catalogue INSPIRE + dashboards BI.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| GeoNode 4.2 | `geonode/geonode:4.2` | Portail, catalogue ISO 19115 |
| Apache Superset 3.1 | `apache/superset:3.1.0` | BI spatiale + Deck.gl |
| Celery (worker) | `apache/superset:3.1.0` | Jobs asynchrones Superset |

### Fichiers à créer

```
geonode/
├── local_settings.py      À créer — surcharge config Django
└── fixtures/
    └── initial_data.json  À créer — données initiales (admin, groupes)

superset/
├── superset_config.py     À créer — config + datasources PostGIS
├── dashboards/
│   └── communes.json      À créer — dashboard choroplèthe exporté
└── init.sh                À créer — script init (admin user, DB upgrade)
```

### Tâches détaillées

1. **GeoNode — portail catalogue**
   - Ajouter services `geonode` + `geonode-celery` dans `docker-compose.yml`
   - Créer `geonode/local_settings.py` : connexion PostGIS, GeoServer, Keycloak (préparation phase 4)
   - Importer les layers publiés dans GeoServer vers le catalogue GeoNode
   - Renseigner les métadonnées ISO 19115 des couches (titre, résumé, mots-clés, emprise)
   - Configurer les droits : couches publiques accessibles sans authentification

2. **Superset — BI spatiale**
   - Ajouter services `superset` + `superset-worker` dans `docker-compose.yml`
   - Créer `superset/superset_config.py` : connexion PostGIS via SQLAlchemy, activer Deck.gl
   - Créer `superset/init.sh` : `superset db upgrade && superset init && superset fab create-admin`
   - Créer dataset SQL `communes_incidents` (jointure communes + incidents + agrégats)
   - Créer dashboard avec 4 charts : carte choroplèthe (deck_geojson), histogramme incidents/commune, top 10 communes, KPI total
   - Exporter le dashboard en JSON dans `superset/dashboards/communes.json`

3. **Intégration GeoNode ↔ GeoServer**
   - Configurer GeoNode pour pointer vers GeoServer (URL interne Docker)
   - Vérifier la synchronisation des layers : modification dans GeoServer → visible dans GeoNode
   - Tester le téléchargement d'un shapefile depuis GeoNode

### Critères d'acceptation

- [ ] `http://localhost:8080` (GeoNode) → page d'accueil avec liste des couches
- [ ] Métadonnées ISO 19115 renseignées pour chaque couche
- [ ] `http://localhost:8088` (Superset) → dashboard communes accessible
- [ ] Carte choroplèthe Superset affiche les données PostGIS en < 3s
- [ ] Téléchargement shapefile depuis GeoNode fonctionnel
- [ ] Celery worker traite les exports asynchrones sans erreur

---

## Phase 4 — Sécurité et authentification (Semaine 4)

**Objectif :** SSO centralisé, contrôle d'accès aux couches par rôle, HTTPS partout.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| Keycloak 24 | `quay.io/keycloak/keycloak:24` | SSO OIDC/OAuth2 |
| Traefik 3.0 | `traefik:v3.0` | Ingress SSL/TLS + routing |

### Fichiers à créer

```
keycloak/
├── realm-gis.json          À créer — realm exporté (clients, rôles, groupes)
└── themes/
    └── gis/                À créer — thème Keycloak personnalisé (optionnel)

traefik/
├── traefik.yml             À créer — configuration statique
├── dynamic/
│   ├── middlewares.yml     À créer — rate limiting, headers sécurité
│   └── routers.yml         À créer — routing par service + TLS
└── certs/                  Répertoire existant (ignoré git)

nginx/
└── conf.d/
    └── martin-auth.conf    À créer — validation JWT pour tuiles protégées
```

### Tâches détaillées

1. **Keycloak — realm et clients**
   - Ajouter service `keycloak` dans `docker-compose.yml` (déjà présent, à finaliser)
   - Créer realm `gis-platform` avec clients : `web-app` (public), `geonode`, `superset`, `martin`
   - Définir rôles realm : `gis-viewer`, `gis-editor`, `gis-admin`
   - Créer groupes : `Visualisateurs`, `Éditeurs`, `Administrateurs`
   - Créer 3 comptes de test (un par rôle)
   - Exporter le realm : `keycloak/realm-gis.json`

2. **Traefik — ingress et SSL**
   - Créer `traefik/traefik.yml` : entrypoints (80 → redirect 443, 443 TLS), ACME Let's Encrypt
   - Créer `traefik/dynamic/routers.yml` : router par service avec règle Host + PathPrefix
   - Créer `traefik/dynamic/middlewares.yml` : rate limit (100 req/s), headers sécurité (HSTS, CSP, X-Frame)
   - Ajouter labels Docker Compose sur chaque service (web, geonode, superset, martin…)
   - Tester certificat SSL valide sur `https://gis.votre-domaine.fr`

3. **Intégration SSO sur chaque application**
   - **GeoNode** : configurer OIDC via `django-allauth` (client_id, secret, URL Keycloak)
   - **Superset** : configurer `AUTH_TYPE = AUTH_OAUTH` dans `superset_config.py`
   - **Martin** : ajouter middleware Nginx `auth_jwt` validant les tokens Keycloak
   - **Web-app MapLibre** : intégrer `keycloak-js` pour login + injection Bearer token dans les requêtes Martin

4. **Contrôle d'accès aux couches**
   - GeoServer : configurer plugin GeoServer Security pour valider JWT Keycloak
   - Règles : couches `public_*` → sans auth ; couches `restricted_*` → rôle `gis-viewer` minimum
   - Tester : requête WMS sans token → 401 ; avec token viewer → 200 ; avec token editor → 200 + écriture WFS-T

### Critères d'acceptation

- [ ] `https://gis.exemple.fr` → HTTPS valide (A+ sur SSL Labs)
- [ ] Login SSO Keycloak fonctionne depuis GeoNode, Superset, web-app
- [ ] Rôle `gis-viewer` : accès lecture seule, pas d'écriture WFS-T
- [ ] Rôle `gis-editor` : accès lecture + écriture WFS-T
- [ ] Token expiré → redirection automatique vers login Keycloak
- [ ] Headers sécurité présents : HSTS, X-Frame-Options, CSP

---

## Phase 5 — Performance et cache (Semaine 5)

**Objectif :** Tenir 500 utilisateurs simultanés, P95 < 50ms sur toutes les requêtes de tuiles.

### Composants

| Composant | Rôle |
|---|---|
| Redis 7.2 | Cache tuiles Martin + sessions |
| PgBouncer 1.22 | Connection pooling PostgreSQL |
| PMTiles (MinIO) | Tuiles statiques pour fond de carte |
| MapProxy | Cache WMS GeoServer |

### Fichiers à créer

```
scripts/
├── generate-pmtiles.sh     ✅ existant — à compléter avec toutes les couches
├── seed-redis.sh           À créer — pré-chauffage cache Redis
└── benchmark.sh            À créer — test de charge k6 automatisé

mapproxy/
├── mapproxy.yaml           À créer — config cache WMS + Redis
└── seed.yaml               À créer — config seeding par bbox France

k6/
└── tiles-load-test.js      À créer — script test de charge 500 utilisateurs

postgresql/
└── postgresql.conf         À créer — tuning prod (shared_buffers 25% RAM, etc.)
```

### Tâches détaillées

1. **PgBouncer — tuning connection pooling**
   - Mode `transaction` (ne pas utiliser `session` en production)
   - `max_client_conn = 1000`, `default_pool_size = 50` par database
   - Activer `server_idle_timeout = 600` pour libérer connexions inactives
   - Vérifier avec `psql -p 6432 pgbouncer -c "SHOW POOLS"` : 0 connexions en attente sous charge

2. **PostgreSQL — tuning selon RAM disponible**
   - Créer `postgresql/postgresql.conf` avec paramètres calculés pour 32 Go RAM :
     - `shared_buffers = 8GB`
     - `effective_cache_size = 24GB`
     - `work_mem = 128MB`
     - `maintenance_work_mem = 2GB`
     - `max_parallel_workers_per_gather = 4`
     - `random_page_cost = 1.1` (SSD)
   - Monter ce fichier dans le service `postgis`
   - Exécuter `CLUSTER communes USING idx_communes_geom` pour clustering physique
   - Créer vues matérialisées `communes_z8` et `communes_z12` pour simplification pré-calculée

3. **Redis — cache tuiles Martin**
   - Vérifier config dans `martin-config.yaml` : `ttl: 86400` pour communes, `ttl: 300` pour incidents
   - Créer `scripts/seed-redis.sh` : pré-chauffer le cache pour les 100 tuiles les plus demandées (zoom 6–10, bbox France)
   - Monitorer hit rate : `redis-cli INFO stats | grep keyspace_hits` (objectif > 80%)

4. **PMTiles — tuiles statiques fond de carte**
   - Compléter `scripts/generate-pmtiles.sh` : ajouter couches `points_interet` et fond OSM
   - Générer `france-admin.pmtiles` (communes z4–z14, départements z4–z10, régions z4–z8)
   - Uploader dans MinIO bucket `tiles` avec accès public
   - Mettre à jour `web-app/styles/style.json` pour utiliser PMTiles local au lieu du CDN
   - Vérifier mode offline : désactiver réseau → carte toujours visible

5. **MapProxy — cache WMS GeoServer**
   - Créer `mapproxy/mapproxy.yaml` : sources WMS GeoServer + cache disque + cache Redis
   - `mapproxy/seed.yaml` : semer la bbox France pour zoom 0–12
   - Lancer seeding : `mapproxy-seed -f mapproxy.yaml -s seed.yaml -c 4`
   - Remplacer les appels WMS directs par MapProxy dans l'application web

6. **Tests de charge**
   - Créer `k6/tiles-load-test.js` : simuler 500 VUs pendant 5 minutes sur les endpoints Martin, TiTiler, pg_featureserv
   - Objectifs : P95 < 50ms Martin MVT, P95 < 500ms TiTiler COG, 0 erreur 5xx
   - Automatiser dans CI : `k6 run k6/tiles-load-test.js --vus 500 --duration 5m`

### Critères d'acceptation

- [ ] Redis hit rate > 80% sous charge soutenue
- [ ] P95 latence tuile MVT Martin < 20ms (cache chaud)
- [ ] P95 latence WMS MapProxy < 50ms (cache chaud)
- [ ] PgBouncer : 0 connexion en file d'attente sous 500 VUs
- [ ] 500 utilisateurs simultanés sans erreur 5xx pendant 5 minutes
- [ ] PMTiles fond de carte accessible offline dans navigateur

---

## Phase 6 — ETL et orchestration (Semaine 6)

**Objectif :** Pipelines automatisés d'import/export de données géographiques.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| Apache Airflow 2.9 | `apache/airflow:2.9` | Orchestration DAGs |
| GDAL/OGR 3.8 | `osgeo/gdal:ubuntu-small-3.8.0` | Conversion formats |

### Fichiers à créer

```
airflow/
├── dags/
│   ├── import_cadastre.py      À créer — import quotidien cadastre DGFIP
│   ├── import_admin.py         À créer — import admin-express IGN mensuel
│   ├── refresh_materialized.py À créer — rafraîchissement vues matérialisées
│   └── generate_pmtiles.py     À créer — régénération PMTiles après import
├── plugins/
│   └── gis_operators.py        À créer — opérateurs custom (Ogr2OgrOperator)
├── requirements.txt            À créer — dépendances Python Airflow
└── airflow.env                 À créer — variables d'environnement

scripts/
├── import-gpkg.sh              À créer — import GeoPackage générique
└── export-geojson.sh           À créer — export couche vers GeoJSON/MinIO
```

### Tâches détaillées

1. **Airflow — déploiement**
   - Ajouter services `airflow-webserver`, `airflow-scheduler`, `airflow-worker` dans `docker-compose.yml`
   - Créer `airflow/requirements.txt` : `apache-airflow-providers-postgres`, `apache-airflow-providers-amazon`
   - Configurer connexions Airflow : `postgres_gis` (PostGIS), `minio_local` (S3 MinIO)

2. **Opérateurs custom GIS**
   - Créer `airflow/plugins/gis_operators.py` :
     - `Ogr2OgrOperator` : encapsule `ogr2ogr` avec paramètres source/cible/options
     - `PostGISOperator` : exécute SQL spatial avec logs
     - `PMTilesOperator` : déclenche `tippecanoe` + upload MinIO

3. **DAG import cadastre**
   - `import_cadastre.py` : schedule `@daily`
     1. Télécharger le fichier cadastre du département (data.gouv.fr)
     2. Dézipper et valider le GeoPackage
     3. `ogr2ogr` vers PostGIS avec option `-overwrite`
     4. Déclencher `REFRESH MATERIALIZED VIEW CONCURRENTLY communes_z8`
     5. Alerter par email si erreur

4. **DAG rafraîchissement vues matérialisées**
   - `refresh_materialized.py` : schedule `@hourly` si table incidents modifiée
   - Rafraîchir `CONCURRENTLY` pour ne pas bloquer les requêtes en cours
   - Invalider cache Redis des tuiles concernées via `redis-cli DEL martin:incidents:*`

5. **Scripts utilitaires**
   - `scripts/import-gpkg.sh` : import GeoPackage générique avec détection automatique CRS
   - `scripts/export-geojson.sh` : export couche PostGIS vers GeoJSON + upload MinIO + URL publique

### Critères d'acceptation

- [ ] Interface Airflow accessible sur `http://localhost:8888`
- [ ] DAG `import_cadastre` s'exécute sans erreur en manuel
- [ ] `ogr2ogr` importe 36 000 communes en < 5 minutes
- [ ] Vues matérialisées rafraîchies sans interruption de service
- [ ] Alertes email envoyées en cas d'échec de DAG
- [ ] `scripts/import-gpkg.sh communes.gpkg` fonctionne en one-liner

---

## Phase 7 — Monitoring et observabilité (Semaine 7)

**Objectif :** Visibilité complète sur la santé de la stack, alertes proactives.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| Prometheus 2.50 | `prom/prometheus:v2.50.0` | Collecte métriques |
| Grafana 10.3 | `grafana/grafana:10.3.0` | Dashboards + alertes |
| Loki 2.9 | `grafana/loki:2.9.0` | Centralisation logs |
| Promtail 2.9 | `grafana/promtail:2.9.0` | Collecte logs Docker |
| postgres_exporter | `prometheuscommunity/postgres-exporter` | Métriques PostGIS |
| nginx_exporter | `nginx/nginx-prometheus-exporter` | Métriques Traefik |

### Fichiers à créer

```
monitoring/
├── prometheus/
│   ├── prometheus.yml          À créer — scrape configs tous services
│   └── alerts/
│       ├── gis.yml             À créer — alertes latence, erreurs, disque
│       └── infra.yml           À créer — alertes CPU, RAM, connexions DB
├── grafana/
│   ├── datasources/
│   │   └── datasources.yml     À créer — Prometheus + Loki + PostGIS
│   └── dashboards/
│       ├── gis-stack.json      À créer — dashboard santé stack GIS
│       ├── postgis.json        À créer — dashboard métriques PostGIS
│       └── tiles.json          À créer — dashboard tuiles MVT/raster
├── loki/
│   └── loki-config.yml         À créer — config Loki (rétention 30j)
└── promtail/
    └── promtail-config.yml     À créer — labels Docker → Loki
```

### Tâches détaillées

1. **Prometheus — scraping**
   - Créer `monitoring/prometheus/prometheus.yml` : scrape Martin, TiTiler, GeoServer JMX, PostgreSQL, Traefik
   - Intervalle : 15s pour services GIS, 30s pour infrastructure
   - Rétention : 15 jours (ajuster selon espace disque)

2. **Alertes Prometheus**
   - Créer `monitoring/prometheus/alerts/gis.yml` :
     - `MartinLatencyHigh` : P95 > 100ms pendant 2 min → warning
     - `TilesErrorRate` : taux erreur > 1% pendant 1 min → critical
     - `PostGISSlowQueries` : requêtes actives > 500ms → warning
     - `DiskSpaceLow` : espace disque < 15% → warning, < 5% → critical
     - `RedisHitRateLow` : hit rate < 70% → warning

3. **Dashboards Grafana**
   - Créer dashboard `gis-stack.json` (5 panels) :
     - Requests/s total (Martin + TiTiler + pg_featureserv)
     - Latence P95 tuiles MVT (heatmap par source-layer)
     - Cache hit rate Redis (%)
     - Erreurs 5xx / minute
     - Utilisateurs actifs (sessions Keycloak)
   - Créer dashboard `postgis.json` (6 panels) :
     - Connexions actives PgBouncer (gauge)
     - Latence requêtes P99 (graph)
     - Taille tables + index (bar chart)
     - Slow queries > 500ms (table)
     - Replication lag si replica (gauge)
     - Cache hit rate PostgreSQL (%)
   - Créer dashboard `tiles.json` (4 panels) :
     - Tuiles générées/min par couche
     - Taille moyenne tuile par zoom
     - Distribution latences (histogram)
     - Top 10 couches les plus demandées

4. **Loki + Promtail — centralisation logs**
   - Créer `monitoring/loki/loki-config.yml` : rétention 30j, stockage filesystem
   - Créer `monitoring/promtail/promtail-config.yml` : collecter logs de tous les containers Docker, labels `service`, `level`
   - Ajouter datasource Loki dans Grafana
   - Créer vue explore Loki : logs Martin filtrés par niveau `ERROR`

5. **Alerting**
   - Configurer Grafana Alerting : canal email + optionnel webhook Slack
   - Relier les alertes Prometheus → Grafana Alertmanager
   - Tester : forcer une erreur sur Martin → alerte reçue en < 5 min

### Critères d'acceptation

- [ ] `http://localhost:9090` (Prometheus) → toutes les cibles `UP`
- [ ] `http://localhost:3001` (Grafana) → 3 dashboards visibles avec données
- [ ] Logs de tous les services visibles dans Loki/Grafana Explore
- [ ] Alerte test déclenchée et reçue par email en < 5 min
- [ ] Dashboard tuiles affiche latence temps réel sans données vides

---

## Phase 8 — Streaming temps réel (Semaines 8–10, optionnelle)

**Objectif :** Ingestion de données IoT/GPS en temps réel, alertes géospatiales < 500ms.
**Prérequis :** Phases 1–5 opérationnelles. Déclencher si le cas d'usage le justifie.

### Composants

| Composant | Image | Rôle |
|---|---|---|
| Mosquitto 2.x | `eclipse-mosquitto:2` | Broker MQTT (IoT/GPS) |
| Apache Kafka 3.6 | `confluentinc/cp-kafka:7.6.0` | Bus de messages |
| Apache Flink 1.18 | `flink:1.18-scala_2.12` | Traitement flux + géofencing |
| TimescaleDB | `timescale/timescaledb-ha:pg16` | Séries temporelles géo |
| Grafana Live | intégré Grafana 10 | Streaming WebSocket vers dashboard |

### Fichiers à créer

```
streaming/
├── docker-compose.streaming.yml  À créer — services streaming en overlay
├── kafka/
│   └── topics.sh                 À créer — création topics au démarrage
├── flink/
│   ├── jobs/
│   │   ├── GeoFencingJob.java    À créer — alertes géofencing Flink
│   │   └── TrackAggregator.java  À créer — agrégation tracks GPS
│   └── pom.xml                   À créer — dépendances Maven
├── mosquitto/
│   └── mosquitto.conf            À créer — config broker MQTT
└── simulators/
    └── gps-simulator.py          À créer — simulateur véhicules GPS (test)
```

### Tâches détaillées

1. **Infrastructure messaging**
   - Créer `streaming/docker-compose.streaming.yml` : Zookeeper + Kafka + Mosquitto
   - Créer `streaming/kafka/topics.sh` : créer topics `gps-positions`, `geo-alerts`, `sensor-data`
   - Créer `streaming/mosquitto/mosquitto.conf` : listener 1883 (interne) + 8883 (TLS externe)
   - Configurer Kafka Connect sink vers PostGIS/TimescaleDB

2. **TimescaleDB — séries temporelles**
   - Créer hypertable `positions` (device_id, timestamp, lat, lon, vitesse, geom)
   - `SELECT create_hypertable('positions', 'timestamp', chunk_time_interval => INTERVAL '1 day')`
   - Activer compression automatique après 7 jours
   - Créer continuous aggregate : position moyenne par heure et par zone

3. **Flink — géofencing**
   - Créer `GeoFencingJob.java` :
     - Source Kafka `gps-positions`
     - Charger les géofences depuis PostGIS au démarrage
     - Alerte si véhicule entre/sort d'une géofence (latence < 200ms)
     - Sink alertes vers topic Kafka `geo-alerts` → PostGIS
   - Créer `TrackAggregator.java` : fenêtre tumbling 1 min → track simplifié en PostGIS

4. **Simulateur de test**
   - Créer `streaming/simulators/gps-simulator.py` : simuler 100 véhicules GPS publiant via MQTT toutes les 5s
   - Vérifier visibilité en temps réel dans Grafana Geomap panel (refresh < 1s)

5. **Front-end temps réel**
   - Ajouter dans `web-app/src/` : source MapLibre rafraîchie toutes les 5s via `fetch('/api/positions/live')`
   - Ou WebSocket depuis Grafana Live si usage monitoring uniquement

### Critères d'acceptation

- [ ] 100 véhicules simulés publient via MQTT → visibles dans Kafka en < 1s
- [ ] Alerte géofencing déclenchée en < 500ms après franchissement de limite
- [ ] Dashboard Grafana affiche positions temps réel avec refresh < 2s
- [ ] TimescaleDB compresse les données après 7 jours (-80% espace)
- [ ] 10 000 événements/s ingérés sans perte ni lag Kafka > 1s

---

## Récapitulatif des livrables par phase

| Phase | Durée | Livrable principal | Dépendances |
|---|---|---|---|
| 1 — Socle données | 1 semaine | Carte MapLibre + tuiles PostGIS | Aucune |
| 2 — Services OGC | 1 semaine | WMS/WFS/OGC API Features | Phase 1 |
| 3 — Portail & BI | 1 semaine | GeoNode + Superset dashboards | Phase 2 |
| 4 — Sécurité | 1 semaine | SSO Keycloak + HTTPS Traefik | Phase 3 |
| 5 — Performance | 1 semaine | 500 VUs sans dégradation | Phase 4 |
| 6 — ETL Airflow | 1 semaine | Pipelines import automatisés | Phase 1 |
| 7 — Monitoring | 1 semaine | Dashboards Grafana + alertes | Phase 5 |
| 8 — Streaming | 2–3 semaines | IoT temps réel < 500ms | Phase 5, 7 |

**MVP production (phases 1–5) : 5 semaines**
**Stack complète (phases 1–7) : 7 semaines**
**Stack complète + streaming (phases 1–8) : 9–10 semaines**

---

## Infrastructure recommandée

### Développement / staging (Docker Compose)

| Ressource | Minimum | Recommandé |
|---|---|---|
| vCPU | 8 | 16 |
| RAM | 16 Go | 32 Go |
| SSD | 100 Go | 500 Go |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

### Production (Kubernetes ou Docker Compose multi-nœuds)

```
Nœud 1 — Applications  : 16 vCPU / 32 Go RAM / 200 Go SSD
Nœud 2 — Base de données: 16 vCPU / 64 Go RAM / 2 To NVMe
Nœud 3 — Cache/Infra   :  8 vCPU / 16 Go RAM / 500 Go SSD
```

---

## Ordre de démarrage recommandé

```bash
# Phase 1
docker compose up -d postgis redis && sleep 15
docker compose up -d pgbouncer
docker compose exec -T postgis psql -U gis -d gis < sql/init.sql
docker compose up -d martin web

# Phase 2 (ajouter dans docker-compose.yml)
docker compose up -d minio titiler pg-featureserv geoserver

# Phase 3
docker compose up -d superset superset-worker geonode

# Phase 4
docker compose up -d keycloak
docker compose up -d traefik   # en dernier — expose tout sur HTTPS

# Phase 7 (après phase 5)
docker compose up -d prometheus grafana loki promtail postgres-exporter
```
