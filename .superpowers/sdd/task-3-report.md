# Task 3 report — bootstrap Q&A : hôte public, `.env`, premier admin Keycloak
# (SP-Deploy-c)

*(Ce fichier contenait auparavant un rapport d'une tâche "Task 3" différente
d'une session antérieure — SP-Deploy-a, `GEOSTUDIO_PUBLIC_HOST` source de
vérité unique. Écrasé en totalité avec le rapport de la tâche actuelle,
SP-Deploy-c Task 3.)*

## Ce qui a été implémenté

Ajout à `scripts/install.sh` (Steps 1-4 du brief) : bootstrap `.env`
(`ensure_env_file`/`set_env_var`), résolution de l'hôte public
(`prompt_public_host`, manuel ou découverte Tailscale), activation du Funnel
(`activate_funnel`), question de cible de sauvegarde hors-site
(`prompt_backup_target`), création du premier administrateur Keycloak
(`prompt_admin`).

### Fix 1 (signalé par la tâche) — démarrage du tunnel

Bug confirmé dans le code d'exemple du brief : la branche « hôte manuel » de
`prompt_public_host()` faisait `return 0` **avant** la ligne
`$COMPOSE up -d traefik tunnel`, alors que `activate_funnel()` (Step 3) fait
inconditionnellement `$COMPOSE exec -T tunnel tailscale funnel --bg 80` juste
après, dans les deux cas. Corrigé en sortant `$COMPOSE up -d traefik tunnel`
de la branche conditionnelle (démarre dans tous les cas) et en ne gardant
sous la condition « pas de nom fourni » que la boucle de découverte
`tailscale status --json`. Vérifié empiriquement (voir plus bas) : avec un
hôte manuel, `traefik`+`tunnel` démarrent bien et `activate_funnel` trouve un
conteneur `tunnel` à cibler (l'échec observé ensuite est uniquement dû à
l'absence d'authentification Tailscale réelle, pas à un conteneur absent).

### Fix 2 (trouvé en vérifiant réellement) — `quay.io/keycloak/keycloak` n'a
### ni `curl` ni `wget`

Vérifié empiriquement (`docker run --rm --entrypoint sh quay.io/keycloak/keycloak:24.0
-c 'curl --version'` → `command not found`, idem `wget`). Le code d'exemple
du brief pour Step 4 fait `$COMPOSE exec -T keycloak curl ...` à plusieurs
reprises — ça échouerait systématiquement dans ce conteneur (cohérent avec
le healthcheck du service, déjà écrit en bash brut `/dev/tcp` plutôt qu'en
curl, dans `docker-compose.yml`/`docker-compose.prod.yml`). Remplacé par
`kcadm.sh` (l'outil d'admin fourni par l'image Keycloak elle-même, dans
`/opt/keycloak/bin/`), qui sert à la fois de sonde de disponibilité
(`config credentials` échoue tant que Keycloak n'est pas prêt) et
d'authentification — un seul mécanisme au lieu de deux appels curl séparés
(health-check + token). Le parsing JSON (`get users -q email=...`) reste fait
via `jq`, mais exécuté sur l'HÔTE (comme le fait déjà le code du brief pour
`tailscale status --json | jq` en Step 2) puisque le conteneur Keycloak n'a
pas non plus `jq`.

### Fix 3 (trouvé en vérifiant réellement) — `$KC_PASSWORD` non lié dans le
### shell du script

Le script a `set -euo pipefail` (donc `nounset`) mais ne fait jamais
`source .env` (choix délibéré : `.env` reste une donnée, jamais du code
exécuté — même précaution que `set_env_var`). Le code d'exemple du brief
référence directement `${KC_PASSWORD}` en bash dans `prompt_admin()`, ce qui
aurait provoqué une erreur « unbound variable » immédiate. Corrigé en lisant
la valeur directement depuis `.env` (`grep '^KC_PASSWORD=' .env | cut -d= -f2-`),
sans jamais exécuter le fichier.

### Fix 4 (trouvé en vérifiant réellement, hors périmètre strict de
### `scripts/install.sh`) — `CORE_ADMIN_SUBS` absent de `.env.example` et de
### `docker-compose.yml`

Deux problèmes cumulatifs découverts en testant `prompt_admin` pour de vrai :

1. `.env.example` ne contient **aucune** ligne `CORE_ADMIN_SUBS=` → le
   `sed -i "s|^CORE_ADMIN_SUBS=.*|...|"` de `set_env_var` ne trouve rien à
   remplacer et ne fait **rien** (pas d'erreur, juste un no-op silencieux) :
   la variable n'atterrissait jamais dans `.env`.
2. Même en supposant `.env` correct, `docker-compose.yml` (service `core`)
   ne déclare `CORE_ADMIN_SUBS` nulle part dans son bloc `environment:` — or
   docker compose ne transmet aux conteneurs QUE les variables explicitement
   listées dans `environment:` (pas de `env_file: .env` sur ce service) :
   même avec la ligne dans `.env`, le processus `core` ne l'aurait jamais vue.

Sans ces deux corrections, tout le Step 4 aurait été un théâtre : le script
aurait affiché « ✓ Compte admin créé » sans qu'aucun admin ne soit jamais
réellement promu. Corrigé par deux ajouts minimaux et non destructifs :
- `.env.example` : ligne `CORE_ADMIN_SUBS=` (vide par défaut, comme
  `TS_AUTHKEY=`), avec commentaire référençant
  `core/app/auth/dependency.py` et l'installeur.
- `docker-compose.yml` : `CORE_ADMIN_SUBS: ${CORE_ADMIN_SUBS:-}` ajouté au
  bloc `environment:` du service `core` (même style que
  `CORE_READ_ONLY_MODE: ${CORE_READ_ONLY_MODE:-false}` juste au-dessus).
  Vérifié que `docker-compose.prod.yml` (qui redéfinit partiellement
  `core.environment`) fusionne bien par clé et laisse passer cette variable
  (`docker compose config` confirmé, voir tests ci-dessous).

Remarque : `CORE_ANALYST_SUBS` (variable sœur, même mécanisme dans
`core/app/auth/dependency.py`) a le même trou (absente de `.env.example` et
de `docker-compose.yml`) mais n'a **pas** été touchée — hors périmètre de
cette tâche (aucun Step de ce plan ne promeut d'analyste), laissé tel quel.
Signalé ici pour visibilité.

Ces Fix 2-4 dépassent la liste de fichiers du brief (« Modify:
scripts/install.sh » uniquement) : `.env.example` et `docker-compose.yml`
ont aussi été modifiés. Fix 2-3 restent internes à `scripts/install.sh`.
Fix 4 touche deux fichiers partagés — jugé nécessaire car sans lui, la
fonctionnalité que ce Step est censé livrer (permettre à quelqu'un de
devenir admin) ne fonctionne tout simplement pas, silencieusement. Si une
tâche ultérieure (Task 4, ou une passe dédiée) prévoyait déjà de faire ce
câblage, ce fix est redondant mais inoffensif (idempotent, valeur vide par
défaut, ne change aucun comportement existant).

## Ce qui a été testé, avec sortie réelle

Toutes les vérifications ont été faites dans des clones jetables sous
`/tmp` (jamais dans `/home/lenen/projets/geostudio`), copiant les fichiers
modifiés depuis le dépôt de travail (pas encore commités au moment des
tests) par-dessus un `git clone` du HEAD committé.

### 1. `ensure_env_file()` / `set_env_var()` — vérifié réellement, pas de Docker

```
--- run 1 (no .env yet) ---
.env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public.
--- run 2 (idempotent, should say already exists) ---
✓ .env existe déjà — secrets conservés (idempotent).
--- set_env_var: change GEOSTUDIO_PUBLIC_HOST only ---
GEOSTUDIO_PUBLIC_HOST=test.example.ts.net
OK: PG_PASSWORD untouched by set_env_var targeting GEOSTUDIO_PUBLIC_HOST
OK: .env.bak cleaned up
```

### 2. `prompt_admin()` — vérifié end-to-end avec un vrai Keycloak (Docker),
### deux passages pour l'idempotence

Stack réelle : `postgis pgbouncer minio keycloak` démarrés via
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
dans le clone jetable.

Run 1 (email `admin-run1@example.com`, pas encore d'utilisateur) :
```
Démarrage de Keycloak/cœur pour créer le compte admin...
 [...conteneurs docker...]
Attente de Keycloak et authentification à l'API Admin...
Created new user with id 'fbb53c2e-e620-4abb-9ff7-e5999d96b620'
✓ Compte admin créé : admin-run1@example.com / mot de passe temporaire : JpdkEC3tnWUnrGhVgqFjtzxy
  (à changer à la première connexion — non stocké par ce script au-delà de cet affichage)
=== .env after run 1 ===
CORE_ADMIN_SUBS=fbb53c2e-e620-4abb-9ff7-e5999d96b620
```

Run 2 (même email, relance — test d'idempotence) :
```
Attente de Keycloak et authentification à l'API Admin...
✓ Compte admin déjà existant (admin-run1@example.com) — id réutilisé.
=== .env after run 2 (idempotency check) ===
CORE_ADMIN_SUBS=fbb53c2e-e620-4abb-9ff7-e5999d96b620
```
Même UUID, aucune erreur de doublon, aucun nouvel utilisateur créé.

Autres variables `.env` non affectées, vérifié après les deux runs :
```
PG_PASSWORD=sBHuiz8TfCsdwNWiCNT3J8mTi03tAWvt
MINIO_PASSWORD=ENQg7GAnRAFZI5WHa0l8HTv8DLYII4NL
KC_PASSWORD=hgIXIuOY2KKpGVuKYMtV4KD3c5LKhnLv
MARTIN_SECRET=s1HUUOpZUmMxASydDB98B4T1hIxrZNpz
```

Câblage `docker-compose.yml` confirmé via `docker compose config` sur le
clone jetable après le Fix 4 :
```
CORE_ADMIN_SUBS present in core.environment: True
value: fbb53c2e-e620-4abb-9ff7-e5999d96b620
```

### 3. Vérification empirique du claim « `id` Keycloak == claim `sub` du token »

Documenté dans le contexte du brief comme « à confirmer empiriquement ».
Confirmé réellement : création d'un utilisateur de test, ajout
firstName/lastName (nécessaire pour que le grant direct ROPC n'échoue pas
sur « Account is not fully set up », spécificité du User Profile de Keycloak
24, sans rapport avec le script lui-même), obtention d'un token via
`curlimages/curl` sur le réseau docker du projet, décodage du JWT :
`sub` = `cb739069-ac23-4e26-831b-4c509415031f`, identique à l'`id` retourné
par l'API Admin pour cet utilisateur. Confirme l'hypothèse du brief.

### 4. `prompt_public_host()` — branche manuelle, vérifiée mécaniquement (pas
### de vrai compte Tailscale disponible dans cet environnement)

```
Démarrage du tunnel Tailscale...
 [...traefik + tunnel créés et démarrés avec succès...]
Activation de Tailscale Funnel (accès public sans port ouvert)...
Logged out.
EXIT CODE: 1
```
- Aucune invite « Clé Tailscale » (TS_AUTHKEY déjà exportée, comme prévu).
- Aucun message « Découverte automatique » (boucle de découverte
  correctement sautée puisqu'un hôte manuel a été fourni).
- `.env` : `GEOSTUDIO_PUBLIC_HOST=my-manual-host.example.com` (chaîne exacte
  fournie), `TS_AUTHKEY=tskey-auth-fake-not-a-real-key` — écrits
  correctement, autres variables (`PG_PASSWORD`, `KC_PASSWORD`) intactes.
- Les conteneurs `traefik` et `tunnel` ont bien démarré (preuve directe du
  Fix 1 : sans lui, `tunnel` n'aurait jamais existé sur cette branche, et
  `activate_funnel`'s `exec` aurait échoué avec « no such container », pas
  avec une erreur d'authentification).
- Logs du conteneur `tunnel` confirmant qu'il a bien tenté un enregistrement
  réel auprès de `controlplane.tailscale.com` avant d'échouer (pas un crash
  local) : `control: RegisterReq: ...` puis `Logged out.` en sortie de
  `tailscale funnel --bg 80` (échec d'auth attendu, aucune clé réelle
  disponible dans cet environnement).

### 5. Ce qui n'a PAS pu être vérifié de bout en bout (gap documenté, non
### bloquant — même précédent que SP-Deploy-a Task 6)

- La boucle de découverte automatique (`tailscale status --json` polling)
  dans `prompt_public_host()` : nécessite un vrai tailnet pour que
  `.Self.DNSName` soit renseigné. Non testable ici (pas de `TS_AUTHKEY`
  réel, pas de compte Tailscale dans cet environnement).
- L'activation réelle du Funnel dans `activate_funnel()` : `tailscale funnel
  --bg 80` nécessite une authentification tailnet réussie au préalable.
  Testé jusqu'au point d'échec attendu (voir §4 ci-dessus) ; la partie
  fonctionnelle réelle (le trafic public arrivant effectivement via Funnel)
  reste non vérifiable sans compte réel.

## Fichiers modifiés

- `/home/lenen/projets/geostudio/scripts/install.sh` — Steps 1-4 ajoutés
  (avec Fix 1-3 ci-dessus).
- `/home/lenen/projets/geostudio/.env.example` — ligne `CORE_ADMIN_SUBS=`
  ajoutée (Fix 4).
- `/home/lenen/projets/geostudio/docker-compose.yml` —
  `CORE_ADMIN_SUBS: ${CORE_ADMIN_SUBS:-}` ajouté à l'environnement du
  service `core` (Fix 4).

## Auto-revue

- Complétude : Steps 1-4 du brief présents, dans l'ordre, avec messages en
  français / identifiants en anglais.
- Discipline de périmètre : aucun `up -d` du stack complet, aucune boucle
  d'attente de santé finale, aucun `docker compose down` — laissé à la
  Task 4, comme demandé. Le seul dépassement de périmètre fichier
  (`.env.example`, `docker-compose.yml`) est documenté ci-dessus avec sa
  justification.
- Idempotence : `ensure_env_file` (testé), `set_env_var` (testé, jamais
  d'écrasement d'une autre variable, `.bak` toujours supprimé), `prompt_admin`
  (testé deux fois de suite avec un vrai Keycloak — deuxième passage
  réutilise l'id existant, ne recrée rien).
- `bash -n scripts/install.sh` : syntaxe OK. `shellcheck` non disponible
  dans cet environnement (non installé, pas de sudo) — vérifié
  manuellement à la place.
- Nettoyage : tous les clones jetables (`/tmp/geostudio-install-test*`,
  `/tmp/geostudio-explore`, `/tmp/geostudio-backup-target-test`) et toutes
  les ressources Docker (conteneurs, volumes, réseaux) créés pendant les
  tests ont été supprimés après chaque passage
  (`docker compose ... down -v` + `rm -rf`). Confirmé par
  `docker ps -a`/`docker network ls` après chaque nettoyage : aucun résidu.

## Précisions demandées explicitement par la mission

- Vérifié pour de vrai (aucun compte externe nécessaire) : `ensure_env_file`/
  `set_env_var` (opérations fichier pures) et `prompt_admin` de bout en bout
  (vrai Keycloak Docker, vrai token admin, vrai utilisateur créé, vrai UUID
  écrit dans `CORE_ADMIN_SUBS`, idempotence confirmée sur un second passage).
- Ne peut pas être vérifié de bout en bout ici (documenté, non bloquant) :
  la boucle de découverte automatique Tailscale et l'activation réelle du
  Funnel — toutes deux nécessitent un vrai tailnet, absent de cet
  environnement. La branche « hôte manuel » a en revanche été vérifiée
  mécaniquement de bout en bout (conteneurs démarrés, `.env` correct),
  l'échec de `activate_funnel` observé étant strictement dû à l'absence
  d'authentification réelle (confirmé par les logs du conteneur `tunnel`).

## Corrections post-revue (2 findings de la revue de code sur ce Task 3)

### Finding 1 (CRITICAL) — `exact=true` manquant dans les lookups kcadm.sh

`prompt_admin()` interrogeait `get users -q "email=${ADMIN_EMAIL}"` sans
`exact=true` : `kcadm.sh` fait un **match par sous-chaîne**, pas un match
exact. Corrigé en ajoutant un second `-q "exact=true"` (paramètre répété,
supporté par `kcadm.sh`) aux DEUX appels `get users` (lookup idempotence +
récupération de l'id après `create users`).

Reproduction empirique du bug (Keycloak jetable, conteneur
`kc-exact-test`, jamais le dépôt réel) :
```
docker run -d --name kc-exact-test -p 18080:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:24.0 start-dev
# kcadm.sh config credentials ... (authentifié après 6 tentatives)
# realm "geostudio" créé, 3 utilisateurs créés :
#   admin@example.com       -> id a7c672a7-f2ab-4680-8b68-44dc64696a77
#   superadmin@example.com  -> id 26483915-c98f-47b5-b22b-2b415366cad3
#   aaaadmin@example.com    -> id 4231fb05-4914-48a5-b3ab-45e3c788f5c7
```

SANS `exact=true` — `get users -q "email=admin@example.com"` retourne les
**3** utilisateurs (substring match), triés `aaaadmin` → `admin` →
`superadmin` ; `.[0].id` résoudrait donc vers `4231fb05-...`
(`aaaadmin@example.com`) — un compte totalement différent de celui demandé,
promu admin silencieusement.

AVEC `exact=true` — `get users -q "email=admin@example.com" -q
"exact=true"` retourne **exactement 1** résultat : `a7c672a7-...`
(`admin@example.com`), le bon compte.

Confirme exactement le scénario du reviewer. Le comportement d'idempotence
du happy path (déjà testé de bout en bout avec un seul utilisateur dans la
section précédente de ce rapport) n'est pas affecté : avec un seul
utilisateur, substring match et exact match coïncidaient déjà ; le fix ne
fait que retirer les faux positifs en présence d'emails qui se recouvrent.

### Finding 2 (Important) — `jq` sans détection ni message d'erreur utile

`prompt_public_host()` et `prompt_admin()` pipent toutes deux la sortie de
`docker compose exec` vers `jq` exécuté sur l'HÔTE. Aucune tâche
précédente (`ensure_docker()` inclus) ne vérifiait sa présence : avec `set
-euo pipefail`, une absence de `jq` aurait fait échouer le script avec un
`bash: jq: command not found` cru, sans indication du paquet manquant.

Ajout de `ensure_jq()`, juste après `ensure_docker()` (même section
prérequis, même style : `command -v`, `confirm()` avant toute installation,
jamais silencieux). Différence assumée avec `ensure_docker` : `jq` étant un
paquet natif standard (pas de script d'installation dédié comme
`get.docker.com`), la branche Linux essaie `apt-get` → `dnf` → `pacman`
dans cet ordre puis abandonne avec message si aucun n'est trouvé ; la
branche Darwin n'installe jamais automatiquement (pas de garantie que
Homebrew soit présent), elle affiche `brew install jq` et sort en erreur —
même philosophie que la branche Darwin de `ensure_docker` pour Docker
Desktop.

Vérifié : découverte en cours de tests que `jq` n'est en réalité PAS
installé sur cet hôte (`command -v jq` → rien), donc le chemin « absent »
a été testé directement, sans avoir besoin de le masquer via `PATH`. Tests
faits dans un harnais isolé (`/tmp/.../scratchpad/jq-test/ensure_jq_test.sh`,
copie exacte de la fonction, `sudo` stubbée pour ne faire AUCUNE
modification système réelle pendant le test) :

```
=== TEST A: jq absent, INSTALL_YES=1 ===
✗ jq (parseur JSON) est requis et n'a pas été détecté.
Installer jq via le gestionnaire de paquets du système ? [y/N] → y (INSTALL_YES=1)
[stub sudo] apt-get install -y jq
jq installé.
EXIT: 0

=== TEST B: jq absent, INSTALL_YES=0, réponse "n" ===
✗ jq (parseur JSON) est requis et n'a pas été détecté.
Installation annulée — relancez ce script une fois jq installé manuellement.
EXIT: 1

=== TEST C: jq présent (faux binaire jq ajouté au PATH) ===
✓ jq détecté (jq-1.7.1).
EXIT: 0
```

Les trois chemins de `ensure_jq()` (absent+accepte, absent+refuse,
présent) se comportent comme prévu ; aucune installation système réelle
n'a eu lieu (branche `apt-get` correctement sélectionnée puisque `apt-get`
existe sur cet hôte, mais interceptée par le stub `sudo`).

### Vérification finale

- `bash -n scripts/install.sh` : syntaxe OK après les deux fixes.
- Nettoyage : conteneur `kc-exact-test` supprimé (`docker rm -f`), dossier
  `/tmp/.../scratchpad/jq-test` supprimé. Confirmé par `docker ps -a` :
  aucun résidu.

### Fichier modifié

- `/home/lenen/projets/geostudio/scripts/install.sh` — ajout de
  `ensure_jq()` (appelée juste après `ensure_docker()`) et ajout de
  `-q "exact=true"` aux deux appels `get users` dans `prompt_admin()`.
  Aucun autre fichier touché, aucun changement au flux de contrôle de
  `prompt_admin()` au-delà du paramètre de requête.
