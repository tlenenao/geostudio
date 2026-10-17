# Parcours persona : Administrateur système (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Scénario : installation depuis le README, Keycloak, sauvegarde/restauration, montée de version, quotas, rotation de secrets.
Captures : `docs/revue/audit-2026-10-16/parcours/admin-systeme/*.png`. Aucun fichier source édité, rien commité, ni `postgis-test` ni suite de tests.

## 0. Conditions de test et limites

- Stack locale déjà en marche (14 services `healthy`), `CORE_AUTH_MODE=oidc`, compte `audit-admin` (rôle Administrateur, `scripts/audit/seed-personas.sh:67` mot de passe `Demo1234!`). Chromium headless Playwright (scripts hors dépôt), `env-config.js` réécrit côté navigateur en `VITE_AUTH_MODE=oidc` (le conteneur shell sert `mock`).
- **Installation « propre » non rejouée telle quelle** : une seconde stack complète (12 services) collisionnerait sur les ports et la RAM WSL2 (~12 Go). Substitut : `bootstrap-env.sh` exécuté dans un répertoire jetable + `docker compose --env-file … config -q`, relecture du code d'`install.sh`. Les constats d'installation sont donc partiels (§2, étape 1).
- **Aucune opération sur les données de la stack vivante.** Sauvegarde, restauration et montée de version ont été jouées sur des copies : `pg_dump` de la base `gis` vers deux bases jetables (`audit_restore`, `audit_restore2`, supprimées en fin de test), un conteneur `core` jetable sur `audit_restore2` (supprimé), une archive de sauvegarde chiffrée avec une clé `age` jetable (supprimée). `restore.sh` n'a **pas** été exécuté : il vise en dur `-h postgis -d gis` avec `--clean` (`deploy/backup/restore.sh:39-40`), donc la base vivante.
- Image `geostudio-core:latest` vieille de 5 jours : sa tête Alembic est `0051` alors que le dépôt va jusqu'à `0081` (`ls core/alembic/versions` = 74 fichiers ; `alembic current` dans le conteneur = `0051 (head)`). Le code HEAD ne démarre pas non plus sur cette image (`ModuleNotFoundError: PIL` depuis `app/ows/render.py:11`), ce qui est cohérent avec une image antérieure au HEAD, pas un défaut de code.

## 1. Chronologie et notes

| Étape | Durée mesurée | Note /10 | Résumé |
|---|---|---|---|
| 1. Installation depuis le README | `bootstrap-env.sh` 0,09 s ; `compose config -q` OK | 3 | Secrets bien générés, mais le chemin README livre un navigateur qui ne peut pas parler au cœur (F1). Pas de démarrage à froid rejoué. |
| 1b. Installeur guidé `install.sh` (lecture) | non rejoué | 5 | Idempotent côté redirectUris, mais importe le realm de démo avec comptes connus (F2). |
| 2. Keycloak : accès, realm, console | token admin 0,32 s ; page login 0,30 s ; connexion console 1,26 s | 6 | Rapide. Realm vivant sans brute-force ni événements (F3), flux mot de passe actif sur un client public (F2). |
| 3. Connexion OIDC au shell, pages admin | login 2,1 s (LCP 1,0 s) ; 10 pages admin 1,6 à 2,1 s, LCP 0,71 à 0,96 s | 8 | Axe wcag2a/aa/21aa : 0 violation sur les 11 écrans. Console et réseau propres (hors F1). `<h1>` présent partout (§3, F10). |
| 4. État de l'instance, utilisation, outils admin | `/v1/instance/status` 36 ms ; `/v1/admin/usage` 389 ms | 8 | Page « Outils d'infrastructure » claire : état PG/S3/CDC/jobs, jauges d'utilisation. Le pied de page affiche `v0.1.0` (F7). |
| 5. Sauvegarde | `backup.sh` 24,5 s, archive 306 Mo chiffrée `age` ; déchiffrement + liste 5,1 s | 7 | Fonctionne, archive complète (postgres.dump, 4 buckets non vides, realm Keycloak). Journal très bavard, clé `age` requise sinon refus (F9). |
| 6. Restauration (sur copie) | `pg_dump` 4,4 s ; `pg_restore` 14,0 s, 0 erreur, 503 items | 7 | La restauration Postgres est saine. `restore.sh` non joué (vivant). Runbook : liste de buckets du « repli » périmée (F8). |
| 7. Montée de version | `alembic upgrade 0051 → 0081` 3,0 s sur 503 items | 4 | Techniquement indolore, mais aucune procédure documentée, version affichée figée, realm Keycloak non resynchronisé (F5, F7, F3). |
| 8. Quotas | 409 RFC 7807 lisible | 5 | Le plafond de collections s'applique proprement ; mais une valeur invalide donne un 500 (F4) et rien n'est réglable sans redémarrage. |
| 9. Rotation de la clé maître des secrets | dry-run 3,0 s ; réelle 3,0 s (13 secrets) | 4 | Script correct et atomique ; runbook faux sur le redémarrage du `worker` (F6). |

Note globale du parcours : **5,8 / 10**.

## 2. Blocages (classés)

1. **F1** : le README prescrit shell `:8300` + cœur `:8200` ; en navigateur réel, toutes les requêtes cœur sont bloquées par CORS (aucun middleware CORS global). L'installation de démarrage rapide ne produit pas une UI utilisable.
2. **F6** : suivre le runbook de rotation de clé laisse le `worker` sur l'ancienne clé ; tout run de pipeline utilisant un secret échoue jusqu'à son redémarrage.
3. **F2** : l'import du realm en production crée `alice`/`bob` avec `Demo1234!` activés, jamais supprimés par l'installeur.
4. **F5** : aucune procédure de montée de version (sauvegarde préalable, bump de tag, vérification, retour arrière) dans `docs/runbooks/` ni le README.
5. **F4** : une valeur de quota non numérique casse la page d'utilisation (500) sans validation au démarrage.

## 3. Constats détaillés

### F1. Le démarrage rapide du README est inutilisable depuis un vrai navigateur (CORS)

- README `:84-85` (tableau des services) : shell `http://localhost:8300`, cœur `http://localhost:8200` ; `docker-compose.yml:986` `VITE_CORE_URL: ${VITE_CORE_URL:-http://localhost:8200}` : le shell appelle donc le cœur en cross-origin.
- `grep -rn CORSMiddleware core/app` : seul le mini-serveur du sidecar (`core/app/pipelines/sidecar/app.py:16,104`) en a un ; l'API générale n'a que des règles étroites d'export d'app (`core/app/main.py:107-138,382-401`).
- Preuve : `curl -i -X OPTIONS -H "Origin: http://localhost:8300" -H "Access-Control-Request-Method: GET" localhost:8200/v1/me` renvoie `404` sans `Access-Control-Allow-Origin`. Dans Chromium sans `--disable-web-security` : `Access to fetch at 'http://localhost:8200/v1/me' from origin 'http://localhost:8300' has been blocked by CORS policy` sur `/v1/me`, `/v1/items`, `/v1/notifications`, `/v1/instance` (toutes). Captures : `00a-readme-cors-catalogue.png`, `00b-readme-cors-utilisateurs.png`.
- Le dépôt le sait : `shell/playwright.journeys.config.ts:15-19` écrit « le déploiement réel passe par Traefik en same-origin sous /api, indisponible sur localhost » et contourne par `--disable-web-security`. Les suites e2e-oidc (`shell/e2e-oidc`) n'y échappent que parce que Playwright n'exerce pas ce chemin avec des appels cœur.
- Piège n°2 (« testé ≠ câblé ») : le README promet un « Essayer en cinq minutes » que seul un navigateur sans sécurité web fait fonctionner. Traefik (`:80`) répond `404` sur `/` en dev (`curl localhost:80/` = 404) et `docker-compose.yml:469` route le cœur sur `Host(${DOMAIN}) && PathPrefix(/api)` en `websecure` avec ACME, donc pas de chemin same-origin sur localhost non plus.
- Gravité : bloquant pour l'étape « installation propre ».

### F2. Realm livré : comptes de démo actifs en production, flux mot de passe sur client public

- `deploy/keycloak/geostudio-realm.json:2290-2299` : utilisateur `alice` avec mot de passe `Demo1234!` non temporaire (idem `bob`) ; `:29` `"sslRequired": "none"` ; `:713` client public `geostudio-shell` avec `directAccessGrantsEnabled: true`.
- Le overlay de production importe ce même fichier (`docker-compose.prod.yml:115-123`, `sed` sur l'hôte seulement). `scripts/install.sh` crée le compte administrateur (`create users`, vers `:466-470`) mais ne supprime ni ne désactive `alice`/`bob` (`grep -in "alice\|bob\|Demo1234" scripts/install.sh` : aucun résultat).
- Preuve vivante : `POST /realms/geostudio/protocol/openid-connect/token` avec `client_id=geostudio-shell&grant_type=password&username=alice&password=Demo1234!` renvoie un `access_token` en 0,25 s ; idem `bob`.
- Impact : sur une instance installée par `install.sh`, quiconque connaît le dépôt public obtient deux comptes Créateur. Atténuation partielle : le rôle par défaut n'est pas Administrateur (`/v1/me` d'alice : rôle `creator`).

### F3. Realm vivant : protections non appliquées et non détectées

- Live (API admin Keycloak) : `bruteForceProtected=False`, `eventsEnabled=False`, `adminEventsEnabled=False`, `passwordPolicy=None`, `smtpServer={}`, `sslRequired=none` alors que `deploy/keycloak/geostudio-realm.json:38` demande `bruteForceProtected: true`. Capture : `13-keycloak-realm-security.png`.
- C'est documenté (`deploy/keycloak/README.md:7`, runbook `2026-09-05-activer-brute-force-protection-keycloak-existant.md`) mais rien dans le produit ne le détecte : `GET /v1/instance/status` ne renvoie que postgres/s3/cdc/jobs (réponse relevée ci-dessus), et `install.sh` ne resynchronise que les redirectUris (`:461-490`).
- Journal de connexion Keycloak désactivé : pas de trace des échecs de connexion côté IdP pour un administrateur (l'`audit_log` du cœur ne couvre pas Keycloak).

### F4. Quotas : valeur invalide = 500, aucune validation

- `core/app/quotas/service.py:174-189` : `int(raw) if raw else None` sans garde. Reproduction sur conteneur `core` jetable (`CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT=10GB`) : `GET /v1/admin/usage` → `500 internal server error`, journal `ValueError: invalid literal for int() with base 10: '10GB'`. L'exemple naturel d'un administrateur (« 10GB », « 10Go ») est précisément le cas qui casse ; `.env.example:331` donne un entier en octets (`10737418240`), sans le dire.
- Aucune validation au démarrage (le cœur démarre, `/v1/me` répond 200 avec `quotasEnabled: true`), l'erreur n'apparaît qu'à l'usage.
- Positif : avec `CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT=188` et 188 collections, `POST /v1/collections/empty` → `409 {"type":"quota-exceeded","detail":"quota de collections du tenant dépassé : 188/188","quota":"collections","current":188,"limit":188}` (`service.py:192-198`). La page `/admin/infrastructure` affiche « Éléments : 503 / 100000 », « Collections : 188 / 10000 », « Stockage : 899,9 Mo (pas de limite configurée) » (`05-infrastructure.png`).
- Limite de conception : plafond unique instance-wide, pas par tenant (`service.py:174-178`), modifiable seulement par variable d'environnement et redémarrage ; aucune alerte à l'approche du seuil.

### F5. Montée de version : aucune procédure

- `ls docs/runbooks` : aucun runbook de mise à jour ; `README.md` n'en parle pas (`grep -in "mise à jour\|upgrade" README.md` : seulement la ligne de présentation). `.env.example:527` fixe `GEOSTUDIO_VERSION=v0.1.0` et `scripts/install.sh:218-220` avertit seulement si la variable est vide.
- Ce qui existe est bon : `docker-compose.yml:237` `alembic upgrade head && uvicorn …` au démarrage du cœur ; mon rejeu `0051 → 0081` sur copie de 503 items prend 3,0 s sans erreur (`0081` atteint). Mais l'administrateur n'est jamais invité à sauvegarder avant, ni à surveiller `alembic` (les journaux de migration impriment la docstring entière de chaque révision, sortie bruyante), ni à valider ensuite. Les migrations lourdes en HA sont traitées ailleurs (`2026-10-14-haute-disponibilite-reelle.md:34`).
- Retour arrière : aucun runbook ; des `downgrade()` existent (`core/alembic/versions/0081_geocode_jobs.py:38`) mais rien ne dit quand les utiliser.
- Les paramètres Keycloak d'une instance existante ne suivent pas la montée (F3).

### F6. Rotation de clé maître : le runbook oublie le `worker`

- `docs/runbooks/2026-09-06-rotation-cle-secrets.md:82-85` : « Redémarrer `core` : `docker compose up -d core` ». Or `docker-compose.yml:360` (service `core`) **et** `:590` (service `worker`) reçoivent `CORE_SECRETS_MASTER_KEY`. Le `worker` consomme la file `etl` (`docker-compose.yml:545`) et déchiffre les secrets des pipelines (`core/app/pipelines/connector_runtime.py:131` `get_secret_payload`). Le mot `worker` n'apparaît pas une seule fois dans le runbook (`grep -ni worker` : aucun résultat).
- Conséquence : après la procédure telle qu'écrite, `core` redémarre sur la nouvelle clé mais le `worker` garde l'ancienne ; tout run de pipeline avec secret échoue en déchiffrement jusqu'à un `docker compose up -d worker`. La « fenêtre de risque » du §7 est donc sous-estimée (elle ne se ferme pas au redémarrage de `core`).
- Le script lui-même est bon : sur la copie, `--dry-run` 3,0 s (« 13 secret(s) déchiffré(s) avec succès … Aucune écriture »), exécution réelle 3,0 s, 13 secrets, un seul tenant.
- Défauts secondaires : (a) rejouer le script avec l'ancienne clé après une rotation réussie affiche une trace brute `cryptography.exceptions.InvalidTag` (`core/app/secrets/crypto.py:52`) sans message du type « clé actuelle incorrecte ou rotation déjà faite » ; (b) l'exemple du runbook `:49` utilise `postgresql+psycopg://gis:gis@localhost:5432/gis`, inutilisable ici (PostGIS n'expose aucun port hôte, mot de passe généré) ; (c) seule la clé maître est couverte : aucun runbook pour `PG_PASSWORD`, `KC_PASSWORD`, `MINIO_PASSWORD` ni les trois secrets HMAC générés par `bootstrap-env.sh:20-21`.

### F7. Version affichée figée à `0.1.0`

- `core/app/main.py:184` `FastAPI(… version="0.1.0")` et `core/pyproject.toml:3` ; `core/app/auth/routes.py:105` la renvoie dans `/v1/me`. Le pied de page du shell affiche `v0.1.0 · default` (`05-infrastructure.png`) alors que les images en marche sont postérieures et que le dépôt parle de v0.1.1/v0.2.0 (`docs/runbooks/2026-10-10-release-v0.1.1-et-protection-main.md`, `CHANGELOG.md` section `[Unreleased]`). Après une montée de version, l'administrateur ne peut pas voir ce qui tourne (le tag réel n'est que dans `.env` : `GEOSTUDIO_VERSION`).
- `README.md:145` dit encore « Version publiée : `v0.1.0` — huit images » alors que le dépôt a depuis publié d'autres versions (runbook v0.1.1) ; à vérifier, non recompté ici.

### F8. Sauvegarde et restauration : dérives de documentation

- `deploy/backup/backup.sh:51` « les cinq buckets » alors que la boucle `:67-74` en sauvegarde huit ; `docs/runbooks/2026-07-24-restauration-sauvegardes.md:61` « sept buckets » et la commande de repli `:169` crée sept buckets sans `S3_RASTER_BUCKET`, absent de la liste manuelle alors que `restore.sh:49-56` en crée huit. Un administrateur suivant le repli à la main perd silencieusement les rasters.
- `retention.py:62` émet un `DeprecationWarning` (`datetime.utcnow()`) à chaque sauvegarde (sortie vue pendant le test).
- `mc mirror --quiet` (`backup.sh:76`) imprime pourtant une ligne par objet (plus de 2 500 pour les pièces jointes) : le journal du conteneur est inexploitable pour repérer un avertissement.
- Positif : `restore.sh` fait une garde base ↔ buckets (`:69-107`, REV-268), recrée les rôles `gis_rls`/`gis_rls_masked` (`:35-38`) ; ma restauration sur copie passe sans aucune erreur `GRANT`. Le realm Keycloak exporté (`partial-export`, `backup.sh:97`) est un secours de lecture ; les utilisateurs vivent dans le dump Postgres.

### F9. Sauvegarde : prérequis et signal

- `backup.sh:108-113` refuse de produire une archive sans `BACKUP_AGE_RECIPIENT` ; or `.env.example` / `bootstrap-env.sh` le laissent vide (`.env` courant : `BACKUP_AGE_RECIPIENT=` vide). Le refus est explicite et correct, mais l'installation ne génère pas la clé : l'administrateur n'apprend la contrainte qu'à la première nuit (03:00 UTC, `entrypoint.sh:4`) ou via la dernière ligne de `print_summary` (`install.sh:571-573`). Sans cible hors-site, avertissement clair (`backup.sh:139-143`) : bon.
- Sonde de fraîcheur `.last_success` (`backup.sh:145`) : bon design ; non vérifiable sur la stack de dev (service `backup` seulement dans l'overlay prod).

### F10. Interface d'administration (points mineurs)

- 11 écrans parcourus : LCP 0,71 à 0,96 s, chargement complet 1,6 à 2,1 s, axe-core 0 violation, `<main>` unique, `<h1>` présent partout, titres de route corrects (`document.title`), 0 erreur console, 0 requête en échec (avec sécurité web coupée pour contourner F1).
- La page « Outils d'infrastructure » liste le lien MinIO avec la mention « non protégé par ce garde-fou » (`05-infrastructure.png`) : honnête, mais c'est un lien mort en production (aucun port hôte).
- « Tâches du tenant » (`10-taches-usage.png`) est un journal d'audit horodaté à la microseconde, pas un état de jobs (le panneau droit le dit) : un administrateur cherchant « quel job est bloqué » doit aller sur `/v1/instance/status` (file de jobs affichée avec « 0 bloqué ») ; pas de lien d'une page à l'autre.
- Jetons de lancement des outils admin dans l'URL (`POST /v1/admin-tools/launch/martin` renvoie `?_at=<jeton HMAC>` ; 60 s, usage unique par conception) : acceptable, à garder à l'esprit pour les journaux d'accès du proxy.

## 4. Recommandations (sans édition faite ici)

1. Same-origin ou CORS : documenter/servir shell et cœur sous une même origine en local (Traefik HTTP sur `localhost`), ou ajouter un middleware CORS borné activable en dev ; corriger le README (F1).
2. Retirer `users` du realm livré en production (ou les désactiver dans `install.sh`), couper `directAccessGrantsEnabled` sur le client public et ajouter `bruteForceProtected`/événements à `/v1/instance/status` (F2, F3).
3. Valider les trois variables de quota au démarrage et rejeter `10GB` avec un message ; mentionner l'unité (F4).
4. Écrire `docs/runbooks/…-montee-de-version.md` (sauvegarde, `GEOSTUDIO_VERSION`, `pull`, `up -d`, vérification `alembic current`, retour arrière) et dériver la version affichée de `GEOSTUDIO_VERSION` (F5, F7).
5. Corriger le runbook de rotation (`up -d core worker`, message d'erreur d'`InvalidTag`, DSN valide) et ajouter la rotation des autres secrets (F6).
6. Aligner `backup.sh:51`, le runbook `:61,:169` sur les huit buckets (F8).
