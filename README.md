# Stack GIS Open-Source — Alternative à ArcGIS Enterprise

Stack de production complète, déployable en Docker Compose, équivalente à ArcGIS Enterprise. Économie estimée : **80–95 % sur les coûts logiciels**.

---

## Prérequis

| Outil | Version minimale | Vérification |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| RAM disponible | 16 Go minimum (32 Go recommandés) | `free -h` |
| Espace disque | 50 Go minimum | `df -h` |

**Outils optionnels (import de données) :**
- `ogr2ogr` / GDAL — conversion de formats géo
- `tippecanoe` — génération de tuiles PMTiles
- `mc` (MinIO Client) — upload vers MinIO

---

## Installation rapide

### 1. Cloner le dépôt

```bash
git clone https://github.com/tlenenao/gis-project.git
cd gis-project
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env et remplir tous les champs obligatoires
nano .env
```

Variables à renseigner dans `.env` :

| Variable | Description | Exemple |
|---|---|---|
| `PG_PASSWORD` | Mot de passe PostgreSQL | `MotDePasse_Fort!` |
| `MINIO_USER` | Utilisateur MinIO | `minioadmin` |
| `MINIO_PASSWORD` | Mot de passe MinIO (≥ 12 car.) | `MinioSecret_123` |
| `KC_PASSWORD` | Mot de passe admin Keycloak | `KeycloakAdmin!` |
| `SUPERSET_SECRET` | Clé secrète Superset (random 64 car.) | voir ci-dessous |
| `ACME_EMAIL` | Email pour certificat Let's Encrypt | `admin@exemple.fr` |
| `DOMAIN` | Nom de domaine public | `gis.exemple.fr` |

Générer une clé secrète Superset :
```bash
openssl rand -base64 48
```

### 3. Démarrer la stack

**Option A — Démarrage ordonné (recommandé en première installation) :**

```bash
# Socle de données
docker compose up -d postgis redis minio
sleep 10

# Middleware
docker compose up -d pgbouncer

# Serveurs de tuiles
docker compose up -d martin titiler pg-featureserv

# Applications
docker compose up -d keycloak superset geonode

# Ingress (SSL/TLS)
docker compose up -d traefik
```

**Option B — Démarrage global :**

```bash
docker compose up -d
```

### 4. Initialiser la base de données

```bash
# Attendre que PostgreSQL soit prêt
docker compose exec postgis pg_isready -U gis

# Appliquer le schéma initial
docker compose exec -T postgis psql -U gis -d gis < sql/init.sql
```

### 5. Vérifier la santé des services

```bash
# Martin (tuiles vectorielles)
curl http://localhost:3000/health

# TiTiler (raster)
curl http://localhost:8000/healthz

# pg_featureserv (OGC API Features)
curl http://localhost:9000/

# GeoNode
curl http://localhost:8080/api/v2/
```

---

## Import de données géographiques

### Depuis un fichier GeoPackage / Shapefile

```bash
ogr2ogr \
  -f PostgreSQL \
  "PG:host=localhost port=5432 dbname=gis user=gis password=${PG_PASSWORD}" \
  communes_france.gpkg \
  -nlt PROMOTE_TO_MULTI \
  -overwrite
```

### Générer des tuiles PMTiles (mode hors-ligne)

```bash
# Installer tippecanoe si nécessaire
# apt install tippecanoe  ou  brew install tippecanoe

bash scripts/generate-pmtiles.sh
```

---

## Accès aux interfaces

| Service | URL | Identifiants par défaut |
|---|---|---|
| GeoNode (portail) | `http://localhost:8080` | admin / (voir .env) |
| Superset (BI) | `http://localhost:8088` | admin / admin |
| Keycloak (auth) | `http://localhost:8180` | admin / KC_PASSWORD |
| MinIO (stockage) | `http://localhost:9001` | MINIO_USER / MINIO_PASSWORD |
| Martin (tuiles MVT) | `http://localhost:3000` | — |
| TiTiler (raster) | `http://localhost:8000` | — |
| pg_featureserv | `http://localhost:9000` | — |
| Traefik dashboard | `http://localhost:8090` | — |

---

## Architecture

```
                    ┌──────────────┐
                    │   Traefik    │  SSL/TLS, routing
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌────────────┐ ┌────────────┐
    │  Martin     │ │  Superset  │ │  GeoNode   │
    │ (MVT <3ms)  │ │  (BI geo)  │ │  (portail) │
    └──────┬──────┘ └─────┬──────┘ └─────┬──────┘
           └──────────────┼──────────────┘
                          ▼
           ┌──────────────────────────────┐
           │   PostgreSQL 16 + PostGIS   │
           │   PgBouncer (pooling)       │
           └──────────────┬───────────────┘
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
      ┌─────────┐   ┌──────────┐   ┌──────────┐
      │  Redis  │   │  MinIO   │   │ Keycloak │
      │ (cache) │   │ (objets) │   │  (auth)  │
      └─────────┘   └──────────┘   └──────────┘
```

Correspondance avec ArcGIS Enterprise :

| ArcGIS Enterprise | Cette stack | Maturité |
|---|---|---|
| Enterprise Geodatabase | PostgreSQL + PostGIS | ⭐⭐⭐⭐⭐ |
| ArcGIS Server (WMS/WFS) | GeoServer | ⭐⭐⭐⭐⭐ |
| ArcGIS Server (tuiles vecteur) | Martin | ⭐⭐⭐⭐ |
| ArcGIS Image Server | TiTiler | ⭐⭐⭐⭐ |
| ArcGIS Portal | GeoNode | ⭐⭐⭐⭐ |
| ArcGIS Dashboards | Grafana + Superset | ⭐⭐⭐⭐⭐ |
| Web Adaptor | Traefik | ⭐⭐⭐⭐⭐ |
| SSO / Auth | Keycloak | ⭐⭐⭐⭐⭐ |

---

## Commandes utiles

```bash
# Voir les logs d'un service
docker compose logs -f martin

# Redémarrer un service
docker compose restart postgis

# Arrêter la stack (données conservées)
docker compose stop

# Supprimer la stack + volumes (DESTRUCTIF)
docker compose down -v

# Voir l'état des services
docker compose ps
```

---

## Documentation détaillée

- **[`plateforme-modulaire.md`](plateforme-modulaire.md)** — 📌 **Document maître** : conception du produit OGE (noyau `GeoCore` + modules enfichables), parité ArcGIS 11.4, performance, gouvernance & roadmap
- [`synthese.md`](synthese.md) — Vue d'ensemble de toute la stack open-source GIS (correspondance ArcGIS ↔ FOSS4G)
- [`stack3-modern-web-gis.md`](stack3-modern-web-gis.md) — Guide complet Modern Web GIS (MapLibre, Deck.gl, PMTiles)
- [`stacks-production.md`](stacks-production.md) — Comparatif des 5 stacks de production
- [`stacks-comparatif.md`](stacks-comparatif.md) — Tableau comparatif approfondi
