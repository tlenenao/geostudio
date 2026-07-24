# SP-Deploy-a — Stack prod (dogfood) — Progress Ledger

Plan: docs/superpowers/plans/2026-07-24-sp-deploy-a-stack-prod.md
Workspace: checkout principal, branche `dev` (pas de worktree — convention
établie depuis SP-6a).
Base globale: dev@2d1ed3c (SP-12g clos, non poussé — dev local en avance
sur origin/dev).

Note : ce fichier remplace le ledger SP-12g (clos, plan/tâche différents).
Contenu précédent préservé dans l'historique git de ce fichier.

## Pré-vol

Scan des 6 tâches : pas de contradiction entre tâches ni avec les
contraintes globales. Contexte vérifié contre l'état réel du dépôt et
conforme au plan : spec
`docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md` existe ;
service `worker` (docker-compose.yml:155-172) a bien la commande non
idempotente citée ; `core/scripts/__init__.py` existe déjà (module
importable) ; `core/tests/conftest.py::pg_engine_with_procrastinate_schema`
(ligne 40) documente déjà la garde `has_table` citée par le plan ; seul
appelant de `loadConfig` hors tests = `shell/src/App.tsx:12` (confirmé par
grep) ; `shell/src/config.ts` correspond exactement à la version "avant"
citée par la Task 4. Docker 29.4.3 + Compose v5.1.3 + uv + npm disponibles
dans l'environnement d'exécution.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 2d1ed3c
- Task 1: complete (commit e0e8adf, review clean — ✅ spec + quality, 0
  Critical/Important). `core/scripts/ensure_procrastinate_schema.py` réutilise
  exactement la garde `has_table("procrastinate_jobs")` de
  `conftest.py::pg_engine_with_procrastinate_schema`. `docker-compose.yml`
  worker `command:` remplacé (une seule ligne touchée, aucun `ports:`
  résiduel). 2 tests postgis passed (idempotence : 2e appel de `main()` ne
  lève pas), E2E réel (start/restart worker) confirmé sans boucle. Minors
  (roll-up) : `DATABASE_URL` sans repli `.get()` (cohérence avec
  `app/jobs.py::_conninfo`, non bloquant, invoqué seulement dans le
  conteneur worker où la var est toujours définie) ; `sys.exit(0)`
  redondant ; race check-then-act théorique si le service `worker` était un
  jour scalé à plusieurs réplicas (hors périmètre, pas de `deploy.replicas`
  aujourd'hui).

Base Task 2: e0e8adf
- Task 2: complete (commits bdb24d1 + fix d3a73b5, review clean après 1
  correction — ✅ spec + quality, 0 Critical/Important au round final).
  **Défaut de mécanisme détecté (round 1, plan-mandated) et corrigé** : le
  `ports: []` littéral du plan (et le `volumes:` réécrit de `traefik`) ne
  fonctionne PAS sous Compose v5.1.3 — `ports:`/`volumes:` sont fusionnés
  par concaténation entre fichiers `-f`, pas remplacés ; un `ports: []` dans
  l'override est un no-op de fusion (vérifié empiriquement par le
  contrôleur ET le reviewer en résolvant `docker compose config` : tous les
  ports de base restaient publiés, `traefik` gardait même `./certs:/certs`).
  Fix : tags de contrôle de fusion compose-spec `ports: !reset []` (7
  services) et `volumes: !override` (`traefik`) — vérifiés réellement
  effectifs (ports résolus = None partout, volumes traefik = docker.sock
  seul). `command:` n'était pas affecté (remplacé par défaut par Compose,
  pas fusionné) — laissé tel quel. Ce même correctif (`!reset`/`!override`)
  doit être réutilisé pour tout nouveau `ports: []` introduit par les Tasks
  3/5 (mêmes services étendus, même mécanisme requis).
  Minor (roll-up, non bloquant) : `postgis` n'a pas de ligne `image:` GHCR
  dans `docker-compose.prod.yml` (reste `build: ./deploy/postgis` de la
  base) alors que la prose du plan (Task 2 Interfaces) affirme que
  `GEOSTUDIO_VERSION` pilote "le tag des 3 images" (core/shell/postgis) —
  la Step 2 YAML du plan elle-même n'ajoute pourtant aucune ligne `image:`
  pour `postgis`, donc transcription fidèle du texte du plan ; incohérence
  entre la prose et le YAML du plan, à trancher par la revue finale (ajouter
  `image: ghcr.io/tlenenao/geostudio-postgis:${GEOSTUDIO_VERSION:-latest}` ou
  corriger la prose).

Base Task 3: d3a73b5
- Task 3: complete (commits 868dc66 + fix a6fe9ef, review clean après 1
  correction — ✅ spec + quality, 0 Critical/Important au round final).
  **Deux nouvelles instances du même bug de fusion Compose détectées et
  corrigées** (même famille que Task 2, mécanismes différents) :
  (a) `keycloak.volumes:` fusionnait par concaténation avec le bind-mount
  `:ro` de base (`import/geostudio-realm.json`), collision directe avec
  l'écriture du `sed` d'entrée dans ce même répertoire (`Read-only file
  system` au boot) — corrigé inline par l'implémenteur avec
  `volumes: !override` (même mécanisme que Task 2).
  (b) `core`/`shell` `labels:` fusionnent PAR CLÉ (pas par concaténation,
  contrairement à `ports`/`volumes`) — l'override ne redéfinissait jamais
  `tls.certresolver`, donc le label résiduel de base
  (`tls.certresolver=letsencrypt`, résolveur ACME qui n'existe plus depuis
  Task 2) survivait tel quel dans la config fusionnée réelle (vérifié par
  `docker compose config` résolu, pas seulement la syntaxe YAML) — corrigé
  par un second commit (`labels: !override` sur `core`/`shell` uniquement ;
  `keycloak`/`martin` n'ont pas de `labels:` de base, donc rien à corriger
  là). Les deux corrections vérifiées réellement sur la config fusionnée
  (ports vides, volumes keycloak sans collision, labels sans
  `tls.certresolver` résiduel, 4 URLs interpolées exactement conformes au
  brief, entrypoint/command keycloak bien pris en compte).
  Minor (roll-up, non bloquant) : `sed` du rendu realm Keycloak
  (`docker-compose.prod.yml:52`) interpolerait mal `GEOSTUDIO_PUBLIC_HOST`
  s'il contenait `#`/`&` (théorique, un hostname valide n'en contient
  jamais) ; le motif `labels/ports/volumes: !override` répété par service
  est un piège de maintenance latent si la base `docker-compose.yml` gagne
  un nouveau label/port par défaut un jour (pas actionnable maintenant).

Base Task 4: a6fe9ef
- Task 4: complete (commit 1b3874d + fix bf56c11, review clean après 1
  correction — ✅ spec + quality, 0 Critical/Important au round final).
  `loadConfig(env, runtimeEnv?)` rétrocompatible, seul appelant hors tests
  (`App.tsx`) mis à jour ; template `env-config.template.js` + script
  d'entrée nginx `40-render-runtime-config.sh` (envsubst avec whitelist
  explicite) + `index.html`/`Dockerfile` câblés. Vérifié réellement par
  build+run Docker (rendu `env-config.js` correct avec vraies valeurs).
  **Bug Important corrigé** (round 1) : le garde `mergeRuntimeEnv`
  rejetait `undefined`/`${...}` mais pas la chaîne vide — or `envsubst`
  avec whitelist rend une variable non définie en chaîne vide, PAS en
  placeholder littéral (vérifié empiriquement par le reviewer : build
  Docker réel, var non définie → `""` dans `env-config.js` rendu, pas
  `${VITE_CORE_URL}`) ; sans le fix, une var runtime manquante aurait
  silencieusement écrasé une bonne valeur de build par `""`, faisant
  lever `loadConfig` au boot pour les champs requis — exactement le
  mécanisme anti-rebuild que cette tâche construit, cassé dans le cas
  qu'il est censé couvrir. Corrigé (`value !== "" &&` ajouté au garde,
  commentaire corrigé, 1 nouveau test RED→GREEN prouvé par stash isolé
  de la ligne de garde). 594/594 suite shell + build clean après fix.
  Minor (roll-up, non bloquant) : le rapport original affirmait à tort que
  Vitest/Playwright "ignorent silencieusement" l'échec de `/env-config.js`
  — en réalité `vite preview`/`vite dev` renvoient `index.html` (200,
  text/html) pour ce chemin (fallback SPA), donc le `<script>` lève une
  `SyntaxError` JS avalée (bruit console, pas d'échec réseau silencieux) ;
  comportement final identique (`window.__GEOSTUDIO_ENV__` reste
  `undefined`), aucun test n'assert sur la console, non bloquant — juste
  une explication technique imprécise dans le rapport/plan, pas dans le
  code livré.

Base Task 5: bf56c11
- Task 5: complete (commit 53135d4, review clean au premier passage — ✅
  spec + quality, 0 finding). Purement additif : service `tunnel`
  (`network_mode: service:traefik`, aucun `ports:`/`networks:` propre,
  aucune ligne existante modifiée — donc pas concerné par le bug de fusion
  Compose des Tasks 2/3) + section `volumes:` top-level (fusion par clé
  confirmée avec les 3 volumes nommés de la base : `pg-data`/`minio-data`/
  `keycloak-data` + `tailscale-state`). `TS_AUTHKEY` ajoutée à
  `.env.example`. Activation `tailscale funnel --bg 80` correctement laissée
  en commande manuelle documentée (pas automatisée dans `command:`).

Base Task 6: 53135d4
- Task 6: complete (vérification pure + 1 fix correctif, commit d2d19ae,
  review clean — ✅ spec + quality, 0 Critical/Important). Steps 1/2/3/5
  exécutés réellement (pas seulement lus) contre la stack complète :
  - Step 1 (§7-1, bloqueur 2) : PASS sur le critère central — volume
    `pg-data` vierge, `alembic upgrade head` au boot, `/me` → 401 (pas 500).
  - Step 2 (§7-2, bloqueur 1) : PASS — worker survit à un `restart` complet
    de la stack (condition plus dure qu'isolé, Task 1) ; un épisode LISTEN/
    NOTIFY transitoire (pgbouncer redémarrant en même temps, pas de
    `depends_on` respecté sur un restart global) auto-résolu par
    l'idempotence Task 1, `RestartCount=0`.
  - Step 3 (§7-4) : PASS — bascule de `GEOSTUDIO_PUBLIC_HOST` + `--no-build`
    confirmé (`env-config.js` et `CORE_OIDC_ISSUER` reflètent le nouvel hôte
    sans rebuild), mécanisme Task 4 vérifié bout-en-bout.
  - Step 4 (§7-3, OIDC réel) : non exécuté, aucun compte Tailscale réel
    disponible — anticipé explicitement par le brief lui-même.
  - Step 5 (§7-7) : PASS intégral — core 775 passed/102 skipped +
    lint-imports clean, shell 594 tests + build clean.
  **Défaut réel n°1 trouvé et corrigé** (dans le périmètre Task 3) :
  `keycloak` healthcheck de base sonde `/health/ready` (racine) mais
  `KC_HTTP_RELATIVE_PATH=/auth` (Task 3) déplace tout le service HTTP sous
  `/auth` → 404 → `unhealthy` permanent malgré un Keycloak fonctionnel
  (vérifié manuellement : `/auth/health/ready` → 200 UP). Corrigé
  (commit d2d19ae) : `healthcheck:` surchargé dans l'overlay prod avec le
  bon chemin, mêmes timings que la base. Vérifié réellement : `keycloak`
  atteint `healthy` (~40s), reproduit indépendamment par le reviewer.
  **Défaut réel n°2 trouvé, HORS PÉRIMÈTRE de ce plan** (pré-existant,
  SP-12e, PAS corrigé ici) : `core/Dockerfile` maintient à la main une
  liste `uv pip install` qui a dérivé de `pyproject.toml` — `defusedxml`
  (ajouté par SP-12e pour le parsing XML sûr des connecteurs OGC) manque à
  l'appel, `core` crash-loop (`ModuleNotFoundError`) sur toute image
  reconstruite fraîchement (dev comme prod) depuis SP-12e. Signalé à
  l'utilisateur en fin de session pour une tâche corrective séparée — même
  classe de bug que celle déjà documentée en commentaire dans le
  Dockerfile pour d'autres dépendances dérivées par le passé.
  Artefact d'environnement (pas un défaut) : les images GHCR `latest`
  publiées sont antérieures au HEAD de `dev` (`release.yml` ne se
  déclenche que sur tag `v*.*.*`, aucun tag n'existe) — images reconstruites
  localement pour exécuter la validation, aucun fichier du dépôt modifié
  pour ce contournement.

## Revue finale de branche (opus, 2d1ed3c..d2d19ae) — 1 Important, corrigé
0 Critical. D4 (aucun port publié) et la suppression ACME confirmées
empiriquement sur la config fusionnée réelle (pas seulement lue) —
les 3 correctifs de fusion Compose des tâches précédentes (`!reset`/
`!override` sur ports/volumes/labels) tiennent bien dans l'état final.
Cohérence `/auth` (Keycloak hostname/relative-path/healthcheck/OIDC
issuer/JWKS interne) vérifiée. Mécanisme runtime-config (Task 4)
architecturalement propre, garde chaîne-vide confirmée couvrir le cas réel
`envsubst`. Fix worker (Task 1) réutilise le patron déjà validé.

1 Important : `postgis` n'avait pas de ligne `image:` GHCR dans l'overlay
prod (restait `build: ./deploy/postgis` de la base, non piloté par
`GEOSTUDIO_VERSION`, contrairement à core/shell/worker/cdc-worker) alors
que `release.yml` publie bien `ghcr.io/tlenenao/geostudio-postgis`
(matrice `build-and-push`) — incohérence de texte du plan (Task 2) déjà
signalée en Minor au niveau tâche, élevée à Important par la revue finale
car elle casse la promesse "images GHCR, un seul curseur de version" pour
l'un des 3 images de première partie. **Corrigé** (commit 1967a42) : ligne
`image: ghcr.io/tlenenao/geostudio-postgis:${GEOSTUDIO_VERSION:-latest}`
ajoutée, vérifiée sur la config fusionnée réelle (résout bien au tag testé,
`build:` context toujours présent mais `image:` prend priorité — cohérent
avec core/shell, mêmes limites déjà actées en Task 2).

Minors non bloquants (laissés tels quels, signalés à l'utilisateur en fin
de session, non ré-ouverts) :
- Route Traefik `/tiles` (Martin) sans `rate-limit@docker` (contrairement à
  `/api` et au catch-all shell) — durcissement pas cher, pas fait ici.
- `sed` du rendu realm Keycloak fragile si `GEOSTUDIO_PUBLIC_HOST` contenait
  `#`/`&` (théorique, hostname valide n'en contient jamais).
- Motif `!override`/`!reset` répété par service = piège de maintenance latent
  si la base gagne un nouveau label/port par défaut un jour.
- `env-config.js` sans `Cache-Control: no-store` explicite — un navigateur
  avec cache chaud pourrait servir une config obsolète après bascule d'hôte
  jusqu'à expiration du cache nginx par défaut.
- Rapport Task 4 (déjà noté) : explication imprécise du pourquoi
  `/env-config.js` échoue proprement en dev/Vitest/Playwright (SyntaxError
  avalée, pas échec réseau silencieux) — comportement final inchangé.

**Défaut hors périmètre signalé mais non corrigé (bloquant pour un déploiement
réel, pas pour ce plan)** : `core/Dockerfile` — liste `uv pip install`
maintenue à la main, dérivée de `pyproject.toml` depuis SP-12e
(`defusedxml` manquant) — `core` crash-loop dès le boot
(`app.main → app.harvest.routes → connectors → ows.py`) sur toute image
fraîchement construite (dev comme prod). Confirmé indépendamment par le
reviewer final (trace d'import complète). À traiter en tâche corrective
séparée avant tout déploiement réel de ce sous-plan — la stack prod ne peut
pas démarrer `core` tant que ce n'est pas corrigé, mais c'est un défaut
pré-existant, pas introduit par SP-Deploy-a.

## SP-Deploy-a COMPLET — 6 tâches + 3 fixes de revue de tâche + 1 fix de
## revue finale, tout clean. Ready to merge: YES (revue finale opus).
## HEAD=1967a42. Non poussé — dev local en avance sur origin/dev.

## SP-Deploy-b — en cours (subagent-driven-development)

Task 1 : complete (commits 5ffcd25..9981170, review clean après 1 fix).
Service `backup` (dump Postgres + mirror MinIO + export Keycloak, chiffré
age, rotation 7+4). 3 bugs trouvés en exécutant réellement le code du plan
(pas seulement lu) : retention.py (ligne de retour incorrecte), Dockerfile
(paquet Alpine `mc` = Midnight Commander, pas le client MinIO — remplacé
par le binaire officiel), commande de vérification Step 11 (entrypoint
n'exec pas "$@"). 1 finding Important de revue (plan-mandated) : `backup.sh`
ne nettoyait pas `WORKDIR` en clair sur échec, `entrypoint.sh` retentait
toutes les 60s → fuite répétée de secrets en clair sur toute
mauvaise config persistante (ex. BACKUP_AGE_RECIPIENT vide, défaut de
.env.example). Corrigé (commit 9981170) par un `trap ... EXIT` couvrant
tous les points d'échec (pg_dump/mc mirror/export Keycloak), sans toucher
ARCHIVES_DIR ; vérifié par échec forcé réel (docker diff/cp sur conteneur
arrêté). Revue finale : Approved, 0 Critical/Important/Minor restants.

Task 2 : complete (commits 9981170..0b4733a, review clean après 1 fix).
Runbook `docs/runbooks/2026-07-24-restauration-sauvegardes.md`, cycle
écriture→backup→destruction (`down -v`)→restauration→relecture exécuté
réellement (projet Compose isolé `spdeploytest`, volumes neufs, volume
`geostudio_pg-data` préexistant jamais touché) : item de test survit,
`psql` direct puis `GET /items/<id>` identiques avant/après (même id,
titre, date à la microseconde). 3 bugs trouvés en exécutant le runbook
(pas seulement lu) : boucle `mc mirror` sans garde sur glob vide (échec
réel, pas un no-op silencieux — corrigé), note `pg_restore` incorrecte sur
volume vierge (succès silencieux, pas d'avertissements — corrigée), motif
`--entrypoint` appliqué partout. 2 findings Important de revue
(plan-mandated) : documentation incomplète de l'interdiction dépôt/
image/volume pour la clé privée age (contrainte du plan), et clôture du
runbook surclamant la couverture du critère §7-5 (reconnexion utilisateur
réelle non testée — CORE_AUTH_MODE=mock substitué pour isoler le test de
données). Corrigés (commit 0b4733a). Revue finale : Approved, 0 Critical/
Important restants.

## SP-Deploy-b COMPLET — 2 tâches, 2 fixes de revue de tâche, tout clean.
## HEAD=0b4733a. Reste : revue finale de branche.

## Revue finale de branche (opus, 5ffcd25..0b4733a) — 0 Critical, 0 Important
0 Critical, 0 Important. Architecture confirmée saine (service compose
dédié, aucun couplage core/, chiffrement-avant-persistance réellement
respecté pas seulement affirmé). Les 3 bugs auto-trouvés (Task 1) et les 3
bugs auto-trouvés (Task 2) re-vérifiés indépendamment par le reviewer final
(retention.py rejoué avec les tests réels, cohérence layout d'archive
backup↔restore confirmée bout en bout, trap EXIT confirmé sans race avec
ARCHIVES_DIR, préfixe /auth Keycloak confirmé correct car le service
backup n'existe que dans l'overlay prod). Seul finding : clé privée age de
test committée en clair dans le rapport de tâche (Minor/courtoisie) —
corrigée (commit fac2606). Ready to merge: YES (revue finale opus).

## SP-Deploy-b COMPLET — 2 tâches, 2 fixes de revue de tâche, 1 fix de
## revue finale (redaction), tout clean. Ready to merge: YES.
## HEAD=fac2606. Non poussé — dev local en avance sur origin/dev.

## SP-Deploy-c — en cours (subagent-driven-development)

Base Task 1: 19e3443
Task 1: complete (commits 42f8900..2d18792, review clean après 1 fix). Squelette
`scripts/install.sh` (`confirm()`/`ensure_docker()`), vérifié réellement en clone
jetable (Docker déjà présent → chemin nominal). 2 findings Important de revue :
bit exécutable manquant (100644 au lieu de 100755, contrairement aux scripts
frères) et message de confirmation ne mentionnant pas explicitement `usermod -aG
docker` (une seule confirmation couvrant install + modification de groupe système,
texte ne divulguant que l'install). Corrigés (commit 2d18792) : bit +x restauré,
message étendu pour divulguer les deux actions. Non-issue écarté sans fix : SPDX
en ligne 2 (après le shebang, physiquement obligatoire en ligne 1) — pas un
défaut, juste une lecture littérale trop stricte de la contrainte. Revue finale
de tâche : Approved, 0 Critical/Important restants.

Base Task 2: 2d18792
Task 2: complete (commits 9d64a96..357e6bd, review clean après 1 fix). Menu de
profils découvert via `docker compose config --profiles` (jamais codé en dur),
`etl` affiché « à venir » tant qu'absent du dépôt (ne ment pas à l'utilisateur),
`SEED_DEMO` produit pour la Task 4. 1 finding Important plan-mandated : `declare -A`
(tableau associatif, bash ≥4) casse macOS (bash 3.2 par défaut sur `/usr/bin/bash`)
alors que le spec §5.1 promet explicitement le support macOS (« détecte et guide,
puis reprend une fois installé »). Utilisateur consulté : a choisi de corriger
maintenant. Corrigé (commit 357e6bd) : lookup portable via fonction `profile_label()`
(case bash 3.2-safe), comportement (labels + repli sur le nom brut) préservé à
l'identique, revérifié en clone jetable. Revue finale de tâche : Approved, 0
Critical/Important restants.

Base Task 3: 357e6bd
Task 3: complete (commits 04cab99..df7ad40, review clean après 1 fix — tâche la
plus complexe des 4, 176k+70k tokens subagent). `ensure_env_file`/`set_env_var`,
`prompt_public_host` (manuel ou découverte Tailscale), `activate_funnel`,
`prompt_backup_target`, `prompt_admin` (API Admin Keycloak, idempotent). 1 bug
pré-identifié par le contrôleur avant dispatch (démarrage du tunnel sauté sur la
branche hôte manuel alors que `activate_funnel` en a besoin dans tous les cas —
corrigé : `up -d traefik tunnel` sorti de la branche conditionnelle). 3 bugs
auto-trouvés en exécutant réellement (pas seulement lus) : `quay.io/keycloak/
keycloak` n'a ni `curl` ni `wget` (remplacé par `kcadm.sh`, l'outil d'admin
fourni par l'image elle-même — `ports: !reset []` sur `keycloak` en overlay prod
confirme qu'exec-dans-le-conteneur est la seule voie viable, host curl
inatteignable) ; `$KC_PASSWORD` non lié sous `set -u` (le script ne `source`
jamais `.env`, lu via `grep`/`cut` à la place) ; `CORE_ADMIN_SUBS` absent de
`.env.example` ET du bloc `environment:` de `docker-compose.yml` (service
`core`) — sans ces deux ajouts, tout le Step 4 aurait été un théâtre silencieux
(aucun admin réellement promu). Dépassement du périmètre fichier déclaré du
brief (« Modify: scripts/install.sh » seul) pour ces 2 fichiers partagés — jugé
nécessaire et confirmé par le contrôleur après vérification indépendante
(`CORE_ANALYST_SUBS`, variable sœur, a le même trou mais laissé tel quel, hors
périmètre — aucune tâche de ce plan ne promeut d'analyste). 1 finding Critical
de revue : `kcadm.sh get users -q email=X` sans `-q exact=true` fait une
correspondance par sous-chaîne, pas exacte — avec des emails qui se chevauchent
(`admin@example.com`/`aaaadmin@example.com`), `.[0].id` pouvait résoudre vers le
mauvais compte, écrivant un UUID Keycloak erroné dans `CORE_ADMIN_SUBS` (promotion
admin silencieusement incorrecte). Corrigé (commit df7ad40) : `-q "exact=true"`
ajouté aux deux appels `get users`. 1 finding Important : `jq` est une dépendance
hôte réelle jamais détectée nulle part dans le plan (Task 1 ne vérifie que
Docker) — `set -euo pipefail` + `jq` absent fait planter le script sans message
utile. Corrigé (même commit) : `ensure_jq()` ajoutée, même patron de consentement
que `ensure_docker()` (apt/dnf/pacman sur Linux, guide manuel sur macOS, jamais
silencieux). `prompt_admin` revérifié end-to-end (vrai Keycloak Docker, deux
passages, idempotence confirmée) après chaque fix. Revue finale de tâche :
Approved, 0 Critical/Important restants.

Base Task 4: df7ad40
Task 4: complete (commit 1b3d7b2 + fix afce89e, review clean au premier passage
— ✅ spec + quality, 0 finding). `launch_stack()` (lancement complet avec
profils sélectionnés, attente `/me` → 401, seed démo optionnel) + `print_summary()`
(dernière tâche du plan, rien au-delà). 1 bug auto-trouvé en vérifiant réellement :
l'image `core` (`python:3.12-slim`) n'a ni `curl` ni `wget` — la sonde de santé du
brief aurait toujours échoué. Remplacée par une sonde `python3`/`urllib.request`
(même écueil que `kcadm.sh`/Keycloak en Task 3), vérifiée par le reviewer :
distingue correctement 401 (succès, via `HTTPError.code`) de connexion refusée
(`000`, via l'except générique), ordre des clauses `except` confirmé correct.
Idempotence (critère §7-6) vérifiée via harnais de fonctions extraites (même
classe de contournement que Task 3 pour l'absence de compte Tailscale réel dans
cet environnement) : 2 passages, `docker compose ps` inchangé, seed démo rejoué
sans erreur ("aucune (déjà en place)"). Suite de non-régression globale : core
775 passed/102 skipped + lint-imports clean, shell 594/594 + build clean.
1 incident de session corrigé par le contrôleur (commit afce89e, hors périmètre
tâche) : un `git add` trop large dans le commit 1b3d7b2 avait accidentellement
écrasé `.superpowers/sdd/task-2-report.md` (fichier scratch réutilisé par
chaque sous-plan, contenu légitime de SP-Deploy-b committé en fac2606) avec le
rapport Task 2 de SP-Deploy-c — restauré au contenu exact de fac2606 (le
rapport SP-Deploy-c ira dans le commit de ledger final, comme pour SP-Deploy-a/b).

## SP-Deploy-c COMPLET — 4 tâches, 3 fixes de revue de tâche, 1 fix de
## contrôleur (incident scratch-file), tout clean. HEAD=afce89e.
## Reste : revue finale de branche.

## Revue finale de branche (opus, 19e3443..afce89e)

0 Critical/Important non traité. Cohérence bout-en-bout confirmée : flux de
contrôle complet tracé (ensure_docker → ensure_jq → prompt_profiles →
ensure_env_file → prompt_public_host → activate_funnel → prompt_backup_target
→ prompt_admin → launch_stack → print_summary), aucune variable inter-tâches
lue avant d'être écrite, idempotence tenue de bout en bout. 1 finding Critical
propre à la revue finale (invisible aux 4 revues de tâche prises séparément,
toutes exécutées sous bash 5.x) : `launch_stack` fait `"${SELECTED_PROFILES[@]}"`
sous `set -u` — bash < 4.4 (macOS stock, bash 3.2.57) lève « unbound variable »
sur un tableau vide, cas courant (aucun profil optionnel choisi), après que
Docker/`.env`/tunnel/admin Keycloak aient déjà tourné. Réintroduisait exactement
la classe de bug corrigée en Task 2 (`declare -A`). 1 finding Important : erreur
`docker compose config --profiles` avalée silencieusement (menu vide sans
avertissement). 1 Minor traité avec : clé secrète S3 échoée en clair au terminal
(contrairement au mot de passe admin, affiché une seule fois par design).
Corrigés (commit 85b107f) : garde `${arr[@]+"${arr[@]}"}` sur les deux
expansions de tableau (vérifié sous `set -u`, vide et 1 élément) ; stderr de
`docker compose config` capturé séparément (pas `2>&1` — les avertissements
`.env` non défini de ce dépôt auraient corrompu la liste de profils, déviation
délibérée et documentée du fix suggéré) et affiché en cas d'échec réel,
succès revérifié inchangé ; `read -r -s` + `echo` pour la clé secrète S3.
3 Minors laissés tels quels (non bloquants, documentés) : fragilité sed
`set_env_var` sur `|`/`&` (idiome partagé pré-existant de `bootstrap-env.sh`,
pas nouveau) ; `ADMIN_SUB` sans `// empty` après `create users` (risque faible,
vérifié en conditions réelles) ; incohérence cosmétique `python3` vs `python`.

## SP-Deploy-c COMPLET — 4 tâches, 4 fixes de revue de tâche, 1 fix de
## contrôleur (incident scratch-file), 1 fix de revue finale, tout clean.
## HEAD=85b107f. Ready to merge: YES (revue finale opus). Non poussé.

## SP-Deploy-e — en cours (subagent-driven-development)

Plan: docs/superpowers/plans/2026-07-25-sp-deploy-e-provisioning-proxmox.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@4e3cc8a (spec SP-Deploy-e committée ; fichier de plan lui-même encore non tracké à ce stade, comme pour SP-Deploy-c).

## Pré-vol

Scan des 5 tâches : pas de contradiction entre tâches ni avec les contraintes
globales. Contexte vérifié contre l'état réel du dépôt : `scripts/install.sh`
(360 lignes) contient bien les 4 fonctions ciblées avec un contenu "avant"
correspondant au texte du plan (`prompt_profiles` ligne 113, `prompt_public_host`
ligne 168, `prompt_backup_target` ligne 218, `prompt_admin` ligne 240) — léger
décalage de quelques lignes vs les numéros exacts du plan mais contenu
identique. Poursuite sans confirmation utilisateur (scan de contradictions clean).

Base Task 1: 4e3cc8a
Task 1: complete (commit 1e552bb, review clean au premier passage — ✅
spec + quality, 0 Critical/Important). Transcription exacte des 4 blocs
de code du brief (prompt_profiles/prompt_public_host/prompt_backup_target/
prompt_admin), branches else non-régressives confirmées identiques
(reviewer a re-exécuté shellcheck indépendamment, 0 warning). Distinction
+x (3 fonctions) vs -n (prompt_admin, seul champ obligatoire) correcte.
Minors (roll-up, hérités du brief tel quel, pas des déviations de
l'implémenteur) : INSTALL_SEED_DEMO n'accepte que la valeur littérale "1" ;
INSTALL_PROFILES sans trim des espaces autour des virgules — à garder en
tête pour la Task 3 (consommateur du contrat).

Base Task 2: 1e552bb
Task 2: complete (commit ee5a7ea, review clean au premier passage — ✅
spec + quality, 0 Critical/Important). Module OpenTofu (6 fichiers)
transcription exacte vérifiée ligne à ligne par le reviewer, validé
réellement via conteneur OpenTofu officiel (`bpg/proxmox` v0.111.1 résolu,
`validate` succès, `fmt -check` propre), artefacts locaux nettoyés avant
commit (aucun `.terraform/`/lock file committé). `ssh_username` défaut
`geostudio` cohérent avec `ansible_user` attendu en Task 3. Minors
(roll-up, hérités du brief tel quel) : contrainte `~> 0.66` autorise en
réalité tout 0.x jusqu'à 1.0.0 (large) ; `.terraform.lock.hcl` non listé
dans le `.gitignore` du module (absence volontaire documentée par le
plan).

Base Task 3: ee5a7ea
Task 3: complete (commit 41e501f, review clean au premier passage — ✅
spec + quality, 0 finding). Playbook Ansible (4 fichiers) transcription
exacte vérifiée, 10 variables d'environnement du contrat comptées
programmatiquement et croisées avec scripts/install.sh (Task 1) — aucun
typo/omission/ajout. Ancre YAML `&geostudio_install_env`/alias
`*geostudio_install_env` évite bien la duplication du bloc environment
entre les 2 passes. `meta: reset_connection` correctement placé entre les
2 tâches `command:`. `inventory.ini`/`vault.yml` matérialisés pour la
validation confirmés absents du commit (`git ls-files` vérifié par le
reviewer). Validé réellement via conteneur ansible-dev-tools officiel
(syntax-check + lint, 0 warning).

Base Task 4: 41e501f
Task 4: complete (commit 13a6ba8, review clean au premier passage — ✅
spec + quality, 0 finding). README.md (110 lignes) transcription exacte
vérifiée, les 5 fichiers référencés (Tasks 2/3) confirmés existants sur
disque par le reviewer.

Base Task 5: 13a6ba8
Task 5: complete (commit 3e07288, review clean au premier passage — ✅
spec + quality, 0 finding). `.gitignore` racine étendu (2 lignes exactes,
aucun doublon), `git status --short deploy/proxmox/` vide (re-vérifié
indépendamment par le reviewer). Cross-check des 3 points de cohérence
inter-tâches spot-checké indépendamment par le reviewer (ssh_username↔
ansible_user, repo_dest↔home dir sans become, 10 env vars↔contrat Task 1
— confirmé via grep sur scripts/install.sh que les 10 vars sont bien
consommées, pas seulement nommées). Suite de non-régression réelle : shell
build vert, core 775 passed/102 skipped + lint-imports contract kept.

## SP-Deploy-e COMPLET — 5 tâches, 0 fix de revue de tâche (les 5 clean
## au premier passage), tout clean. HEAD=3e07288. Reste : revue finale de
## branche.

## Revue finale de branche (opus, 4e3cc8a..3e07288) — 0 Critical, 0 Important
Chaîne des 3 couches vérifiée cohérente de bout en bout par le reviewer :
outputs Terraform (vm_ip/vm_ssh_username) → inventory.ini.example
(ansible_host/ansible_user) → contrat d'env-vars Task 1 consommé par
playbook.yml, sans dérive (10 noms, aucun 11e introduit, tous réellement
consommés dans scripts/install.sh — grep vérifié ligne par ligne).
Mécanisme deux-passes/reset_connection confirmé sain quand les deux
fichiers sont lus ensemble (ensure_docker exit 0 après install Docker,
reset_connection ouvre une session SSH neuve, 2e passe trouve Docker
présent et termine le déploiement). Discipline secrets confirmée sur tout
le diff (aucun secret/IP/hostname réel, seuls des placeholders). Séparation
group_vars/all.yml + vault.yml confirmée nécessaire (vault.yml ne charge
pas automatiquement, groupe "vault" inexistant — vars_files explicite
indispensable). CLAUDE.md et feuille de route confirmés absents du diff
(propriété de SP-Deploy-d, non dupliqués ici).

3 Minors laissés tels quels (non bloquants, cosmétiques) : README ne
documente pas l'absence de trim d'espaces dans INSTALL_PROFILES (risque
faible, un seul profil illustré en exemple) ; minor Task 1 INSTALL_SEED_DEMO
"1" strict confirmé moot au niveau intégration (seul producteur, le
playbook, émet toujours "1"/"0" canonique) ; clone HTTPS anonyme suppose
le dépôt public au moment du déploiement (intentionnel, Apache-2.0).

## SP-Deploy-e COMPLET — 5 tâches, 0 fix de revue de tâche, 0 fix de
## revue finale, tout clean. Ready to merge: YES (revue finale opus).
## HEAD=3e07288. Non poussé — dev local en avance sur origin/dev.
