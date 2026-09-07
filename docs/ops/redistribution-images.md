# Redistribution des images publiées

GeoStudio publie 8 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
(cf. `.github/workflows/release.yml`) : `geostudio-core`, `geostudio-shell`,
`geostudio-postgis`, `geostudio-appexport-standalone`,
`geostudio-export-worker`, `geostudio-qgis-worker`,
`geostudio-appexport-runtime-builder`, `geostudio-backup`.

**Trois d'entre elles distribuent du logiciel copyleft fort (GPL/réseau)** :
`geostudio-qgis-worker` (GPL — QGIS + GRASS), `geostudio-postgis` (GPL —
PostGIS) et `geostudio-backup` (AGPL — le client MinIO `mc`) ; voir les
trois sections dédiées ci-dessous. Une version précédente de ce document
affirmait que « sept d'entre elles ne contiennent que du code GeoStudio
(Apache-2.0) et des dépendances permissives » — c'était faux pour
`geostudio-postgis` (jamais vérifié) et pour `geostudio-backup` (jamais
vérifié non plus, et le seul des deux trouvé en réappliquant la checklist
ci-dessous le 2026-08-21).

**Deux images de plus (`geostudio-core` et `geostudio-export-worker`)
distribuent en outre un composant copyleft faible (LGPL)** : `psycopg` et
`psycopg2-binary`, découverts en réappliquant la même checklist, le même
jour, à un niveau de grain plus fin que la première réapplication
(dépendances Python directes déclarées dans `core/pyproject.toml`, pas
seulement l'image de base et les extensions DuckDB) — cf. section dédiée
plus bas. Ce n'est pas de la même famille que les trois cas GPL/AGPL
ci-dessus (obligation bien plus légère en pratique pour un paquet Python
non modifié importé dynamiquement), mais ce n'était documenté nulle part
avant cette correction.

Les trois images restantes à ce jour purement permissives à l'échelle
vérifiée (`geostudio-shell`, `geostudio-appexport-standalone`,
`geostudio-appexport-runtime-builder`) ont été vérifiées le même jour à
l'échelle de leur image de base et des paquets/binaires ajoutés
explicitement par leur `Dockerfile` — le détail est dans le tableau
ci-dessous. Cette vérification ne couvre **pas** un audit licence par
licence exhaustif des arbres de dépendances npm/pip transitives de chaque
image (seules les dépendances déclarées directement sont énumérées) ; pour
`geostudio-export-worker`, un point n'a en outre pas pu être établi avec
confiance (Chromium/FFmpeg embarqués par Playwright) et est signalé comme
tel plutôt que classé permissif par défaut.

**Cohérence de la colonne Statut (2026-08-21)** : la réserve d'audit non
exhaustif énoncée ci-dessus s'applique identiquement aux arbres npm et
pip — une version précédente de ce document ne l'affichait qu'aux images
npm (« OK, avec réserve » pour `geostudio-shell`/
`geostudio-appexport-runtime-builder`) tout en marquant les images pip
(`geostudio-core`, `geostudio-appexport-standalone`) d'un « OK » flat, ce
qui laissait croire à tort qu'elles avaient été auditées de façon
exhaustive. Choix retenu : la même étiquette « OK, avec réserve »
s'applique désormais aux cinq images de ce statut, quelle que soit leur
techno — plutôt que de supprimer l'étiquette par ligne et de compter sur
le seul paragraphe global, pour qu'un lecteur qui ne lit que le tableau
voie la réserve sans devoir remonter au texte.

## Vérification des 8 images (checklist appliquée le 2026-08-21)

| Image | Base(s) | Ajouts notables du Dockerfile | Licence(s) établie(s) | Statut |
|---|---|---|---|---|
| `geostudio-core` | `python:3.12-slim` (CPython, `PSF-2.0` [^python]) | 36 dépendances Python directes de `core/pyproject.toml` (`fastapi`, `sqlalchemy`, `pydantic`, `httpx`, `requests`, `dlt`, `snowflake-sqlalchemy`, `psycopg`, `psycopg2-binary`, `alembic`, `pyjwt`, `cryptography`, `croniter`, `boto3`, `mcp`, `shapely`, `procrastinate`, `pyogrio`, `pyproj`, `rasterio`, `geopandas`, `pyarrow`, `pgvector`, `duckdb`, `openpyxl`, `playwright`, `opentelemetry-*`, etc. — liste complète et licence de chacune : cf. section dédiée) + extensions DuckDB `httpfs`/`spatial` (MIT [^duckdb-ext]), `h3` community (Apache-2.0 [^h3-duckdb]) + code GeoStudio (Apache-2.0) | Permissif pour l'immense majorité, **sauf `psycopg` (`LGPL-3.0-only`) et `psycopg2-binary` (`LGPL-3.0-or-later`)** — copyleft faible, cf. section dédiée | **OK, avec réserve** (pip non exhaustif au-delà des dépendances directes ; + LGPL psycopg/psycopg2, voir note) |
| `geostudio-shell` | `node:20-slim` (étage de build, jeté) + `nginx:1.27-alpine` (`BSD-2-Clause` [^nginx]) | code GeoStudio (Apache-2.0) ; dépendances npm non auditées une à une (étage `node` jeté avant l'image finale — seul le bundle JS compilé est copié) | Permissif à ce niveau (npm non exhaustif) | OK, avec réserve |
| `geostudio-postgis` | `postgis/postgis:16-3.4` | `postgresql-16-pgvector`, `postgresql-16-wal2json` (APT PGDG) | **GPL-2.0-or-later** (PostGIS) + permissif (PostgreSQL, pgvector, wal2json) | **Copyleft — section dédiée** |
| `geostudio-appexport-standalone` | `node:20-slim` (build shell, jeté) + `python:3.12-slim` | code GeoStudio (Apache-2.0) ; `pip install fastapi 'uvicorn[standard]' pydantic duckdb sqlalchemy` (tous les cinq explicitement listés dans le `Dockerfile`, pas seulement `sqlalchemy` comme l'affirmait une version précédente de ce tableau) — `fastapi`/`pydantic`/`sqlalchemy`/`duckdb` MIT [^fastapi] [^pydantic] [^sqlalchemy] [^duckdb-py], `uvicorn` BSD-3-Clause [^uvicorn] ; dépendances npm de l'étage de build non auditées (jeté avant l'image finale, comme `geostudio-shell`) | Permissif à ce niveau | OK, avec réserve (pip+npm non exhaustifs au-delà des dépendances directes listées) |
| `geostudio-export-worker` | `python:3.12-slim` | **Même liste complète que `geostudio-core`** (`uv pip install --system --no-cache -r pyproject.toml` — littéralement le même fichier, donc les mêmes 36 dépendances directes, y compris `psycopg`/`psycopg2-binary`) + binaires Chromium/FFmpeg téléchargés par `playwright install --with-deps chromium` | Playwright lui-même permissif (Apache-2.0 [^playwright]) ; **licence du binaire Chromium/FFmpeg embarqué non établie avec confiance** — Chromium agrège des centaines de composants tiers sous licences hétérogènes et aucun `THIRD_PARTY_NOTICES` consolidé n'a été trouvé en un temps raisonnable ; **+ LGPL `psycopg`/`psycopg2-binary` héritées de `core/pyproject.toml`**, même réserve que `geostudio-core` | **Non tranché** (Chromium/FFmpeg, cf. note ci-dessous) **+ réserve LGPL** (voir section dédiée) |
| `geostudio-qgis-worker` | `qgis/qgis:release-3_34` | GRASS (`grassprovider` activé) | **GPL-2.0-or-later** (QGIS + GRASS) | **Copyleft — section dédiée existante** |
| `geostudio-appexport-runtime-builder` | `node:20-slim` (image finale, pas un étage jeté — c'est un conteneur one-shot dont la sortie est un volume, pas un runtime servi) | code GeoStudio (Apache-2.0) ; dépendances npm non auditées une à une | Permissif à ce niveau (npm non exhaustif) | OK, avec réserve |
| `geostudio-backup` | `alpine:3.20` | `postgresql16-client`, `age`, `curl`, `jq`, `bash`, `tzdata`, `python3` (apk) + binaire `mc` (MinIO Client) téléchargé depuis `dl.min.io` — détail complet par composant : `/LICENSE-BACKUP.md`, embarquée dans l'image | **AGPL-3.0-or-later** (`mc`) + permissif pour le reste | **Copyleft — section dédiée, notice embarquée** |

[^python]: <https://docs.python.org/3/license.html> ; <https://spdx.org/licenses/PSF-2.0.html>
[^duckdb-ext]: `httpfs`/`spatial` MIT — <https://github.com/duckdb/duckdb-httpfs>, <https://github.com/duckdb/duckdb-spatial>
[^h3-duckdb]: <https://github.com/isaacbrodsky/h3-duckdb/blob/main/LICENSE>
[^nginx]: <https://nginx.org/LICENSE>
[^fastapi]: <https://pypi.org/project/fastapi/> (métadonnée `License-Expression: MIT`)
[^pydantic]: <https://pypi.org/project/pydantic/> (métadonnée `License-Expression: MIT`)
[^sqlalchemy]: <https://pypi.org/project/SQLAlchemy/> (métadonnée `License: MIT`)
[^duckdb-py]: <https://pypi.org/project/duckdb/> (classifieur `License :: OSI Approved :: MIT License`)
[^uvicorn]: <https://pypi.org/project/uvicorn/> (métadonnée `License-Expression: BSD-3-Clause`)
[^playwright]: <https://pypi.org/project/playwright/> (métadonnée `License-Expression: Apache-2.0`)

Toutes les licences ci-dessus (sauf mention contraire) ont été vérifiées le
2026-08-21 en interrogeant les métadonnées réelles des paquets installés
dans l'environnement `core` (`importlib.metadata`, champs `License-Expression`
PEP 639 quand présent, sinon `License`/`Classifier`), pas transcrites depuis
une source tierce non vérifiée.

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

## `geostudio-core` et `geostudio-export-worker` — dépendance LGPL non embarquée (constat du 2026-08-21)

Ces deux images installent, via `uv pip install --system --no-cache -r
pyproject.toml`, **le même fichier `core/pyproject.toml`** — donc les mêmes
36 dépendances Python directes. `geostudio-export-worker` ajoute par-dessus
Playwright + Chromium/FFmpeg (cf. note dédiée ci-dessus) ; les 36
dépendances directes sont identiques dans les deux images.

Licence de chacune, vérifiée le 2026-08-21 en interrogeant les métadonnées
réelles des paquets installés dans l'environnement `core`
(`importlib.metadata`, `uv run python`, pas transcrite depuis une source
tierce) :

| Licence (SPDX) | Paquets | Nature |
|---|---|---|
| `MIT` | `fastapi`, `sqlalchemy`, `pydantic`, `alembic`, `pyjwt`, `croniter`, `mcp`, `procrastinate`, `pyogrio`, `pyproj`, `pgvector`, `duckdb`, `openpyxl` | permissif |
| `BSD-3-Clause` | `uvicorn`, `httpx`, `shapely`, `rasterio`, `geopandas`, `rio-cogeo` | permissif |
| `Apache-2.0` | `requests`, `dlt`, `boto3`, `python-multipart`, `pyarrow`, `playwright`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx,botocore}`, `snowflake-sqlalchemy`, `snowflake-connector-python` (dépendance transitive de `snowflake-sqlalchemy`) | permissif |
| `Apache-2.0 OR BSD-3-Clause` (dual, au choix du redistributeur) | `cryptography` | permissif |
| `PSF-2.0` | `defusedxml` | permissif |
| **`LGPL-3.0-only`** | `psycopg` | **copyleft faible** |
| **`LGPL-3.0-or-later`** (+ exception de liaison OpenSSL propre au projet, sans identifiant d'exception SPDX catalogué — cf. `LICENSE` amont) | `psycopg2-binary` | **copyleft faible** |

`snowflake-sqlalchemy` (ajouté par GAP-16, connecteur entrepôt cloud
analytique) et sa dépendance transitive `snowflake-connector-python`
vérifiées le 2026-09-07 par la même méthode (`importlib.metadata` dans
l'environnement `core`) : `snowflake-sqlalchemy` porte
`License-Expression: Apache-2.0` ; `snowflake-connector-python` porte
`License: Apache-2.0` (pas de champ `License-Expression`, mais classifieur
`License :: OSI Approved :: Apache Software License` concordant) — aucune
des deux n'introduit de copyleft.

Sources vérifiées pour les deux composants copyleft : `psycopg` —
<https://github.com/psycopg/psycopg/blob/master/LICENSE.txt> (confirmé par
la métadonnée PyPI `License-Expression: LGPL-3.0-only`, champ auto-déclaré
par le projet) ; `psycopg2-binary` —
<https://github.com/psycopg/psycopg2/blob/master/LICENSE> (« version 3 of
the License, or (at your option) any later version », plus l'exception
OpenSSL citée ci-dessus).

**Traitement pratique, sans reconduire l'analyse GPL/AGPL ci-dessus/dessous
telle quelle** : `psycopg`/`psycopg2-binary` sont utilisés ici tels que
publiés sur PyPI, non modifiés, importés dynamiquement par un interpréteur
Python — pas liés statiquement dans un binaire compilé. L'obligation LGPL
pertinente (permettre le remplacement/la relecture de la bibliothèque, en
donner accès aux sources) est de fait déjà satisfaite : le paquet est
public, inchangé, et remplaçable par l'utilisateur final sans recompiler
quoi que ce soit (`pip install psycopg==<version>` suffit). Ceci reste une
analyse d'ingénieur, non une revue juridique formelle — même réserve que
pour les trois sections GPL/AGPL de ce document.

**Point ouvert (2026-08-21, non bloquant) : aucune notice ni label OCI
n'est embarqué dans `geostudio-core` ni `geostudio-export-worker` pour ce
composant.** Contrairement à `geostudio-qgis-worker`/`geostudio-backup`,
ni `core/Dockerfile` ni `deploy/export-worker/Dockerfile` ne sont dans le
périmètre de fichiers autorisés pour la tâche qui a produit cette section
— cette correction se limite donc à documenter le constat. À faire dans
une session ultérieure : évaluer si une notice `LICENSE-CORE.md` est
justifiée pour du LGPL utilisé de cette façon (l'analyse ci-dessus suggère
que non, au même titre qu'aucun projet Python courant n'embarque une
notice pour ses dépendances LGPL importées telles quelles — mais la
question n'a pas été tranchée avec Tanguy).

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
direct du binaire amont. La publier est un acte de distribution de `mc` :
l'image embarque désormais `/LICENSE-BACKUP.md` (notice détaillée
composant par composant + pointeurs vers les sources amont) et porte les
3 labels OCI correspondants (`org.opencontainers.image.licenses` =
`AGPL-3.0-or-later AND Apache-2.0`, `.source`, `.description`), à parité
avec `geostudio-qgis-worker` — **décision explicite de Tanguy (2026-08-21)
de traiter ce point maintenant plutôt que de le différer**, contrairement
à `geostudio-postgis` (dont le `Dockerfile` porte du travail non commité
d'une autre session, cf. point ouvert ci-dessus, inchangé).

`mc` est publié par MinIO sous **AGPL-3.0-or-later** depuis que le projet
MinIO (serveur et client) est passé intégralement sous cette licence en
2021 — vérifié sur l'en-tête de licence des fichiers sources du dépôt amont
(<https://github.com/minio/mc/blob/master/cmd/access-perms.go> : « GNU
Affero General Public License [...] either version 3 of the License, or
(at your option) any later version ») et sur le badge de licence du dépôt
(<https://github.com/minio/mc>, `LICENSE`). Le dépôt `minio/mc` a depuis
été archivé (2026) mais cela ne change pas la licence du binaire déjà
téléchargé par notre `Dockerfile`.

Le détail par composant (`postgresql16-client`, `age`, `curl`, `jq`,
`tzdata`, `python3`, `bash`, `mc`, code GeoStudio propre) — chacun avec son
identifiant SPDX canonique et sa source vérifiée — vit désormais dans
`/LICENSE-BACKUP.md` (embarquée dans l'image, cf. ci-dessus) plutôt que
d'être dupliqué ici, à la manière de `geostudio-qgis-worker`/
`LICENSE-QGIS.md`. Point notable : `bash` (`GPL-3.0-or-later`) y est
traité comme un interpréteur système invoqué pour exécuter `backup.sh`,
pas comme un composant applicatif redistribué — même convention que pour
les utilitaires GPL universellement présents dans toute image
Debian/Alpine (`coreutils`, `busybox`, etc.), hors du périmètre de ce
document.

**L'AGPL est une licence copyleft plus stricte que la GPL** (clause
d'usage réseau, §13), mais l'obligation pertinente ici, pour un binaire
redistribué tel quel sans modification et jamais exposé comme service
réseau par GeoStudio, est l'offre d'accès aux sources correspondantes —
la même que pour QGIS/GRASS/PostGIS. Le code source de `mc` à la version
téléchargée est public sur le dépôt amont — offre par référence, même
réserve de pratique usuelle non revue par un juriste que pour les deux
sections précédentes. **Cette analyse est spécifique à l'usage réel ici**
(`mc` non modifié, invoqué en sous-processus par `backup.sh`, jamais
servi sur le réseau par GeoStudio) : elle ne vaut pas affirmation générale
qu'une offre de source suffirait à décharger l'AGPL §13 dans une situation
où un programme AGPL modifié serait exploité comme service réseau — voir
`/LICENSE-BACKUP.md` pour la formulation complète de cette réserve.

**Limite connue, non corrigée par cette notice** : le téléchargement de
`mc` (`release/linux-amd64/mc`) n'est pas épinglé en version — la version
exacte redistribuée par une image donnée est celle qui était courante au
moment du build, non reproductible d'un build à l'autre. C'est une vraie
limite pour une offre de source (le pointeur vers le dépôt amont ne cible
pas un commit/tag précis correspondant au binaire embarqué), documentée
dans `/LICENSE-BACKUP.md` mais délibérément non corrigée dans cette
passe : épingler la version changerait le contenu réel de l'image et
nécessiterait sa propre vérification.

## Avant d'ajouter une image à la matrice de release

Vérifier la licence de l'image de base **et de chaque paquet/binaire ajouté
explicitement par le `Dockerfile`** — c'est l'oubli de ce second point qui a
laissé passer PostGIS et `mc` jusqu'à la correction du 2026-08-21 de ce
document (leur image de base ou leurs ajouts n'avaient jamais été vérifiés,
malgré la présence de cette checklist), puis, à un grain encore plus fin,
`psycopg`/`psycopg2-binary` dans `geostudio-core`/`geostudio-export-worker`
(dépendances Python *directes*, pas seulement l'image de base et les
extensions marquantes). Si l'un ou l'autre est copyleft (fort ou faible),
ajouter ici sa section (composant par composant, sources amont précises) et
embarquer une notice + des labels OCI dans l'image, comme pour
`geostudio-qgis-worker`/`geostudio-backup`.

**Si la licence d'un composant ne peut pas être établie avec confiance en
un temps raisonnable** (cas de Chromium/FFmpeg embarqués par Playwright
dans `geostudio-export-worker`, ci-dessus) : le documenter explicitement
comme « non tranché », avec la raison précise de l'impasse (pas de
`THIRD_PARTY_NOTICES` consolidé trouvé, licence hétérogène agrégeant de
nombreux composants tiers, etc.), plutôt que de classer par défaut le
composant comme permissif ou de laisser la ligne du tableau silencieuse
sur ce point.
