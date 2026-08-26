# SP-26 — Durcissement avant v0.1 publique (Vague 3) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-23-sp26-durcissement.md
Spec: docs/superpowers/specs/2026-08-23-sp26-durcissement-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Ledger précédent trouvé au démarrage : SP-25 (clos, CLAUDE.md déjà à jour),
mais son ledger/briefs/rapports n'avaient jamais été commités — commité
tel quel (f1cb51e, `docs(sp25): ledger de session`) avant de repartir de
zéro pour SP-26. `deploy/postgis/pg_hba.conf` non suivi trouvé dans l'arbre
de travail : connu et documenté inerte par CLAUDE.md (suivi SP-20), laissé
tel quel.

## Pre-flight plan review

10 tâches (9 chantiers + clôture). Numérotation de la spec (3.1, 3.3, 3.4,
3.5a/b/c, 3.6, 3.7, 3.8) correspond exactement aux Tasks 1-9 ; 3.2 (clé
maître) déjà fait, non retouché. Aucune contradiction interne trouvée entre
tâches ou avec les Global Constraints. Risque d'exécution documenté par
CLAUDE.md à surveiller (pas une contradiction du plan lui-même) : pannes de
packaging Docker pré-existantes pour `core`/`worker` (résolution `mcp==2.0.0`
ignorant `uv.lock`, `libexpat.so.1` manquant pour `defusedxml`) pourraient
gêner la vérification `docker build`/`docker run` de Task 1 et de Task 10 —
hors périmètre de ce plan à corriger si rencontré, à documenter comme tel
plutôt qu'à contourner en modifiant le Dockerfile au-delà de ce que le plan
demande.

## Tâches

Task 1: complete (commit 4b15da9, review clean — 0 Critical/Important, 3
Minor non bloquants : `chown -R` sur `/run` plus large que nécessaire dans
`shell/Dockerfile` ; scénario de volume nommé frais non testé
explicitement pour `/scratch` de `qgis-worker` — même classe de risque que
`/data`/`backup/archives`, testée ailleurs mais pas ici ; corps de commit
non visible dans le paquet de revue). 7 des 8 conteneurs (core,
export-worker, appexport-standalone, appexport-runtime-builder,
qgis-worker, backup, shell) passés en utilisateur non-root, `HOME` pinné
avant les étapes de build DuckDB/GRASS partout où nécessaire, `postgis`
vérifié déjà non-root au niveau process serveur (gosu à l'entrypoint),
non modifié. 2 bugs réels trouvés et corrigés par l'implémenteur au-delà
du contenu Dockerfile littéral du brief (vérifiés indépendamment par le
reviewer) : `shell` (nginx) plantait au démarrage (`/run/nginx.pid`
permission denied, `chown` étendu à `/run`) ; `backup`'s vrai point de
montage runtime `/backup/archives` (`docker-compose.prod.yml`) était
root-owned et non inscriptible par l'utilisateur non-root — cas non
couvert par l'arbre de décision `$HOME`/`/tmp` du brief lui-même.

Task 2: complete (commit 0062182, review clean — 0 Critical, 1 Important
(qualité de rapport, pas un défaut de code, cf. ci-dessous), 1 Minor
cosmétique). `reject_mock_outside_development()` dans
`core/app/auth/dependency.py`, appelée dans `create_app()` juste après
`load_master_key()` — même patron. `CORE_ENV` : `setdefault` dans
`conftest.py`, câblé dans `docker-compose.yml`, documenté dans
`.env.example`, garde-fou de déployabilité vert (31/31). **Même classe de
lacune d'évidence que SP-25 Task 1** : le rapport de l'implémenteur a
rejoué la suite complète sans `CORE_TEST_DATABASE_URL`, skippant en
silence les ~162 tests `@postgis` (1719 passed, 167 skipped rapportés) —
contrôleur a rejoué la suite en direct contre `postgis-test`
(`localhost:5433`) : **1880 passed, 5 skipped, 1 failed**
(`tests/test_features_rls.py::test_scope_preserves_original_sql_error`).
Échec confirmé **préexistant, sans rapport avec Task 2** — reproduit à
l'identique dans un worktree jetable au commit 4b15da9 (juste avant cette
tâche), et le diff de Task 2 ne touche rien à RLS/RESET ROLE/gestion de
transaction. **Point à investiguer hors SP-26** (pas une régression de ce
plan) : cet échec préexiste sur ce dépôt indépendamment de SP-26 —
probablement une dérive psycopg2/gestion de transaction, non encore
diagnostiquée. **Vraie référence de suite pour la suite de cette
exécution : 1880 passed, 5 skipped, 1 failed pré-existant (pas
1878/5/0).**

Task 3: complete (commit 2dafc5b, review clean — 0 Critical/Important,
2 Minor à reporter à la revue finale de branche). Format RFC 7807 unique
(`application/problem+json`) via 3 handlers d'exception (`ValidationHTTPException`/
`HTTPException`/`Exception` bare) dans `core/app/main.py`, nouveau module
`core/app/errors.py` (hors contrat de couches import-linter, précédent
`app.db`/`app.observability`, vérifié : absent de `[tool.importlinter]`).
`_validation_error` (features/routes.py) et les 6 sites inline de
harvest/routes.py convertis, chacun son propre contenu `errors` préservé
(vérifié site par site par le reviewer). 2 sites shell (`requestFeatureWrite`/
`requestAnalyticsSql`) mis à jour pour lire `errors` au premier niveau.
Diff OpenAPI/TS **vide** — vérifié correct, pas un oubli : aucune route de
ce dépôt ne déclare `responses=` explicite (`grep -rln "responses=" core/app/`
→ rien), donc aucun handler d'exception global ne peut jamais apparaître
dans le schéma documenté, prédiction du brief factuellement fausse sur ce
point précis, pas un défaut de l'implémenteur. 3 fixtures de test hors
périmètre nommé du brief corrigées en cours de route (2 core + 1 shell,
toutes mécaniques : `["detail"]["errors"]` → `["errors"]`, rien d'autre
changé) — conséquence directe et inévitable du changement cassant, pas du
scope creep. Suite complète (avec la vraie base PostGIS) : 1883 passed, 5
skipped, 1 failed (le même échec préexistant de Task 2, confirmé toujours
sans rapport). Shell : 161 fichiers / 1461 tests, tout vert.

**2 Minor reportés à la revue finale de branche** : (1)
`core/app/appexport/miniserver/main.py:173-179` (mini-serveur standalone
SP-18c, sa propre app FastAPI, hors périmètre nommé de ce brief) émet
toujours l'ancienne forme imbriquée sur son propre `/collections/{id}/aggregate`
— inconsistance d'API réelle mais actuellement inerte (le shell ne parse
pas structurellement `errors` sur ce chemin d'appel) ; (2) le
`RequestValidationError` natif de FastAPI (422 pydantic sur body/query)
n'est touché par aucun des 3 handlers et continue de répondre en
`application/json` classique, pas encore RFC 7807 — non nommé par le
brief, pas une régression, mais l'API ne parle pas encore RFC 7807
partout au sens strict.

Task 4: complete (commit 24a8294, review clean — 0 Critical/Important, 2
Minor : incohérence FR/EN sur le message du 429 vs. `read_only_guard`
(le dépôt est déjà incohérent ailleurs, pas une régression de cette
tâche) ; croissance non bornée de `RateLimiter._hits` — déjà documentée
comme limite assumée). `core/app/ratelimit/limiter.py` (`RateLimiter`
en mémoire, budgets sql=10/llm=20/jobs=15/harvest=10 par 60s,
`route_group()`), middleware câblé dans `create_app()` — `RateLimiter()`
bien instanciée À L'INTÉRIEUR de `create_app()` (pas au niveau module,
vérifié explicitement), `/mcp` couvert (mount ASGI brut, middleware
tourne avant tout routage). 429 en `application/problem+json`, cohérent
avec la forme RFC 7807 de Task 3 bien que construit directement (pas via
`raise HTTPException`, middleware hors dispatch route/handler — correct
par construction, pas un raccourci). 1 déviation auto-signalée par
l'implémenteur et vérifiée indépendante par le reviewer : le test
littéral du brief plante (`KeyError` sur `S3_ENDPOINT_URL`, l'utilisateur
mock est toujours `is_analyst` donc atteint toujours le vrai
`conn_factory()`) — corrigé par le même override de
`get_duckdb_connection_factory` que `test_analytics_sql_routes.py`
préexistant, vérifié nécessaire/non-affaiblissant/bien scopé. Suite
complète : 1886 passed, 5 skipped, 1 failed (même échec RLS préexistant,
toujours sans rapport).

Task 5: complete (commit 1ba0952, review clean — 0 Critical/Important/Minor).
`_ShutdownState` (core/app/cdc/main.py) — SIGTERM positionne un flag,
branché sur le paramètre `should_stop` déjà accepté par `stream_changes()`
mais jamais câblé, flush final après sortie de boucle. Test isolé
(`test_cdc_shutdown.py`), pas de test sur `run()` lui-même (exige DB/S3
réels, comme documenté). Aucune restructuration des closures existantes.
Suite complète : 1887 passed, 5 skipped, 1 failed (même échec RLS
préexistant).

Task 6: complete (commit 3598ce2, review clean — 0 Critical/Important/Minor).
`AppErrorBoundary` (shell/src/AppErrorBoundary.tsx) — nouveau boundary
racine, distinct de `WidgetErrorBoundary` (WidgetHost.tsx, non touché),
posé autour d'`AuthProvider`/`QueryClientProvider` dans `App.tsx` (pas à
l'intérieur, pour attraper aussi un crash d'initialisation des providers
eux-mêmes). 2 tests, `console.error` correctement mocké/restauré. Shell :
162 fichiers / 1463 tests, lint/format/build verts.

Task 7: complete (commit 36ac18c, review clean — 0 Critical/Important, 1
Minor cosmétique : commentaire inline référençant les numéros d'étape du
brief plutôt que de décrire l'état directement). CSP (Report-Only)/
Permissions-Policy ajoutées au middleware `security-headers` Traefik
EXISTANT (pas un nouveau), nouveau middleware `compress` chaîné sur
`core` et `shell` ; mêmes en-têtes + gzip sur `shell/nginx.conf`
(`connect-src`/`img-src` restent `'self'` sans host en dur, car ce
fichier sert aussi les bundles d'export). **Bascule en enforcing (Step
5) délibérément NON faite** — repli explicitement sanctionné par le
brief lui-même : aucun binaire Chromium disponible dans cet
environnement (Playwright et chrome-devtools-mcp ont échoué au
lancement), séparé du bug de packaging préexistant `core`/`mcp==2.0.0`
(reproduit, confirmé sans rapport, non corrigé — hors périmètre).
Vérification réelle : curl direct contre le conteneur `shell` nginx réel
(en-têtes présents, gzip appliqué au bundle JS, absent sur le petit
`index.html` sous le seuil `gzip_min_length`) ; chemin Traefik vérifié
config-only (`docker compose ... config`, résolu et reparsé
indépendamment par le reviewer). 1 bug YAML réel trouvé et corrigé dans
le texte littéral du brief (guillemets manquants sur la valeur CSP,
`data: blob:` casse le parse YAML) — reproduit indépendamment par le
reviewer (PyYAML), substitution `${GEOSTUDIO_PUBLIC_HOST}` confirmée
préservée. Mésaventure git auto-corrigée en cours de tâche (`--amend` a
brièvement fusionné avec le commit de Task 6, récupéré par `git reset
--soft`) — historique vérifié intact des deux côtés par le reviewer.
Garde-fou de déployabilité : 31/31.

Task 8: complete (commit 4e2e7d0, review clean — 0 Critical/Important, 2
Minor cosmétiques : en-tête `.env.example` avec des backticks, seule
section sur ~15 à le faire ; nom du contact point sans référence SP).
Point de contact webhook + politique de routage (dossier SLO,
`object_matchers` sur `slo`), Step 1 empiriquement vérifié contre l'image
réelle (Grafana 12.0.1 dans `grafana/otel-lgtm:0.11.4`) — expansion
`${VAR}` native confirmée fonctionner, branche 2a retenue (pas de
`.template`/envsubst). **Déviation réelle et vérifiée par rapport au
texte littéral du brief** : le défaut `${GRAFANA_ALERT_WEBHOOK_URL:-}`
(chaîne vide) proposé par le brief fait planter tout le conteneur au
démarrage (`required field 'url' is not specified` — Grafana exige une
URL non vide même pour un contact point censé rester inerte) — corrigé
par un défaut syntaxiquement valide mais délibérément inatteignable
(`http://127.0.0.1:1/grafana-alert-webhook-not-configured`), vérifié
sain indépendamment par le reviewer (port tcpmux, loopback, jamais de
livraison accidentelle). **Preuve de bout en bout réellement observée** :
POST réel reçu par un listener HTTP local via `host.docker.internal`
après dépause temporaire de `test-alert-do-not-keep-in-prod`, alerte
passée `active` dans l'API Alertmanager puis arrêtée après repause,
`git diff` sur `rules.yaml` confirmé vide (vérifié indépendamment par le
reviewer). Contournement d'un problème de port-forwarding WSL2/Docker
Desktop sans rapport (docker run au lieu de docker compose up pour la
preuve E2E) — jugé plausible et hors périmètre par le reviewer. Garde-fou
de déployabilité : 31/31 (re-exécuté indépendamment par le reviewer).

Task 9: complete (commits f338f0a..5284a7f, review « Needs fixes » sur le
rapport uniquement — le code lui-même est approuvé sans réserve, corrigé
par édition directe du rapport plutôt qu'une passe de fix/re-revue
complète, cf. ci-dessous). `shell/playwright.oidc.config.ts` +
`shell/e2e-oidc/auth-oidc.spec.ts` (login+logout), stack réelle
(postgis+keycloak+core en `CORE_AUTH_MODE=oidc`+shell) — **preuve de
bout en bout réellement obtenue** : 2 specs passées 4 fois de suite en
local, 0 échec, sélecteur de déconnexion vérifié contre le vrai code
(`AppLayout.tsx`) et re-vérifié indépendamment par le reviewer. **Bug
produit réel trouvé et corrigé** (2 commits séparés, précédent SP-23
tâche 18) : la déconnexion Keycloak laissait l'utilisateur sur la page
nue "vous êtes déconnecté" faute de `post_logout_redirect_uri` —
`AuthProvider.tsx` + `deploy/keycloak/geostudio-realm.json` (`post.logout.redirect.uris`
sur `geostudio-shell`), vérifié indépendamment par le reviewer contre
`react-oidc-context`/`oidc-client-ts` réels et le mécanisme de sed déjà
existant de `docker-compose.prod.yml`. Contournement local temporaire du
bug préexistant `mcp==2.0.0`/`fastmcp` (CLAUDE.md SP-21) intégralement
annulé avant tout commit — vérifié absent des deux diffs.

**Régression réelle découverte, PAS causée par Task 9, sans rapport avec
OIDC** : `shell/e2e/sql-lab.spec.ts` échoue sur `dev` HEAD (107 passed, 4
skipped, 1 failed — pas 108/4/0), tracée au commit `2dafc5b` (Task 3, RFC
7807) qui a mis à jour `itemClient.ts` et ses tests unitaires mais jamais
le mock E2E de ce fichier (toujours l'ancienne forme imbriquée). Root
cause confirmée indépendamment par le reviewer (lecture directe
d'`itemClient.ts`/`sql-lab.spec.ts`, commit `2dafc5b`). **Premier run de
la suite E2E complète depuis Task 3** — précédent SP-23 Task 18/SP-25
Task 12 (régression cross-tâche invisible tant que personne ne relance
la suite complète). **À corriger avant Task 10** (baseline réelle
actuelle : 107 passed, 4 skipped, 1 failed, pas 108/4/0).

**Correction apportée après revue** (édition directe du rapport, pas de
re-dispatch d'implémenteur — le code était déjà approuvé) : le rapport
minimisait le risque du nouveau job CI `shell-e2e-oidc` (« jamais tourné
sur GHA, fidélité par comparaison ligne à ligne ») alors que le
contournement local qui a permis les 4/4 n'existe pas dans l'état
committé — ce nouveau job est le PREMIER job CI de ce dépôt à faire
`docker compose build core` (les jobs `core`/`shell`/`api-types-drift`
existants utilisent `uv sync`, respectent `uv.lock`, ne buildent jamais
l'image Docker) — **attendu rouge de façon déterministe au premier run
GHA réel**, tant que le bug `core/Dockerfile`/`mcp==2.0.0` (CLAUDE.md
SP-21) n'est pas corrigé séparément (hors périmètre de Task 9, brief
littéral). Reportée clairement pour Task 10. 2 Minor supplémentaires
(inexactitude mineure sur la liste des fichiers exclus du `git stash`
d'investigation ; `docker build -t geostudio-postgis-ci` non consommé par
`docker compose build`, buildé deux fois — non testé par le Step 5 réel,
coût CI gaspillé mais pas un bug de correction).

Fix (hors numérotation de tâche, entre Task 9 et Task 10) : commit
d3086eb — `shell/e2e/sql-lab.spec.ts` mis à jour vers la forme RFC 7807
top-level (`errors` au lieu de `detail.errors`), fixant la régression
Task 3 découverte par Task 9. Vérifié directement par le contrôleur (diff
de 4 lignes, chirurgical, rien d'autre touché). Baseline E2E réellement
restaurée : **108 passed, 4 skipped, 0 failed**. Vitest : 162 fichiers /
1463 tests, 0 régression.

**Décision de scope actée** (précédent CLAUDE.md très établi, pas
re-questionné) : le bug préexistant `core/Dockerfile`/`mcp==2.0.0` cassant
`fastmcp` (documenté CLAUDE.md SP-21, confirmé toujours présent par Task
9) N'EST PAS corrigé dans SP-26 — hors périmètre, comme toutes les
occurrences précédentes de cette classe de bug dans ce dépôt. Conséquence
directe et significative à documenter clairement dans la clôture Task 10 :
le nouveau job CI `shell-e2e-oidc` (Task 9) est le premier job de ce dépôt
à faire `docker compose build core`, et est donc attendu ROUGE de façon
déterministe à son premier run GitHub Actions réel, tant que ce bug
préexistant n'est pas corrigé séparément.

## Task 10 : revue finale de branche et clôture

**Étape 1 (suite complète, contrôleur)** : core `uv run pytest` (PostGIS
réel) → 1887 passed, 5 skipped, 1 failed (même échec RLS préexistant,
confirmé une 3e fois indépendant de SP-26 via worktree jetable) ;
couverture 92,94% (seuil 85) ; ruff/ruff format/mypy --strict (4
modules)/lint-imports verts ; garde-fou de déployabilité 31/31. Shell :
162 fichiers / 1463 tests (après nettoyage `dist/`/`dist-export/`, même
piège documenté SP-22-25) ; couverture 89,57% (seuil 88) ; lint/format/
build verts ; E2E 108 passed, 4 skipped, 0 failed (baseline restaurée par
le fix interstitiel de sql-lab.spec.ts). `uvx pre-commit run --all-files` :
5/5.

**Étape 2 (revue finale de branche, opus, f1cb51e..d3086eb)** : 1 Critical
(C1) + 6 Important (I1-I6). **C1** — `/scratch` jamais créé/chowné dans
`core/Dockerfile` (le service `worker` partage la même image core non-root
et monte `etl-scratch:/scratch` pour les jobs pipeline/terrain3d) + uid
mismatch entre `app` (core) et `qgis` (qgis-worker), deux images de base
différentes, chacune `useradd --system` sans uid explicite — casse la
remise de fichier pipeline→sidecar QGIS à travers ce même répertoire
partagé. **I1** — budget rate-limit harvest (10/min, `_HARVEST_RE`
couvrant TOUTES les routes) tue silencieusement les couches externes du
sélecteur de couches (recherche sans debounce, échecs avalés par
`Promise.allSettled`). **I2** — défaut compose `CORE_ENV: ${CORE_ENV:-development}`
désarme la garde mock-mode de Task 2 exactement dans le scénario qu'elle
visait (compose de base sans `.env`). **I3** — 403 démo lecture-seule
encore en JSON plat, pas RFC 7807 (angle mort de Task 3, middleware pas
exception handler). **I4** — `RateLimiter._hits` clé sur le JWT brut
(rotation OIDC) croît sans borne, docstring affirmant à tort une
croissance négligeable. **I5** — CSP Report-Only a 4 bloqueurs concrets
déjà identifiés pour la bascule enforcing (tuiles WMS/WMTS/terrain
externes, tileset 3D externe, widgets d'extension tiers, `nginx.conf`
faux hors overlay prod) — documentation seule. **I6** — volumes nommés
déjà peuplés (déploiement pré-SP-26) resteront `root:root` à l'upgrade —
documentation seule. Les 3 risques d'intégration cross-tâches
explicitement nommés par le brief de Task 10 (429/RFC7807, non-root ×
Tasks 2-4, CSP × `AppErrorBoundary`) tous vérifiés propres. Aucune régression
trouvée sur le fond des 9 tâches individuelles.

**Fix round 1** (commits 6acf4bb/5714e16/de778e4) : les 7 findings
corrigés en une passe. C1 : uid/gid 1001 fixé identique dans
`core/Dockerfile`/`deploy/qgis-worker/Dockerfile` (vérifié libre dans les
deux images de base), `/scratch` créé+chowné dans `core/Dockerfile`,
**écriture croisée réelle prouvée dans les deux ordres de démarrage
possibles du volume nommé** (pas seulement égalité d'uid), RED→GREEN
Docker réel. I1 : `route_group()` gagne un paramètre `method`, le groupe
harvest ne retient que les 4 routes non-GET (écriture/coût réel), 4
routes de lecture (list_sources/list_layers/list_feature_layers/
get_source) exemptées. I2 : défaut compose vidé (`${CORE_ENV:-}`), flux
`.env.example`→`bootstrap-env.sh` non affecté. I3 : 403 aligné sur les 3
autres sites RFC 7807 existants, fix inline conservateur. I4 : balayage
périodique (toutes les 50 requêtes) retire réellement les entrées vides
du dict, docstring corrigé. I5/I6 : notes ajoutées (commentaire CSP dans
`docker-compose.prod.yml`, nouveau runbook
`docs/runbooks/2026-08-27-migration-conteneurs-non-root.md`). Suite
complète : 1895 passed, 5 skipped, 1 failed (même échec préexistant).
Garde-fou de déployabilité : 34/34 (+3 : 1 pour I2, 2 pour C1).

**Re-revue** (opus) : 6/7 fermés correctement et vérifiés indépendamment
(C1 par relecture statique + tests non-vacueux prouvés par revert simulé ;
I1 par exhaustivité du découpage GET/non-GET relu dans le code réel ; I2
par simulation de régression sur le test ; I3 par comparaison octet-à-octet
avec les 3 autres sites ; I4 par lecture du mécanisme de retrait réel du
dict). **I6 partiellement fermé** — 2 Important supplémentaires trouvés :
N1 (la commande `chown backup:backup` du runbook échoue réellement — le
nom `backup` n'existe pas dans l'image `alpine` générique utilisée pour la
commande, et l'uid de `deploy/backup/Dockerfile` n'était de toute façon pas
fixé) ; N2 (un 3e volume nommé cassé par le même changement non-root,
`appexport-runtime` — `deploy/appexport-runtime-builder/Dockerfile`, absent
du runbook). Plus 4 Minor (test I2 ne couvre qu'une direction de
régression ; test C1 ne pin que `core/Dockerfile`, pas
`qgis-worker/Dockerfile` ; classification I1 par "pas GET" plutôt que "est
une écriture" — inatteignable aujourd'hui ; bloqueur CSP #4 documenté
seulement dans `docker-compose.prod.yml`, pas près de `shell/nginx.conf`).

**Fix round 2** (commits 64d36d6/2f7ff0f/2c3c9cc/9e3b278) : N1/N2/M1/M2/M4
fermés (M3 explicitement non touché, inatteignable aujourd'hui, reporté en
suivi non bloquant). `deploy/backup/Dockerfile`/
`deploy/appexport-runtime-builder/Dockerfile` fixent désormais leur
utilisateur à uid/gid 1001 (vérifié libre dans leurs images de base
respectives — pas de contrainte de convergence avec `app`/`qgis`, aucun
volume partagé avec eux, 1001 choisi par cohérence documentaire
seulement). Runbook corrigé (chown numérique, pas par nom) et complété
(3e volume `appexport-runtime`) — vérifié empiriquement dans les deux
sens (ancienne commande échoue réellement, nouvelle réussit). Tests I2/C1
renforcés (valeur résolue plutôt que seulement la syntaxe de défaut ;
`qgis-worker` couvert en plus de `core`), RED→GREEN prouvé. Commentaire
de renvoi ajouté dans `shell/nginx.conf`. Suite complète : 1896 passed, 5
skipped, 1 failed (même échec préexistant). Garde-fou de déployabilité :
35/35. **0 Critical/Important ouvert à ce stade — vérifié directement par
le contrôleur (lecture des 3 diffs de fichiers Dockerfile/runbook/nginx.conf),
sans re-dispatcher de revue complète, jugé proportionné pour une passe de
suivi de cette taille.**

Minor reportés en suivi non bloquant (jamais corrigés, disposition
identique aux autres SP) : classification I1 par "pas GET" plutôt que
"est une écriture" (OPTIONS/HEAD sur `/harvest/*` techniquement dans le
budget harvest, inatteignable aujourd'hui — aucun CORS preflight répondu
sur ce chemin) ; ~8 Minor de la revue finale round 1, explicitement non
touchés (voir le rapport de revue pour le détail : `HTTPStatus(...).phrase`
ValueError latent sur un code non standard, `import logging` en corps de
handler, double-log sur un 500, tag `geostudio-postgis-ci` du job CI OIDC
non consommé, `docker-compose.prod.yml` n'affiche pas `CORE_ENV: production`
explicitement, `AppErrorBoundary` ne couvre pas le crash de `loadConfig()`
en portée module ni ne se réinitialise au changement de route, la police
Grafana racine route TOUTES les alertes pas seulement SLO, `cdc-worker` ne
gère pas SIGINT).
