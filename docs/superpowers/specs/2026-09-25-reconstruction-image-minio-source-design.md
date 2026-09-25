# Reconstruction de l'image MinIO depuis les sources AGPL — design

Date : 2026-09-25. Statut : approuvé (brainstorm en session, décisions
utilisateur inline ci-dessous). Escalade de `REV-194`
(`docs/revue/2026-09-04-backlog.md`).

## Problème

`quay.io/minio/minio` (image du service `minio:` dans `docker-compose.yml` et
`docker-compose.prod.yml`) est devenu totalement inaccessible en pull anonyme —
Docker Hub (déjà connu, 2026-09-12) **et** quay.io (nouveau). Vérifié en
session par pull réel :

- `docker pull quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` (tag épinglé
  actuel) → `401 UNAUTHORIZED`.
- Idem sur un autre tag récent et sur `latest`.
- `docker pull minio/minio:latest` (Docker Hub) → `pull access denied`.
- L'API `quay.io/api/v1/repository/minio/minio/tag/` répond elle-même `401
  invalid_token` — le dépôt entier semble verrouillé, pas un tag isolé.
- Contrôle : un autre dépôt public quay.io (`quay.io/prometheus/prometheus`)
  se pull sans problème et son API tags répond normalement → ce n'est **pas**
  un rate-limit ou un blocage quay.io généralisé, c'est spécifique au dépôt
  `minio/minio`.

Cause CI immédiate : le job `shell-e2e-oidc` (`docker compose up -d postgis
keycloak core shell`, qui démarre `minio` comme dépendance) échoue sur
`minio Error unauthorized`. Mais le même `docker-compose.yml` est utilisé en
dev et en prod (`docker-compose.prod.yml` n'a pas d'`image:` propre pour
`minio`, il hérite du `image:`/`build:` de base) — donc **tout déploiement
neuf, dev ou prod, est cassé aujourd'hui**, pas seulement la CI.

Périmètre de l'impact applicatif : borné. `grep` confirme que les ~13
fichiers `core/app/*` qui touchent S3 (`ingestion`, `attachments`, `export`,
`reports`, `alerts`, `pipelines`, `tileset3d`, `terrain3d`, `cdc`,
`appexport`) n'utilisent que l'API S3 générique (`boto3.client("s3",
endpoint_url=...)`, présignature, `httpfs` DuckDB SigV4 path-style, VSI
GDAL/rasterio) — jamais la console web ni une API d'administration
propriétaire MinIO. C'est donc un problème d'**image de conteneur**, pas de
code applicatif.

Recherche faite en session (à vérifier de nouveau si ce chantier traîne) :

- La propre distribution binaire précompilée de MinIO (`dl.min.io/server/...`)
  répond aussi `410 Gone` (même rupture que celle déjà rencontrée sur `mc`,
  cf. `2026-09-17-portage-arm64-multiarch.md`).
- Le code source reste public et **AGPL-3.0** sur GitHub
  (`github.com/minio/minio`), dernier tag `RELEASE.2025-10-15T17-29-55Z`
  (« Security/CVE » — corrige GHSA-jjjj-jwhf-8rgr, une élévation de privilège
  via contournement de policy de session sur les comptes de service/STS).
  Les notes de cette release recommandent elles-mêmes désormais de cloner
  les sources et de builder son image (`git clone` + `checkout` +
  `make docker`).
- Mais la cible `make docker` de l'amont est **elle-même cassée** : son
  `Dockerfile` top-level fait `FROM minio/minio:latest` (circulaire — dépend
  du dépôt verrouillé) ; son `Dockerfile.release` télécharge le binaire
  depuis `dl.min.io` (mort). Seule sa cible `make build` (`CGO_ENABLED=0
  GOARCH=$TARGETARCH go build -tags kqueue -trimpath --ldflags
  "$(go run buildscripts/gen-ldflags.go)" -o minio`, un simple `go build`
  d'un module Go pur) reste valide et reproductible sans dépendance externe.

## Décision retenue

**Reconstruire l'image depuis les sources AGPL**, dans un nouveau
`deploy/minio/`, avec le même patron que `deploy/postgis` et `deploy/titiler`
(rapatrier une recette officielle cassée par sa propre distribution, pas
changer d'architecture). Alternatives écartées explicitement par
l'utilisateur : migration vers SeaweedFS ou Garage (toutes deux déjà évaluées
dans `REV-194`) — gardées en note pour une décision future si ce nouveau
socle devait à son tour se refermer.

Version : **`RELEASE.2025-10-15T17-29-55Z`** (la plus récente au moment de ce
design, corrige un CVE réel), pas la version actuellement épinglée
(`RELEASE.2025-09-07T16-13-09Z`) — puisqu'il faut de toute façon recompiler,
autant partir de la dernière AGPL disponible plutôt que de figer une version
qui a un CVE connu.

## Section 1 — Build de l'image

Nouveau `deploy/minio/Dockerfile`, multi-stage :

- **Stage build** : `golang:1.24-bookworm` (multi-arch officiel, cohérent
  avec le choix déjà fait pour `deploy/postgis`, `postgres:16-bookworm`).
  `git clone https://github.com/minio/minio`, `git checkout
  RELEASE.2025-10-15T17-29-55Z`, puis reproduire exactement la cible `build`
  du Makefile amont :
  `CGO_ENABLED=0 GOARCH=$TARGETARCH go build -tags kqueue -trimpath --ldflags
  "$(go run buildscripts/gen-ldflags.go)" -o /out/minio`. Ne **jamais**
  repartir de `Dockerfile.release` (télécharge depuis `dl.min.io`, mort) ni
  du `Dockerfile` top-level (`FROM minio/minio:latest`, circulaire).
- **Stage runtime** : `debian:bookworm-slim` + `ca-certificates` (TLS
  sortant, ex. si un déploiement pointe MinIO en mode passerelle/replication
  vers un vrai S3) + `curl` (le healthcheck existant,
  `curl -f http://localhost:9000/minio/health/live`, reste inchangé). Le
  binaire est standalone (`CGO_ENABLED=0`), aucune autre dépendance runtime.
  `COPY --from=build /out/minio /usr/bin/minio` +
  `COPY dockerscripts/docker-entrypoint.sh` (récupéré depuis les mêmes
  sources clonées — gère `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`,
  comportement identique à aujourd'hui). `EXPOSE 9000 9001`.
- Licence : `LICENSE` + `CREDITS` du dépôt source copiés dans l'image,
  documentés dans un nouveau `deploy/minio/LICENSE-MINIO.md` — même patron
  que `deploy/backup/LICENSE-BACKUP.md` pour `mc` (AGPL-3.0-or-later).
- Aucun changement d'API ni de comportement runtime attendu côté
  `core/app/*` (API S3 générique inchangée — le binaire recompilé est censé
  être bit-pour-bit fonctionnellement identique à l'image officielle du même
  tag, modulo la base OS du stage final).

## Section 2 — Câblage compose (dev + prod)

- `docker-compose.yml:92` : `image:
  quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` → `build: ./deploy/minio`
  (même patron que `postgis`/`titiler`). Mettre à jour le commentaire
  existant (lignes 88-91) pour documenter la nouvelle cause (verrouillage
  total du dépôt source d'image, pas juste une disparition Docker Hub) et
  pointer vers `deploy/minio/Dockerfile`.
- `docker-compose.prod.yml` : le bloc `minio:` actuel (`restart:
  unless-stopped`, `ports: !reset []`) n'a **pas** d'`image:` propre — il
  hérite du `build:` de base, ce qui reconstruirait l'image en prod à chaque
  déploiement. Ajouter `image:
  ghcr.io/tlenenao/geostudio-minio:${GEOSTUDIO_VERSION:-latest}` + `build:
  !reset null`, même patron que le bloc `postgis:` du même fichier
  (lignes ~21-24).

## Section 3 — CI / publication

- `.github/workflows/_build-and-push.yml` : nouvelle entrée dans la matrice
  `build-and-push` :
  ```yaml
  - image: geostudio-minio
    context: ./deploy/minio
    dockerfile: Dockerfile
    platforms: linux/amd64,linux/arm64
  ```
  → publie `ghcr.io/tlenenao/geostudio-minio:{tag,latest}` via
  `release.yml` **et** `publish-edge.yml` (les deux réutilisent ce workflow).
  8 → 9 images publiées. `core/scripts/check_published_images.py` lit la
  matrice dynamiquement — rien à modifier là.
- `.github/workflows/release.yml`, job `test-gate-arm64` : ajouter un
  smoke-test « build + run + health check », même patron que celui déjà
  présent pour titiler (`docker build -t geostudio-minio-ci:latest
  ./deploy/minio`, `docker run -d ... -p 9000:9000 geostudio-minio-ci:latest`,
  boucle `curl -f http://127.0.0.1:9000/minio/health/live`, `docker rm -f`).
  C'est le seul endroit qui vérifie qu'un binaire Go cross-compilé pour
  arm64 démarre réellement sur du matériel natif, pas seulement que
  `docker buildx` ne plante pas sous QEMU.
- `docs/ops/redistribution-images.md` : nouvelle ligne `geostudio-minio`
  (base `debian:bookworm-slim` + binaire `minio` compilé depuis les sources
  AGPL-3.0-or-later, notice dans `deploy/minio/LICENSE-MINIO.md`, même
  patron que la ligne `geostudio-backup`). Corriger dans la foulée la ligne
  `geostudio-backup` existante, qui mentionne encore `dl.min.io` comme
  source de `mc` — obsolète depuis le portage arm64 (2026-09-17, GitHub
  Releases) ; sinon deux affirmations contradictoires sur le même sujet
  dans le même fichier. Le reste de la dérive documentaire de ce fichier
  (ex. `geostudio-qgis-worker` toujours listé bien que le moteur ait été
  retiré) reste **hors périmètre** de ce chantier — à signaler en backlog,
  pas à corriger ici.

## Section 4 — Vérification / tests

- `core/tests/test_deployability.py::test_images_are_pinned` : le cas
  paramétré `"minio/minio:RELEASE.2025-09-07T16-13-09Z"` (~ligne 915)
  devient obsolète (`minio` n'a plus d'`image:`) — à retirer de la liste ;
  le commentaire « neuf références » (~ligne 906) devient « huit ».
- Nouveau test dans le même fichier, même patron que celui qui garde déjà
  `deploy/backup/Dockerfile` contre `dl.min.io` (~ligne 1732) : assertion
  que `deploy/minio/Dockerfile` clone bien `github.com/minio/minio` sur un
  tag `RELEASE.*` épinglé, et ne référence ni `dl.min.io` ni
  `FROM minio/minio` — garde-fou contre un retour accidentel vers une
  source de distribution qui vient de se refermer deux fois.
- Vérification manuelle avant merge : `docker build ./deploy/minio` en
  local, puis `docker compose up -d minio` + `curl -f
  http://localhost:9000/minio/health/live`.
- Pas de nouveau test d'intégration Python : la suite `core` (pytest) ne
  démarre jamais de vrai conteneur MinIO (S3 mocké). La vérification réelle
  passe par `shell-e2e-oidc` (CI, amd64, démarre déjà `minio` comme
  dépendance de `core`/`shell`) et `test-gate-arm64` (Section 3, arm64
  natif).

## Section 5 — Docs

- `CLAUDE.md` : mise à jour de l'entrée `REV-194` (§ Suivis et dette non
  bloquante) — passe d'« ouvert, veille » à fermé/référencé vers ce
  chantier, avec la preuve à jour (verrouillage confirmé sur quay.io **et**
  Docker Hub, pas seulement une dérive commerciale observée sans action).
  Une ligne dans `### Livré`.
- `docs/revue/2026-09-04-backlog.md` : entrée `REV-194` mise à jour en
  place (même sujet, escalade confirmée) — pas de nouvelle entrée `REV-nnn`.
- Pas de changement `.env.example` (aucune variable liée au tag/registre
  MinIO n'y est exposée aujourd'hui).

## Hors périmètre (explicitement)

- Migration vers SeaweedFS ou Garage — écartée par décision utilisateur
  pour ce chantier, gardée en option si le nouveau socle se referme aussi.
- Nettoyage de la dérive documentaire préexistante sur
  `geostudio-qgis-worker` dans `docs/ops/redistribution-images.md`.
- Tout changement du modèle de licence global du produit (l'image reste
  copyleft AGPL-3.0-or-later comme aujourd'hui, notice déjà prévue).
