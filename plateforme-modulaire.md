# OGE — Open Geospatial Enterprise
## Étude maître : plateforme SIG open-source modulaire (corps central + modules) pour égaler et dépasser ArcGIS Enterprise

> **Document maître consolidé.** Il s'appuie sur les 4 études du dépôt
> ([`synthese.md`](./synthese.md), [`stacks-comparatif.md`](./stacks-comparatif.md),
> [`stacks-production.md`](./stacks-production.md),
> [`stack3-modern-web-gis.md`](./stack3-modern-web-gis.md)) et les dépasse : on passe d'un
> **catalogue de stacks** (assemblages de briques) à la **conception d'UN produit** — une plateforme
> unifiée à **noyau central** (`GeoCore`) + **modules enfichables** installables/connectables selon les besoins.
>
> *Codename de travail : noyau **GeoCore**, plateforme **OGE — Open Geospatial Enterprise**. À renommer librement.*
> *Cible de parité : ArcGIS Enterprise 11.4 (état 2025). Recherche web : juin 2026.*

---

## Table des matières

1. [Résumé exécutif](#1-résumé-exécutif)
2. [La cible à dépasser : ArcGIS Enterprise 11.4](#2-la-cible-à-dépasser--arcgis-enterprise-114)
3. [Principe directeur : corps central + modules](#3-principe-directeur--corps-central--modules)
4. [Architecture du noyau (GeoCore) et contrats d'API](#4-architecture-du-noyau-geocore-et-contrats-dapi)
5. [Catalogue des modules enfichables](#5-catalogue-des-modules-enfichables)
6. [Matrice de parité ArcGIS Enterprise 11.4 ↔ OGE](#6-matrice-de-parité-arcgis-enterprise-114--oge)
7. [Performance & cloud-native geospatial](#7-performance--cloud-native-geospatial)
8. [Modèle de déploiement](#8-modèle-de-déploiement)
9. [Gouvernance, licences & roadmap projet](#9-gouvernance-licences--roadmap-projet)
10. [Trajectoire d'adoption & annexes](#10-trajectoire-dadoption--annexes)

---

## 1. Résumé exécutif

### 1.1 Vision

**OGE** est une plateforme SIG d'entreprise **open-source, modulaire et cloud-native**. Là où ArcGIS
Enterprise est un produit intégré mais propriétaire, fermé et facturé 100 k–500 k €/an, OGE propose la
**même offre fonctionnelle** (publication de services, portail, dashboards, analytique, temps réel,
imagerie, 3D, graphes de connaissances) avec :

- **0 € de licence** logicielle (coût = infrastructure + expertise) ;
- des **performances structurellement supérieures** sur le web (tuiles vectorielles 10–60× plus rapides,
  rendu WebGL natif, formats cloud-native) ;
- une **modularité réelle** : on installe le noyau, puis **uniquement les modules dont on a besoin**,
  chacun déployable et scalable indépendamment ;
- **zéro vendor lock-in** : données dans des formats ouverts (PostGIS, GeoParquet, COG, PMTiles),
  API 100 % standards **OGC**.

### 1.2 Pourquoi pas « juste une stack » ?

Les 4 documents existants démontrent qu'on **peut** reproduire ArcGIS avec des briques FOSS4G. Mais un
assemblage de briques n'est pas un produit : il manque le **liant** qui fait la valeur d'ArcGIS
Enterprise — **identité unique (SSO), autorisations cohérentes, catalogue central, administration
unifiée, expérience d'installation/mise à jour**. OGE apporte ce liant sous la forme d'un **noyau fin**
(`GeoCore`) qui standardise les contrats d'intégration, de sorte que chaque brique devient un **module
interchangeable** plutôt qu'un silo à intégrer manuellement.

Le précédent existe et valide l'approche : **geOrchestra** (SDI modulaire INSPIRE, release 25 en
sept. 2025) et **GeoNode** font déjà cela à plus petite échelle. OGE généralise le modèle avec une
architecture cible plus moderne (microservices, cloud-native geospatial, observabilité native).

### 1.3 Chiffres clés

| Indicateur | ArcGIS Enterprise | OGE |
|---|---|---|
| Licence logicielle / an | 100 k–500 k € | **0 €** |
| Latence tuile vecteur P95 | 150–850 ms (Feature Service) | **3–12 ms** (Martin/PostGIS) |
| Lock-in données | Format propriétaire / SDE | **Nul** (PostGIS, GeoParquet, COG, PMTiles) |
| API | REST Esri + OGC partiel | **OGC API natif** (Features, Tiles, Maps, Records, Coverages) |
| Scalabilité | Par cœur licencié | **Horizontale illimitée** (K8s/HPA) |
| 3D / offline | CityEngine (payant) / limité | **deck.gl + 3D Tiles** / **PMTiles + Service Worker** |
| Économie logicielle estimée | — | **80–95 %** |

---

## 2. La cible à dépasser : ArcGIS Enterprise 11.4

ArcGIS Enterprise (version courante **11.4**, 2025) est un système distribué de plusieurs serveurs et
applications. Inventaire à jour des composants à égaler :

| Composant ArcGIS 11.4 | Rôle | Évolution récente |
|---|---|---|
| **ArcGIS Server** | Serveur SIG de base : services carto, features, géoprocessing | Socle |
| **Portal for ArcGIS** | Portail web, comptes, partage, apps (Dashboards, Experience Builder, Field Maps) | Socle |
| **ArcGIS Data Store** | Stockage (relationnel, tuiles, spatiotemporel, graphe, objet) | Socle |
| **Web Adaptor** | Intégration reverse-proxy IIS/Java | Socle |
| **ArcGIS Notebook Server** | Notebooks (Python) : data science, automatisation, viz | En montée |
| **ArcGIS Knowledge Server** | **Graphes de connaissances** entité-relation, requêtes | **Stratégique 11.x** |
| **ArcGIS Image Server** | Services raster/imagerie, mosaïques, COG, raster analytics | Socle |
| **ArcGIS Mission / Reality** | Opérations terrain ; photogrammétrie/3D reality mapping | Spécialisés |
| **ArcGIS GeoAnalytics Server** | Analyse spatiale distribuée (gros volumes) | **⚠️ RETIRÉ à la 11.4** → reporté sur *GeoAnalytics Engine* (bibliothèque Spark) |
| **ArcGIS Pro** | Client desktop d'analyse et de publication | Client lourd |
| **Apps** : Dashboards, Experience Builder, StoryMaps, Field Maps, Insights | Visualisation, applis no-code, BI, terrain | Couche applicative |

**À noter pour la stratégie de parité :** le retrait de GeoAnalytics *Server* confirme la bascule de
l'industrie (Esri compris) vers des moteurs analytiques **type Spark/bibliothèque** — exactement le
terrain de **Apache Sedona / SedonaDB / DuckDB**, où l'open-source est aujourd'hui **en avance**.

**Coût indicatif** : ArcGIS Enterprise se facture par niveau + extensions (Image, Knowledge, Notebook,
Indoors…), typiquement **100 k–500 k €/an** pour un déploiement d'organisation, hors infrastructure.

---

## 3. Principe directeur : corps central + modules

### 3.1 Pourquoi le modèle modulaire (vs monolithe)

| Critère | Monolithe (assemblage figé) | OGE : noyau + modules |
|---|---|---|
| Installation | Tout ou rien | Noyau + **seulement les modules utiles** |
| Montée en charge | Verticale globale | **Horizontale, par module** (le tuilage scale sans scaler le portail) |
| Évolution | Couplage fort, régressions | Modules **versionnés indépendamment** derrière un contrat stable |
| Coût d'exploitation | Surdimensionnement | **Empreinte minimale** par besoin réel |
| Remplaçabilité | Lock-in technique interne | Brique remplaçable (ex. Martin ↔ pg_tileserv) si elle respecte le contrat |

### 3.2 Précédents qui valident l'approche

- **geOrchestra (release 25, sept. 2025)** — SDI modulaire née en 2009 pour INSPIRE. **Noyau =
  sécurité/SSO** (proxy d'authentification, CAS/Keycloak) + **GeoFence** (autorisations fines, y compris
  spatiales) ; **modules** = GeoServer (et **GeoServer Cloud**), GeoNetwork (catalogue, microservices),
  GeoWebCache, visualiseur. Déploiement **Ansible ou Kubernetes**. C'est le modèle de référence direct d'OGE.
- **GeoNode 4.x** — CMS géospatial (Django + GeoServer + PostGIS + MapStore) : catalogue, comptes,
  styles, partage. Démontre le « portail intégré » open-source.
- **GeoServer Cloud** — GeoServer **éclaté en microservices** (chaque service OGC = un service
  déployable/scalable). Brique-clé pour la modularité d'OGE.

### 3.3 Règles de modularité (contrat d'architecture)

Un **module OGE** respecte 5 règles :

1. **Une responsabilité** claire (ex. « servir des tuiles vectorielles », « exécuter de l'analyse distribuée »).
2. **Une interface explicite** : expose des **API OGC standard** et/ou s'enregistre via le SDK de module.
3. **Sans état partagé caché** : l'état va dans les services socles du noyau (DB, object store, bus).
4. **Déployable et scalable indépendamment** (conteneur, chart Helm).
5. **Auth/policy déléguées au noyau** : aucun module ne réimplémente l'identité ou les autorisations.

> Test de validation d'un module : *« Peut-on comprendre ce qu'il fait, l'utiliser et le remplacer sans
> lire son code interne ni toucher aux autres modules ? »* Si non, la frontière est mal placée.

---

## 4. Architecture du noyau (GeoCore) et contrats d'API

Le **noyau est volontairement fin** : il ne fait pas de SIG, il fournit les **services socles** et les
**contrats** qui permettent aux modules de coopérer.

```
                          UTILISATEURS / SYSTÈMES TIERS
                       (Web · Mobile · Desktop QGIS · API)
                                     │
                          ┌──────────▼──────────┐
                          │   API GATEWAY        │  routage, quotas,
                          │   (Traefik / Kong)   │  rate-limit, TLS
                          └──────────┬──────────┘
       ┌───────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐          ┌──────────────────┐          ┌──────────────┐
│ IDENTITY/SSO │          │  MODULE REGISTRY │          │  CATALOGUE   │
│  Keycloak    │◄────────►│  + service mesh  │◄────────►│ GeoNetwork / │
│  OIDC/OAuth2 │          │  (découverte)    │          │ pycsw · STAC │
└──────┬───────┘          └────────┬─────────┘          └──────┬───────┘
       │                           │                            │
       ▼                           ▼                            ▼
┌──────────────┐          ┌──────────────────┐          ┌──────────────┐
│ POLICY ENGINE│          │  EVENT BUS        │          │ OBSERVABILITÉ│
│ GeoFence/OPA │          │  Kafka / NATS     │          │ OTel·Prom·   │
│ (autz spat.) │          │  (événements)     │          │ Grafana·Loki │
└──────┬───────┘          └────────┬─────────┘          └──────────────┘
       │                           │
       └─────────────┬─────────────┘
                     ▼
       ┌──────────────────────────────────┐
       │   DATA ABSTRACTION LAYER          │
       │   PostgreSQL 17 + PostGIS 3.5     │  ← données vectorielles authoritatives
       │   Object Store S3 (MinIO/Ceph)    │  ← COG · GeoParquet · PMTiles · MBTiles
       │   PgBouncer (pooling)             │
       └──────────────────────────────────┘
                     ▲
       ┌─────────────┴──────────────┐
       │  ADMIN CONSOLE + SDK/CLI    │  installation, config, santé des modules
       └────────────────────────────┘
```

### 4.1 Services socles du noyau

| Service socle | Rôle | Brique de référence | Remplaçables par |
|---|---|---|---|
| **Identity & SSO** | Comptes, OIDC/OAuth2, fédération, rôles | **Keycloak** | Authentik, Zitadel |
| **Policy engine (autz spatiale)** | Droits fins, filtres par couche/zone géo | **GeoFence** (style geOrchestra) | OPA + sidecars |
| **API Gateway** | Point d'entrée unique, TLS, quotas, routage | **Traefik** | Kong, Envoy |
| **Module registry / mesh** | Déclaration, découverte, santé des modules | **Consul/K8s API** + SDK OGE | Istio, linkerd |
| **Catalogue & métadonnées** | Recherche, ISO 19115, INSPIRE, STAC | **GeoNetwork** / **pycsw** | — |
| **Data abstraction** | Source de vérité vecteur + object store | **PostGIS** + **MinIO/Ceph** | CloudNativePG, Garage |
| **Event bus** | Événements inter-modules (publication, edits, alertes) | **Kafka** / **NATS** | RabbitMQ |
| **Observabilité** | Métriques, logs, traces, alertes | **OpenTelemetry + Prometheus + Grafana + Loki + Tempo** | — |
| **Admin console + SDK/CLI** | Installer/configurer/superviser les modules | App OGE (à développer) | — |

### 4.2 Contrats d'interface noyau ↔ module

Tout module dialogue avec le noyau via **4 contrats** stables :

| Contrat | Mécanisme | Ce qu'il garantit |
|---|---|---|
| **C1 — Identité** | JWT OIDC émis par Keycloak, validé au gateway et au module | Un seul login ; le module connaît l'utilisateur et ses rôles |
| **C2 — Autorisation** | Décision déléguée au policy engine (appel ou sidecar) ; réponses filtrées par zone/couche | Droits cohérents partout, y compris **filtres spatiaux** |
| **C3 — Données** | Accès via la couche d'abstraction : PostGIS (vecteur), S3 (COG/GeoParquet/PMTiles) | Pas de copie privée ; formats ouverts ; remplaçabilité |
| **C4 — Événements & enregistrement** | Le module **s'enregistre** au registry (capacités, endpoints OGC, santé) et publie/consomme sur le bus | Découverte automatique ; catalogue à jour ; intégration temps réel |

**Manifeste de module (exemple, format déclaratif) :**

```yaml
# module.oge.yaml
module:
  name: vector-tiles
  version: 1.4.0
  provides:
    - ogc-api: tiles            # capacité standard exposée
    - endpoint: /tiles
  requires:
    core: ">=1.0"
    data: [postgis]             # contrat C3
  auth: { contract: C1, roles: [gis-viewer] }   # contrats C1/C2
  events:
    publishes: [tiles.invalidated]
    consumes:  [features.updated]                # contrat C4
  scaling: { kind: hpa, minReplicas: 2, maxReplicas: 10, metric: rps }
```

L'**admin console** lit ce manifeste, provisionne le module (chart Helm / conteneur), l'enregistre au
registry, applique les politiques d'auth et branche l'observabilité — **sans intégration manuelle**.

---

## 5. Catalogue des modules enfichables

Chaque module : **rôle · brique OSS · contrat avec le noyau · équivalent ArcGIS · maturité**.

### 5.1 Modules « publication & diffusion »

| Module | Rôle | Brique OSS | Contrat noyau | Équivalent ArcGIS | Maturité |
|---|---|---|---|---|---|
| **Services OGC** | WMS/WFS/WCS/WMTS/WPS + OGC API | **GeoServer Cloud**, QGIS Server | C1·C2·C3·C4 | ArcGIS Server | ⭐⭐⭐⭐⭐ |
| **Tuiles vecteur** | MVT dynamiques < 5 ms | **Martin** (Rust), pg_tileserv | C2·C3 | Vector Tile / Feature Service | ⭐⭐⭐⭐ |
| **Tuiles statiques** | PMTiles sans serveur (CDN/offline) | **PMTiles** + tippecanoe/planetiler | C3 (S3) | Tile packages | ⭐⭐⭐⭐ |
| **OGC API Features** | API REST features légère | **pg_featureserv** | C1·C2·C3 | Feature Service | ⭐⭐⭐⭐ |
| **Raster / Imagery** | COG dynamiques (NDVI à la volée), STAC | **TiTiler**, **STAC** | C3 (S3) | Image Server | ⭐⭐⭐⭐ |
| **Cache de tuiles** | WMTS/TMS, seeding, invalidation | **GeoWebCache**, MapProxy | C4 (invalidation) | inclus Server | ⭐⭐⭐⭐⭐ |

### 5.2 Modules « applications & visualisation »

| Module | Rôle | Brique OSS | Contrat noyau | Équivalent ArcGIS | Maturité |
|---|---|---|---|---|---|
| **Web App Builder** | Cartes web WebGL, 3D, offline | **MapLibre GL JS v3** + **deck.gl** | C1·C3 | Experience Builder / JS SDK | ⭐⭐⭐⭐ |
| **Portail / catalogue** | Comptes, partage, métadonnées, viewer | **GeoNode**, MapStore2 | C1·C2·C4 | Portal for ArcGIS | ⭐⭐⭐⭐ |
| **Dashboards opérationnels** | KPI, alertes, temps réel | **Grafana** (Geomap) | C1·C3 | ArcGIS Dashboards | ⭐⭐⭐⭐⭐ |
| **BI spatiale** | Exploration, choroplèthes, deck.gl, H3 | **Apache Superset** | C1·C3 | ArcGIS Insights | ⭐⭐⭐⭐ |
| **3D** | Globe/scènes, tilesets 3D | **CesiumJS** + **3D Tiles**, deck.gl | C3 | Scene Viewer / CityEngine | ⭐⭐⭐⭐ |
| **StoryMaps** | Narration cartographique | MapLibre + framework statique (Astro) | C3 | StoryMaps | ⭐⭐⭐ |

### 5.3 Modules « analyse & données »

| Module | Rôle | Brique OSS | Contrat noyau | Équivalent ArcGIS | Maturité |
|---|---|---|---|---|---|
| **Analytique distribuée** | Jointures/agrégations spatiales massives | **Apache Sedona** (vecteur+raster), **Wherobots** | C3·C4 | GeoAnalytics (retiré 11.4) → Engine | ⭐⭐⭐⭐ |
| **Analytique embarquée** | Spatial SQL ultra-rapide ad-hoc | **DuckDB Spatial**, **SedonaDB** (Rust) | C3 (GeoParquet) | Insights / Pro | ⭐⭐⭐⭐ |
| **Notebooks** | Data science Python, automatisation | **JupyterHub** + GeoPandas/Rasterio | C1·C3 | Notebook Server | ⭐⭐⭐⭐⭐ |
| **ETL / Orchestration** | Pipelines, 200+ formats | **GDAL/OGR** + **Apache Airflow** | C3·C4 | Data Interoperability | ⭐⭐⭐⭐⭐ |
| **Knowledge Graph** | Entités-relations, requêtes graphe | **Apache AGE** (PostgreSQL) / Neo4j, pgRouting | C3 | Knowledge Server | ⭐⭐⭐ |
| **Géocodage / Routage** | Adresses ↔ coords, itinéraires, isochrones | **Nominatim**, **Valhalla**, **pgRouting** | C3 | Geocoding / Network Analyst | ⭐⭐⭐⭐ |

### 5.4 Modules « temps réel & terrain »

| Module | Rôle | Brique OSS | Contrat noyau | Équivalent ArcGIS | Maturité |
|---|---|---|---|---|---|
| **Streaming géospatial** | Ingestion/CEP, géofencing < 50 ms | **Mosquitto** + **Kafka** + **Flink** | C4 | GeoEvent Server | ⭐⭐⭐⭐ |
| **Séries temporelles** | Tracking, IoT | **TimescaleDB** | C3 | spatiotemporal Data Store | ⭐⭐⭐⭐ |
| **Terrain / mobile** | Collecte offline, formulaires | **QField**, **Mergin Maps**, **ODK** | C1·C3·C4 | Field Maps / Survey123 | ⭐⭐⭐⭐ |
| **Photogrammétrie / Reality** | 3D depuis images/LiDAR | **OpenDroneMap**, **Entwine/PDAL** | C3 | ArcGIS Reality | ⭐⭐⭐ |

> **Lecture clé :** sur l'**analytique** (Sedona/SedonaDB/DuckDB + GeoParquet/H3) et le **web/3D**
> (MapLibre/deck.gl/PMTiles), l'open-source **dépasse** ArcGIS. Les écarts honnêtes subsistent sur la
> maturité « clé-en-main » du portail, des StoryMaps et du knowledge graph (voir §6).

---

## 6. Matrice de parité ArcGIS Enterprise 11.4 ↔ OGE

| Capacité ArcGIS 11.4 | Module OGE | Maturité | Écart honnête / Dépassement |
|---|---|---|---|
| Enterprise Geodatabase | PostGIS 3.5 (PostgreSQL 17) | ⭐⭐⭐⭐⭐ | **=** Standard, sans lock-in |
| ArcGIS Server (WMS/WFS/WPS) | GeoServer Cloud / QGIS Server | ⭐⭐⭐⭐⭐ | **=** OGC API natif |
| Feature/Vector Tile Service | Martin / pg_tileserv / PMTiles | ⭐⭐⭐⭐ | **▲ Dépasse** (10–60× latence) |
| Image Server | TiTiler + COG + STAC | ⭐⭐⭐⭐ | **▲** NDVI à la volée gratuit ; ▼ mosaïques avancées clé-en-main |
| Portal for ArcGIS | GeoNode / MapStore2 | ⭐⭐⭐⭐ | ▼ UX clé-en-main < Portal ; **=** catalogue INSPIRE ▲ |
| Dashboards | Grafana | ⭐⭐⭐⭐⭐ | **=/▲** alerting, temps réel |
| Experience Builder | MapLibre + deck.gl (code) ou MapStore | ⭐⭐⭐⭐ | ▼ no-code < ExB ; **▲** perf/3D/offline |
| Insights | Superset + DuckDB | ⭐⭐⭐⭐ | **=** ; ▲ H3, SQL ouvert |
| GeoAnalytics Server (**retiré 11.4**) | Apache Sedona / SedonaDB / Wherobots | ⭐⭐⭐⭐ | **▲ Dépasse** (scale + raster + Rust) |
| Notebook Server | JupyterHub | ⭐⭐⭐⭐⭐ | **=/▲** écosystème PyData complet |
| Knowledge Server (graphes) | Apache AGE / Neo4j + pgRouting | ⭐⭐⭐ | ▼ intégration carto graphe moins mûre |
| GeoEvent Server | Kafka + Flink + Mosquitto | ⭐⭐⭐⭐ | **=/▲** débit ; ▼ complexité ops |
| StoryMaps | MapLibre + Astro/Observable | ⭐⭐⭐ | ▼ authoring no-code |
| Field Maps / Survey123 | QField / Mergin / ODK | ⭐⭐⭐⭐ | **=** ; offline solide |
| Data Interoperability | GDAL/OGR + Airflow | ⭐⭐⭐⭐⭐ | **=/▲** 200+ formats |
| ArcGIS Pro (desktop) | QGIS 3.x LTR | ⭐⭐⭐⭐⭐ | **=** ; ▼ certaines extensions métier |
| Web Adaptor | Traefik / Nginx | ⭐⭐⭐⭐⭐ | **=** |
| Identity / sharing | Keycloak + GeoFence/OPA | ⭐⭐⭐⭐⭐ | **=/▲** SSO standard, autz spatiale |

**Synthèse de parité :** OGE **égale ou dépasse** ArcGIS sur ~15/18 capacités. Les **3 écarts réels**
sont l'**UX no-code** (Portal/Experience Builder/StoryMaps clé-en-main) et la **maturité du knowledge
graph cartographique** — ce sont précisément les axes à prioriser pour le développement propre d'OGE
(admin console, app builder no-code), là où l'assemblage de briques ne suffit pas.

---

## 7. Performance & cloud-native geospatial

### 7.1 Le pari architectural : cloud-native geospatial

OGE adopte les **formats cloud-native** comme colonne vertébrale — accès par *range requests* HTTP, sans
serveur lourd, indexés, parallélisables :

| Format | Usage | Remplace |
|---|---|---|
| **GeoParquet** | Vecteur analytique colonne (jointures massives, échange) | File geodatabase |
| **COG** (Cloud Optimized GeoTIFF) | Raster/imagerie, lecture partielle | Mosaic dataset |
| **PMTiles** | Tuiles vecteur/raster en 1 fichier, CDN/offline | Tile package |
| **STAC** | Catalogue d'assets spatio-temporels | Image catalog |
| **Zarr** | Tableaux N-D (climat, multidim) | netCDF serveur |

> DuckDB + GeoParquet est qualifié par la communauté de *« logiciel géospatial le plus important de la
> décennie »* : il rend l'analyse spatiale instantanée **sans infrastructure**.

### 7.2 Benchmarks — tuiles vectorielles

| Métrique (zoom 10) | Martin (MVT/PostGIS) | ArcGIS Feature Service | Ratio |
|---|---|---|---|
| Latence P50 | 3 ms | 180 ms | **60×** |
| Latence P95 | 12 ms | 850 ms | **70×** |
| Throughput max | 8 000 req/s | 400 req/s | **20×** |
| Taille réponse | 45 KB | 320 KB | **7×** |

### 7.3 Benchmarks — spatial SQL (choix du moteur analytique)

| Moteur | Nature | Force | Quand l'utiliser (module OGE) |
|---|---|---|---|
| **PostGIS** | Relationnel transactionnel | Multi-utilisateur, écriture, le plus mûr | **Source de vérité** (noyau) |
| **DuckDB Spatial** | Embarqué analytique | Zéro infra, vectorisé, GeoParquet | Analytique ad-hoc, conversions |
| **SedonaDB** | Embarqué (Rust/DataFusion) | Fonctions spatiales « blazing fast » | Analytique locale nouvelle génération |
| **Apache Sedona** | Distribué (Spark) | **Vecteur + raster**, multi-To | Jointures continent-scale |
| **Wherobots** | Distribué managé (Lakehouse) | **20–60×** vs Spark standard | Ingénierie spatiale massive |

**Règle de décision OGE :** transactionnel → PostGIS ; analytique laptop/serveur → DuckDB/SedonaDB ;
massif → Sedona/Wherobots. Les résultats persistent en **GeoParquet** (échange) et/ou **PostGIS** (service).

### 7.4 Optimisations transverses

- **Simplification géométrique par zoom** (vues matérialisées `ST_Simplify` + `ST_AsMVT`) ;
- **PgBouncer** (pooling : 1000 → 50 connexions) ; index **GIST/BRIN** ; `CLUSTER` spatial ;
- **Cache Redis** des tuiles chaudes + **GeoWebCache/MapProxy** ;
- **MapLibre GL JS v3** : WebGL2, terrain 3D et hillshade GPU, rendu vectoriel côté client ;
- **deck.gl interleaved** : couches WebGL massives intercalées avec MapLibre (3D, arcs, hexbins).

---

## 8. Modèle de déploiement

OGE se décline en **profils**, du plus simple au plus scalable. Le **même noyau**, on **ajoute des
modules**.

### 8.1 Profil « Single-node » (MVP / évaluation)

```
Docker Compose : Traefik · Keycloak · PostGIS · MinIO · Redis
  + modules choisis (GeoServer Cloud, Martin, TiTiler, GeoNode, Grafana)
```
- Cible : collectivité, évaluation, dev. **1–2 serveurs**. Déploiement **< 1 jour**.

### 8.2 Profil « Cloud-native » (production scalable)

```
Kubernetes :
  - Ingress Traefik · Keycloak (HA) · GeoFence/OPA
  - CloudNativePG (PostGIS HA) · MinIO distribué · Redis Sentinel · Kafka
  - Modules en Deployments + HPA (GeoServer Cloud ×N, Martin ×N, TiTiler ×N)
  - Observabilité : Prometheus + Grafana + Loki + Tempo + AlertManager
  - GitOps : ArgoCD + Helm charts (un chart par module)
```
- Cible : grande organisation, SLA 99.9 %+. **Auto-scaling**, zéro downtime, multi-tenant.

### 8.3 Matrice profils × modules

| Module | Single-node | Cloud-native |
|---|---|---|
| Noyau (Keycloak, PostGIS, MinIO, Gateway) | ✅ | ✅ HA |
| Services OGC / Tuiles / Raster | ✅ | ✅ HPA |
| Portail / Dashboards / BI | ✅ | ✅ |
| Analytique distribuée (Sedona) | ➖ (DuckDB suffit) | ✅ cluster Spark |
| Streaming (Kafka/Flink) | ➖ optionnel | ✅ |
| Knowledge graph / 3D / Reality | optionnel | optionnel |

---

## 9. Gouvernance, licences & roadmap projet

### 9.1 Stratégie de licence (point critique)

- **Noyau OGE (GeoCore + SDK + admin console)** : licence **permissive Apache-2.0** → adoption large,
  contributions d'entreprise, pas d'effet de contamination.
- **Vigilance sur les briques intégrées** (à documenter pour chaque module) :
  - **AGPL-3.0** : MinIO, GeoNode (à isoler comme service réseau, pas à lier) ;
  - **BSL / SSPL** : Elasticsearch (≥ 7.11) → préférer **OpenSearch** si un module search est requis ;
  - permissives/LGPL : PostGIS, GeoServer (GPL côté serveur, usage réseau OK), Martin, MapLibre, deck.gl.
- **Principe** : le noyau ne *lie* jamais une dépendance copyleft ; les briques copyleft sont consommées
  **comme services réseau** via les contrats C1–C4 → conformité préservée.

### 9.2 Organisation des dépôts

| Option | Avantage | Inconvénient | Reco OGE |
|---|---|---|---|
| **Mono-repo** | Refactors atomiques, CI unique | Build lourd, couplage perçu | Noyau + SDK |
| **Multi-repo** (1 module = 1 repo) | Versionnage/contribution indépendants | Coordination | **Modules** |
| **Méta-repo** (charts + manifests) | Vue d'ensemble déploiement | — | **Distributions** |

→ **Hybride recommandé** : mono-repo pour le noyau/SDK, multi-repo pour les modules, méta-repo de
distribution (Helm/Compose) qui épingle des versions compatibles (« OGE 1.0 = noyau 1.0 + modules X.Y »).

### 9.3 Roadmap de versions

| Jalon | Contenu | Critère de sortie |
|---|---|---|
| **MVP (0.1)** | Noyau (Keycloak, PostGIS, Gateway, registry) + modules Services OGC, Tuiles vecteur, Portail, Dashboards. Profil single-node. | Publier une couche PostGIS → service OGC + tuiles + dashboard via SSO unique, en < 1 j. |
| **0.5** | Admin console + SDK de module ; modules Raster, BI, Notebooks, ETL ; policy engine spatial (GeoFence/OPA). | Installer/désinstaller un module depuis la console ; autz spatiale effective. |
| **1.0** | Profil cloud-native (Helm/HPA/ArgoCD), observabilité complète, catalogue STAC, géocodage/routage. | SLA 99.9 % en charge ; matrice de parité ≥ 15/18. |
| **1.x enterprise** | Streaming, analytique distribuée (Sedona), 3D/Reality, **app builder no-code**, knowledge graph carto. | Combler les 3 écarts du §6. |

### 9.4 Risques & dépendances

| Risque | Impact | Mitigation |
|---|---|---|
| UX no-code en retard (Portal/ExB) | Adoption métier freinée | Prioriser admin console + app builder dès 0.5/1.x |
| Complexité opérationnelle (K8s, Kafka) | Coût DevOps | Profil single-node par défaut ; modules optionnels |
| Pièges de licence (AGPL/BSL) | Conformité | Consommation réseau via contrats ; OpenSearch vs Elastic |
| Dispersion des briques | Dette d'intégration | Contrats C1–C4 stricts + tests de conformité de module |
| Knowledge graph immature | Écart vs Esri | Apache AGE + investissement ciblé |

---

## 10. Trajectoire d'adoption & annexes

### 10.1 Trajectoire recommandée

```
Semaine 1      →  Noyau + Services OGC + Tuiles + Portail + Dashboards (single-node)
Mois 1–2       →  + BI (Superset/DuckDB) + Notebooks + ETL (Airflow)
Mois 2–4       →  Modernisation web (MapLibre/deck.gl/PMTiles) + Raster (TiTiler/STAC)
Mois 4–8       →  Passage cloud-native K8s (Helm/HPA/ArgoCD) + observabilité
Sur besoin     →  Streaming (Kafka/Flink) · Analytique distribuée (Sedona) · 3D/Reality · Knowledge graph
```

### 10.2 Ce qu'OGE fait mieux qu'ArcGIS Enterprise

1. **Performance web** : tuiles MVT 10–60× plus rapides, WebGL natif, formats cloud-native.
2. **Coût** : 0 € de licence (économie 80–95 %).
3. **Souveraineté** : données en formats ouverts, aucune dépendance cloud Esri, conformité INSPIRE/RGPD.
4. **Modularité** : on n'installe et ne scale que ce dont on a besoin.
5. **Analytique** : DuckDB/SedonaDB/Sedona + GeoParquet/H3 — domaine où l'open-source mène, ArcGIS s'y replie.
6. **Standards** : OGC API de bout en bout, interopérabilité maximale.

### 10.3 Ce qui reste à construire (honnêteté projet)

- **Admin console + SDK de module** (le « liant » qui n'existe pas dans un simple assemblage) ;
- **App builder no-code** (parité Experience Builder / StoryMaps) ;
- **Intégration knowledge graph ↔ carto**.

Ces trois chantiers sont la **valeur ajoutée propre d'OGE** par-dessus l'écosystème FOSS4G existant.

### 10.4 Annexes — documents sources du dépôt

- [`synthese.md`](./synthese.md) — correspondance composant par composant ArcGIS ↔ FOSS4G.
- [`stacks-comparatif.md`](./stacks-comparatif.md) — 8 stacks autonomes et tableau de décision.
- [`stacks-production.md`](./stacks-production.md) — 5 stacks de production opinionées.
- [`stack3-modern-web-gis.md`](./stack3-modern-web-gis.md) — guide complet « Modern Web GIS ».

### 10.5 Références web (recherche juin 2026)

- ArcGIS Enterprise 11.4 — *What's new* : https://enterprise.arcgis.com/en/get-started/11.4/windows/what-s-new-in-arcgis-enterprise.htm
- geOrchestra — software & release 25 : https://www.georchestra.org/software.html · https://www.georchestra.org/blog/2025/09/06/georchestra-25-release-en/
- GeoServer Cloud : https://github.com/geoserver/geoserver-cloud
- Spatial SQL Landscape 2026 (M. Forrest) : https://forrest.nyc/best-spatial-sql-tools/
- SedonaDB vs DuckDB vs PostGIS (M. Forrest) : https://forrest.nyc/sedonadb-vs-duckdb-vs-postgis-which-spatial-sql-engine-is-fastest/
- MapLibre GL JS : https://maplibre.org/projects/gl-js/ · deck.gl + MapLibre : https://deck.gl/docs/developer-guide/base-maps/using-with-maplibre
- DuckDB geospatial / GeoParquet : https://medium.com/radiant-earth-insights/performance-explorations-of-geoparquet-and-duckdb-84c0185ed399
- Geoportal alternatives to Esri : https://geomatics-expert.com/articles/geoportal-alternatives-to-esri/

---

> **Conclusion.** Reproduire ArcGIS Enterprise avec des briques FOSS4G est résolu (cf. les 4 études
> annexes). La proposition d'OGE est d'aller plus loin : transformer cet écosystème en **un produit** —
> noyau fin + modules enfichables, contrats d'intégration stricts, cloud-native — qui **égale ArcGIS sur
> ~15/18 capacités, le dépasse sur la performance, le coût et l'analytique**, et concentre l'effort de
> développement propre sur les 3 seuls écarts réels : l'UX no-code et le knowledge graph cartographique.
