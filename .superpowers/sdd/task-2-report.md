# Rapport — Task 2 SP-Deploy-b : runbook de restauration (critère §7-5)

## Ce qui a été implémenté

`docs/runbooks/2026-07-24-restauration-sauvegardes.md` — runbook de
restauration sur perte totale, en 6 étapes (prérequis, récupération +
déchiffrement de l'archive, démarrage DB seule, restauration Postgres
(couvre Keycloak), recréation + repeuplement des buckets MinIO, démarrage
du reste de la stack, vérification). Contenu de départ copié verbatim du
brief (Step 1), puis corrigé à trois endroits après exécution réelle
(Step 2) — voir « Écarts par rapport au brief » ci-dessous. Commit
`ebf6c01` (fichier seul, aucun code applicatif touché, conforme au
scope du brief).

## Écarts par rapport au brief (trouvés en exécutant réellement le runbook)

### 1. Bug réel — étape 4, boucle `mc mirror` sur une archive sans buckets

Le brief écrit :
```bash
for b in /backup/restore-minio/*/; do
  mc mirror --overwrite "$b" "local/$(basename $b)"
done
```
Si l'archive ne contient aucun sous-répertoire de bucket (cas testé : aucun
fichier jamais uploadé avant le backup), le glob ne matche rien et `sh`
(pas de `nullglob`) laisse le motif **littéral** `/backup/restore-minio/*/`
comme valeur de `$b`. `mc mirror` reçoit alors ce chemin littéral, échoue
avec `Unable to stat source... not found`, code de retour 1 — pas un
« ne fait rien » silencieux comme le brief le supposait implicitement.

Fix appliqué au runbook (une garde) :
```bash
for b in /backup/restore-minio/*/; do
  [ -d "$b" ] || continue
  mc mirror --overwrite "$b" "local/$(basename $b)"
done
```
Vérifié : avec la garde, code de retour 0 sans rien mirorer quand `minio/`
est vide ; testé séparément avec un fichier réel dans un bucket synthétique
— `mc mirror` copie effectivement et le fichier est relisible via `mc ls`
après coup (voir transcript plus bas).

### 2. Invocation `backup.sh`/`pg_restore`/`mc` — entrypoint

Anticipé dès la rédaction du runbook (signalé par Task 1, confirmé de
nouveau ici) : l'image `backup` a `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`,
qui ne fait pas `exec "$@"`. Toute commande manuelle doit passer par
`--entrypoint sh backup -c "..."` (ou `--entrypoint /usr/local/bin/backup.sh
backup` pour un backup complet) — jamais `backup <commande>` nu, sous peine
de rester bloqué dans la boucle de planification infinie. Le runbook final
applique ce patron partout (étapes 3, 4).

### 3. Note `pg_restore` corrigée

Le brief anticipait des avertissements `role "..." does not exist` à cette
étape. En exécution réelle sur une base fraîche (volumes neufs), `pg_restore
--clean --if-exists --no-owner` ne produit **aucune sortie** — succès
silencieux, code retour 0 (rien à `--clean` sur une base vierge). Le runbook
a été corrigé pour refléter ce cas réel, en gardant la mention des
avertissements possibles comme cas secondaire (second essai sur un volume
déjà peuplé).

## Transcript d'exécution live complet (Step 2, critère §7-5)

Environnement : projet Compose isolé `-p spdeploytest`, `--env-file`
dédié (`/tmp/spdeploytest.env`, jamais le `.env` du dépôt — qui n'existait
pas au départ de la session), volumes neufs `spdeploytest_*`. Le volume
préexistant `geostudio_pg-data` (mot de passe périmé, incident documenté
dans CLAUDE.md, sans rapport avec cette tâche) n'a jamais été touché —
vérifié avant/après (`docker volume ls | grep geostudio` inchangé tout du
long).

Override local (non commité) `test-auth-override.yml` : force
`CORE_AUTH_MODE: mock` sur le service `core` — la surcouche prod force
`oidc` en dur (pas de `${VAR}`), donc pas modifiable via `.env` seul.
Nécessaire pour créer/relire un item via un `Authorization: Bearer x`
factice sans monter tout le flux OIDC Keycloak/Traefik (hors périmètre de
ce test — le test cible le cycle sauvegarde/restauration des données, pas
l'authentification). Seuls `postgis`, `pgbouncer`, `minio`, `keycloak`,
`core`, `backup` ont été démarrés — `worker`/`cdc-worker`/`martin`/
`titiler`/`shell`/`traefik`/`tunnel` ne participent pas à l'état persistant
testé (Postgres + MinIO) et `tunnel` exige un `TS_AUTHKEY` réel non
disponible dans cet environnement de test.

Confirmé que `docker compose ... -f docker-compose.prod.yml config core`
conserve `build: context: ./core` malgré l'`image: ghcr.io/...` de la
surcouche prod (Compose construit localement et tague, ne tire pas de
GHCR tant que l'image n'existe pas déjà) — pas de dépendance réseau vers
un registre privé pour ce test.

### 1. Item de test créé AVANT le backup

```
$ docker compose -p spdeploytest ... up -d postgis pgbouncer minio keycloak
  Container spdeploytest-postgis-1 Healthy
  Container spdeploytest-keycloak-1 Healthy   (~30s, healthcheck /auth ou racine selon surcouche)

$ docker compose ... up -d core
core-1  | INFO [alembic.runtime.migration] Running upgrade  -> 0001 ... -> 0017   (17 révisions, base vierge)
core-1  | INFO:     Uvicorn running on http://0.0.0.0:8200

$ docker compose ... run --rm --no-deps --entrypoint sh backup -c \
  "curl -sS -X POST http://core:8200/configs -H 'Authorization: Bearer x' \
   -H 'Content-Type: application/json' \
   -d '{\"title\": \"sp-deploy-restore-check\", \"config\": {\"kind\": \"app\", \"layout\": {\"type\": \"grid\", \"items\": []}}}'"
{"id":"9138e31456d54ffb857f215508784dfc","kind":"app",
 "itemId":"54fec78cfd464fc2b25c838997af52cf","version":1, ...}

$ docker compose ... run --rm --no-deps --entrypoint sh backup -c \
  "curl -sS http://core:8200/items/54fec78cfd464fc2b25c838997af52cf -H 'Authorization: Bearer x'"
{"pk":"54fec78cfd464fc2b25c838997af52cf","resourceType":"app","slug":null,
 "title":"sp-deploy-restore-check","abstract":"","owner":"mockuser",
 "thumbnailUrl":null,"date":"2026-07-24T17:46:50.445945","configId":null,
 "isPublished":false,"keywords":[]}
```
Item confirmé pré-backup : `id=54fec78cfd464fc2b25c838997af52cf`,
`title=sp-deploy-restore-check`, `date=2026-07-24T17:46:50.445945`.

### 2. Clé `age` de test + backup réel

```
$ docker compose ... run --rm --no-deps --entrypoint age-keygen backup
Public key: age17n65zwd5drve2uahu22lcsd9s83x820mrhmdzyd9mku7rtm0wptsvgndy6
# created: 2026-07-24T17:47:10Z
AGE-SECRET-KEY-1PC2664KFMK5QC4TV02067DFVJ2XKK6XT4HY2TTGZ2RQHMZ9MSWTQV2NSY5
(clé privée écrite dans un fichier scratch, BACKUP_AGE_RECIPIENT=age17n65... ajouté au .env de test)

$ docker compose ... run --rm --entrypoint /usr/local/bin/backup.sh backup
[backup] 20260724-174731 — début
[backup] postgres.dump: 272.0K
[backup] bucket geostudio-thumbnails absent — rien à mirorer (jamais utilisé)
[backup] bucket geostudio-uploads absent — rien à mirorer (jamais utilisé)
[backup] bucket geostudio-cdc absent — rien à mirorer (jamais utilisé)
[backup] archive chiffrée: /backup/archives/20260724-174731.tar.gz.age
[backup] AVERTISSEMENT: aucune cible hors-site configurée (BACKUP_S3_ENDPOINT vide).
[backup] 20260724-174731 — terminé
```
Aucune ligne `ERREUR`. Archive copiée hors du volume Docker vers un
répertoire hôte bind-monté (`docker compose run -v <hôte>:/host ...`,
copie binaire propre — évite toute corruption par capture shell) :
`latest-for-test.tar.gz.age`, 89144 octets, `md5sum
ccf43fdadd4174d6512d8578aacad7aa`.

### 3. Destruction totale

```
$ docker compose -p spdeploytest ... down -v
  Volume spdeploytest_pg-data Removed
  Volume spdeploytest_minio-data Removed
  Volume spdeploytest_keycloak-data Removed
  Volume spdeploytest_backup-archives Removed
  Network spdeploytest_gis-net Removed

$ docker volume ls | grep spdeploytest   → (rien)
$ docker volume ls | grep geostudio      → geostudio_keycloak-data / minio-data / pg-data (inchangés)
```

### 4. Restauration — étapes 1 à 5 du runbook (texte final, corrigé)

**Étape 1** (déchiffrement, via le conteneur `backup` faute d'`age`/`mc`
installés sur l'hôte de test) :
```
$ age -d -i .../restore-test-key.txt -o restored.tar.gz latest-for-test.tar.gz.age
$ tar -xzf restored.tar.gz
$ find .
./20260724-174731
./20260724-174731/minio
./20260724-174731/keycloak-realm.json
./20260724-174731/postgres.dump
```
Layout confirmé identique à celui documenté par Task 1. Export Keycloak
validé : `{"realm": "geostudio", "clients": 8}`.

**Étape 2** (DB seule, volumes neufs) :
```
$ docker compose ... up -d postgis pgbouncer minio
  Container spdeploytest-postgis-1 Healthy
```

**Étape 3** (`pg_restore`) :
```
$ docker compose ... run --rm -v .../20260724-174731:/backup/restore:ro \
  --no-deps --entrypoint sh backup -c \
  "PGPASSWORD=$PG_PASSWORD pg_restore -h postgis -U gis -d gis --clean --if-exists --no-owner /backup/restore/postgres.dump"
(aucune sortie — succès silencieux, code 0)

$ psql -h postgis -U gis -d gis -c 'select id, title, resource_type from items;'
                id                |          title          | resource_type
-----------------------------------+-------------------------+---------------
 54fec78cfd464fc2b25c838997af52cf | sp-deploy-restore-check | app
(1 row)
```
**Preuve directe** : l'item survit à la destruction totale et à la
restauration Postgres, avant même que `core` ne soit redémarré.

**Étape 4** (buckets MinIO, avec la garde corrigée) :
```
$ mc mb --ignore-existing local/geostudio-thumbnails local/geostudio-uploads local/geostudio-cdc
Bucket created successfully `local/geostudio-thumbnails` (×3)

$ for b in /backup/restore-minio/*/; do [ -d "$b" ] || continue; mc mirror ...; done
(code 0, rien à mirorer — l'archive ne contenait aucun bucket, cf. étape 2 du backup)
```
Test complémentaire (bucket synthétique avec un fichier réel, pour prouver
que le chemin non vide fonctionne aussi) :
```
`/backup/restore-minio/geostudio-uploads/test-object.txt` -> `local/geostudio-uploads/test-object.txt`
$ mc ls local/geostudio-uploads/
[...]  41B  STANDARD test-object.txt
```

**Étape 5** (reste de la stack) :
```
$ docker compose ... up -d keycloak core

keycloak-1 | KC-SERVICES0030: Full model import requested. Strategy: IGNORE_EXISTING
keycloak-1 | Realm 'geostudio' already exists. Import skipped
keycloak-1 | KC-SERVICES0032: Import finished successfully

core-1 | INFO [alembic.runtime.migration] Context impl PostgresqlImpl.
core-1 | (aucune ligne "Running upgrade" — comparé aux 17 lignes du démarrage à froid)
core-1 | INFO:     Uvicorn running on http://0.0.0.0:8200
```
Confirme empiriquement les deux points que le brief demandait de vérifier :
`--import-realm` n'écrase ni ne duplique (stratégie par défaut
`IGNORE_EXISTING`), et `alembic upgrade head` est un no-op réel (pas
seulement "silencieux" — zéro migration listée, contre 17 au premier
démarrage).

### 5. Vérification finale — relecture de l'item post-restauration

```
$ docker compose ... run --rm --no-deps --entrypoint sh backup -c \
  "curl -sS http://core:8200/items/54fec78cfd464fc2b25c838997af52cf -H 'Authorization: Bearer x'"
{"pk":"54fec78cfd464fc2b25c838997af52cf","resourceType":"app","slug":null,
 "title":"sp-deploy-restore-check","abstract":"","owner":"mockuser",
 "thumbnailUrl":null,"date":"2026-07-24T17:46:50.445945","configId":null,
 "isPublished":false,"keywords":[]}
```
Réponse **identique** à celle obtenue avant le backup (même `pk`, même
`title`, même `date` de création à la microseconde près) — preuve que la
restauration réinjecte la donnée existante et n'en recrée pas une nouvelle.
Cycle complet écriture → backup → destruction → restauration → relecture
prouvé (critère §7-5).

### Nettoyage

```
$ docker compose -p spdeploytest ... down -v   → tous les volumes spdeploytest_* supprimés
$ docker volume ls | grep geostudio            → inchangé (3 volumes préexistants, non touchés)
$ docker rmi spdeploytest-backup:latest        → image de test supprimée
                                                  (ghcr.io/tlenenao/geostudio-core:latest laissé
                                                   intact — tag partagé/réutilisable entre projets
                                                   Compose, pas propre à ce test, contenu inchangé
                                                   par ce build en cache)
```
Fichiers scratch (`.env` de test, clé `age` de test, archive copiée,
répertoire de restauration, override compose) supprimés (`rm -rf`, plus un
conteneur Alpine jetable pour les quelques fichiers écrits root:root par
les conteneurs).

## Fichiers modifiés

- `docs/runbooks/2026-07-24-restauration-sauvegardes.md` (créé) — seul
  fichier commité (`ebf6c01`).

Aucun fichier applicatif touché. Fichiers de test/scratch (`.env` isolé,
override compose, clé `age`, archive de test) tous supprimés avant la fin
de la session — rien laissé sur le disque au-delà du runbook.

## Auto-revue

- **Le runbook commité correspond à ce qui a été réellement exécuté**, pas
  au brouillon du brief : les 3 écarts trouvés en marchant dessus (boucle
  `mc mirror` sur glob vide, note `pg_restore` corrigée, patron
  `--entrypoint` appliqué partout) sont reflétés dans le texte final, avec
  preuve empirique citée inline.
- **Le cycle live prouve réellement la survie des données au `down -v`** :
  la vérification à l'étape 3 (avant même de redémarrer `core`) montre
  l'item directement en base via `psql`, pas seulement via l'API — élimine
  toute ambiguïté sur une éventuelle re-création côté application.
  Volumes/réseau du projet de test entièrement neufs à chaque étape
  (`Volume ... Creating` visible dans les logs Compose), pas de résidu de
  l'exécution précédente qui aurait pu fausser le test.
- **Preuve concrète** : tous les extraits de commande ci-dessus sont des
  sorties réelles copiées depuis la session (identifiants d'item, horodatage
  à la microseconde, md5sum de l'archive, logs Keycloak/Alembic verbatim) —
  pas des affirmations.
- Le volume préexistant `geostudio_pg-data` (incident documenté dans
  CLAUDE.md, mot de passe périmé) n'a jamais été touché — projet Compose
  isolé du début à la fin, vérifié explicitement avant et après chaque
  opération destructive.

## Points d'attention / suivis non bloquants

- La surcouche prod (`docker-compose.prod.yml`) fixe `CORE_AUTH_MODE: oidc`
  en dur sur `core` (pas de `${VAR}`) — un runbook de restauration en
  production réelle n'a pas besoin de contourner ça (l'auth OIDC réelle
  fonctionne normalement une fois Keycloak/Traefik/DNS en place), mais toute
  future vérification live similaire sur cette surcouche devra soit monter
  tout le flux OIDC, soit passer par un override de test comme celui utilisé
  ici (non commité, documenté dans ce rapport pour référence).
- `retention.py` émet un `DeprecationWarning` (`datetime.utcnow()`) à
  chaque exécution de `backup.sh` — visible dans les logs, sans impact
  fonctionnel, mais à corriger un jour (hors périmètre de cette tâche,
  signalé pour information comme demandé par le brief).
- Aucun défaut bloquant trouvé dans le service `backup` de Task 1 lui-même :
  le seul bug réel de cette session était dans le **texte du runbook**
  (boucle `mc mirror`), pas dans `backup.sh`/`entrypoint.sh`/`Dockerfile`.

## Corrections post-revue (2 findings, documentation seule)

Deux findings « Important » remontés par la revue de tâche sur le commit
`ebf6c01`, corrigés dans `docs/runbooks/2026-07-24-restauration-sauvegardes.md`
seul (aucun autre fichier touché, pas de ré-exécution Docker — la procédure
sous-jacente était déjà prouvée correcte, seul le texte manquait de
précision).

### Finding 1 — prérequis clé privée `age` incomplet vis-à-vis de la contrainte du plan

Le plan (Global Constraints, `docs/superpowers/plans/2026-07-24-sp-deploy-b-durabilite.md`)
exige explicitement : *« La clé privée `age` ne vit JAMAIS dans le dépôt,
l'image, ni un volume Docker — seule la clé **publique**
(`BACKUP_AGE_RECIPIENT`) est en `.env`. Documenté explicitement dans le
runbook de restauration. »* Le runbook ne mentionnait que le stockage « hors
de la machine de production », sans jamais dire explicitement ce qui est
interdit.

**Avant** (ligne 8-11) :
```
- La clé **privée** `age` correspondant à `BACKUP_AGE_RECIPIENT` — stockée
  **hors de la machine de production** (gestionnaire de mots de passe,
  copie papier). Sans elle, les archives sont irrécupérables : c'est
  volontaire (chiffrement au repos, spec SP-Deploy §4.1).
```

**Après** :
```
- La clé **privée** `age` correspondant à `BACKUP_AGE_RECIPIENT`. Elle ne
  vit **jamais** dans le dépôt git, dans l'image `backup` (ni aucune autre
  image), ni dans un volume Docker — seule la clé **publique**
  (`BACKUP_AGE_RECIPIENT`) a sa place en `.env`. La clé privée est stockée
  **hors de la machine de production**, exclusivement chez l'opérateur
  (gestionnaire de mots de passe, copie papier, ou tout autre stockage
  personnel sécurisé équivalent). Sans elle, les archives sont
  irrécupérables : c'est volontaire (chiffrement au repos, spec
  SP-Deploy §4.1).
```

### Finding 2 — section de clôture surinterprétait le critère §7-5

Spec §7 critère 5 : *« écrire une donnée → backup → détruire les volumes →
restaurer → relire la donnée + reconnexion utilisateur. »* La conclusion du
runbook affirmait le critère « entièrement vérifié », alors que le
transcript live (section ci-dessus) montre que l'exécution a utilisé un
override non commité `CORE_AUTH_MODE: mock` pour contourner Keycloak/OIDC —
seule la survie de la donnée (via `psql` puis via l'API) a été prouvée ; la
reconnexion utilisateur réelle via OIDC n'a jamais été exercée.

**Avant** (ligne 139-147) :
```
**Procédure exécutée et vérifiée de bout en bout (Task 2, Step 2, critère
§7-5)** : cycle complet écriture → backup → destruction totale (`down -v`)
→ étapes 1-5 ci-dessus → relecture, sur environnement isolé (volumes
jetables). Un item `sp-deploy-restore-check` créé avant le backup
(`GET /items/<id>` avant destruction) a été retrouvé identique après
restauration (`GET /items/<id>` après l'étape 5 — même `id`, même `title`,
même horodatage de création `date`), confirmant que la restauration
réinjecte les données existantes plutôt que d'en créer de nouvelles.
Détail de l'exécution : rapport `.superpowers/sdd/task-2-report.md`.
```

**Après** (reformulé en deux paragraphes distincts « vérifié » / « pas
vérifié », plus la mention `Détail de l'exécution`) :
```
**Ce qui a été vérifié en exécution réelle (Task 2, Step 2)** : la moitié
« survie de la donnée » du critère §7-5 — cycle complet écriture → backup →
destruction totale (`down -v`) → étapes 1-5 ci-dessus → relecture, sur
environnement isolé (volumes jetables). Un item `sp-deploy-restore-check`
créé avant le backup (`GET /items/<id>` avant destruction) a été retrouvé
identique après restauration : d'abord relu **directement en base** via
`psql -c 'select id, title, resource_type from items;'` juste après
`pg_restore` (étape 3, avant même le redémarrage de `core`), puis via
`GET /items/<id>` après l'étape 5 (même `id`, même `title`, même horodatage
de création `date` à la microseconde près) — confirmant que la restauration
réinjecte les données existantes plutôt que d'en créer de nouvelles.

**Ce qui n'a PAS été vérifié** : la reconnexion utilisateur réelle via
Keycloak/OIDC. Cette exécution a démarré `core` avec un override local non
commité (`CORE_AUTH_MODE: mock`) pour appeler l'API avec un
`Authorization: Bearer x` factice, spécifiquement pour isoler le test sur
le cycle de restauration des données sans monter tout le flux OIDC
Keycloak/Traefik (hors périmètre de ce test). La surcouche prod
(`docker-compose.prod.yml`) fixe `CORE_AUTH_MODE: oidc` en dur en
production réelle, donc ce contournement ne s'applique pas à un vrai
déploiement — mais cela signifie que **le critère §7-5 n'a été vérifié qu'à
moitié par cette exécution** : la connexion effective d'un compte Keycloak
restauré via un vrai flux OIDC contre une stack restaurée reste un point
ouvert, à couvrir lors d'un futur exercice de restauration grandeur nature
(ou de la première restauration réelle en production).

Détail de l'exécution : rapport `.superpowers/sdd/task-2-report.md`.
```

Aucune ré-exécution Docker nécessaire pour ces deux corrections : le texte
d'origine décrivait fidèlement les commandes exécutées, seule
l'interprétation/portée de ce qui avait été prouvé (finding 2) et le niveau
de détail d'une contrainte déjà respectée en pratique (finding 1 — la clé
privée de test n'a jamais été commitée, mise en image, ni en volume ; le
texte ne le disait simplement pas assez explicitement) manquaient. Commité
séparément de `ebf6c01`.
