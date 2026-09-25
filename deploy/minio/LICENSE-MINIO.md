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
