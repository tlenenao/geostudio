# Portage arm64 multi-arch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre publiable en multi-arch (amd64 **et** arm64) chacune des 8 images du dépôt qui en a besoin, en fermant les deux blocages de conception (base `postgis/postgis:16-3.4` mono-arch, image tierce `titiler` mono-arch) et en prouvant sur du matériel arm64 réel — pas seulement via l'émulation QEMU de publication — que Postgres/PostGIS/pgvector/wal2json fonctionnent.

**Architecture:** `deploy/postgis/Dockerfile` change de base (`postgres:16-bookworm` + paquets PGDG installés nous-mêmes). Un nouveau `deploy/titiler/Dockerfile` rapatrie la recette officielle de titiler 0.18.4 (au lieu de consommer l'image tierce mono-arch), construit comme les autres services du dépôt. `deploy/backup/Dockerfile` choisit son binaire `mc` par architecture cible (`$TARGETARCH`, fourni par buildx). `.github/workflows/release.yml` construit chaque image sous QEMU pour les deux plateformes (`build-and-push`) et fait tourner une porte de tests complète sur un runner arm64 **natif** (`test-gate-arm64`) avant toute publication.

**Tech Stack:** Docker/Buildx, GitHub Actions (`docker/setup-qemu-action`, `docker/build-push-action`), Debian bookworm + PGDG, Python/pytest (garde-fous `core/tests/test_deployability.py`).

## Constat vérifié en session, avant d'écrire ce plan (piège CLAUDE.md n°3 : ne jamais faire confiance au texte du spec sans revérifier contre la source réelle)

Ces vérifications ont été faites avec un builder `docker buildx create --driver docker-container` + `docker run --rm --privileged tonistiigi/binfmt --install all` (exactement ce que fait `docker/setup-qemu-action` en CI) — donc sous émulation QEMU réelle, pas supposées :

- **postgis rebasé sur `postgres:16-bookworm`** : build arm64 réussi, conteneur démarré avec `wal_level=logical`, `CREATE EXTENSION postgis` (3.6.4) + `CREATE EXTENSION vector` (0.8.6) + `pg_create_logical_replication_slot(..., 'wal2json')` tous confirmés fonctionnels sur `aarch64` réel (émulé).
- **titiler rapatrié** (recette `ghcr.io/vincentsarago/uvicorn-gunicorn` + 4 paquets PyPI épinglés) : build arm64 réussi (rasterio 1.4.4 installé depuis une wheel `manylinux_..._aarch64`, aucune compilation), conteneur démarré, `curl http://127.0.0.1:8000/healthz` → `{"ping":"pong!"}` HTTP 200 sur `aarch64` réel.
- **Extension communautaire DuckDB `h3`** (risque §4 du spec) : `INSTALL h3 FROM community` réussi sur `python:3.12-slim` en `aarch64` réel — risque levé, pas seulement supposé.
- **Playwright Chromium** (risque §4 du spec) : `playwright install --with-deps chromium` réussi sur `python:3.12-slim` (Debian trixie) en `aarch64` réel — télécharge `linux-arm64/chrome-linux-arm64.zip` depuis `cdn.playwright.dev`, confirmé dans le driver Playwright lui-même (`debian12-arm64`/`debian13-arm64` sont des clés connues de `coreBundle.js`). Risque levé.
- **Trouvaille non prévue par le spec, bloquante pour §2.3** : l'URL codée en dur dans `deploy/backup/Dockerfile` (`https://dl.min.io/client/mc/release/linux-amd64/mc`) répond **410 Gone aujourd'hui, pour les DEUX architectures** — ce n'est pas un problème d'arch, `dl.min.io` a changé de schéma d'URL. Le remplacement naïf `dl.min.io/aistor/mc/release/linux-{arch}/mc` répond bien 200 sur les deux arch, MAIS le binaire qu'il sert s'identifie lui-même `mc --version` → **« MinIO Enterprise License »** (pas AGPL) : l'adopter romprait silencieusement la cohérence avec `deploy/backup/LICENSE-BACKUP.md` et le `LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later..."` déjà posés sur cette image. Le dépôt GitHub `minio/mc` (toujours sous `LICENSE` = AGPLv3, vérifié) publie encore ses binaires de release sous forme d'assets nommés `mc.linux-{amd64,arm64}.RELEASE.<timestamp>` — confirmé par un vrai `mc --version` → `License GNU AGPLv3` sur les deux architectures. Task 3 ci-dessous corrige donc **deux** bugs dans la même ligne : mono-arch **et** URL morte.

## Global Constraints

- Ce chantier ne monte **pas** la version de titiler au-delà de 0.18.4 — il rapatrie exactement la version consommée aujourd'hui.
- `geostudio-qgis-worker` reste **`linux/amd64` seul**, jamais multi-arch (base `qgis/qgis:release-3_34`, mono-arch, image 11 Go) — exception nommée dans la matrice, jamais une valeur globale au job.
- Un seul Dockerfile par service, testé identiquement sur les deux architectures — jamais de `Dockerfile.arm64` séparé à maintenir en parallèle.
- Le provisioning Oracle proprement dit (réseau, TLS, runbook, sizing) est **hors périmètre** de ce plan.
- `martin`/`keycloak`/`minio`/`pgbouncer`/`traefik`/`grafana/otel-lgtm` sont déjà multi-arch — aucune action sur ces services.
- `test-gate-arm64` doit tourner sur un runner **natif** (`ubuntu-24.04-arm`), jamais sous émulation QEMU — QEMU (`docker/setup-qemu-action`) n'est acceptée que pour `build-and-push` (publication d'image, pas exécution de tests).
- Toute image publiée reste sous le préfixe `ghcr.io/tlenenao/geostudio-*`.

---

## File Structure

- **Modify** `deploy/postgis/Dockerfile` — rebase `postgis/postgis:16-3.4` → `postgres:16-bookworm` + PGDG.
- **Create** `deploy/titiler/Dockerfile` — recette officielle rapatriée (titiler 0.18.4).
- **Modify** `docker-compose.yml` — service `titiler` : `image:` externe → `build: ./deploy/titiler`.
- **Modify** `docker-compose.prod.yml` — service `titiler` : ajoute `image:`/`build: !reset null`.
- **Modify** `deploy/backup/Dockerfile` — client `mc` choisi par `$TARGETARCH`, depuis les GitHub Releases AGPL de `minio/mc` (pas `dl.min.io`).
- **Modify** `.github/workflows/release.yml` — nouvelle entrée de matrice `geostudio-titiler`, `platforms:` par entrée, `docker/setup-qemu-action`, nouveau job `test-gate-arm64`, `build-and-push.needs` étendu.
- **Modify** `core/tests/test_deployability.py` — 8 nouveaux gardes-fous (2 sur les Dockerfiles postgis/titiler, 1 sur backup, 4 sur la matrice/le job arm64 de `release.yml`, repris ci-dessous tâche par tâche).

---

### Task 1: `deploy/postgis/Dockerfile` — base multi-arch

**Files:**
- Modify: `deploy/postgis/Dockerfile`
- Test: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: rien (fichier autonome).
- Produces: l'image `deploy/postgis` que consomment `docker-compose.yml` (service `postgis`, déjà `build: ./deploy/postgis` — inchangé), `ci.yml` (job `core`, `docker build ... ../deploy/postgis` — inchangé) et `release.yml` (job `test-gate`, matrice `build-and-push` — inchangés par cette tâche).

- [ ] **Step 1: Écrire le garde-fou (test qui échoue)**

Ouvrir `core/tests/test_deployability.py`. Repérer les deux constantes de chemin déjà déclarées en tête de fichier :

```python
REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "docker-compose.yml"
```

Juste en dessous du bloc de constantes existant (après la ligne `KEYCLOAK_REALM_JSON = REPO / "deploy/keycloak/geostudio-realm.json"`), ajouter :

```python
POSTGIS_DOCKERFILE = REPO / "deploy" / "postgis" / "Dockerfile"
```

Puis, n'importe où après la définition de `RESET`/`ComposeLoader` (par exemple juste avant `def test_every_build_service_has_a_released_image():`), ajouter la fonction de test :

```python
def test_postgis_dockerfile_uses_multiarch_base_with_pgdg_packages():
    """Portage arm64 : `postgis/postgis:16-3.4` est mono-arch amd64 (confirmé
    via `docker manifest inspect` sur ce tag et les tags récents — aucun n'a
    d'arm64). Rebase sur `postgres:16-bookworm` (image officielle, multi-arch)
    + les 4 paquets PGDG installés nous-mêmes — élimine au passage le flake
    `bullseye-security` (Debian 11, dépôt de sécurité au Valid-Until expiré,
    observé le 2026-09-12)."""
    text = POSTGIS_DOCKERFILE.read_text()
    assert "FROM postgres:16-bookworm" in text, (
        "deploy/postgis/Dockerfile doit partir de postgres:16-bookworm "
        "(multi-arch), pas de postgis/postgis:16-3.4 (mono-arch amd64)."
    )
    for package in (
        "postgresql-16-postgis-3",
        "postgresql-16-postgis-3-scripts",
        "postgresql-16-pgvector",
        "postgresql-16-wal2json",
    ):
        assert package in text, f"deploy/postgis/Dockerfile doit installer {package}"
    assert "Check-Valid-Until=false" not in text, (
        "le contournement bullseye-security n'a plus lieu d'être une fois "
        "rebasé sur bookworm-pgdg (dépôt PGDG activement maintenu)."
    )
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_deployability.py::test_postgis_dockerfile_uses_multiarch_base_with_pgdg_packages -v`
Expected: `FAILED` — `AssertionError: deploy/postgis/Dockerfile doit partir de postgres:16-bookworm...`

- [ ] **Step 3: Réécrire `deploy/postgis/Dockerfile`**

Remplacer tout le contenu du fichier par :

```dockerfile
# postgres:16-bookworm (image officielle, multi-arch amd64+arm64) sert de
# base — postgis/postgis:16-3.4 (Debian 11 bullseye) est mono-arch amd64,
# confirmé sur ce tag et les tags récents (16-3.5, 17-3.5, latest) via
# `docker manifest inspect`. Le dépôt PGDG (déjà configuré dans l'image
# officielle Postgres) sert aussi les paquets Debian
# postgresql-16-postgis-3(-scripts), postgresql-16-pgvector (SP-7) et
# postgresql-16-wal2json (SP-11a, décodage JSON du flux de réplication
# logique — pas de protocole binaire pgoutput à implémenter côté client) —
# tous les quatre publiés en arm64 sur bookworm-pgdg (vérifié).
FROM postgres:16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         postgresql-16-postgis-3 \
         postgresql-16-postgis-3-scripts \
         postgresql-16-pgvector \
         postgresql-16-wal2json \
    && rm -rf /var/lib/apt/lists/*
```

(Le contournement `-o Acquire::Check-Valid-Until=false` de l'ancienne base bullseye disparaît : `bookworm-pgdg` est un dépôt activement maintenu, sans le flake de fraîcheur de métadonnées de `bullseye-security`.)

- [ ] **Step 4: Relancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_deployability.py::test_postgis_dockerfile_uses_multiarch_base_with_pgdg_packages -v`
Expected: `PASSED`

- [ ] **Step 5: Vérification réelle — build + run + extensions, sur l'architecture native**

Run:
```bash
docker build -t geostudio-postgis-ci:latest ./deploy/postgis
docker run -d --name pg-arm64-plan-check \
  -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis \
  geostudio-postgis-ci:latest \
  -c wal_level=logical -c output_plugin_libraries=wal2json,pgoutput,test_decoding
for i in $(seq 1 30); do docker exec pg-arm64-plan-check pg_isready -U gis && break; sleep 2; done
docker exec -e PGPASSWORD=gis pg-arm64-plan-check psql -U gis -d gis -c \
  "CREATE EXTENSION postgis; CREATE EXTENSION vector; SELECT pg_create_logical_replication_slot('t','wal2json'); SELECT extname, extversion FROM pg_extension;"
docker rm -f pg-arm64-plan-check
```
Expected: `CREATE EXTENSION` ×2, une ligne `pg_create_logical_replication_slot`, et une liste `pg_extension` contenant `plpgsql`, `postgis` (3.6.x), `vector` (0.8.x). Aucune erreur.

Si un builder buildx multi-plateforme est disponible (`docker buildx create --driver docker-container --use` puis `docker run --rm --privileged tonistiigi/binfmt --install all`), répéter la même séquence avec `docker buildx build --platform linux/arm64 -t geostudio-postgis-ci:latest --load ./deploy/postgis` puis `docker run ... --platform linux/arm64 ...` — déjà vérifié une fois lors de l'écriture de ce plan (2026-09-17, résultat identique sur `aarch64`), à revérifier ici seulement si l'environnement d'exécution en a le temps/la capacité.

- [ ] **Step 6: Commit**

```bash
git add deploy/postgis/Dockerfile core/tests/test_deployability.py
git commit -m "fix(deploy): rebase postgis sur postgres:16-bookworm (multi-arch)"
```

---

### Task 2: `deploy/titiler/Dockerfile` — recette officielle rapatriée + câblage compose/release

**Files:**
- Create: `deploy/titiler/Dockerfile`
- Modify: `docker-compose.yml` (service `titiler`, lignes 162-215)
- Modify: `docker-compose.prod.yml` (service `titiler`, lignes 65-79)
- Modify: `.github/workflows/release.yml` (matrice `build-and-push`)
- Test: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: rien de neuf (fichier autonome + wiring compose/CI).
- Produces: le contexte de build `./deploy/titiler` que la Task 4 référencera dans le nouveau job `test-gate-arm64` (fumée titiler arm64).

- [ ] **Step 1: Créer `deploy/titiler/Dockerfile`**

```dockerfile
# deploy/titiler/Dockerfile
# Reproduit à l'identique dockerfiles/Dockerfile.gunicorn du dépôt
# developmentseed/titiler (tag 0.18.4, la version actuellement consommée —
# ce chantier ne monte PAS de version titiler, il rapatrie exactement ce qui
# est déployé aujourd'hui). L'image tierce ghcr.io/developmentseed/titiler
# est mono-arch amd64, mais sa PROPRE base,
# ghcr.io/vincentsarago/uvicorn-gunicorn (recette officielle titiler), est
# multi-arch — le blocage est une lacune de publication côté devseed, pas
# une limite technique GDAL/rasterio (rasterio 1.5.1 publie des wheels
# manylinux_2_28_aarch64 sur PyPI : pas de compilation requise ici).
#
# Épinglage par version PyPI plutôt que COPY src/titiler/ + build depuis les
# sources (comme le fait l'amont) : plus simple à maintenir dans ce dépôt,
# comportement runtime identique — titiler.application.main:app est le même
# point d'entrée. Coût de possession assumé : une future montée de version
# de titiler en amont nécessitera de rebasculer à la main ces 4 numéros de
# version — même modèle que deploy/postgis/Dockerfile (pgvector/wal2json).
ARG PYTHON_VERSION=3.11
FROM ghcr.io/vincentsarago/uvicorn-gunicorn:${PYTHON_VERSION}
RUN python -m pip install -U pip
RUN python -m pip install --no-cache-dir \
      "titiler.core==0.18.4" \
      "titiler.extensions[cogeo,stac]==0.18.4" \
      "titiler.mosaic==0.18.4" \
      "titiler.application==0.18.4"
ENV MODULE_NAME=titiler.application.main
ENV VARIABLE_NAME=app
```

(Forme `ENV KEY=value`, pas `ENV KEY value` : la forme historique du spec déclenche un avertissement `LegacyKeyValueFormat` de BuildKit — confirmé en construisant ce Dockerfile pendant l'écriture de ce plan. Comportement runtime strictement identique.)

- [ ] **Step 2: Écrire le garde-fou de contenu (test qui échoue tant que le fichier n'existe pas)**

Dans `core/tests/test_deployability.py`, ajouter la constante (à côté de `POSTGIS_DOCKERFILE` posée en Task 1) :

```python
TITILER_DOCKERFILE = REPO / "deploy" / "titiler" / "Dockerfile"
```

Et la fonction de test (à côté de `test_postgis_dockerfile_uses_multiarch_base_with_pgdg_packages`) :

```python
def test_titiler_dockerfile_pins_the_currently_deployed_version():
    """deploy/titiler/Dockerfile rapatrie EXACTEMENT la version consommée
    aujourd'hui (0.18.4) depuis la recette officielle (base
    ghcr.io/vincentsarago/uvicorn-gunicorn) — ce chantier ne monte pas de
    version titiler, il change seulement sa publication (image tierce
    mono-arch -> construite par nous, multi-arch)."""
    text = TITILER_DOCKERFILE.read_text()
    assert "ghcr.io/vincentsarago/uvicorn-gunicorn" in text, (
        "deploy/titiler/Dockerfile doit repartir de la même base que la "
        "recette officielle titiler (multi-arch)."
    )
    for package in (
        "titiler.core==0.18.4",
        "titiler.extensions[cogeo,stac]==0.18.4",
        "titiler.mosaic==0.18.4",
        "titiler.application==0.18.4",
    ):
        assert package in text, f"deploy/titiler/Dockerfile doit épingler {package}"
```

Run: `cd core && uv run pytest tests/test_deployability.py::test_titiler_dockerfile_pins_the_currently_deployed_version -v`
Expected (avant le Step 1 si vous testez l'ordre strict, ou si vous exécutez ce test avant d'avoir créé le fichier) : `FAILED` — `FileNotFoundError`. Une fois le Step 1 fait : `PASSED`.

- [ ] **Step 3: Câbler `docker-compose.yml`**

Le service `titiler` (aux alentours de la ligne 162-163) déclare aujourd'hui :

```yaml
  titiler:
    image: ghcr.io/developmentseed/titiler:0.18.4
```

Remplacer uniquement cette ligne `image:` par :

```yaml
  titiler:
    build: ./deploy/titiler
```

Tout le reste du service (`environment:`, `ports:`, `healthcheck:`, `labels:`, lignes ~164-215) reste **inchangé** — la configuration runtime ne change pas, seule la provenance de l'image change.

- [ ] **Step 4: Câbler `docker-compose.prod.yml`**

Le service `titiler` (lignes 65-79) déclare aujourd'hui :

```yaml
  titiler:
    restart: unless-stopped
    ports: !reset []
```

Insérer `image:`/`build: !reset null` juste après l'en-tête du service (même patron que `postgis` juste au-dessus dans ce fichier) :

```yaml
  titiler:
    image: ghcr.io/tlenenao/geostudio-titiler:${GEOSTUDIO_VERSION:-latest}
    build: !reset null
    restart: unless-stopped
    ports: !reset []
```

Le reste du bloc (`labels: !override` et ses 6 lignes) reste inchangé.

- [ ] **Step 5: Lancer les 3 gardes-fous génériques existants, vérifier qu'ils échouent**

Ces trois tests existent déjà dans `core/tests/test_deployability.py` (aucune modification requise sur leur code) — ils vérifient une propriété générique (tout `build:` a une image publiée ; toute image GHCR référencée est publiée ; tout `build:` de base est substitué en prod) qui échoue tant que `release.yml` ne connaît pas encore `geostudio-titiler` :

Run: `cd core && uv run pytest tests/test_deployability.py -k "test_every_build_service_has_a_released_image or test_prod_overlay_substitutes_every_build_with_an_image" -v`
Expected: `FAILED` sur les deux — `test_every_build_service_has_a_released_image` rapporte `{'docker-compose.yml:titiler': ('./deploy/titiler', 'Dockerfile')}` manquant ; `test_prod_overlay_substitutes_every_build_with_an_image` rapporte `titiler` dans `not_substituted` (si le Step 4 n'a pas encore été fait) ou passe déjà (si le Step 4 est fait avant ce Step 5 — dans ce cas seul le premier test reste rouge, ce qui est attendu).

- [ ] **Step 6: Ajouter l'entrée de matrice dans `.github/workflows/release.yml`**

Dans le job `build-and-push`, la matrice (`strategy.matrix.include`, à partir de la ligne ~95) liste aujourd'hui `geostudio-core`, `geostudio-shell`, `geostudio-postgis`, `geostudio-appexport-standalone`, puis (après le commentaire SP-21) `geostudio-export-worker`, `geostudio-qgis-worker`, `geostudio-appexport-runtime-builder`, `geostudio-backup`. Insérer une nouvelle entrée juste après `geostudio-postgis` :

```yaml
          - image: geostudio-postgis
            context: ./deploy/postgis
            dockerfile: Dockerfile
          - image: geostudio-titiler
            context: ./deploy/titiler
            dockerfile: Dockerfile
          - image: geostudio-appexport-standalone
```

(Le champ `platforms:` sur chaque entrée — y compris celle-ci — est ajouté par la Task 4, qui touche les 9 entrées en une seule fois. Ne pas l'ajouter ici : cette étape ne fait que rendre `geostudio-titiler` connu de la matrice.)

- [ ] **Step 7: Relancer les gardes-fous, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_deployability.py -k "test_every_build_service_has_a_released_image or test_every_referenced_ghcr_image_is_released or test_prod_overlay_substitutes_every_build_with_an_image or test_titiler_dockerfile_pins_the_currently_deployed_version" -v`
Expected: 4 `PASSED`.

- [ ] **Step 8: Vérification réelle — build + smoke test `/healthz`**

Run:
```bash
docker build -t geostudio-titiler-ci:latest ./deploy/titiler
docker run -d --name titiler-plan-check -e PORT=8000 -p 18000:8000 geostudio-titiler-ci:latest
for i in $(seq 1 15); do curl -sf http://127.0.0.1:18000/healthz && break; sleep 2; done
curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:18000/healthz
docker rm -f titiler-plan-check
```
Expected: `{"ping":"pong!"}` puis `HTTP 200`.

- [ ] **Step 9: Vérifier la configuration compose résolue**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -A2 "^  titiler:"`
Expected: le bloc `titiler:` montre `image: ghcr.io/tlenenao/geostudio-titiler:latest` (résolu, `GEOSTUDIO_VERSION` non défini) — **aucune** occurrence de `ghcr.io/developmentseed/titiler` nulle part dans la sortie complète (`docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep developmentseed` ne doit rien renvoyer).

- [ ] **Step 10: Commit**

```bash
git add deploy/titiler/Dockerfile docker-compose.yml docker-compose.prod.yml \
  .github/workflows/release.yml core/tests/test_deployability.py
git commit -m "feat(deploy): construit titiler depuis la recette officielle (multi-arch)"
```

---

### Task 3: `deploy/backup/Dockerfile` — client `mc` multi-arch, sans régression de licence

**Files:**
- Modify: `deploy/backup/Dockerfile`
- Test: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: rien.
- Produces: rien de consommé par une tâche ultérieure de ce plan (tâche indépendante).

- [ ] **Step 1: Écrire le garde-fou (test qui échoue)**

Dans `core/tests/test_deployability.py`, `BACKUP_DOCKERFILE` est déjà déclaré (ligne ~1458 : `BACKUP_DOCKERFILE = REPO / "deploy" / "backup" / "Dockerfile"`) — pas de nouvelle constante nécessaire. Ajouter la fonction de test à côté des tests existants qui utilisent `BACKUP_DOCKERFILE` :

```python
def test_backup_dockerfile_downloads_mc_per_target_arch_from_agpl_source():
    """Portage arm64 : deploy/backup/Dockerfile téléchargeait le client MinIO
    `mc` depuis une URL mono-arch codée en dur (.../linux-amd64/mc) — et,
    trouvaille indépendante de l'arch, cette URL précise renvoie aujourd'hui
    410 Gone pour LES DEUX architectures (dl.min.io a changé de schéma
    d'URL, confirmé le 2026-09-17). Le remplacement naïf
    dl.min.io/aistor/mc/release/linux-{arch}/mc répond 200 mais sert un
    binaire qui s'identifie lui-même « MinIO Enterprise License » — pas
    AGPL, en contradiction avec LICENSE-BACKUP.md et le LABEL
    org.opencontainers.image.licenses de cette image. Le correctif utilise
    $TARGETARCH (fourni par buildx) ET pointe vers les assets GitHub
    Releases de minio/mc, toujours publiés sous AGPLv3 (vérifié :
    `mc --version` y affiche `License GNU AGPLv3`)."""
    text = BACKUP_DOCKERFILE.read_text()
    assert "TARGETARCH" in text, (
        "deploy/backup/Dockerfile doit déclarer et utiliser $TARGETARCH "
        "pour choisir le binaire mc de la bonne architecture."
    )
    assert "dl.min.io" not in text, (
        "dl.min.io/client/... ne sert plus les binaires mc attendus ici "
        "(410 Gone) — et son chemin de remplacement /aistor/ sert un "
        "binaire sous licence propriétaire, pas AGPL. Utiliser les GitHub "
        "Releases de minio/mc à la place."
    )
    assert "github.com/minio/mc/releases/download" in text, (
        "deploy/backup/Dockerfile doit télécharger mc depuis les GitHub "
        "Releases de minio/mc (toujours AGPL)."
    )
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_deployability.py::test_backup_dockerfile_downloads_mc_per_target_arch_from_agpl_source -v`
Expected: `FAILED` — `AssertionError: deploy/backup/Dockerfile doit déclarer et utiliser $TARGETARCH...`

- [ ] **Step 3: Modifier `deploy/backup/Dockerfile`**

Le fichier contient aujourd'hui (juste après le commentaire expliquant que `mc` est le client MinIO, pas Midnight Commander) :

```dockerfile
RUN apk add --no-cache postgresql16-client age curl jq bash tzdata python3 \
  && curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
  && chmod +x /usr/local/bin/mc
```

Remplacer par :

```dockerfile
# TARGETARCH (auto-fourni par buildx : linux/amd64 -> "amd64", linux/arm64
# -> "arm64") choisit le binaire mc de la bonne architecture. Épinglé aux
# GitHub Releases de minio/mc plutôt qu'à dl.min.io/client/... : cette
# dernière URL renvoie 410 Gone pour les DEUX architectures depuis que
# MinIO a changé de schéma de distribution (dl.min.io/aistor/... existe
# mais sert un binaire "MinIO Enterprise License", incompatible avec la
# notice AGPL de cette image, cf. LICENSE-BACKUP.md). Les GitHub Releases
# du dépôt minio/mc restent sous AGPLv3 (vérifié : `mc --version` y affiche
# `License GNU AGPLv3`) — même modèle d'épinglage par version que
# deploy/postgis/Dockerfile et deploy/titiler/Dockerfile : une future
# release mc nécessitera de rebasculer MC_RELEASE à la main.
ARG TARGETARCH
ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
RUN apk add --no-cache postgresql16-client age curl jq bash tzdata python3 \
  && curl -sSL "https://github.com/minio/mc/releases/download/${MC_RELEASE}/mc.linux-${TARGETARCH}.${MC_RELEASE}" -o /usr/local/bin/mc \
  && chmod +x /usr/local/bin/mc
```

- [ ] **Step 4: Relancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_deployability.py::test_backup_dockerfile_downloads_mc_per_target_arch_from_agpl_source -v`
Expected: `PASSED`

- [ ] **Step 5: Vérification réelle — build natif + licence affichée**

Run:
```bash
docker build -t geostudio-backup-ci:latest ./deploy/backup
docker run --rm --entrypoint /usr/local/bin/mc geostudio-backup-ci:latest --version
```
Expected : une ligne `mc version RELEASE.2025-08-13T08-35-41Z (...)`, une ligne `Runtime: go... linux/<arch native de la machine>`, et **`License GNU AGPLv3 <https://www.gnu.org/licenses/agpl-3.0.html>`** (pas « MinIO Enterprise License »).

Si un builder buildx multi-plateforme est disponible, répéter avec `docker buildx build --platform linux/arm64 -t geostudio-backup-ci:latest --load ./deploy/backup` puis le même `docker run --rm --platform linux/arm64 --entrypoint /usr/local/bin/mc geostudio-backup-ci:latest --version` — déjà vérifié une fois lors de l'écriture de ce plan (`Runtime: go1.24.6 linux/arm64`, `License GNU AGPLv3`).

- [ ] **Step 6: Commit**

```bash
git add deploy/backup/Dockerfile core/tests/test_deployability.py
git commit -m "fix(deploy): backup télécharge mc par arch cible depuis les releases AGPL de minio/mc"
```

---

### Task 4: `.github/workflows/release.yml` — matrice multi-arch + porte arm64 native

**Files:**
- Modify: `.github/workflows/release.yml`
- Test: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: `deploy/titiler/` (Task 2), `deploy/postgis/Dockerfile` rebasé (Task 1).
- Produces: rien de consommé par une tâche ultérieure de ce plan (dernière tâche technique avant la clôture, Task 5).

- [ ] **Step 1: Écrire les 4 gardes-fous (tests qui échouent)**

Dans `core/tests/test_deployability.py`, ajouter ces 4 fonctions à côté de `test_release_gate_starts_postgres_like_ci` (qui définit déjà l'helper réutilisé ici, `_postgres_run_flags`) :

```python
def test_release_matrix_declares_multiarch_platforms_except_qgis_worker():
    """Portage arm64 : chaque entrée de la matrice build-and-push doit
    déclarer `platforms: linux/amd64,linux/arm64` — sauf
    `geostudio-qgis-worker` (base qgis/qgis:release-3_34 mono-arch amd64,
    image 11 Go), qui doit rester `linux/amd64` seul. Sans ce garde-fou, un
    futur ajout d'entrée de matrice pourrait silencieusement omettre
    `platforms:` (docker/build-push-action retombe alors sur l'arch native
    du runner seule, amd64)."""
    matrix = release_matrix()
    missing = [e["image"] for e in matrix if not e.get("platforms")]
    assert not missing, f"entrées de matrice sans `platforms:` : {missing}"
    by_image = {e["image"]: e["platforms"] for e in matrix}
    qgis = by_image.pop("geostudio-qgis-worker", None)
    assert qgis == "linux/amd64", (
        "geostudio-qgis-worker doit rester linux/amd64 seul (base "
        f"mono-arch), trouvé : {qgis!r}"
    )
    not_multiarch = {
        img: plats for img, plats in by_image.items() if plats != "linux/amd64,linux/arm64"
    }
    assert not not_multiarch, f"entrées non multi-arch (hors qgis-worker) : {not_multiarch}"


def test_build_and_push_needs_both_test_gates():
    """`build-and-push` ne doit publier qu'après le succès des DEUX portes de
    test — amd64 (`test-gate`) ET arm64 (`test-gate-arm64`, ce chantier).
    Sans ceci, une image cassée sur arm64 (postgis/titiler) pourrait être
    publiée dès que la seule porte amd64 est verte."""
    doc = yaml.safe_load(RELEASE.read_text())
    needs = doc["jobs"]["build-and-push"]["needs"]
    needed = {needs} if isinstance(needs, str) else set(needs)
    assert needed == {"test-gate", "test-gate-arm64"}, (
        f"build-and-push.needs = {needs!r}, attendu test-gate ET test-gate-arm64"
    )


def test_release_gate_arm64_runs_on_native_arm_runner():
    """`test-gate-arm64` doit tourner sur `ubuntu-24.04-arm` (runner GitHub
    natif, gratuit pour les dépôts publics) — jamais sous émulation QEMU,
    qui ne prouverait rien de fiable sur le comportement réel de
    Postgres/PostGIS (temporisations, I/O). Vérifie aussi la présence d'une
    fumée titiler (`/healthz`) sur ce même job."""
    doc = yaml.safe_load(RELEASE.read_text())
    job = doc["jobs"].get("test-gate-arm64")
    assert job is not None, "release.yml n'a plus de job `test-gate-arm64`"
    assert job.get("runs-on") == "ubuntu-24.04-arm", (
        f"test-gate-arm64 tourne sur {job.get('runs-on')!r}, attendu "
        "'ubuntu-24.04-arm' (runner natif)."
    )
    runs = " ".join(st.get("run", "") for st in job["steps"])
    assert "healthz" in runs, (
        "test-gate-arm64 n'a plus de fumée titiler (aucune étape n'appelle "
        "/healthz)."
    )


def test_release_gate_arm64_starts_postgres_like_ci():
    """Miroir arm64 de `test_release_gate_starts_postgres_like_ci` : la
    porte arm64 doit démarrer Postgres avec au moins les réglages du job
    `core` de ci.yml, pour la même raison (sinon elle n'exécute pas les
    mêmes tests que la CI amd64)."""
    ci_flags = _postgres_run_flags(CI, "core")
    release_flags = _postgres_run_flags(RELEASE, "test-gate-arm64")
    missing = ci_flags - release_flags
    assert not missing, (
        "release.yml (test-gate-arm64) démarre Postgres sans les réglages "
        f"que ci.yml (core) lui donne : {sorted(missing)}."
    )
```

- [ ] **Step 2: Lancer les 4 tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_deployability.py -k "arm64 or multiarch_platforms or needs_both_test_gates" -v`
Expected: 4 `FAILED` — `test_release_matrix_declares_multiarch_platforms_except_qgis_worker` rapporte que toutes les entrées manquent `platforms:` ; les 3 autres échouent en `AssertionError`/`KeyError` (`build-and-push.needs` vaut encore `"test-gate"` seul, le job `test-gate-arm64` n'existe pas).

- [ ] **Step 3: Ajouter `platforms:` à chaque entrée de la matrice**

Dans `.github/workflows/release.yml`, la section `strategy.matrix.include` du job `build-and-push` compte désormais 9 entrées (8 + `geostudio-titiler` posée en Task 2). Réécrire cette section pour ajouter `platforms:` à chacune :

```yaml
      matrix:
        include:
          - image: geostudio-core
            context: ./core
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-shell
            context: ./shell
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-postgis
            context: ./deploy/postgis
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-titiler
            context: ./deploy/titiler
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-appexport-standalone
            context: .
            dockerfile: deploy/appexport-standalone/Dockerfile
            platforms: linux/amd64,linux/arm64
          # SP-21 : ces quatre images existaient uniquement en `build:` dans
          # le compose — donc introuvables au déploiement. `context` et
          # `dockerfile` doivent correspondre **exactement** aux valeurs du
          # compose : c'est ce couple que vérifie
          # tests/test_deployability.py::test_every_build_service_has_a_released_image.
          - image: geostudio-export-worker
            context: ./core
            dockerfile: ../deploy/export-worker/Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-qgis-worker
            context: ./deploy/qgis-worker
            dockerfile: Dockerfile
            # Base qgis/qgis:release-3_34 mono-arch (probable amd64 seul),
            # image 11 Go — hors périmètre du portage arm64.
            platforms: linux/amd64
          - image: geostudio-appexport-runtime-builder
            context: .
            dockerfile: deploy/appexport-runtime-builder/Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-backup
            context: ./deploy/backup
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
```

- [ ] **Step 4: Câbler QEMU + `platforms:` sur l'étape de build**

Toujours dans le job `build-and-push`, juste avant `- uses: docker/setup-buildx-action@v4`, ajouter :

```yaml
      - uses: docker/setup-qemu-action@v4
```

Puis, dans l'étape `docker/build-push-action@v7`, ajouter `platforms:` :

```yaml
      - uses: docker/build-push-action@v7
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.context }}/${{ matrix.dockerfile }}
          platforms: ${{ matrix.platforms }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

- [ ] **Step 5: Ajouter le job `test-gate-arm64`**

Juste après la fin du job `test-gate` (après l'étape `Shell tests`, avant `build-and-push:`), insérer :

```yaml
  test-gate-arm64:
    # Duplique test-gate sur un runner arm64 NATIF (gratuit pour les dépôts
    # publics) — pas seulement une vérification que le build buildx aboutit
    # (ça, c'est le rôle de build-and-push sous QEMU), mais
    # Postgres/PostGIS/pgvector/wal2json réellement démarrés et exercés par
    # la suite de tests sur du vrai matériel arm64. Contrairement à
    # build-and-push, une exécution de tests sous émulation QEMU ne
    # prouverait rien de fiable (temporisations, I/O, JIT).
    #
    # Le volet shell (Vitest/Playwright/`npm run build`) n'est PAS dupliqué
    # ici : JS/TS pur, aucune dépendance native, le job amd64 (test-gate)
    # suffit à le garantir.
    runs-on: ubuntu-24.04-arm
    steps:
      - uses: actions/checkout@v7

      - name: Build postgis+pgvector image
        run: docker build -t geostudio-postgis-ci:latest ./deploy/postgis

      - name: Start Postgres
        run: |
          docker run -d --name ci-postgres \
            -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis \
            -p 5432:5432 geostudio-postgis-ci:latest \
            -c wal_level=logical \
            -c output_plugin_libraries=wal2json,pgoutput,test_decoding
          for i in $(seq 1 30); do
            docker exec ci-postgres pg_isready -U gis && break
            sleep 2
          done

      - uses: astral-sh/setup-uv@v7

      - name: Migrations up/down
        working-directory: core
        env:
          DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
        run: |
          uv sync
          uv run alembic upgrade head
          uv run alembic downgrade base

      - name: Core tests
        working-directory: core
        env:
          CORE_TEST_DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
        run: |
          uv run pytest
          uv run lint-imports

      - name: Stop Postgres
        if: always()
        run: docker rm -f ci-postgres

      - name: Build + smoke-test titiler (arm64)
        run: |
          docker build -t geostudio-titiler-ci:latest ./deploy/titiler
          docker run -d --name ci-titiler -e PORT=8000 -p 8000:8000 geostudio-titiler-ci:latest
          for i in $(seq 1 30); do
            curl -sf http://127.0.0.1:8000/healthz && break
            sleep 2
          done
          curl -sf http://127.0.0.1:8000/healthz
          docker rm -f ci-titiler
```

- [ ] **Step 6: Étendre `build-and-push.needs`**

Remplacer :

```yaml
  build-and-push:
    needs: test-gate
```

par :

```yaml
  build-and-push:
    needs: [test-gate, test-gate-arm64]
```

- [ ] **Step 7: Relancer les 4 tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_deployability.py -k "arm64 or multiarch_platforms or needs_both_test_gates" -v`
Expected: 4 `PASSED`.

- [ ] **Step 8: Valider la syntaxe du workflow**

Run: `cd /home/lenen/projets/geostudio && uvx --from actionlint-py actionlint .github/workflows/release.yml`
Expected: aucune sortie, code de sortie 0 (déjà vérifié comme baseline propre avant ce plan).

- [ ] **Step 9: Relancer toute la suite `test_deployability.py`**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: tous `PASSED` (y compris les 3 gardes-fous génériques déjà existants, réutilisés par la Task 2, et les 8 nouveaux gardes-fous des Tasks 1-4).

- [ ] **Step 10: Commit**

```bash
git add .github/workflows/release.yml core/tests/test_deployability.py
git commit -m "feat(ci): publie les images en multi-arch, porte de tests arm64 native"
```

---

### Task 5: Clôture — suite complète, config résolue, documentation

**Files:**
- Modify: `CLAUDE.md` (section `### Livré`)
- (Vérification seule, aucune autre modification) `core/tests/test_deployability.py`, `docker-compose.yml` + `docker-compose.prod.yml`

**Interfaces:**
- Consumes: le résultat des Tasks 1-4.
- Produces: rien (dernière tâche du plan).

- [ ] **Step 1: Suite complète `core`**

Run: `cd core && uv run pytest`
Expected: aucune régression sur les fichiers touchés par ce plan (`test_deployability.py` doit être entièrement vert ; un échec ailleurs, sans rapport avec `deploy/`, `docker-compose*.yml` ou `release.yml`, est pré-existant — vérifier avec `git diff origin/dev...HEAD --stat` que le fichier en échec n'est pas dans le diff de cette branche avant de l'imputer à ce plan, cf. piège CLAUDE.md n°9/n°12).

- [ ] **Step 2: Portes de qualité**

Run:
```bash
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```
Expected: tout vert (ce plan ne touche aucun fichier `.py` de logique applicative — seulement des tests dans `test_deployability.py` — donc aucune raison de régression ici).

- [ ] **Step 3: Config compose résolue — aucune trace de l'image tierce titiler**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -c developmentseed`
Expected: `0`

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -A2 "^  titiler:"`
Expected: `image: ghcr.io/tlenenao/geostudio-titiler:latest` (pas de `build:` résiduel).

- [ ] **Step 4: Documenter la clôture dans `CLAUDE.md`**

Dans `CLAUDE.md`, section `### Livré`, ajouter une entrée à la fin de la liste (même patron que les entrées non-SP déjà présentes, ex. « OperationContract », « IPC d'échange DuckDB↔Arrow ») :

```markdown
- **Portage arm64 multi-arch** — ferme le préalable générique à tout hôte
  arm64 (évaluation Oracle Cloud Ampere A1 Flex, hors périmètre de ce
  chantier) identifié par `docs/superpowers/specs/2026-09-15-portage-
  arm64-multiarch-design.md` : `deploy/postgis/Dockerfile` rebasé sur
  `postgres:16-bookworm` (multi-arch) + 4 paquets PGDG installés
  nous-mêmes (élimine au passage le flake `bullseye-security`) ;
  `deploy/titiler/Dockerfile` (nouveau) rapatrie la recette officielle de
  titiler 0.18.4 au lieu de consommer l'image tierce mono-arch
  `ghcr.io/developmentseed/titiler` ; `.github/workflows/release.yml`
  publie désormais les 8 images concernées (toutes sauf
  `geostudio-qgis-worker`, base mono-arch) en `linux/amd64,linux/arm64`
  via `docker/setup-qemu-action`, et un nouveau job `test-gate-arm64` fait
  tourner Postgres/PostGIS/pgvector/wal2json + la suite pytest complète
  sur un runner `ubuntu-24.04-arm` **natif** avant toute publication.
  **Trouvaille hors périmètre initial, corrigée dans le même geste** :
  `deploy/backup/Dockerfile` téléchargeait son client MinIO `mc` depuis une
  URL (`dl.min.io/client/mc/release/linux-amd64/mc`) qui répond 410 Gone
  pour les deux architectures depuis un changement de schéma de
  distribution côté MinIO ; le remplacement naïf (`dl.min.io/aistor/...`)
  sert un binaire sous licence propriétaire (« MinIO Enterprise
  License »), incompatible avec `LICENSE-BACKUP.md`/le `LABEL` AGPL déjà
  posés sur cette image — corrigé en pointant vers les GitHub Releases de
  `minio/mc`, toujours publiées sous AGPLv3, avec sélection de l'archive
  par `$TARGETARCH`. Risques du design (extension DuckDB communautaire
  `h3`, Playwright/Chromium) vérifiés levés empiriquement sous émulation
  QEMU réelle avant d'écrire le plan d'exécution — pas supposés. **Reste
  hors périmètre, assumé** : le provisioning Oracle Cloud lui-même
  (réseau, TLS, runbook, sizing) — chantier séparé, consommateur de
  celui-ci ; `docker manifest inspect` sur les 8 images après un vrai tag
  de release n'a pas pu être vérifié depuis cette session (nécessite un
  `git tag`/push réel, action à déclencher délibérément par Tanguy, hors
  du périmètre d'une session d'exécution de plan).
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôture du portage arm64 multi-arch"
```

- [ ] **Step 6: Note pour la suite (pas une action de ce plan)**

Le critère de validation §5 du spec (« `docker manifest inspect ghcr.io/tlenenao/geostudio-<image>:<tag>` porte amd64 et arm64 ») ne peut être vérifié qu'après un vrai `git tag vX.Y.Z && git push origin vX.Y.Z` déclenchant `release.yml` en conditions réelles sur GitHub Actions — action irréversible qui publie de vraies images, à ne déclencher qu'avec l'accord explicite de Tanguy, hors du périmètre de cette session d'exécution de plan.

---

## Self-Review (fait par l'auteur du plan)

**1. Couverture du spec** — chaque section a une tâche :
- §2.1 (postgis) → Task 1.
- §2.2 (titiler) → Task 2.
- §2.3 (backup, correctif $TARGETARCH) → Task 3 (+ bug de licence trouvé et corrigé au passage).
- §2.4 (matrice release.yml, QEMU, platforms) → Task 4, Steps 1-6.
- §2.5 (test-gate-arm64 natif + fumée titiler) → Task 4, Step 5.
- §3 (périmètre : qgis-worker exclu, titiler pas monté en version, martin/keycloak/etc. non touchés) → respecté explicitement dans Task 4 Step 3 (commentaire qgis-worker) et Task 2 (titiler épinglé 0.18.4) ; aucune tâche ne touche martin/keycloak/minio/pgbouncer/traefik/otel-lgtm.
- §4 (risques) → h3/Playwright vérifiés empiriquement avant l'écriture du plan (section dédiée en tête) ; `test_deployability.py` étendu (Task 2 Step 5-7, Task 4 Step 1-2) ; durée de `build-and-push` acceptée comme coût, aucune action requise.
- §5 (plan de validation) → chaque critère mappé à un test automatisé (Tasks 1-4) sauf le `docker manifest inspect` post-tag réel, explicitement documenté comme hors périmètre d'exécution de plan (Task 5 Step 6).

**2. Scan de placeholders** — aucun "TBD"/"à compléter" ; chaque step de code contient le contenu réel (Dockerfiles complets, diff YAML complets, code Python complet des 8 nouveaux tests) ; chaque commande a une sortie attendue concrète, tirée de vérifications réellement exécutées pendant l'écriture de ce plan (pas supposée).

**3. Cohérence des types/noms** — `POSTGIS_DOCKERFILE`/`TITILER_DOCKERFILE` (Tasks 1-2) et `BACKUP_DOCKERFILE` (Task 3, déjà existant) utilisés de façon cohérente ; les 4 noms de test de la Task 4 (`test_release_matrix_declares_multiarch_platforms_except_qgis_worker`, `test_build_and_push_needs_both_test_gates`, `test_release_gate_arm64_runs_on_native_arm_runner`, `test_release_gate_arm64_starts_postgres_like_ci`) réutilisent l'helper `_postgres_run_flags` et la fonction `release_matrix()` déjà définis plus haut dans le fichier — aucune redéfinition, aucune divergence de signature.
