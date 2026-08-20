# Redistribution des images publiées

GeoStudio publie 8 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
(cf. `.github/workflows/release.yml`) : `geostudio-core`, `geostudio-shell`,
`geostudio-postgis`, `geostudio-appexport-standalone`,
`geostudio-export-worker`, `geostudio-qgis-worker`,
`geostudio-appexport-runtime-builder`, `geostudio-backup`.

**Trois d'entre elles distribuent du logiciel copyleft** : `geostudio-qgis-worker`
(GPL — QGIS + GRASS), `geostudio-postgis` (GPL — PostGIS) et
`geostudio-backup` (AGPL — le client MinIO `mc`) ; voir les trois sections
dédiées ci-dessous. Une version précédente de ce document affirmait que
« sept d'entre elles ne contiennent que du code GeoStudio (Apache-2.0) et
des dépendances permissives » — c'était faux pour `geostudio-postgis` (jamais
vérifié) et pour `geostudio-backup` (jamais vérifié non plus, et le seul
des deux trouvé en réappliquant la checklist ci-dessous le 2026-08-21).

Les cinq images restantes (`geostudio-core`, `geostudio-shell`,
`geostudio-appexport-standalone`, `geostudio-export-worker`,
`geostudio-appexport-runtime-builder`) ont été vérifiées ce même jour à
l'échelle de leur image de base et des paquets/binaires ajoutés
explicitement par leur `Dockerfile` — le détail est dans le tableau
ci-dessous. Cette vérification ne couvre **pas** un audit licence par
licence exhaustif des arbres de dépendances npm/pip de chaque image ; pour
`geostudio-export-worker`, un point n'a pas pu être établi avec confiance
(Chromium/FFmpeg embarqués par Playwright) et est signalé comme tel plutôt
que classé permissif par défaut.

## Vérification des 8 images (checklist appliquée le 2026-08-21)

| Image | Base(s) | Ajouts notables du Dockerfile | Licence(s) établie(s) | Statut |
|---|---|---|---|---|
| `geostudio-core` | `python:3.12-slim` (Python, licence PSF, permissive) | extensions DuckDB `httpfs` (MIT), `spatial` (MIT), `h3` community (Apache-2.0) + code GeoStudio (Apache-2.0) | Permissif à ce niveau | OK |
| `geostudio-shell` | `node:20-slim` (étage de build, jeté) + `nginx:1.27-alpine` (BSD-2-Clause) | code GeoStudio (Apache-2.0) ; dépendances npm non auditées une à une | Permissif à ce niveau (npm non exhaustif) | OK, avec réserve |
| `geostudio-postgis` | `postgis/postgis:16-3.4` | `postgresql-16-pgvector`, `postgresql-16-wal2json` (APT PGDG) | **GPL-2.0-or-later** (PostGIS) + permissif (PostgreSQL, pgvector, wal2json) | **Copyleft — section dédiée** |
| `geostudio-appexport-standalone` | `node:20-slim` (build) + `python:3.12-slim` | code GeoStudio (Apache-2.0), `sqlalchemy` (MIT) | Permissif à ce niveau | OK |
| `geostudio-export-worker` | `python:3.12-slim` | Playwright (Apache-2.0) + binaires Chromium/FFmpeg téléchargés par `playwright install --with-deps chromium` | Playwright lui-même permissif ; **licence du binaire Chromium/FFmpeg embarqué non établie avec confiance** — Chromium agrège des centaines de composants tiers sous licences hétérogènes et aucun `THIRD_PARTY_NOTICES` consolidé n'a été trouvé en un temps raisonnable | **Non tranché, cf. note ci-dessous** |
| `geostudio-qgis-worker` | `qgis/qgis:release-3_34` | GRASS (`grassprovider` activé) | **GPL-2.0-or-later** (QGIS + GRASS) | **Copyleft — section dédiée existante** |
| `geostudio-appexport-runtime-builder` | `node:20-slim` | code GeoStudio (Apache-2.0) ; dépendances npm non auditées une à une | Permissif à ce niveau (npm non exhaustif) | OK, avec réserve |
| `geostudio-backup` | `alpine:3.20` | `postgresql16-client`, `age`, `curl`, `jq`, `bash`, `tzdata`, `python3` (apk) + binaire `mc` (MinIO Client) téléchargé depuis `dl.min.io` | **AGPL-3.0-or-later** (`mc`) + permissif pour le reste | **Copyleft — section dédiée** |

**Note sur `geostudio-export-worker`** : Playwright (le paquet Python) est
Apache-2.0, mais les binaires de navigateur qu'il télécharge et que
`deploy/export-worker/Dockerfile` embarque dans l'image publiée n'ont pas
de licence unique établie ici. Chromium est publié par Google sous une
licence de type BSD, mais agrège de très nombreuses bibliothèques tierces
sous des licences hétérogènes (potentiellement dont des composants LGPL
pour certains codecs FFmpeg selon la configuration de build) ; ceci
**n'est pas tranché** — à creuser avant une release publique si ce point
devient sensible, plutôt que d'affirmer ici une licence non vérifiée.

## `geostudio-qgis-worker` — contient du GPL

Cette image dérive de `qgis/qgis:release-3_34` (QGIS 3.34.5 « Prizren »,
LTR) et contient **QGIS** et **GRASS GIS**, sous GPL-2.0-or-later. La
publier est un acte de distribution : l'image embarque `/LICENSE-QGIS.md`
(notice + pointeurs vers les sources amont) et porte les labels OCI
correspondants.

GeoStudio ne modifie pas les sources de QGIS ni de GRASS ; la seule
opération appliquée par-dessus l'image amont est l'activation du plugin
`grassprovider` (réglage de configuration, livré désactivé par défaut dans
l'image amont). Les deux seuls fichiers ajoutés (`server.py`,
`allowlist.txt`) sont publics dans ce dépôt sous Apache-2.0 : l'offre de
source est donc satisfaite par référence, forme usuelle pour une image
dérivée sans modification de l'amont — pratique usuelle, non revue par un
juriste.

**Ce que cela ne change pas** : le cœur GeoStudio (`core/`) reste
Apache-2.0. Il n'est pas lié à QGIS — il appelle ce conteneur en HTTP, isolé,
sans credential de base de données ni accès réseau externe (arbitrage A39).
La capacité est de surcroît éteinte par défaut (`CORE_ETL_ENABLED=false`,
profil compose `etl`).

## `geostudio-postgis` — contient du GPL

Cette image dérive de `postgis/postgis:16-3.4` et installe en plus, via le
dépôt APT PGDG déjà configuré par l'image amont, `postgresql-16-pgvector`
et `postgresql-16-wal2json` (`deploy/postgis/Dockerfile`). La publier est
un acte de distribution de PostGIS, au même titre que
`geostudio-qgis-worker` pour QGIS/GRASS.

| Composant | Licence (SPDX) | Nature | Source vérifiée |
|---|---|---|---|
| PostgreSQL 16 (image de base) | `PostgreSQL` (licence permissive de type BSD/MIT) | permissif | <https://www.postgresql.org/about/licence/> |
| PostGIS 3.4 | `GPL-2.0-or-later` | **copyleft** | `COPYING` du dépôt amont (<https://github.com/postgis/postgis/blob/master/COPYING>, en-tête GPLv2) + `debian/copyright` du paquet Debian (`Files: *` → `License: GPL-2+`, <https://sources.debian.org/src/postgis/3.3.2%2Bdfsg-1/debian/copyright/>) — exceptions ponctuelles pour quelques sous-dossiers (`deps/flatgeobuf`, `deps/ryu`, `doc/`, etc.) sous des licences permissives distinctes, non redistribuées séparément par notre image |
| `postgresql-16-pgvector` (extension pgvector) | `PostgreSQL` (licence permissive) | permissif | `LICENSE` du dépôt amont <https://github.com/pgvector/pgvector/blob/master/LICENSE> |
| `postgresql-16-wal2json` | `BSD-3-Clause` | permissif | `LICENSE` du dépôt amont <https://github.com/eulerto/wal2json/blob/master/LICENSE> |

**PostGIS est donc sous GPL-2.0-or-later, dans la même famille de licence
que QGIS et GRASS** — contrairement à ce qu'affirmait la version
précédente de ce document. PostgreSQL lui-même, ainsi que pgvector et
wal2json, sont permissifs : ne pas confondre les quatre composants, un
seul d'entre eux (PostGIS) porte l'obligation copyleft de cette image.

GeoStudio ne modifie pas les sources de PostGIS ; `deploy/postgis/Dockerfile`
installe seulement deux paquets additionnels par-dessus l'image amont,
sans toucher au code de PostGIS/PostgreSQL. L'offre de source amont est
disponible par référence (dépôts publics ci-dessus, même réserve de
pratique usuelle non revue par un juriste que pour `geostudio-qgis-worker`).

**Point ouvert (2026-08-21, non bloquant) : notice et labels OCI pas
encore embarqués dans cette image.** Contrairement à `geostudio-qgis-worker`,
`geostudio-postgis` ne porte à ce jour ni fichier de notice de licence
embarqué (`LICENSE-POSTGIS.md`), ni label OCI
`org.opencontainers.image.licenses`. Raison : au moment de cette
correction, `deploy/postgis/Dockerfile` porte des modifications non
commitées et sans lien avec cette tâche (ajout d'un `COPY pg_hba.conf`,
travail d'une autre session en cours — cf. CLAUDE.md, « Suivis non
bloquants ouverts »). Éditer ce fichier maintenant risquerait d'emporter ce
travail tiers dans un commit qui n'est pas le sien ; la correction de ce
document se limite donc à documenter le constat, sans embarquer la notice.
À faire dans une session ultérieure, une fois ce `Dockerfile` stabilisé :
ajouter `LICENSE-POSTGIS.md` (miroir de `LICENSE-QGIS.md`) + les 3 `LABEL`
OCI correspondants.

## `geostudio-backup` — contient de l'AGPL

Cette image (`deploy/backup/Dockerfile`, base `alpine:3.20`) télécharge le
binaire officiel du client MinIO (`mc`, depuis
`https://dl.min.io/client/mc/release/linux-amd64/mc`) pour piloter les
sauvegardes vers S3/MinIO — le paquet Alpine `mc` est autre chose
(Midnight Commander, cf. commentaire du Dockerfile), d'où ce téléchargement
direct du binaire amont.

`mc` est publié par MinIO sous **AGPL-3.0-or-later** depuis que le projet
MinIO (serveur et client) est passé intégralement sous cette licence en
2021 — vérifié sur l'en-tête de licence des fichiers sources du dépôt amont
(<https://github.com/minio/mc/blob/master/cmd/access-perms.go> : « GNU
Affero General Public License [...] either version 3 of the License, or
(at your option) any later version ») et sur le badge de licence du dépôt
(<https://github.com/minio/mc>, `LICENSE`). Le dépôt `minio/mc` a depuis
été archivé (2026) mais cela ne change pas la licence du binaire déjà
téléchargé par notre `Dockerfile`.

Ceci n'était **pas** documenté par la version précédente de ce fichier, qui
classait `geostudio-backup` parmi les images « code GeoStudio + dépendances
permissives » — c'est exactement l'affirmation non vérifiée que cette
correction retire. Les autres paquets installés par ce `Dockerfile`
(`postgresql16-client`, `age`, `curl`, `jq`, `tzdata`, `python3`) sont
permissifs : PostgreSQL License, BSD-3-Clause (<https://github.com/FiloSottile/age>,
confirmé par le champ licence du paquet Alpine), licence `curl` (permissive,
type MIT/ISC), MIT + composants tiers permissifs pour `jq`, domaine public
(base de données IANA tz) et PSF respectivement. `bash` lui-même est
GPL-3.0-or-later (confirmé par le champ licence du paquet Alpine) mais
n'est ici qu'un interpréteur système invoqué pour exécuter `backup.sh`,
pas un composant applicatif que GeoStudio redistribue comme partie de son
produit — traité comme les autres utilitaires GPL universellement présents
dans toute image Debian/Alpine (`coreutils`, `busybox`, etc.), hors du
périmètre de ce document.

**L'AGPL est une licence copyleft plus stricte que la GPL** (clause
d'usage réseau), mais l'obligation pertinente ici, pour un binaire
redistribué tel quel sans modification, est la même que pour
QGIS/GRASS/PostGIS : offrir l'accès aux sources correspondantes. Le code
source de `mc` à la version téléchargée est public sur le dépôt amont —
offre par référence, même réserve de pratique usuelle non revue par un
juriste que pour les deux sections précédentes.

**Point ouvert (2026-08-21, non bloquant) : notice et labels OCI non
embarqués.** Même situation que `geostudio-postgis` ci-dessus, pour une
raison différente et plus simple : cette correction ne touche, par
contrainte explicite de la tâche, que `docs/ops/redistribution-images.md`
et `deploy/qgis-worker/LICENSE-QGIS.md` — modifier
`deploy/backup/Dockerfile` est hors périmètre. À faire dans une session
ultérieure : ajouter un `LICENSE-BACKUP.md` (notice `mc`/AGPL) + labels
OCI. À noter séparément (préoccupation de déployabilité, pas de licence) :
le binaire `mc` est téléchargé depuis un chemin `release/linux-amd64/mc`
sans version épinglée, donc non reproductible d'un build à l'autre.

## Avant d'ajouter une image à la matrice de release

Vérifier la licence de l'image de base **et de chaque paquet/binaire ajouté
explicitement par le `Dockerfile`** — c'est l'oubli de ce second point qui a
laissé passer PostGIS et `mc` jusqu'à la correction du 2026-08-21 de ce
document (leur image de base ou leurs ajouts n'avaient jamais été vérifiés,
malgré la présence de cette checklist). Si l'un ou l'autre est copyleft,
ajouter ici sa section (composant par composant, sources amont précises) et
embarquer une notice + des labels OCI dans l'image, comme pour
`geostudio-qgis-worker`.
