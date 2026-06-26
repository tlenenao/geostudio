# Stack 3 — Modern Web GIS : Guide Complet Production

> Remplace et dépasse ArcGIS Experience Builder + ArcGIS Dashboards + ArcGIS StoryMaps
> Rendu WebGL natif, tuiles vectorielles MVT, 3D, mobile-first, offline-capable.

---

## 1. Architecture complète

```
                        UTILISATEURS
                   Browser / Mobile / Desktop
                            │
                     ┌──────▼──────┐
                     │   Traefik   │  SSL/TLS, rate limit,
                     │  (Ingress)  │  gzip, headers sécurité
                     └──────┬──────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌────────────┐      ┌───────────┐
  │  App Web  │      │  Superset  │      │  GeoNode  │
  │ MapLibre  │      │  BI Spatiale│     │  Portail  │
  │  Deck.gl  │      │  Deck.gl   │      │ Catalogue │
  └─────┬─────┘      └──────┬─────┘      └─────┬─────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌────────────┐      ┌───────────┐
  │  Martin   │      │  TiTiler   │      │pg_feature │
  │ MVT Rust  │      │COG Raster  │      │  serv     │
  │  < 3ms   │      │  dynamique │      │OGC API    │
  └─────┬─────┘      └──────┬─────┘      └─────┬─────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
             ┌──────────────────────────────┐
             │    PostgreSQL 16 + PostGIS   │
             │    PgBouncer (100→20 conn)   │
             │    Replica lecture           │
             └──────────────┬───────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
       ┌─────────┐    ┌──────────┐    ┌─────────┐
       │  Redis  │    │  MinIO   │    │Keycloak │
       │  cache  │    │ PMTiles  │    │  auth   │
       │  tiles  │    │  COG     │    │  OIDC   │
       └─────────┘    └──────────┘    └─────────┘
```

---

## 2. Composants & versions

| Composant | Version | Image Docker | Port |
|---|---|---|---|
| Traefik | 3.0 | `traefik:v3.0` | 80/443 |
| Martin | 0.13 | `ghcr.io/maplibre/martin` | 3000 |
| TiTiler | 0.18 | `developmentseed/titiler` | 8000 |
| pg_featureserv | 1.3 | `pramsey/pg_featureserv` | 9000 |
| Apache Superset | 3.1 | `apache/superset` | 8088 |
| GeoNode | 4.2 | `geonode/geonode` | 8080 |
| PostgreSQL | 16 | `postgis/postgis:16-3.4` | 5432 |
| PgBouncer | 1.22 | `edoburu/pgbouncer` | 6432 |
| Redis | 7.2 | `redis:7.2-alpine` | 6379 |
| MinIO | AGPL | `minio/minio` | 9001 |
| Keycloak | 24 | `quay.io/keycloak/keycloak:24` | 8180 |
| Nginx (front) | 1.25 | `nginx:1.25-alpine` | — |

---

## 3. Docker Compose — déploiement complet

```yaml
# docker-compose.yml
version: '3.9'

networks:
  gis-net:
    driver: bridge

volumes:
  pg-data:
  redis-data:
  minio-data:
  keycloak-data:

services:

  # ─── Base de données ───────────────────────────────────

  postgis:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: gis
      POSTGRES_USER: gis
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - pg-data:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks: [gis-net]
    command: >
      postgres
        -c shared_buffers=4GB
        -c effective_cache_size=12GB
        -c work_mem=64MB
        -c max_connections=200
        -c random_page_cost=1.1
        -c max_parallel_workers_per_gather=4
        -c wal_level=replica

  pgbouncer:
    image: edoburu/pgbouncer:1.22
    environment:
      DB_HOST: postgis
      DB_NAME: gis
      DB_USER: gis
      DB_PASSWORD: ${PG_PASSWORD}
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 1000
      DEFAULT_POOL_SIZE: 50
    depends_on: [postgis]
    networks: [gis-net]

  # ─── Cache ─────────────────────────────────────────────

  redis:
    image: redis:7.2-alpine
    volumes: [redis-data:/data]
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
    networks: [gis-net]

  # ─── Stockage objet ────────────────────────────────────

  minio:
    image: minio/minio
    environment:
      MINIO_ROOT_USER: ${MINIO_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    volumes: [minio-data:/data]
    command: server /data --console-address ":9001"
    networks: [gis-net]

  # ─── Serveurs de tuiles ────────────────────────────────

  martin:
    image: ghcr.io/maplibre/martin:v0.13
    environment:
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    volumes:
      - ./martin-config.yaml:/config.yaml
    command: --config /config.yaml
    networks: [gis-net]
    depends_on: [pgbouncer]

  titiler:
    image: developmentseed/titiler:0.18
    environment:
      CPL_VSIL_CURL_ALLOWED_EXTENSIONS: .tif,.TIF,.tiff
      GDAL_HTTP_MERGE_CONSECUTIVE_RANGES: YES
      GDAL_DISABLE_READDIR_ON_OPEN: EMPTY_DIR
      AWS_ACCESS_KEY_ID: ${MINIO_USER}
      AWS_SECRET_ACCESS_KEY: ${MINIO_PASSWORD}
      AWS_ENDPOINT_URL: http://minio:9000
    networks: [gis-net]

  pg-featureserv:
    image: pramsey/pg_featureserv:latest
    environment:
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    networks: [gis-net]
    depends_on: [pgbouncer]

  # ─── Applications ──────────────────────────────────────

  superset:
    image: apache/superset:3.1.0
    environment:
      SUPERSET_SECRET_KEY: ${SUPERSET_SECRET}
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    networks: [gis-net]
    depends_on: [pgbouncer, redis]

  geonode:
    image: geonode/geonode:4.2
    environment:
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
      DJANGO_SETTINGS_MODULE: geonode.settings
      GEOSERVER_PUBLIC_HOST: geoserver
    networks: [gis-net]

  # ─── Auth ──────────────────────────────────────────────

  keycloak:
    image: quay.io/keycloak/keycloak:24
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: ${KC_PASSWORD}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgis:5432/keycloak
      KC_DB_USERNAME: gis
      KC_DB_PASSWORD: ${PG_PASSWORD}
    command: start-dev
    networks: [gis-net]
    volumes: [keycloak-data:/opt/keycloak/data]

  # ─── Ingress ───────────────────────────────────────────

  traefik:
    image: traefik:v3.0
    command:
      - --api.insecure=false
      - --providers.docker=true
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.letsencrypt.acme.storage=/certs/acme.json
      - --certificatesresolvers.letsencrypt.acme.tlschallenge=true
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./certs:/certs
    networks: [gis-net]
```

---

## 4. Configuration Martin (tuiles vectorielles)

```yaml
# martin-config.yaml
listen_addresses: '0.0.0.0:3000'
keep_alive: 75
worker_processes: 8

cache:
  # Cache Redis pour les tuiles chaudes
  redis:
    url: redis://redis:6379
    ttl: 3600
    max_size: 536870912  # 512 MB

postgres:
  connection_string: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
  pool_size: 20
  default_srid: 4326

# Sources de tuiles depuis PostGIS
tables:
  communes:
    schema: public
    table: communes
    srid: 4326
    geometry_column: geom
    geometry_type: MULTIPOLYGON
    minzoom: 5
    maxzoom: 14
    properties:
      - code_insee
      - nom
      - population
      - surface_ha

  points_interet:
    schema: public
    table: points_interet
    geometry_column: geom
    geometry_type: POINT
    minzoom: 10
    maxzoom: 20
    properties:
      - id
      - categorie
      - nom
      - score

# Sources depuis requêtes SQL personnalisées
functions:
  incidents_heatmap:
    schema: public
    function: get_incidents_tiles
    # Fonction PostGIS qui retourne MVT
```

```sql
-- sql/init.sql
-- Fonction MVT optimisée pour Martin
CREATE OR REPLACE FUNCTION get_incidents_tiles(z INT, x INT, y INT)
RETURNS bytea AS $$
DECLARE
    bounds geometry;
    mvt bytea;
BEGIN
    bounds := ST_TileEnvelope(z, x, y);

    SELECT ST_AsMVT(tile, 'incidents_heatmap', 4096, 'geom')
    INTO mvt
    FROM (
        SELECT
            id,
            categorie,
            severite,
            date_trunc('day', date_incident) AS date_jour,
            ST_AsMVTGeom(
                geom,
                bounds,
                4096,
                256,
                true
            ) AS geom
        FROM incidents
        WHERE geom && bounds
          AND ST_Intersects(geom, bounds)
          AND date_incident > NOW() - INTERVAL '90 days'
    ) tile
    WHERE geom IS NOT NULL;

    RETURN mvt;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- Index spatial GIST
CREATE INDEX CONCURRENTLY idx_incidents_geom
    ON incidents USING GIST(geom);

-- Index composite pour filtres temporels
CREATE INDEX idx_incidents_date_geom
    ON incidents(date_incident, geom)
    WHERE date_incident > NOW() - INTERVAL '1 year';
```

---

## 5. Application Front-End MapLibre GL JS

### 5.1 Structure du projet

```
web-app/
├── index.html
├── src/
│   ├── map.js          # Carte principale MapLibre
│   ├── layers.js       # Définition des couches
│   ├── controls.js     # Contrôles custom
│   ├── offline.js      # Service Worker + PMTiles
│   └── dashboard.js    # Intégration Deck.gl
├── styles/
│   └── style.json      # Style MapLibre (fond de carte)
└── sw.js               # Service Worker offline
```

### 5.2 Carte MapLibre avec couches PostGIS

```javascript
// src/map.js
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import * as deck from '@deck.gl/core';
import { MapboxOverlay } from '@deck.gl/mapbox';

// Enregistrer le protocole PMTiles (tuiles offline)
const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

const map = new maplibregl.Map({
  container: 'map',
  style: '/styles/style.json',
  center: [2.3522, 48.8566],
  zoom: 10,
  maxZoom: 20,
  antialias: true,          // WebGL anti-aliasing
  hash: true,               // URL reflète la vue
  transformRequest: (url) => {
    // Injection token Keycloak sur toutes les requêtes
    if (url.startsWith('https://api.')) {
      return {
        url,
        headers: { Authorization: `Bearer ${getToken()}` }
      };
    }
  }
});

map.on('load', () => {
  addVectorLayers();
  addDeckGlLayers();
  setupInteractions();
});

function addVectorLayers() {

  // ── Source Martin (MVT dynamique depuis PostGIS) ────────
  map.addSource('communes-src', {
    type: 'vector',
    tiles: ['https://api.example.com/martin/communes/{z}/{x}/{y}'],
    minzoom: 5,
    maxzoom: 14,
    promoteId: 'code_insee',
  });

  // Remplissage choroplèthe
  map.addLayer({
    id: 'communes-fill',
    type: 'fill',
    source: 'communes-src',
    'source-layer': 'communes',
    paint: {
      'fill-color': [
        'interpolate', ['linear'],
        ['get', 'population'],
        0,       '#f7fcf0',
        10000,   '#ccebc5',
        50000,   '#7bccc4',
        200000,  '#2b8cbe',
        1000000, '#084081'
      ],
      'fill-opacity': 0.75,
    }
  });

  // Contours
  map.addLayer({
    id: 'communes-line',
    type: 'line',
    source: 'communes-src',
    'source-layer': 'communes',
    paint: {
      'line-color': '#ffffff',
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.5, 14, 1.5],
    }
  });

  // ── Source PMTiles (offline, CDN MinIO) ─────────────────
  map.addSource('poi-offline-src', {
    type: 'vector',
    url: 'pmtiles://https://minio.example.com/tiles/poi.pmtiles',
  });

  map.addLayer({
    id: 'poi-circles',
    type: 'circle',
    source: 'poi-offline-src',
    'source-layer': 'points_interet',
    minzoom: 12,
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 4, 20, 14],
      'circle-color': [
        'match', ['get', 'categorie'],
        'santé',       '#e74c3c',
        'éducation',   '#3498db',
        'commerce',    '#f39c12',
        /* default */ '#95a5a6'
      ],
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
    }
  });

  // ── Source TiTiler (raster COG depuis MinIO) ─────────────
  map.addSource('ortho-src', {
    type: 'raster',
    tiles: [
      'https://api.example.com/titiler/cog/tiles/{z}/{x}/{y}.png' +
      '?url=s3://tiles/ortho_2024.tif&bidx=1,2,3&rescale=0,255'
    ],
    tileSize: 256,
  });

  map.addLayer({
    id: 'ortho-raster',
    type: 'raster',
    source: 'ortho-src',
    minzoom: 13,
    paint: { 'raster-opacity': 0.85 }
  });
}
```

### 5.3 Deck.gl — visualisations 3D avancées

```javascript
// src/dashboard.js
import { HexagonLayer, HeatmapLayer, ArcLayer, TripsLayer } from '@deck.gl/aggregation-layers';
import { ScatterplotLayer, GeoJsonLayer, ColumnLayer } from '@deck.gl/layers';
import { MapboxOverlay } from '@deck.gl/mapbox';

function addDeckGlLayers() {

  const overlay = new MapboxOverlay({
    interleaved: true,  // Layers entre les couches MapLibre
    layers: getDeckLayers()
  });

  map.addControl(overlay);
  window._deckOverlay = overlay;
}

function getDeckLayers() {
  return [

    // Hexbin densité incidents
    new HexagonLayer({
      id: 'incidents-hexbin',
      data: '/api/incidents/geojson?days=30',
      getPosition: d => d.geometry.coordinates,
      getWeight: d => d.properties.severite,
      radius: 500,
      elevationScale: 20,
      extruded: true,
      pickable: true,
      colorRange: [
        [255, 255, 204], [161, 218, 180], [65, 182, 196],
        [44, 127, 184],  [37, 52, 148]
      ],
      onHover: ({ object, x, y }) => {
        if (object) showTooltip(x, y, `${object.points.length} incidents`);
      }
    }),

    // Arcs de flux (origine → destination)
    new ArcLayer({
      id: 'flux-arcs',
      data: '/api/flux/od?type=domicile_travail',
      getSourcePosition: d => d.properties.origine_coords,
      getTargetPosition: d => d.properties.dest_coords,
      getSourceColor: [0, 128, 200, 100],
      getTargetColor: [200, 0, 80, 100],
      getWidth: d => Math.sqrt(d.properties.volume) / 5,
      pickable: true,
    }),

    // Colonnes 3D par commune
    new ColumnLayer({
      id: 'population-3d',
      data: '/api/communes/centroids',
      getPosition: d => d.centroid,
      getElevation: d => d.population / 10,
      getColor: d => populationColor(d.population),
      radius: 300,
      extruded: true,
      pickable: true,
    }),

  ];
}

// Mise à jour temps réel des layers Deck.gl
function refreshDeckLayers() {
  window._deckOverlay.setProps({ layers: getDeckLayers() });
}
setInterval(refreshDeckLayers, 30000);
```

### 5.4 Style MapLibre — fond de carte OpenMapTiles

```json
// styles/style.json
{
  "version": 8,
  "name": "Modern GIS Style",
  "glyphs": "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  "sprite": "https://openmaptiles.github.io/osm-bright-gl-style/sprite",
  "sources": {
    "openmaptiles": {
      "type": "vector",
      "url": "pmtiles://https://minio.example.com/tiles/france-2024.pmtiles"
    }
  },
  "layers": [
    { "id": "background", "type": "background",
      "paint": { "background-color": "#f8f4f0" }},
    { "id": "water", "type": "fill",
      "source": "openmaptiles", "source-layer": "water",
      "paint": { "fill-color": "#a0c8f0" }},
    { "id": "roads", "type": "line",
      "source": "openmaptiles", "source-layer": "transportation",
      "paint": { "line-color": "#ffffff", "line-width": 1.5 }}
  ]
}
```

---

## 6. TiTiler — Serveur raster dynamique

```python
# titiler-custom/main.py
# Extension TiTiler avec endpoints métier custom

from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from fastapi import FastAPI, Query
from typing import Optional
import numpy as np

app = FastAPI(title="GIS Raster API", version="1.0")

cog = TilerFactory()
app.include_router(cog.router, prefix="/cog", tags=["COG"])

# Endpoint NDVI calculé à la volée
@app.get("/cog/ndvi/{z}/{x}/{y}.png")
async def ndvi_tile(
    z: int, x: int, y: int,
    url: str = Query(..., description="URL COG S3"),
    nir_band: int = Query(4, description="Bande NIR"),
    red_band: int = Query(3, description="Bande Rouge"),
):
    """Génère tuile NDVI colorée dynamiquement."""
    from titiler.core.utils import render_image
    from rio_tiler.io import COGReader

    with COGReader(url) as cog:
        img = cog.tile(x, y, z, indexes=[nir_band, red_band])

    nir = img.data[0].astype(float)
    red = img.data[1].astype(float)
    ndvi = np.where((nir + red) == 0, 0, (nir - red) / (nir + red))

    # Colormap NDVI (rouge → vert)
    colormap = {
        -1.0: (165, 0, 38),
         0.0: (253, 174, 97),
         0.3: (166, 217, 106),
         1.0: (0, 104, 55),
    }
    return render_image(ndvi, colormap=colormap, format="PNG")
```

**Exemple appel depuis MapLibre :**
```javascript
map.addSource('ndvi-src', {
  type: 'raster',
  tiles: [
    'https://api.example.com/cog/ndvi/{z}/{x}/{y}.png' +
    '?url=s3://tiles/sentinel2_2024.tif&nir_band=4&red_band=3'
  ],
  tileSize: 256,
});
```

---

## 7. PMTiles — Tuiles sans serveur (offline/CDN)

### Génération depuis PostGIS

```bash
#!/bin/bash
# scripts/generate-pmtiles.sh

PGCONN="postgresql://gis:${PG_PASSWORD}@localhost:5432/gis"

echo "Export communes → GeoJSON..."
ogr2ogr \
  -f GeoJSON /vsistdout/ \
  "$PGCONN" \
  -sql "SELECT code_insee, nom, population, geom FROM communes" \
  | \

tippecanoe \
  --output=/tmp/communes.pmtiles \
  --layer=communes \
  --minimum-zoom=4 \
  --maximum-zoom=14 \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  --force \
  /dev/stdin

echo "Upload MinIO..."
mc cp /tmp/communes.pmtiles minio/tiles/communes.pmtiles
mc anonymous set download minio/tiles

echo "Done: https://minio.example.com/tiles/communes.pmtiles"
```

### Service Worker — mode offline

```javascript
// sw.js
import { leafletRasterCoords } from 'pmtiles';

const CACHE_NAME = 'gis-tiles-v1';
const PMTILES_CACHE_MB = 500;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Cache des tuiles PMTiles (offline)
  if (url.pathname.includes('.pmtiles')) {
    event.respondWith(
      caches.open(CACHE_NAME).then(cache =>
        cache.match(event.request).then(cached =>
          cached || fetch(event.request).then(response => {
            cache.put(event.request, response.clone());
            return response;
          })
        )
      )
    );
  }
});
```

---

## 8. Apache Superset — BI spatiale avec Deck.gl

### Configuration connexion PostGIS

```python
# superset_config.py
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://gis:${PG_PASSWORD}@pgbouncer:6432/gis"
)

# Activer Deck.gl
MAPBOX_API_KEY = ''  # Pas nécessaire avec MapLibre
VIZ_TYPE_DENYLIST = []

# Datasource PostGIS custom
EXTRA_CATEGORICAL_COLOR_SCHEMES = []
DEFAULT_FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "ALLOW_FULL_CSV_EXPORT": True,
    "DASHBOARD_NATIVE_FILTERS": True,
}
```

### Dashboard Superset — carte choroplèthe Deck.gl

```sql
-- Dataset SQL Superset : densité incidents par commune
SELECT
    c.code_insee,
    c.nom,
    COUNT(i.id)                             AS nb_incidents,
    ROUND(AVG(i.severite)::NUMERIC, 2)     AS severite_moy,
    ST_AsGeoJSON(c.geom)                   AS geojson,
    ST_X(ST_Centroid(c.geom))             AS longitude,
    ST_Y(ST_Centroid(c.geom))             AS latitude
FROM communes c
LEFT JOIN incidents i
    ON ST_Within(i.geom, c.geom)
    AND i.date_incident > NOW() - INTERVAL '{{ filter_values("periode")[0] | default("30") }} days'
GROUP BY c.code_insee, c.nom, c.geom
ORDER BY nb_incidents DESC;
```

**Types de visualisation Deck.gl disponibles dans Superset :**
- `deck_geojson` — polygones colorés (choroplèthe)
- `deck_scatter` — points scalés
- `deck_hex` — hexbins agrégées
- `deck_arc` — arcs flux OD
- `deck_grid` — grille densité
- `deck_path` — tracés linéaires
- `deck_polygon` — extrusion 3D (bâtiments)
- `deck_heatmap` — heatmap continue

---

## 9. OGC API Features — pg_featureserv

```yaml
# pg-featureserv-config.toml
[Server]
HttpPort = 9000
UrlBase = "https://api.example.com/features"
AssetsPath = "/app/assets"

[Database]
DbConnection = "postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis"
DbPoolMaxConns = 10
DbPoolMinConns = 1

[Paging]
LimitDefault = 100
LimitMax = 5000

[Metadata]
Title = "GIS Open API"
Description = "OGC API Features — données géographiques"
```

**Endpoints générés automatiquement :**
```
GET /features/                          # Landing page
GET /features/conformance               # OGC conformance
GET /features/collections               # Toutes les collections
GET /features/collections/communes      # Métadonnées communes
GET /features/collections/communes/items           # Features
GET /features/collections/communes/items?limit=50  # Paginé
GET /features/collections/communes/items?bbox=2,48,3,49  # Filtre bbox
GET /features/collections/communes/items/{id}      # Feature unique
```

---

## 10. Keycloak — authentification et autorisation spatiale

### Realm configuration

```json
{
  "realm": "gis-platform",
  "clients": [
    {
      "clientId": "web-app",
      "publicClient": true,
      "redirectUris": ["https://app.example.com/*"],
      "webOrigins": ["https://app.example.com"]
    },
    {
      "clientId": "martin",
      "secret": "${MARTIN_SECRET}",
      "serviceAccountsEnabled": true
    }
  ],
  "roles": {
    "realm": [
      { "name": "gis-viewer",   "description": "Lecture seule" },
      { "name": "gis-editor",   "description": "Lecture + écriture" },
      { "name": "gis-admin",    "description": "Administration complète" }
    ]
  }
}
```

### Proxy Martin avec validation JWT

```nginx
# nginx/martin-auth.conf
location /martin/ {
    # Validation JWT Keycloak
    auth_jwt "GIS Platform";
    auth_jwt_key_request /_jwks;

    # Rôle minimum requis
    if ($jwt_claim_roles !~* "gis-viewer") {
        return 403;
    }

    proxy_pass http://martin:3000/;
    proxy_cache tiles_cache;
    proxy_cache_valid 200 1h;
    proxy_cache_key "$scheme$request_method$host$request_uri";
    add_header X-Cache-Status $upstream_cache_status;
}
```

---

## 11. Performance — benchmarks et optimisations

### Comparaison tuiles : Martin vs ArcGIS Feature Service

| Métrique | Martin (MVT) | ArcGIS Feature Service | Ratio |
|---|---|---|---|
| Latence P50 (zoom 10) | 3 ms | 180 ms | **60x** |
| Latence P95 (zoom 10) | 12 ms | 850 ms | **70x** |
| Throughput max | 8 000 req/s | 400 req/s | **20x** |
| Taille réponse Z10 | 45 KB | 320 KB | **7x** |
| Coût licence | 0 € | inclus ArcGIS | — |

### Optimisations PostGIS pour MVT

```sql
-- 1. Simplification géométrique par zoom (précomputation)
CREATE MATERIALIZED VIEW communes_z8 AS
SELECT
    code_insee, nom, population,
    ST_Simplify(geom, 0.01) AS geom
FROM communes;

CREATE MATERIALIZED VIEW communes_z12 AS
SELECT
    code_insee, nom, population,
    ST_Simplify(geom, 0.001) AS geom
FROM communes;

-- 2. Clustering physique (accès séquentiel pour spatial)
CLUSTER communes USING idx_communes_geom;

-- 3. Statistiques à jour
ANALYZE communes;

-- 4. Index partiel (données récentes fréquemment accédées)
CREATE INDEX idx_incidents_recent
ON incidents(geom)
WHERE date_incident > NOW() - INTERVAL '1 year';

-- 5. Fonction MVT avec simplification adaptative
CREATE FUNCTION get_communes_tiles(z INT, x INT, y INT)
RETURNS bytea AS $$
DECLARE
    bounds geometry := ST_TileEnvelope(z, x, y);
    tolerance float := CASE
        WHEN z < 8  THEN 0.01
        WHEN z < 12 THEN 0.001
        ELSE 0.0001
    END;
BEGIN
    RETURN (
        SELECT ST_AsMVT(tile, 'communes', 4096, 'geom')
        FROM (
            SELECT
                code_insee, nom, population,
                ST_AsMVTGeom(
                    ST_Simplify(geom, tolerance),
                    bounds, 4096, 256, true
                ) AS geom
            FROM communes
            WHERE geom && bounds
        ) tile
        WHERE geom IS NOT NULL
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;
```

### Configuration Redis cache tuiles

```yaml
# martin-config.yaml — cache Redis
cache:
  redis:
    url: redis://redis:6379/0
    ttl: 86400          # 24h pour tuiles stables
    max_size: 1073741824 # 1 GB
    key_prefix: "martin:"

# Stratégie de cache par couche
tables:
  communes:
    cache_ttl: 86400    # Données stables : 24h
  incidents:
    cache_ttl: 300      # Données dynamiques : 5min
  positions_live:
    cache_ttl: 0        # Pas de cache (temps réel)
```

---

## 12. Monitoring avec Grafana

### Métriques clés à surveiller

```yaml
# prometheus/alerts.yml
groups:
  - name: gis-web
    rules:

      - alert: MartinLatencyHigh
        expr: histogram_quantile(0.95,
          rate(martin_tile_duration_seconds_bucket[5m])) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Martin P95 > 100ms ({{ $value }}s)"

      - alert: TilesErrorRate
        expr: rate(martin_tile_errors_total[5m]) /
              rate(martin_tile_requests_total[5m]) > 0.01
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Taux erreur tuiles > 1%"

      - alert: PostGISSlowQueries
        expr: pg_stat_activity_count{state="active",
          wait_event_type="Lock"} > 5
        for: 30s
        labels:
          severity: warning
```

### Dashboard Grafana — santé de la stack

**Panels recommandés :**
```
Row 1 — Vue globale
  ├── Requests/s total (martin + titiler + featureserv)
  ├── Latence P95 tuiles MVT
  ├── Cache hit rate Redis (%)
  └── Erreurs 5xx / minute

Row 2 — Base de données
  ├── Connexions actives PgBouncer
  ├── Latence requêtes PostGIS P99
  ├── Taille des index spatiaux
  └── Slow queries (> 500ms)

Row 3 — Infrastructure
  ├── CPU / RAM par service
  ├── IOPS disque PostGIS
  ├── Bande passante MinIO
  └── Saturation Redis
```

---

## 13. Déploiement — checklist production

```bash
# 1. Variables d'environnement
cp .env.example .env
# Remplir : PG_PASSWORD, MINIO_USER, MINIO_PASSWORD,
#           KC_PASSWORD, SUPERSET_SECRET, ACME_EMAIL

# 2. Lancement des services
docker compose up -d postgis redis minio
docker compose up -d pgbouncer
docker compose up -d martin titiler pg-featureserv
docker compose up -d keycloak superset geonode
docker compose up -d traefik

# 3. Import données initiales
docker compose exec postgis psql -U gis -f /init.sql
ogr2ogr -f PostgreSQL "PG:host=localhost dbname=gis" \
  communes_france.gpkg -nlt PROMOTE_TO_MULTI

# 4. Génération PMTiles
bash scripts/generate-pmtiles.sh

# 5. Vérification santé
curl https://api.example.com/martin/health
curl https://api.example.com/titiler/healthz
curl https://api.example.com/features/

# 6. Test tuile MVT
curl "https://api.example.com/martin/communes/10/512/368" \
  -o /tmp/tile.mvt && file /tmp/tile.mvt
# → /tmp/tile.mvt: data (application/x-protobuf)
```

---

## 14. Ce que cette stack fait mieux qu'ArcGIS

| Critère | ArcGIS Experience Builder | Stack 3 Modern Web GIS |
|---|---|---|
| Performance tuiles | 150–800ms | **3–12ms** (50x plus rapide) |
| 3D natif | CityEngine (payant) | **Deck.gl WebGL gratuit** |
| Offline | Non | **PMTiles + Service Worker** |
| Mobile | App ArcGIS Field Maps | **Progressive Web App native** |
| Rendu vectoriel | ArcGIS JS SDK | **MapLibre GL JS (standard W3C)** |
| NDVI à la volée | Image Server (payant) | **TiTiler (gratuit)** |
| OGC API Features | Extension | **pg_featureserv natif** |
| Coût annuel | ~80 000 € | **0 € (infra seule)** |
| Lock-in vendor | Total | **Zéro** |
