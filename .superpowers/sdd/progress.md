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
