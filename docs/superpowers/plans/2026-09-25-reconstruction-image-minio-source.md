# Reconstruction de l'image MinIO depuis les sources AGPL — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer `quay.io/minio/minio` (verrouillé en pull anonyme sur
quay.io **et** Docker Hub, vérifié le 2026-09-25) par une image `minio`
reconstruite depuis les sources AGPL-3.0 officielles (`github.com/minio/minio`),
publiée par notre CI comme `ghcr.io/tlenenao/geostudio-minio`, sans aucun
changement de comportement applicatif côté `core/app/*`.

**Architecture:** Nouveau `deploy/minio/Dockerfile` multi-stage (build
`golang:1.24-bookworm` reproduisant la cible `build` du Makefile amont, puis
runtime `debian:bookworm-slim`) — même patron que `deploy/postgis` et
`deploy/titiler` (rapatrier une recette officielle cassée par sa propre
distribution). `docker-compose.yml` bascule de `image:` à `build:
./deploy/minio` ; `docker-compose.prod.yml` gagne `image:
ghcr.io/tlenenao/geostudio-minio:${GEOSTUDIO_VERSION:-latest}` + `build: !reset
null`, comme `postgis`. La matrice CI (`_build-and-push.yml`, source unique
partagée par `release.yml` et `publish-edge.yml`) gagne une 9e image.

**Tech Stack:** Docker multi-stage build, Go 1.24 (module `minio/minio`,
sans CGO), Debian bookworm, GitHub Actions (matrice réutilisable), pytest
(`core/tests/test_deployability.py`, garde-fous source-only sans conteneur).

## Global Constraints

- Version épinglée : **`RELEASE.2025-10-15T17-29-55Z`** (dernière release
  amont au moment de ce design, corrige un CVE réel) — PAS
  `RELEASE.2025-09-07T16-13-09Z` (version actuellement pinnée mais avec un
  CVE connu).
- Reproduire EXACTEMENT la cible `build` du Makefile amont (`CGO_ENABLED=0
  GOARCH=$TARGETARCH go build -tags kqueue -trimpath --ldflags "$(go run
  buildscripts/gen-ldflags.go)" -o ...`). Ne jamais repartir du `Dockerfile`
  top-level de l'amont (`FROM minio/minio:latest`, circulaire) ni de
  `Dockerfile.release` (télécharge depuis `dl.min.io`, mort — même rupture
  déjà rencontrée sur `mc`, cf. `deploy/backup/Dockerfile`).
- Stage de build : `golang:1.24-bookworm` (multi-arch, cohérent avec
  `postgres:16-bookworm` déjà choisi pour `deploy/postgis`). Stage runtime :
  `debian:bookworm-slim` + `ca-certificates` + `curl` (healthcheck existant
  inchangé : `curl -f http://localhost:9000/minio/health/live`).
- Licence : `LICENSE` + `CREDITS` du dépôt source copiés dans l'image
  (`/licenses/`), documentés dans `deploy/minio/LICENSE-MINIO.md` — même
  patron que `deploy/backup/LICENSE-BACKUP.md`, mais analyse AGPL §13
  différente : ce conteneur EST le service réseau AGPL exposé (pas un
  binaire invoqué en sous-processus comme `mc`).
- Matrice de publication : une seule source de vérité,
  `.github/workflows/_build-and-push.yml` — jamais recopiée dans
  `release.yml` ou `publish-edge.yml`.
- Aucun changement de `.env.example` (aucune variable liée au tag/registre
  MinIO n'y est exposée aujourd'hui).
- Hors périmètre (ne pas toucher dans ce plan) : migration vers SeaweedFS ou
  Garage ; nettoyage de la dérive documentaire préexistante sur
  `geostudio-qgis-worker` dans `docs/ops/redistribution-images.md` ; tout
  changement du modèle de licence global du produit ; tout changement de
  code applicatif `core/app/*` (l'API S3 générique qu'il consomme est
  inchangée).
- Vérifié en préparant ce plan (build réel, pas de confiance dans le texte
  du design) : `golang:1.24-bookworm` embarque déjà `git` (image
  `buildpack-deps`) — pas besoin de l'installer ; `go build -o /out/minio`
  crée `/out/` lui-même, pas besoin de `mkdir` préalable ; sans la variable
  d'environnement `MINIO_RELEASE=RELEASE` (distincte de l'ARG Docker de même
  nom), `minio --version` affiche `DEVELOPMENT.2025-10-15T17-29-55Z` au lieu
  de `RELEASE.2025-10-15T17-29-55Z` — cosmétique mais trompeur en
  diagnostic d'incident, corrigé en fixant cette variable au moment du
  build.

---

## Task 1 — `deploy/minio/Dockerfile` + notice de licence

**Files:**
- Create: `deploy/minio/Dockerfile`
- Create: `deploy/minio/LICENSE-MINIO.md`
- Modify: `core/tests/test_deployability.py` (nouvelle constante
  `MINIO_DOCKERFILE`, nouveau test)

**Interfaces:**
- Consumes: rien (première tâche du plan).
- Produces: `deploy/minio/Dockerfile` qui construit un exécutable
  `/usr/bin/minio` fonctionnellement équivalent à
  `quay.io/minio/minio:RELEASE.2025-10-15T17-29-55Z`, healthcheck compatible
  sur `9000` (`/minio/health/live`) et console sur `9001` — consommé par
  Task 3 (`docker-compose.yml: build: ./deploy/minio`) et par Task 2 (entrée
  de matrice CI `context: ./deploy/minio`, `dockerfile: Dockerfile`).

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_deployability.py`, ajouter la constante à côté de
`TITILER_DOCKERFILE` (ligne 81) :

```python
TITILER_DOCKERFILE = REPO / "deploy" / "titiler" / "Dockerfile"
MINIO_DOCKERFILE = REPO / "deploy" / "minio" / "Dockerfile"
```

Puis ajouter le test, par exemple juste après
`test_titiler_dockerfile_pins_the_currently_deployed_version` (ligne 291) :

```python
def test_minio_dockerfile_builds_from_pinned_agpl_source_not_broken_upstream_recipes():
    """quay.io/minio/minio (401 sur TOUS les tags, sur quay.io ET Docker
    Hub, vérifié le 2026-09-25) est totalement injoignable en pull anonyme
    — la propre distribution binaire de MinIO (dl.min.io) répond aussi 410
    Gone (même rupture que celle déjà rencontrée sur `mc`, cf.
    deploy/backup/Dockerfile). La cible `make docker` de l'amont est
    elle-même cassée : son Dockerfile top-level fait `FROM
    minio/minio:latest` (circulaire — dépend du dépôt verrouillé) et son
    Dockerfile.release télécharge depuis dl.min.io (mort). Seule la cible
    Makefile `build` (un simple `go build` d'un module Go pur, sans
    dépendance à un registre) reste reproductible — c'est elle que ce
    Dockerfile doit reproduire, jamais `make docker`."""
    text = MINIO_DOCKERFILE.read_text()
    assert "github.com/minio/minio" in text, (
        "deploy/minio/Dockerfile doit cloner les sources officielles "
        "(github.com/minio/minio), pas une image binaire tierce."
    )
    assert re.search(r"RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z", text), (
        "deploy/minio/Dockerfile doit épingler un tag RELEASE.* précis, "
        "jamais une branche mouvante (main/master/latest)."
    )
    assert "dl.min.io" not in text, (
        "dl.min.io ne sert plus de binaire MinIO exploitable (410 Gone) — "
        "et y repointer a déjà cassé deploy/backup/Dockerfile une première "
        "fois (le remplacement /aistor/ sert une licence Enterprise, pas "
        "AGPL). Ne jamais y revenir."
    )
    assert "FROM minio/minio" not in text, (
        "le Dockerfile top-level de l'amont (FROM minio/minio:latest) est "
        "circulaire : il dépend du dépôt d'image verrouillé que ce "
        "Dockerfile a justement pour but de remplacer."
    )
    assert "-tags kqueue" in text and "go build" in text, (
        "deploy/minio/Dockerfile doit reproduire la cible `build` du "
        "Makefile amont (go build -tags kqueue ...), pas make docker."
    )
    assert "MINIO_RELEASE=RELEASE" in text, (
        "sans la variable d'environnement MINIO_RELEASE=RELEASE au moment "
        "du go build, minio --version affiche DEVELOPMENT.<tag> au lieu de "
        "RELEASE.<tag> — cosmétique mais trompeur en diagnostic d'incident "
        "(vérifié empiriquement en préparant ce plan)."
    )
```

- [ ] **Step 2: Vérifier que le test échoue**

```bash
cd core && uv run pytest tests/test_deployability.py -k test_minio_dockerfile_builds_from_pinned_agpl_source_not_broken_upstream_recipes -v
```

Attendu : ÉCHEC — `FileNotFoundError` (`deploy/minio/Dockerfile` n'existe
pas encore).

- [ ] **Step 3: Créer `deploy/minio/Dockerfile`**

```dockerfile
# deploy/minio/Dockerfile
# quay.io/minio/minio ET minio/minio (Docker Hub) sont verrouillés en pull
# anonyme sur TOUS les tags (401 Unauthorized / pull access denied,
# vérifié le 2026-09-25). La propre distribution binaire de MinIO
# (dl.min.io) répond aussi 410 Gone (même rupture déjà rencontrée sur
# `mc`, cf. deploy/backup/Dockerfile). Les recettes Docker officielles de
# l'amont sont elles-mêmes cassées : son Dockerfile top-level fait
# `FROM minio/minio:latest` (circulaire — dépend du dépôt verrouillé) et
# son Dockerfile.release télécharge depuis dl.min.io (mort). Seule sa
# cible Makefile `build` (un simple `go build` d'un module Go pur, sans
# dépendance à un registre ni à dl.min.io) reste reproductible — c'est
# elle que ce Dockerfile reproduit, PAS `make docker`.
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z

FROM golang:1.24-bookworm AS build
ARG MINIO_RELEASE
ARG TARGETARCH
WORKDIR /src
# MINIO_RELEASE=RELEASE (variable d'environnement lue par
# buildscripts/gen-ldflags.go, distincte de l'ARG Docker de même nom
# ci-dessus) fait porter au binaire un préfixe de version
# "RELEASE.<tag>" au lieu de "DEVELOPMENT.<tag>" par défaut — vérifié :
# sans cette variable, `minio --version` affiche
# DEVELOPMENT.2025-10-15T17-29-55Z. Cosmétique (le binaire est identique)
# mais trompeur en diagnostic d'incident ; l'amont ne publie pas la
# recette CI exacte qui positionne cette variable pour ses propres builds
# de release — reconstituée ici par lecture de
# buildscripts/gen-ldflags.go.
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio . \
    && MINIO_RELEASE=RELEASE CGO_ENABLED=0 GOARCH="${TARGETARCH}" \
       go build -tags kqueue -trimpath \
       --ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go)" \
       -o /out/minio

FROM debian:bookworm-slim
# ca-certificates : TLS sortant (un déploiement peut pointer ce MinIO en
# mode passerelle/réplication vers un vrai S3). curl : le healthcheck
# compose existant (curl -f .../minio/health/live) reste inchangé.
# Binaire standalone (CGO_ENABLED=0) : aucune autre dépendance runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/bin/minio
COPY --from=build /src/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
RUN chmod +x /usr/bin/minio /usr/bin/docker-entrypoint.sh

# Cette image DISTRIBUE ET EXPOSE COMME SERVICE RÉSEAU un binaire AGPL —
# contrairement à deploy/backup/Dockerfile (mc, invoqué en sous-processus,
# jamais servi sur le réseau), voir LICENSE-MINIO.md pour l'analyse
# complète de la clause réseau AGPL §13, qui s'applique directement ici.
COPY --from=build /src/LICENSE /licenses/LICENSE
COPY --from=build /src/CREDITS /licenses/CREDITS
COPY LICENSE-MINIO.md /LICENSE-MINIO.md
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Serveur MinIO (stockage objet S3) recompile depuis les sources AGPL officielles (github.com/minio/minio) car quay.io/minio/minio et minio/minio sont verrouilles en pull anonyme. Voir /LICENSE-MINIO.md."

EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio"]
```

- [ ] **Step 4: Créer `deploy/minio/LICENSE-MINIO.md`**

```markdown
# Licences des composants de cette image

Cette image est publiée par le projet GeoStudio (Apache-2.0) et **contient
et expose comme service réseau un logiciel sous GNU Affero GPL** (le
serveur MinIO lui-même) — pas seulement un composant embarqué invoqué en
sous-processus comme `mc` dans `deploy/backup/`.

## Composant copyleft réseau

- **Serveur MinIO** — code source cloné sans modification depuis
  `https://github.com/minio/minio`, tag `RELEASE.2025-10-15T17-29-55Z`
  (voir `deploy/minio/Dockerfile` pour le tag exact épinglé), compilé par
  la cible `build` du Makefile amont (`go build -tags kqueue ...`) plutôt
  que par les recettes Docker officielles, elles-mêmes cassées
  (`Dockerfile` top-level circulaire, `Dockerfile.release` dépendant de
  `dl.min.io`, mort). **AGPL-3.0-or-later**, licence du projet MinIO
  (serveur et client) depuis son passage intégral sous cette licence en
  2021 — vérifié sur le `LICENSE` du dépôt amont au tag exact utilisé
  (copié dans cette image sous `/licenses/LICENSE`, avec
  `/licenses/CREDITS`).

  **Contrairement au client `mc` embarqué par `deploy/backup/` (invoqué en
  sous-processus, jamais exposé sur le réseau), ce conteneur EST le
  service réseau AGPL lui-même** : GeoStudio le déploie et l'expose (port
  9000, API S3) à ses propres services internes (`core`, `martin`,
  `titiler`, le worker d'export, etc.). La clause réseau de l'AGPL (§13 —
  obligation de proposer le code source aux utilisateurs distants d'un
  programme AGPL modifié et exploité comme service réseau) **s'applique
  donc directement à ce déploiement**, contrairement à l'analyse faite
  pour `mc` (`deploy/backup/LICENSE-BACKUP.md`). Elle est satisfaite ici
  par le fait que **le binaire n'est pas modifié** (recompilation à
  l'identique du code source public, sans aucun patch appliqué par
  `deploy/minio/Dockerfile`) et que **le code source à la version exacte
  exécutée est déjà public** à l'adresse ci-dessus, sous le tag épinglé —
  l'offre de source AGPL §13 est donc satisfaite par référence à ce tag
  public, pratique usuelle pour une redistribution non modifiée, non
  revue par un juriste.

  **Si ce Dockerfile venait un jour à appliquer un patch au code source de
  MinIO avant compilation, cette analyse ne tiendrait plus** : l'AGPL §13
  imposerait alors de publier les sources modifiées elles-mêmes (par
  exemple sur un miroir public de ce dépôt à ce commit), pas seulement de
  référencer le dépôt amont non modifié.

## Composants systèmes (paquets Debian ajoutés explicitement)

| Composant | Licence (SPDX) | Nature | Source vérifiée |
|---|---|---|---|
| `curl` | `curl` (identifiant SPDX propre, permissive de type MIT/ISC) | permissif | <https://curl.se/docs/copyright.html> ; <https://spdx.org/licenses/curl.html> |
| `ca-certificates` (scripts d'empaquetage Debian) | `GPL-2.0-or-later` | traité comme utilitaire système, hors périmètre de redistribution applicative (même convention que `bash` dans `deploy/backup/LICENSE-BACKUP.md`) — ces scripts régénèrent le trousseau de confiance TLS local, ils ne sont ni liés ni exécutés par le binaire `minio` | `/usr/share/doc/ca-certificates/copyright` du paquet Debian bookworm (vérifié dans l'image `debian:bookworm-slim` en préparant ce plan) |
| `ca-certificates` (données `mozilla/certdata.txt`) | `MPL-2.0` | données de confiance TLS publiques, pas du code | idem |

## Image de base

- **`golang:1.24-bookworm`** (étage de build, jeté — ne survit pas dans
  l'image publiée) — Go lui-même est `BSD-3-Clause`.
- **`debian:bookworm-slim`** (étage final) — licences hétérogènes par
  paquet Debian, non auditées exhaustivement au-delà des deux paquets
  ajoutés explicitement ci-dessus (même réserve que pour les autres images
  publiées de ce dépôt, cf. `docs/ops/redistribution-images.md`).

## Code GeoStudio

`deploy/minio/Dockerfile` — Apache-2.0, publié dans le dépôt GeoStudio
(<https://github.com/tlenenao/geostudio>, `deploy/minio/`). Aucun autre
fichier GeoStudio n'est embarqué dans cette image.

## Ce que cela ne change pas

Le cœur GeoStudio (`core/`) reste sous Apache-2.0 : il n'est pas lié à
MinIO, il lui parle par l'API S3 générique (HTTP présigné, `httpfs` DuckDB,
VSI GDAL/rasterio) — un service S3 quelconque, y compris un vrai AWS S3,
pourrait le remplacer sans changement de code applicatif.
```

- [ ] **Step 5: Vérifier que le test passe**

```bash
cd core && uv run pytest tests/test_deployability.py -k test_minio_dockerfile_builds_from_pinned_agpl_source_not_broken_upstream_recipes -v
```

Attendu : PASS.

- [ ] **Step 6: Vérification manuelle (build réel)**

```bash
docker build -t geostudio-minio-manual:latest ./deploy/minio
docker run -d --name geostudio-minio-manual-check \
  -e MINIO_ROOT_USER=geostudio -e MINIO_ROOT_PASSWORD=geostudio123 \
  -p 19000:9000 -p 19001:9001 geostudio-minio-manual:latest \
  server /data --console-address ":9001"
sleep 3
curl -f http://127.0.0.1:19000/minio/health/live
docker exec geostudio-minio-manual-check minio --version
docker rm -f geostudio-minio-manual-check
docker rmi geostudio-minio-manual:latest
```

Attendu : `curl` répond 200 (aucune sortie autre que le succès de la
commande) ; `minio --version` affiche
`minio version RELEASE.2025-10-15T17-29-55Z (...)` (pas
`DEVELOPMENT...`).

- [ ] **Step 7: Commit**

```bash
git add deploy/minio/Dockerfile deploy/minio/LICENSE-MINIO.md core/tests/test_deployability.py
git commit -m "$(cat <<'EOF'
feat(deploy): reconstruit l'image minio depuis les sources AGPL

quay.io/minio/minio et minio/minio (Docker Hub) sont verrouilles en pull
anonyme sur tous les tags (401/pull access denied, verifie le
2026-09-25). Nouveau deploy/minio/Dockerfile multi-stage reproduisant la
cible `build` du Makefile amont (go build, pas make docker, casse par
dl.min.io) — meme patron que deploy/postgis et deploy/titiler.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Publication CI (matrice + smoke-test arm64)

**Files:**
- Modify: `.github/workflows/_build-and-push.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/publish-edge.yml`
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: `deploy/minio/Dockerfile` (Task 1) — construit et testé par le
  nouveau smoke-test arm64.
- Produces: entrée de matrice `geostudio-minio` (`context: ./deploy/minio`,
  `dockerfile: Dockerfile`, `platforms: linux/amd64,linux/arm64`) —
  consommée par Task 3 (`test_every_build_service_has_a_released_image` et
  `test_every_referenced_ghcr_image_is_released` exigent que cette entrée
  existe AVANT que `docker-compose.yml`/`docker-compose.prod.yml`
  référencent `build: ./deploy/minio` / `image:
  ghcr.io/tlenenao/geostudio-minio:...`).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_deployability.py`, modifier
`test_build_and_push_matrix_lives_in_the_reusable_workflow` (ligne 164) :
mettre à jour le docstring et l'ensemble attendu :

```python
def test_build_and_push_matrix_lives_in_the_reusable_workflow():
    """§2 de la spec 2026-09-19 : la matrice des 9 images doit vivre dans un
    SEUL fichier (`_build-and-push.yml`, réutilisable par `release.yml` ET
    par `publish-edge.yml`) — jamais recopiée, sous peine de dériver
    silencieusement entre les deux (classe de bug déjà payée sur ce dépôt,
    cf. CLAUDE.md piège n°2)."""
    assert BUILD_AND_PUSH.exists(), (
        "attendu : .github/workflows/_build-and-push.yml (workflow réutilisable)"
    )
    doc = yaml.safe_load(BUILD_AND_PUSH.read_text())
    assert "workflow_call" in doc[True], (
        "_build-and-push.yml doit être déclenchable via `on: workflow_call`"
    )
    matrix = doc["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]
    images = {e["image"] for e in matrix}
    assert images == {
        "geostudio-core",
        "geostudio-shell",
        "geostudio-postgis",
        "geostudio-titiler",
        "geostudio-appexport-standalone",
        "geostudio-export-worker",
        "geostudio-appexport-runtime-builder",
        "geostudio-backup",
        "geostudio-minio",
    }, f"matrice inattendue : {images}"
```

Puis ajouter un nouveau test juste après
`test_release_gate_arm64_runs_on_native_arm_runner` (ligne 744) :

```python
def test_release_gate_arm64_smoke_tests_minio_health():
    """Miroir de test_release_gate_arm64_runs_on_native_arm_runner pour
    minio : le binaire recompilé (Task 1, deploy/minio/Dockerfile) doit
    démarrer réellement sur du matériel arm64 natif, pas seulement passer
    docker buildx sous QEMU."""
    doc = yaml.safe_load(RELEASE.read_text())
    job = doc["jobs"]["test-gate-arm64"]
    runs = " ".join(st.get("run", "") for st in job["steps"])
    assert "deploy/minio" in runs, (
        "test-gate-arm64 doit builder ./deploy/minio (aucune étape ne le "
        "référence)."
    )
    assert "minio/health/live" in runs, (
        "test-gate-arm64 n'a pas de fumée minio (aucune étape n'appelle "
        "/minio/health/live)."
    )
```

- [ ] **Step 2: Vérifier que les tests échouent**

```bash
cd core && uv run pytest tests/test_deployability.py -k "test_build_and_push_matrix_lives_in_the_reusable_workflow or test_release_gate_arm64_smoke_tests_minio_health" -v
```

Attendu : les deux ÉCHOUENT (`test_build_and_push_matrix...` sur
l'assertion d'égalité d'ensemble, `test_release_gate_arm64_smoke_tests...`
sur `assert "deploy/minio" in runs`).

- [ ] **Step 3: Ajouter l'entrée à la matrice `_build-and-push.yml`**

Dans `.github/workflows/_build-and-push.yml`, dans `matrix.include`,
ajouter après l'entrée `geostudio-backup` :

```yaml
          - image: geostudio-backup
            context: ./deploy/backup
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-minio
            context: ./deploy/minio
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
```

Corriger dans la foulée le commentaire `fail-fast` du même fichier (compte
désormais faux — huit legs devient neuf) :

```yaml
      # Sans ceci, un échec sur une seule des neuf legs (par ex. disque ou
      # timeout sur geostudio-export-worker, 3.14 Go) annule les huit
      # autres avant publication — dont core/shell/postgis, qui n'ont
      # eux-mêmes aucune raison d'échouer.
```

- [ ] **Step 4: Ajouter le smoke-test arm64 dans `release.yml`**

Dans `.github/workflows/release.yml`, job `test-gate-arm64`, juste après
l'étape « Build + smoke-test titiler (arm64) » :

```yaml
      - name: Build + smoke-test minio (arm64)
        run: |
          docker build -t geostudio-minio-ci:latest ./deploy/minio
          docker run -d --name ci-minio \
            -e MINIO_ROOT_USER=geostudio -e MINIO_ROOT_PASSWORD=geostudio123 \
            -p 9000:9000 geostudio-minio-ci:latest server /data --console-address ":9001"
          for i in $(seq 1 30); do
            curl -sf http://127.0.0.1:9000/minio/health/live && break
            sleep 2
          done
          curl -sf http://127.0.0.1:9000/minio/health/live
          docker rm -f ci-minio
```

Puis mettre à jour le nom et le commentaire de l'étape `verify-published`
du même fichier (compte désormais faux — 8 devient 9) :

```yaml
      - name: Vérifie que les 9 images existent sous ce tag
        working-directory: core
        env:
          # Sans authentification, "jamais publiée" et "publiée mais
          # encore privée" renvoient le même 403 (vérifié empiriquement
          # contre le vrai registre) — un nouveau package GHCR naît privé
          # par défaut, ce qui aurait rendu ce garde-fou rouge au tout
          # premier succès de publication de geostudio-titiler.
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          IMAGE_TAG: ${{ github.ref_name }}
```

- [ ] **Step 5: Mettre à jour les compteurs dans `publish-edge.yml`**

Dans `.github/workflows/publish-edge.yml`, remplacer les deux occurrences
« 8 images » de l'en-tête et le nom de l'étape `verify-published` :

```yaml
# Reconstruit les 9 images sous le tag `edge` à chaque MERGE vers `main`
```

```yaml
# de travail quotidienne, cf. CLAUDE.md — un rebuild des 9 images à
```

```yaml
      - name: Vérifie que les 9 images existent sous le tag edge
```

- [ ] **Step 6: Vérifier que les tests passent**

```bash
cd core && uv run pytest tests/test_deployability.py -k "test_build_and_push_matrix_lives_in_the_reusable_workflow or test_release_gate_arm64_smoke_tests_minio_health or test_release_yml_calls_the_reusable_build_workflow or test_build_and_push_needs_both_test_gates or test_release_gate_arm64_runs_on_native_arm_runner" -v
```

Attendu : tous PASS (le dernier, `test_release_gate_arm64_runs_on_native_arm_runner`,
reste vert : la fumée titiler existante n'est pas touchée).

- [ ] **Step 7: Valider le YAML**

```bash
cd core && uv run python -c "import yaml,pathlib; [yaml.safe_load(pathlib.Path(p).read_text()) for p in ('../.github/workflows/_build-and-push.yml','../.github/workflows/release.yml','../.github/workflows/publish-edge.yml')]" && echo OK
```

Attendu : `OK` (aucune exception de parsing YAML).

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/_build-and-push.yml .github/workflows/release.yml .github/workflows/publish-edge.yml core/tests/test_deployability.py
git commit -m "$(cat <<'EOF'
feat(ci): publie geostudio-minio, 8 -> 9 images de release

Ajoute geostudio-minio a la matrice reutilisable (_build-and-push.yml),
avec fumee arm64 dediee (build + /minio/health/live) sur test-gate-arm64,
meme patron que geostudio-titiler. Corrige les compteurs "8 images"
devenus faux dans release.yml/publish-edge.yml.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Câblage compose (dev + prod)

**Files:**
- Modify: `docker-compose.yml:82-92`
- Modify: `docker-compose.prod.yml:29-31`
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consumes: `deploy/minio/Dockerfile` (Task 1), entrée de matrice
  `geostudio-minio` (Task 2) — sans elle,
  `test_every_build_service_has_a_released_image` échouerait dès que
  `docker-compose.yml` déclarerait `build: ./deploy/minio`.
- Produces: service `minio` construit localement en dev
  (`docker compose up -d minio`), publié en prod
  (`ghcr.io/tlenenao/geostudio-minio:${GEOSTUDIO_VERSION:-latest}`) — plus
  aucune dépendance à un registre tiers verrouillé.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_deployability.py`, retirer l'entrée
`"minio/minio:RELEASE.2025-09-07T16-13-09Z"` de la liste paramétrée de
`test_unpinned_reason_accepts_real_pinned_tags` (ligne 912-924) et corriger
le commentaire au-dessus (ligne 906, « neuf » devient « huit ») :

```python
# Les huit références d'images tierces réellement présentes dans les deux
# compose, recopiées telles quelles. Le durcissement du regex flottant est
# la seule chose qui pourrait les rejeter à tort : aucune n'est du semver
# canonique (`RELEASE.2025-…`, `1.22.1-p0`), et le chemin de registre
# multi-segment (`ghcr.io/maplibre/…`) est précisément ce que la résolution
# du tag par dernier segment doit traverser sans se tromper.
@pytest.mark.parametrize(
    "image",
    [
        "edoburu/pgbouncer:1.22.1-p0",
        "ghcr.io/maplibre/martin:v0.18.0",
        "ghcr.io/developmentseed/titiler:0.18.4",
        "grafana/otel-lgtm:0.11.4",
        "prometheuscommunity/postgres-exporter:v0.20.1",
        "traefik:v3.0.4",
        "quay.io/keycloak/keycloak:24.0.5",
        "tailscale/tailscale:v1.102.3",
    ],
)
def test_unpinned_reason_accepts_real_pinned_tags(image):
    assert unpinned_reason(image) is None
```

- [ ] **Step 2: Vérifier que le test échoue encore de la bonne façon**

```bash
cd core && uv run pytest tests/test_deployability.py -v
```

Attendu : `test_every_build_service_has_a_released_image` et
`test_prod_overlay_substitutes_every_build_with_an_image` restent VERTS
(rien n'a encore changé dans les compose) ; la suite entière passe déjà à
ce stade — cette étape ne fait que retirer une entrée obsolète, elle ne
fait échouer aucun test tant que `docker-compose.yml` référence encore
`quay.io/minio/minio`. Continuer directement à l'étape 3.

- [ ] **Step 3: Câbler `docker-compose.yml`**

Remplacer les lignes 84-92 :

```yaml
  minio:
    # Pin explicite (SP-21) : cette ligne était sans tag, donc `latest` —
    # le stockage objet de toutes les données du produit changeait de
    # version à chaque pull.
    # Registre quay.io (2026-09-12) : minio/minio a disparu de Docker Hub
    # (« pull access denied », y compris en local, tout tag confondu — plus
    # un simple rate-limit) ; MinIO publie désormais sur quay.io sous le
    # même namespace/tag. Vérifié par un pull réel avant ce changement.
    image: quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z
```

par :

```yaml
  minio:
    # Image tierce verrouillée en pull anonyme sur les DEUX registres
    # publics testés (2026-09-25) : quay.io/minio/minio (401 sur tous les
    # tags, y compris celui pinné ci-avant) et minio/minio sur Docker Hub
    # (« pull access denied », déjà connu depuis 2026-09-12). Ce n'est
    # plus une simple dérive de distribution (cf. REV-194) : plus aucun
    # registre public ne sert cette image. Reconstruite depuis les
    # sources AGPL-3.0 officielles (github.com/minio/minio) — voir
    # deploy/minio/Dockerfile.
    build: ./deploy/minio
```

(Les lignes 93-105 — `environment:`, `volumes:`, `ports:`, `command:`,
`networks:`, `healthcheck:` — restent inchangées.)

- [ ] **Step 4: Câbler `docker-compose.prod.yml`**

Remplacer les lignes 29-31 :

```yaml
  minio:
    restart: unless-stopped
    ports: !reset []
```

par :

```yaml
  minio:
    image: ghcr.io/tlenenao/geostudio-minio:${GEOSTUDIO_VERSION:-latest}
    build: !reset null
    restart: unless-stopped
    ports: !reset []
```

- [ ] **Step 5: Vérifier que toute la suite `test_deployability.py` passe**

```bash
cd core && uv run pytest tests/test_deployability.py -v
```

Attendu : suite entièrement verte, y compris
`test_images_are_pinned`, `test_every_build_service_has_a_released_image`,
`test_every_referenced_ghcr_image_is_released`,
`test_prod_overlay_substitutes_every_build_with_an_image`.

- [ ] **Step 6: Valider la configuration Compose résolue**

```bash
docker compose -f docker-compose.yml config --services >/dev/null && echo "dev OK"
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/tmp/prod-config.yml \
  && grep -A2 "^  minio:" /tmp/prod-config.yml
```

Attendu : `dev OK`, puis le bloc résolu du service `minio` en prod montre
`image: ghcr.io/tlenenao/geostudio-minio:latest` (ou la version de
`GEOSTUDIO_VERSION` si définie) et **aucune clé `build:`** (piège
documenté par CLAUDE.md, piège n°2 : la fusion Compose est additive, un
`build:` hérité survivrait sans le `!reset null`).

- [ ] **Step 7: Vérification manuelle bout en bout**

```bash
docker compose up -d --build minio
sleep 3
curl -f http://localhost:9000/minio/health/live
docker compose ps minio
```

Attendu : `curl` répond 200, `docker compose ps minio` montre l'état
`healthy` (ou `starting` puis `healthy` après le premier intervalle de
30s défini par le `healthcheck`).

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml core/tests/test_deployability.py
git commit -m "$(cat <<'EOF'
fix(deploy): bascule minio sur l'image reconstruite depuis les sources

docker-compose.yml construit desormais minio depuis deploy/minio/ (build:)
au lieu de tirer quay.io/minio/minio, verrouille en pull anonyme sur
quay.io ET Docker Hub (401/pull access denied, verifie le 2026-09-25).
docker-compose.prod.yml pointe ghcr.io/tlenenao/geostudio-minio, meme
patron que postgis (image: + build: !reset null).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Docs (redistribution, CLAUDE.md, backlog)

**Files:**
- Modify: `docs/ops/redistribution-images.md`
- Modify: `CLAUDE.md`
- Modify: `docs/revue/2026-09-04-backlog.md`

**Interfaces:**
- Consumes: rien de technique (documentation pure) — mais dépend
  logiquement de Tasks 1-3 pour être exacte (nombre d'images publiées,
  contenu réel de `LICENSE-MINIO.md`).
- Produces: rien consommé par une tâche ultérieure de ce plan (dernière
  tâche).

**Rappel (§ Comment on travaille de CLAUDE.md) : ce chantier n'ajoute
aucune route REST, outil MCP ou route shell — pas de régénération OpenAPI/
types TS, pas de `feature_health_cli.py --write` à lancer** (ces deux
obligations ne s'appliquent qu'à une nouvelle surface applicative ; ici,
seuls l'image de conteneur et le câblage CI/compose changent, aucun
comportement observable de `core/app/*` n'est modifié).

- [ ] **Step 1: `docs/ops/redistribution-images.md` — nouvelle image + correction de la ligne backup**

Remplacer la première ligne du document :

```markdown
GeoStudio publie 8 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
```

par :

```markdown
GeoStudio publie 9 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
```

Ajouter `geostudio-minio` à la liste énumérée juste après (même phrase),
et au titre de la section « Vérification des 8 images » (`## Vérification
des 8 images` → `## Vérification des 9 images`).

Ajouter une ligne au tableau de vérification (même section), après la
ligne `geostudio-backup` :

```markdown
| `geostudio-minio` | `golang:1.24-bookworm` (étage de build, jeté) + `debian:bookworm-slim` (étage final) | Binaire `minio` compilé depuis les sources officielles AGPL (`github.com/minio/minio`, cible `build` du Makefile amont) ; `ca-certificates`, `curl` (apt) — détail complet par composant : `/LICENSE-MINIO.md`, embarquée dans l'image | **AGPL-3.0-or-later** (serveur MinIO, exposé comme service réseau — contrairement à `mc` dans `geostudio-backup`, invoqué en sous-processus) + permissif pour le reste | **Copyleft réseau — section dédiée ci-dessous** |
```

Corriger la ligne `geostudio-backup` du même tableau, qui affirme encore
que `mc` vient de `dl.min.io` (obsolète depuis le portage arm64,
2026-09-17) :

Chercher :

```markdown
| `geostudio-backup` | `alpine:3.20` | `postgresql16-client`, `age`, `curl`, `jq`, `bash`, `tzdata`, `python3` (apk) + binaire `mc` (MinIO Client) téléchargé depuis `dl.min.io` — détail complet par composant : `/LICENSE-BACKUP.md`, embarquée dans l'image | **AGPL-3.0-or-later** (`mc`) + permissif pour le reste | **Copyleft — section dédiée, notice embarquée** |
```

Remplacer par :

```markdown
| `geostudio-backup` | `alpine:3.20` | `postgresql16-client`, `age`, `curl`, `jq`, `bash`, `tzdata`, `python3` (apk) + binaire `mc` (MinIO Client) téléchargé depuis les GitHub Releases de `minio/mc` (portage arm64, 2026-09-17 — `dl.min.io` répond 410 Gone) — détail complet par composant : `/LICENSE-BACKUP.md`, embarquée dans l'image | **AGPL-3.0-or-later** (`mc`) + permissif pour le reste | **Copyleft — section dédiée, notice embarquée** |
```

Ajouter enfin une nouvelle section, après la section « `geostudio-backup`
— contient de l'AGPL » et avant « Avant d'ajouter une image à la matrice
de release » :

```markdown
## `geostudio-minio` — contient de l'AGPL, exposé comme service réseau

Cette image (`deploy/minio/Dockerfile`) recompile le serveur MinIO
lui-même depuis ses sources officielles (`github.com/minio/minio`, tag
`RELEASE.2025-10-15T17-29-55Z`), après que `quay.io/minio/minio` et
`minio/minio` (Docker Hub) ont tous deux été verrouillés en pull anonyme
(401/pull access denied, vérifié le 2026-09-25 — escalade de REV-194).

**Différence structurante avec `geostudio-backup` (`mc`)** : `mc` est un
binaire invoqué en sous-processus, jamais exposé sur le réseau par
GeoStudio ; le serveur MinIO packagé ici **est** le service réseau AGPL
lui-même, déployé et exposé (port 9000, API S3) aux autres services du
stack. La clause réseau de l'AGPL (§13) s'applique donc directement à ce
déploiement. Elle est satisfaite parce que le binaire n'est pas modifié
(recompilation à l'identique, aucun patch) et que le code source à la
version exacte exécutée est déjà public au tag ci-dessus — offre de
source par référence, pratique usuelle non revue par un juriste. Détail
complet, y compris la réserve si ce Dockerfile venait à appliquer un jour
un patch : `deploy/minio/LICENSE-MINIO.md`, embarquée dans l'image.
```

- [ ] **Step 2: `CLAUDE.md` — ligne `### Livré` + pointeur `REV-194`**

Ajouter, à la fin de la liste `### Livré` (juste après l'entrée « Vague A
diagnostic UI/UX »), une nouvelle ligne :

```markdown
- **Reconstruction de l'image MinIO depuis les sources AGPL** — remplace
  `quay.io/minio/minio` (verrouillé en pull anonyme sur quay.io **et**
  Docker Hub, 401/pull access denied sur tous les tags, vérifié le
  2026-09-25) par `deploy/minio/Dockerfile` (build multi-stage
  `golang:1.24-bookworm` → `debian:bookworm-slim`, reproduit la cible
  `build` du Makefile amont, `RELEASE.2025-10-15T17-29-55Z`), publié
  `ghcr.io/tlenenao/geostudio-minio` (8 → 9 images) ; ferme `REV-194`.
```

Dans la section `### Suivis et dette non bloquante`, ajouter un nouveau
point-pointeur (l'entrée `REV-194` n'y figurait jusqu'ici sous aucune
forme — seul `docs/revue/2026-09-04-backlog.md` la portait) :

```markdown
- `REV-194` (dérive MinIO vers l'offre commerciale) close par la
  **reconstruction de l'image MinIO depuis les sources AGPL** : ce n'était
  plus une simple veille, `quay.io/minio/minio` ET `minio/minio` (Docker
  Hub) sont devenus totalement injoignables en pull anonyme (vérifié le
  2026-09-25).
```

- [ ] **Step 3: `docs/revue/2026-09-04-backlog.md` — clôture de `REV-194`**

Dans l'entrée `### REV-194` (chercher `### REV-194 — minor — coût 0`),
remplacer le titre :

```markdown
### REV-194 — minor — coût 0 (veille documentée, aucune action engagée)
```

par :

```markdown
### REV-194 — minor — coût 0 (fermée, escaladée en chantier — voir ci-dessous)
```

Remplacer la ligne `**État :**` :

```markdown
- **État :** ouvert (observation/veille — aucune action requise pour l'instant).
```

par :

```markdown
- **État :** fermé — escaladé le 2026-09-25 (« pas bloquant aujourd'hui »
  n'est plus vrai : `quay.io/minio/minio` **et** `minio/minio` sur Docker
  Hub répondent tous deux 401/pull access denied sur tous les tags, vérifié
  par pull réel — plus une dérive commerciale observée sans conséquence,
  un verrouillage total qui casse tout déploiement neuf, dev ou prod).
  Résolu par la reconstruction de l'image depuis les sources AGPL
  officielles (`deploy/minio/Dockerfile`), publiée
  `ghcr.io/tlenenao/geostudio-minio` — cf. `docs/superpowers/specs/
  2026-09-25-reconstruction-image-minio-source-design.md` et l'entrée
  `### Livré` de CLAUDE.md. Alternatives (SeaweedFS, Garage) réévaluées et
  écartées explicitement pour ce chantier — gardées en note si ce nouveau
  socle se refermait à son tour.
```

- [ ] **Step 4: Vérifier la taille de `CLAUDE.md`**

```bash
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold
```

Attendu : le script sort en succès (le garde-fou de taille existant, cf.
CLAUDE.md § Commandes). Si le seuil est dépassé, ne PAS augmenter le
seuil ici : d'abord relire la nouvelle ligne `### Livré` pour vérifier
qu'elle tient sur un seul item de liste comme les autres, avant d'alerter
Tanguy — ce script fait partie des hooks pre-commit et de la CI, un
dépassement bloquerait le commit.

- [ ] **Step 5: Commit**

```bash
git add docs/ops/redistribution-images.md CLAUDE.md docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs: documente la reconstruction de l'image minio, ferme REV-194

docs/ops/redistribution-images.md : nouvelle ligne geostudio-minio (8 -> 9
images), corrige la ligne geostudio-backup qui citait encore dl.min.io
comme source de mc (obsolete depuis le portage arm64, 2026-09-17).
CLAUDE.md : ligne ### Livre + pointeur REV-194. backlog.md : REV-194
fermee (le verrouillage total quay.io+Docker Hub confirme le 2026-09-25
depasse le "pas bloquant" initial du 2026-09-17).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Vérification finale de branche

Avant de proposer la fusion (`superpowers:finishing-a-development-branch`) :

```bash
cd core && uv run pytest tests/test_deployability.py -v
cd core && uv run ruff check . && uv run ruff format --check .
docker compose config --services >/dev/null && echo "compose dev OK"
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "compose prod OK"
docker build -t geostudio-minio-final-check:latest ./deploy/minio && docker rmi geostudio-minio-final-check:latest
```

Attendu : tout vert. Rappel du piège n°4 de CLAUDE.md (revue par tâche ≠
revue finale de branche) : vérifier en particulier qu'aucun autre fichier
du dépôt ne référence encore littéralement `quay.io/minio/minio` ou
`minio/minio:RELEASE.2025-09-07T16-13-09Z` en dehors des documents
historiques datés (specs/plans déjà clos, jamais réécrits a posteriori) :

```bash
grep -rn "quay.io/minio/minio\|minio/minio:RELEASE" --include="*.py" --include="*.yml" --include="*.yaml" --include="*.sh" . 2>/dev/null | grep -v '\.claude/worktrees/'
```

Attendu : aucune sortie (le seul répertoire à exclure,
`.claude/worktrees/agent-a805d8d613a116895`, est un worktree orphelin
d'une session antérieure, hors périmètre de ce plan — à signaler à Tanguy
séparément, ne pas le supprimer sans confirmation explicite).
