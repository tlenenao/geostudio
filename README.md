# GeoStudio

**Plateforme d'applications géospatiales open-source** : cataloguer des données,
créer des cartes, construire des applications et dashboards métier **sans code**
— et à terme, la couche géospatiale de la data platform moderne (formats ouverts,
API standards OGC, architecture AI-native via MCP).

> **Statut : refondation en cours (pré-v0.1).** Ce dépôt est le fork de travail
> issu de `gis-project`, restructuré pour exécuter la feuille de route « option C » :
> le shell et son builder sont le produit ; le socle GeoNode est remplacé
> progressivement par un cœur maison. Voir
> [la feuille de route](docs/vision/2026-07-04-feuille-de-route-geostudio.md).

---

## Ce qui existe aujourd'hui

- **`shell/`** — le front React (TypeScript, Vite, MapLibre GL + deck.gl, ECharts) :
  - catalogue d'items (cartes, apps, dashboards) : création, édition, partage,
    publication, vignettes ;
  - éditeur de cartes (tuiles vectorielles Martin, raster TiTiler, couches
    deck.gl) ;
  - **builder d'apps/dashboards no-code** : grille responsive par breakpoint,
    widgets (carte, texte, image, bouton, table, indicateur, filtre, graphique,
    navigation), bus d'actions, variables, multi-pages, thèmes, templates —
    le tout rendu par un runtime unique config-driven (`AppConfig` JSON) ;
  - SDK de widgets embryonnaire (`registerWidget`).
- **`core/`** — le cœur naissant (Python/FastAPI, ex `builder-service`) :
  persistance des configs d'apps **versionnées avec révisions et rollback**.
  Il grossira en cœur complet (items, partage, OGC API Features, MCP) selon la
  feuille de route.
- **`docker-compose.yml`** — la stack de dev : PostGIS, PgBouncer, MinIO, Martin,
  TiTiler, pg_featureserv, Keycloak, Traefik, cœur, shell. GeoNode, Superset et
  Redis sont sortis (jalon M1).

## Où va le projet

| Jalon | Contenu |
|---|---|
| **M1 GeoNode-free** ✅ | Items/partage/publication dans le cœur ; GeoNode, Superset, Redis sortis |
| **M2 AI-operable** | Serveur MCP : un agent crée un dashboard valide |
| **M3 Les apps écrivent** | OGC API Features (CRUD) + widget Formulaire schema-driven |
| **M4 Donnée→carte** | Upload GPKG/GeoJSON → carte stylée partageable en minutes |
| **M5 SDK ouvrable** | Contrat de widget Web Components, chargement dynamique |
| **M6 v0.1 publique** | CI, images versionnées, install docs, démo publique |
| **M7 exploitable** | OpenTelemetry + dashboards/SLO packagés |
| **M8 data platform** | CDC PostGIS → GeoParquet, analytique DuckDB |
| **M9 catalogue ouvert** | API STAC, export DCAT-AP, moissonnage (STAC, WMS/WFS, CSW, CKAN) |
| **M10 3D & print** | Couches 3D Tiles + terrain, export PNG/PDF mis en page |

Détail, arbitrages techniques et estimations :
[`docs/vision/2026-07-04-feuille-de-route-geostudio.md`](docs/vision/2026-07-04-feuille-de-route-geostudio.md).

## Démarrage rapide (dev)

Prérequis : Docker 24+, Node 20+, [uv](https://docs.astral.sh/uv/) (Python).

```bash
cp .env.example .env       # renseigner les mots de passe
docker compose up -d       # stack complète
```

| Service | URL |
|---|---|
| Shell (front) | http://localhost:8300 |
| Cœur (API) | http://localhost:8200 |
| Martin (tuiles MVT) | http://localhost:3000 |
| pg_featureserv (OGC API Features) | http://localhost:9000 |
| Keycloak | http://localhost:8180 |
| MinIO console | http://localhost:9001 |

### Vérifier le mode `oidc` réel (manuel)

Le mode `mock` (`VITE_AUTH_MODE=mock`, `CORE_AUTH_MODE=mock`) suffit pour le
développement courant et pour les 13 specs E2E — aucun accès réseau à
Keycloak n'est nécessaire. Le mode `oidc` réel (utilisé en usage réel, pas en
CI) se vérifie manuellement :

1. `docker compose up -d` (stack complète, y compris `keycloak` avec le realm
   `geostudio` importé automatiquement — voir `docker compose ps keycloak`
   pour confirmer `healthy`), puis appliquer les migrations du cœur :
   `cd core && DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head`.
   Sans cette étape, `GET /me` échoue même avec un token Keycloak valide —
   `get_current_user` écrit dans les tables `tenants`/`users`, absentes tant
   que les migrations n'ont pas tourné sur une base Postgres neuve
   (`init_db()` ne les crée qu'en SQLite, jamais en Postgres).
2. Construire et lancer le shell avec `CORE_AUTH_MODE=oidc` côté cœur et sans
   `VITE_AUTH_MODE=mock` côté shell (retirer la variable ou la mettre à
   `oidc`).
3. Ouvrir http://localhost:8300 — être redirigé vers Keycloak
   (`http://localhost:8180/realms/geostudio/...`), se connecter avec un des
   utilisateurs de démo du realm importé.
4. Après redirection retour vers le shell : le catalogue doit se charger
   normalement (preuve que le token JWT émis par Keycloak est accepté par le
   cœur — `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` validés côté
   `app/auth/dependency.py`).
5. Ouvrir les DevTools réseau, vérifier qu'un appel `GET /me` retourne un
   `username` cohérent avec l'utilisateur Keycloak connecté (pas `mockuser`).

Un échec à l'étape 3 (pas de redirection, ou erreur `invalid_redirect_uri`)
indique un realm mal configuré (`Valid redirect URIs` du client
`geostudio-shell` doit inclure exactement `http://localhost:8300/`). Un échec
à l'étape 4 (401 du cœur après connexion réussie) indique un décalage entre
l'`audience`/`issuer` attendus par le cœur (`CORE_OIDC_AUDIENCE`,
`CORE_OIDC_ISSUER`) et ce que le realm émet réellement.

### Développement front (shell)

```bash
cd shell
npm ci
npm run test        # unitaires (Vitest)
npm run e2e         # E2E (Playwright, auth mockée)
npm run dev         # serveur de dev Vite
```

### Développement cœur

```bash
cd core
uv sync
uv run pytest
uv run uvicorn app.main:app --reload --port 8200
```

## Documentation

| Document | Rôle |
|---|---|
| [`docs/vision/2026-07-04-feuille-de-route-geostudio.md`](docs/vision/2026-07-04-feuille-de-route-geostudio.md) | **Référence** : phasage SP-1→SP-9, arbitrages, jalons |
| [`docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md`](docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md) | La décision d'orientation (option C) et ses raisons |
| [`docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md`](docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md) | La vision long terme (exploration 2026) |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) et [`plans/`](docs/superpowers/plans/) | Specs et plans datés de chaque sous-projet (SP-0x…) |
| [`docs/archive/`](docs/archive/) | Études préalables (générations dépassées, conservées pour traçabilité) |
| [`CLAUDE.md`](CLAUDE.md) | Guide de travail pour les sessions de développement (Claude) |

## Licence

[Apache-2.0](LICENSE).
