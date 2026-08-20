# Licences des composants de cette image

Cette image est publiée par le projet GeoStudio (Apache-2.0) et **contient
un logiciel sous GNU Affero GPL** (le client MinIO `mc`), aux côtés de
composants permissifs et d'un interpréteur système sous GPL non applicatif.

## Composant copyleft

- **`mc` (client MinIO)** — binaire officiel téléchargé directement depuis
  `https://dl.min.io/client/mc/release/linux-amd64/mc` (le paquet Alpine
  `mc` est Midnight Commander, un gestionnaire de fichiers terminal sans
  rapport, cf. commentaire du `Dockerfile`) — **AGPL-3.0-or-later**, licence
  du projet MinIO (serveur et client) depuis son passage intégral sous
  cette licence en 2021. Vérifié sur l'en-tête de licence d'un fichier
  source réel du dépôt amont
  (<https://github.com/minio/mc/blob/master/cmd/access-perms.go> : « GNU
  Affero General Public License [...] either version 3 of the License, or
  (at your option) any later version ») et sur le `LICENSE` du dépôt
  (<https://github.com/minio/mc>, dépôt aujourd'hui archivé mais dont la
  licence du binaire déjà téléchargé n'en est pas affectée).

  **Ce binaire est utilisé ici tel quel, non modifié, invoqué en
  sous-processus par `backup.sh` pour piloter des transferts vers S3/MinIO
  — il n'est jamais servi par GeoStudio comme service réseau, et GeoStudio
  n'expose aucune de ses fonctionnalités à travers un réseau.** La clause
  réseau de l'AGPL (§13 — obligation de proposer le code source aux
  utilisateurs distants d'un programme AGPL modifié et exploité comme
  service réseau) **ne s'applique donc pas à cet usage** : GeoStudio ne
  modifie pas `mc` et ne l'expose pas comme service. L'obligation qui
  s'applique bien ici, comme pour tout binaire copyleft redistribué sans
  modification, est l'offre d'accès aux sources correspondantes — satisfaite
  par référence au dépôt amont ci-dessus, pratique usuelle, non revue par un
  juriste. **Cette analyse est spécifique à ce déploiement précis** (binaire
  non modifié, invoqué en sous-processus, jamais servi sur le réseau) : elle
  ne doit pas être lue comme une affirmation générale qu'une offre de
  source suffirait à décharger l'AGPL §13 dans une situation où `mc` (ou un
  logiciel AGPL modifié) serait lui-même exposé comme service réseau.

  **Limite connue (non corrigée dans cette notice) : le téléchargement
  n'est pas épinglé en version.** `deploy/backup/Dockerfile` télécharge
  `mc` depuis `release/linux-amd64/mc`, un chemin qui pointe toujours vers
  la dernière version publiée au moment du build — pas un tag figé. La
  version exacte de `mc` réellement redistribuée par une image donnée est
  donc celle qui était courante au moment de ce build précis, non
  reproductible d'un build à l'autre. C'est une limite réelle pour une
  offre de source (le pointeur ci-dessus renvoie vers le dépôt, pas vers un
  commit/tag précis correspondant au binaire embarqué) — signalée ici
  plutôt que masquée, mais non corrigée par cette notice : la corriger
  changerait le contenu réel de l'image (version de `mc` exacte) et
  nécessiterait sa propre vérification, hors périmètre de cette tâche.

## Composants permissifs (paquets Alpine ajoutés explicitement)

| Composant | Licence (SPDX) | Source vérifiée |
|---|---|---|
| `postgresql16-client` | `PostgreSQL` (permissive de type BSD/MIT) | <https://www.postgresql.org/about/licence/> |
| `age` (FiloSottile/age) | `BSD-3-Clause` | <https://github.com/FiloSottile/age/blob/main/LICENSE> |
| `curl` | `curl` (identifiant SPDX propre, permissive de type MIT/ISC) | <https://curl.se/docs/copyright.html> ; <https://spdx.org/licenses/curl.html> |
| `jq` | `MIT` | <https://github.com/jqlang/jq/blob/master/COPYING> |
| `tzdata` (base de données de fuseaux horaires IANA) | domaine public — aucun identifiant SPDX canonique ne couvre ce cas à ce jour (SPDX n'a pas encore standardisé de licence « domaine public » générique) | <https://github.com/eggert/tz/blob/main/LICENSE> : « Unless specified below, all files in the tz code and data [...] are in the public domain. » |
| `python3` (CPython) | `PSF-2.0` | <https://docs.python.org/3/license.html> ; <https://spdx.org/licenses/PSF-2.0.html> |

## Interpréteur système (hors périmètre de redistribution applicative)

- **`bash`** — `GPL-3.0-or-later` (confirmé par le champ licence du paquet
  Alpine). Traité, comme dans le reste de ce document
  (`docs/ops/redistribution-images.md`), comme un utilitaire système
  invoqué pour exécuter `backup.sh` — pas comme un composant applicatif
  redistribué par GeoStudio comme partie de son produit, au même titre que
  `coreutils`/`busybox` dans toute image Debian/Alpine.

## Code GeoStudio

`backup.sh`, `retention.py`, `entrypoint.sh` — Apache-2.0, publiés dans le
dépôt GeoStudio (<https://github.com/tlenenao/geostudio>,
`deploy/backup/`).

## Ce que cela ne change pas

Le cœur GeoStudio (`core/`) reste sous Apache-2.0 : ce conteneur est un
utilitaire de sauvegarde autonome, il n'est pas lié à `mc` — il l'invoque
en sous-processus pour transférer des sauvegardes vers S3/MinIO.
