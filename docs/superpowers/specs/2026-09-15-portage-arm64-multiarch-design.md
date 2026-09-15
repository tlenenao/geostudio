# Portage arm64 multi-arch (postgis, titiler, matrice de release) — design

## 0. Cadrage

Déclencheur : évaluation d'un déploiement de GeoStudio sur le tiers gratuit
Oracle Cloud. Seule l'offre avec assez de RAM pour la pile par défaut (11
services, `docker-compose.yml`) est **Ampere A1 Flex, arm64** (jusqu'à
4 OCPU/24 Go, « always free ») — l'offre amd64 gratuite
(2× VM.Standard.E2.1.Micro, 1 Go de RAM chacune) est hors sujet, `postgis`
seul est configuré avec `shared_buffers=2GB` (`docker-compose.yml`).

Ce document ne traite **pas** le provisioning Oracle lui-même (réseau, TLS,
runbook) — c'est un chantier séparé qui consomme le résultat de celui-ci. Il
ferme un préalable générique, utile à tout hôte arm64 et pas seulement
Oracle : **`.github/workflows/release.yml` ne publie que de l'amd64**
(`docker/build-push-action` sans `platforms:`, runner `ubuntu-latest`), et
deux images du dépôt ne peuvent aujourd'hui pas exister en arm64 sans
changement de conception, pas seulement de config CI :

- `deploy/postgis/Dockerfile` part de `postgis/postgis:16-3.4`, un tag
  **mono-arch amd64** — pas d'arm64 sur ce tag ni sur aucun tag récent.
- `docker-compose.yml` consomme `ghcr.io/developmentseed/titiler:0.18.4`,
  également **mono-arch amd64** publié par l'amont.

Objectif : qu'une montée de version de GeoStudio soit aussi simple en arm64
qu'en amd64 — `git tag` → CI construit et publie des images multi-arch →
`docker compose pull && up -d` sur l'hôte — sans rebuild manuel ni fork à
maintenir en parallèle.

## 1. Constat vérifié, image par image

Vérifié en session (`docker manifest inspect`, API Docker Hub, index de
paquets PGDG, PyPI), pas supposé :

| Image | Architectures publiées | Constat |
|---|---|---|
| `postgis/postgis:16-3.4` | amd64 seul | Confirmé sur `16-3.4`, `16-3.5`, `17-3.5`, `latest` — aucun n'a d'arm64. |
| `ghcr.io/developmentseed/titiler:0.18.4` | amd64 seul | Mais sa **propre base**, `ghcr.io/vincentsarago/uvicorn-gunicorn:3.11` (recette officielle titiler, `dockerfiles/Dockerfile.gunicorn`), **est multi-arch** (amd64+arm64) — le blocage est une lacune de publication côté devseed, pas une limite technique GDAL/rasterio. `rasterio` 1.5.1 publie des wheels `manylinux_2_28_aarch64` sur PyPI : pas de compilation requise à l'installation. |
| `qgis/qgis:release-3_34` | mono-arch (probable amd64 seul) | Hors périmètre de ce chantier (rappel ci-dessous). |
| `postgres:16-bookworm` | amd64 + arm64 | Confirmé. |
| Paquets PGDG `postgresql-16-postgis-3`, `-postgis-3-scripts`, `-pgvector`, `-wal2json` | amd64 + arm64 | Confirmé sur l'index `bookworm-pgdg/main`. |
| `python:3.12-slim`, `node:20-slim`, `alpine:3.20`, `quay.io/keycloak/keycloak:24.0.5`, `ghcr.io/maplibre/martin:v0.18.0`, `edoburu/pgbouncer:1.22.1-p0`, `quay.io/minio/minio`, `traefik:v3.0.4`, `grafana/otel-lgtm` | amd64 + arm64 | Confirmé — aucune action requise sur ces bases. |

## 2. Décisions de conception

### 2.1 `deploy/postgis/Dockerfile` — base unifiée, un seul fichier

Remplace `FROM postgis/postgis:16-3.4` (Debian bullseye, sujet au flake
connu « Release file is expired » sur `bullseye-security`) par
`FROM postgres:16-bookworm` (image officielle multi-arch). Installe
nous-mêmes, via PGDG (déjà configuré dans l'image officielle Postgres),
`postgresql-16-postgis-3` + `postgresql-16-postgis-3-scripts` +
`postgresql-16-pgvector` + `postgresql-16-wal2json`. Un seul Dockerfile,
une seule recette, testée identiquement sur les deux architectures — pas de
`Dockerfile.arm64` séparé à maintenir en parallèle.

Conséquence assumée : ce changement de base s'applique à **tous** les
déploiements existants (amd64 compris), pas seulement à un futur hôte
arm64 — à documenter comme tel dans le commit. Bénéfice collatéral : élimine
le flake `bullseye-security` au passage (`bookworm-pgdg` est un dépôt
activement maintenu).

### 2.2 `deploy/titiler/Dockerfile` (nouveau) — recette officielle rapatriée

Nouveau répertoire `deploy/titiler/` avec un Dockerfile qui reproduit à
l'identique `dockerfiles/Dockerfile.gunicorn` du dépôt `developmentseed/titiler`
(tag `0.18.4`, la version actuellement consommée — **ce chantier ne monte
pas de version titiler**, il rapatrie exactement ce qui est déployé
aujourd'hui) :

```dockerfile
ARG PYTHON_VERSION=3.11
FROM ghcr.io/vincentsarago/uvicorn-gunicorn:${PYTHON_VERSION}
RUN python -m pip install -U pip
RUN python -m pip install --no-cache-dir \
      "titiler.core==0.18.4" \
      "titiler.extensions[cogeo,stac]==0.18.4" \
      "titiler.mosaic==0.18.4" \
      "titiler.application==0.18.4"
ENV MODULE_NAME titiler.application.main
ENV VARIABLE_NAME app
```

(épinglage par version PyPI plutôt que `COPY src/titiler/` + build depuis
les sources comme le fait l'amont : plus simple à maintenir dans ce dépôt,
comportement runtime identique — `titiler.application.main:app` est le
même point d'entrée.)

`docker-compose.yml` : le service `titiler` passe de
`image: ghcr.io/developmentseed/titiler:0.18.4` à `build: ./deploy/titiler`
(même patron que `postgis`). `docker-compose.prod.yml` gagne le même bloc
`image: ghcr.io/tlenenao/geostudio-titiler:${GEOSTUDIO_VERSION:-latest}` +
`build: !reset null` que les autres services construits par ce dépôt. Toute
la configuration actuelle (`TITILER_API_ROOT_PATH`, `PORT`, les variables
`AWS_*` pour l'accès MinIO, le healthcheck `/healthz`) reste inchangée —
c'est la même application, seulement construite par nous plutôt que
consommée en image prête.

Coût de possession assumé : une future montée de version de titiler en
amont nécessitera de rebasculer à la main les 4 numéros de version épinglés
dans notre Dockerfile — même modèle que celui déjà accepté pour
`deploy/postgis/Dockerfile` (pgvector/wal2json) depuis sa création.

### 2.3 `deploy/backup/Dockerfile` — correctif bloquant

Le téléchargement du client MinIO est codé en dur sur
`https://dl.min.io/client/mc/release/linux-amd64/mc`. Puisque `backup`
entre dans le périmètre multi-arch retenu (§3), ce correctif est un
prérequis direct : détecter l'architecture cible (`$TARGETARCH`, fourni par
buildx au moment du build) et choisir `linux-amd64`/`linux-arm64` dans
l'URL en conséquence.

### 2.4 `.github/workflows/release.yml` — matrice multi-arch

`docker/setup-qemu-action` (nouveau) + `docker/setup-buildx-action` (déjà
présent) permettent de construire les deux plateformes depuis le runner
`ubuntu-latest` existant, via l'émulation QEMU pour la jambe arm64 — choix
standard pour `build-and-push` : c'est une publication d'image, pas une
exécution de tests, la lenteur relative de l'émulation n'y coûte que du
temps de CI, jamais de fiabilité fonctionnelle (contrairement à un test qui
tournerait sous émulation, cf. §2.5).

`platforms: linux/amd64,linux/arm64` par défaut sur toutes les entrées de
la matrice, **sauf `geostudio-qgis-worker`** qui garde `platforms:
linux/amd64` seul (base `qgis/qgis:release-3_34` mono-arch, image 11 Go) —
chaque entrée de la matrice porte son propre champ `platforms`, pas une
valeur globale au job. Nouvelle entrée de matrice :

```yaml
- image: geostudio-titiler
  context: ./deploy/titiler
  dockerfile: Dockerfile
```

Chaque tag `ghcr.io/tlenenao/geostudio-*` (sauf qgis-worker) devient une
manifest list — `docker compose pull` choisit automatiquement la bonne
variante. **Aucun changement requis dans `docker-compose.prod.yml`** au-delà
de l'ajout du service `titiler` du §2.2 : les références d'image existantes
(`${GEOSTUDIO_VERSION:-latest}`) résolvent déjà correctement une manifest
list.

### 2.5 Validation CI réelle sur arm64

Le job `test-gate` (build image postgis, `alembic upgrade head` /
`downgrade base`, suite pytest complète) est **dupliqué sur un runner
`ubuntu-24.04-arm`** natif (hébergé gratuitement par GitHub pour les dépôts
publics) — pas une simple vérification que le build buildx aboutit, mais
Postgres/PostGIS/pgvector/wal2json réellement démarrés et exercés par la
suite de tests sur du vrai matériel arm64. Contrairement à `build-and-push`,
une exécution de tests sous émulation QEMU ne prouverait rien de fiable sur
le comportement réel (temporisations, I/O, JIT) — d'où le runner natif ici
précisément.

Le volet shell (Vitest/Playwright/`npm run build`) **n'est pas dupliqué** :
JS/TS pur, aucune dépendance native, le job amd64 existant suffit à le
garantir.

Nouveau : une **fumée `titiler` arm64**, sur ce même runner — construire
l'image `geostudio-titiler` en natif, démarrer le conteneur, `curl -f
http://127.0.0.1:8000/healthz` (même sonde que celle déjà vérifiée à
l'exécution par SP-21 en amd64). Ce n'est pas un test fonctionnel complet
de titiler (aucune suite de tests dédiée n'existe dans ce dépôt pour ce
service, consommé jusqu'ici en boîte noire) — seulement la preuve que
l'image démarre et sert une réponse sur ce matériel.

## 3. Périmètre

**Dans le périmètre** (multi-arch) : `geostudio-core`, `geostudio-shell`,
`geostudio-postgis`, `geostudio-titiler` (nouveau), `geostudio-backup`,
`geostudio-export-worker`, `geostudio-appexport-standalone`,
`geostudio-appexport-runtime-builder`.

**Hors périmètre, explicitement** :
- `geostudio-qgis-worker` (profil `etl`, optionnel) — base mono-arch,
  reste amd64 seul.
- Toute montée de version de titiler au-delà de `0.18.4` — ce chantier
  rapatrie la version actuellement déployée, il ne la fait pas évoluer.
- Le provisioning Oracle proprement dit (réseau, TLS, runbook, sizing) —
  chantier séparé, consommateur de celui-ci.
- `martin`/`keycloak`/`minio`/`pgbouncer`/`traefik`/`otel-lgtm` — déjà
  multi-arch en l'état, aucune action.

## 4. Risques identifiés, à vérifier en tâche dédiée — pas assumés ici

- **Playwright/Chromium arm64** (`deploy/export-worker/Dockerfile`,
  `playwright install --with-deps chromium`) — support arm64 existant côté
  Playwright mais jamais vérifié dans ce dépôt. À valider par un build +
  démarrage réel sur le runner arm64.
- **Extension communautaire DuckDB `h3`** (`core`, `export-worker` —
  `INSTALL h3 FROM community`) — disponibilité arm64 à confirmer à la
  construction, pas supposée.
- **`test_deployability.py`** (garde-fou CI existant, `test_every_build_service_has_a_released_image`
  et voisins) doit être étendu pour connaître `geostudio-titiler` comme
  nouveau service construit — sans quoi cette image resterait invisible au
  garde-fou qui vérifie la cohérence `context`/`dockerfile` compose ↔ CI.
- **Durée du job `build-and-push`** : croît sensiblement (émulation QEMU
  sur 7 des 8 legs) — accepté comme coût, pas un risque fonctionnel.

## 5. Plan de validation (détaillé dans le plan d'exécution)

- `docker manifest inspect ghcr.io/tlenenao/geostudio-<image>:<tag>` porte
  `amd64` **et** `arm64` après un tag de release, pour chacune des 8 images
  du §3 — sauf `geostudio-qgis-worker` (amd64 seul, vérifié comme un choix,
  pas une régression).
- Le job `test-gate-arm64` (nouveau) est vert : migrations up/down + suite
  pytest complète, sur runner `ubuntu-24.04-arm` natif.
- Un conteneur `geostudio-titiler` construit en arm64 répond `200` sur
  `/healthz`.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
  ne référence plus `ghcr.io/developmentseed/titiler` nulle part.
- `core/tests/test_deployability.py` reste vert, étendu pour couvrir
  `geostudio-titiler`.
- Migrations Postgis rejouées avec succès (up **et** down) sur l'image
  reconstruite depuis `postgres:16-bookworm`, sur les deux architectures.
