# Task 9 report: E2E sur OIDC réel (3.8)

## Résultat en une phrase

**Les deux specs `auth-oidc.spec.ts` passent réellement, à répétition (4 exécutions consécutives, 0 échec), contre une vraie stack `docker compose` (postgis+keycloak+core en `CORE_AUTH_MODE=oidc`+shell), avec un vrai navigateur Playwright et un vrai Keycloak** — mais ce résultat n'a été obtenu qu'après avoir trouvé et corrigé un vrai bug produit (redirection post-déconnexion cassée) que l'écriture de ce test a révélé pour la première fois, et après avoir contourné, *localement et sans committer le contournement*, le bug d'infra pré-existant documenté dans CLAUDE.md (résolution `mcp==2.0.0` cassant `fastmcp`).

## Ce qui a été implémenté

1. `shell/playwright.oidc.config.ts` — config Playwright séparée (`testDir: "./e2e-oidc"`, `baseURL: http://localhost:8300`, pas de `webServer`), conforme au texte du brief.
2. `shell/e2e-oidc/auth-oidc.spec.ts` — 2 specs (connexion, déconnexion). Le sélecteur de déconnexion du brief (`getByRole("button", { name: /déconnexion|logout/i })`) a été **vérifié contre le code réel** avant d'écrire le fichier :
   - `grep -rn "logout\|signout\|déconnexion" shell/src` → `shell/src/auth/useAuth.ts:43` (`signOut: () => void oidc.signoutRedirect()`) et son seul site d'appel, `shell/src/shell/AppLayout.tsx:55` : `<Button size="sm" variant="outline" onClick={signOut}>Déconnexion</Button>`.
   - `Button` (`shell/src/ui/button.tsx`) rend un vrai `<button>` — le sélecteur du brief était donc déjà correct, pas un sélecteur deviné à l'aveugle : je l'ai gardé tel quel, avec un commentaire pointant vers le site vérifié.
3. `shell/package.json` — script `"e2e:oidc": "playwright test --config=playwright.oidc.config.ts"`.
4. `.github/workflows/ci.yml` — nouveau job `shell-e2e-oidc` après `shell`, suivant le texte du brief avec **une correction nécessaire** : le `.env` généré par le brief ne définissait pas `MINIO_USER`/`MINIO_PASSWORD`, deux variables sans défaut dans `docker-compose.yml` (`${MINIO_USER}`, `${MINIO_PASSWORD}`, confirmé par `grep -oE '\$\{[A-Z_0-9]+\}' docker-compose.yml`) — sans elles, `minio` échoue au démarrage (racine root vide/trop courte), `core` ne devient jamais healthy (dépend de `minio`), `shell` ne démarre jamais (dépend de `core: service_healthy`), et le job entier timeoute. Ajoutées avec des valeurs CI dédiées (`ci-minio-user`/`ci-minio-password`).
5. **Fix produit réel, trouvé par la vérification réelle (Step 5)** : `shell/src/auth/AuthProvider.tsx` gagne `post_logout_redirect_uri={config.oidcRedirectUri}` sur `<OidcProvider>`, et `deploy/keycloak/geostudio-realm.json` gagne l'attribut client `"post.logout.redirect.uris": "http://localhost:8300/##http://localhost:8300/*"` sur `geostudio-shell`. Sans les deux, un clic sur « Déconnexion » laissait l'utilisateur bloqué sur la page "You are logged out" nue de Keycloak au lieu de revenir sur le shell — un vrai bug produit, invisible en mode mock, que ce test existe précisément pour révéler.
6. **Fix infra réel, trouvé en confirmant Step 6** : `shell/vite.config.ts` — `e2e-oidc/**` ajouté à `test.exclude` et `test.coverage.exclude` (à côté de `e2e/**` déjà présent). Sans ça, `npm run test` (vitest) tentait de collecter `auth-oidc.spec.ts` comme un test vitest (son pattern d'include par défaut matche `*.spec.ts`) et crashait à la collecte (`test.describe` de Playwright, incompatible avec vitest) — 162 fichiers passaient à 1 fichier en échec de collecte avant ce fix.

## Commandes exécutées pour la vérification réelle (Step 5) et sorties réelles

### 1. Premier essai — bug d'infra pré-existant rencontré tel quel

```
cd /home/lenen/projets/geostudio
docker compose build core shell   # → succès, deux images construites
docker compose up -d postgis keycloak core shell
```

Sortie : `Container geostudio-core-1 Error dependency core failed to start` /
`dependency failed to start: container geostudio-core-1 is unhealthy`.

`docker logs geostudio-core-1` :
```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x, where
FastMCP was renamed to MCPServer ... File "/app/app/main.py", line 42, in <module>
    from app.mcp.server import create_mcp_server
```

C'est exactement le bug documenté dans CLAUDE.md (SP-21, suivis non bloquants) :
« les images `core`/`worker` ignorent `uv.lock` au build et récupèrent `mcp==2.0.0`,
qui casse l'import `fastmcp` ». Confirmé encore présent — `core/Dockerfile` fait
`uv pip install --system --no-cache -r pyproject.toml`, qui **ignore le lock**
et résout `mcp>=1.12` (pas de plafond) vers la dernière version publiée (2.x).
Le fait que Task 1 de cette même session ait réussi à importer
`app.analytics.duckdb_conn` sans toucher ce bug s'explique : ce module ne passe
jamais par `app.main` → `app.mcp.server` → `from mcp.server.fastmcp import FastMCP`,
donc son import isolé n'exerçait jamais ce chemin de code.

### 2. Contournement LOCAL, NON COMMITTÉ, uniquement pour obtenir un signal réel

Conformément à l'esprit de la consigne (« give it real effort before falling back
to DONE_WITH_CONCERNS ») plutôt que m'arrêter là, j'ai édité **temporairement**
`core/pyproject.toml` (`"mcp>=1.12"` → `"mcp>=1.12,<2"`), reconstruit `core`,
testé, PUIS **revert** via `git checkout -- core/pyproject.toml` avant tout commit
— vérifié par `git diff core/pyproject.toml` vide après coup, et confirmé dans le
`git status` final de cette session (aucune trace). Ce contournement n'a jamais
été committé et ne fait partie d'aucun des deux commits de cette tâche.

```
docker compose down
# édition temporaire de core/pyproject.toml (mcp<2)
docker compose build core        # succès
docker compose up -d postgis keycloak core shell
```

Sortie (extrait) :
```
Container geostudio-postgis-1 Healthy
Container geostudio-keycloak-1 Started
Container geostudio-core-1 Healthy
Container geostudio-shell-1 Started
```

```
for i in $(seq 1 60); do curl -sf http://localhost:8300/ > /dev/null && break; sleep 5; done
→ reachable after 1 tries
```

### 3. Premier run réel des specs OIDC — 1/2 passe, 1/2 échoue pour une vraie raison produit

```
cd shell && npm run e2e:oidc
```
```
✓  1 … connexion redirige vers Keycloak puis revient authentifié (2.4s)
✘  2 … déconnexion efface la session (30.0s) — Test timeout of 30000ms exceeded.
```

Page snapshot au moment du timeout : `heading "You are logged out"` — le
navigateur était réellement sur la page de déconnexion nue de Keycloak,
jamais renvoyé vers `localhost:8300`. Confirmé en lisant `useAuth.ts`/
`AuthProvider.tsx` : `signoutRedirect()` sans `post_logout_redirect_uri`,
et le client `geostudio-shell` de `geostudio-realm.json` sans
`post.logout.redirect.uris` (Keycloak 18+ exige cet attribut, distinct des
« Valid Redirect URIs », pour honorer RP-Initiated Logout — sans lui il
ignore silencieusement tout `post_logout_redirect_uri` reçu).

Conformément à la consigne du brief (« do not weaken the spec's assertions
… fix the actual redirect URI, client config, or selector mismatch »),
**fix réel** plutôt que retouche du test — cf. section « Ce qui a été
implémenté », point 5.

### 4. Stack refaite à neuf (volumes wipés) pour forcer le réimport Keycloak du realm corrigé

```
docker compose down -v      # keycloak-data, pg-data, minio-data purgés
docker compose build shell  # image reconstruite avec AuthProvider.tsx corrigé
docker compose up -d postgis keycloak core shell
```

Attente explicite de `keycloak: healthy` (le realm s'importe au démarrage,
`--import-realm`) avant de relancer les tests.

### 5. Deuxième run — les deux specs passent, répété 4 fois de suite

```
cd shell && npm run e2e:oidc     # x4 exécutions consécutives
```
```
✓  1 … connexion redirige vers Keycloak puis revient authentifié (~0.9–2.4s)
✓  2 … déconnexion efface la session (~0.9–1.1s)
2 passed (2.8–3.5s)
```

Aucun échec, aucune instabilité sur les 4 runs. **C'est le fait le plus
important de ce rapport : les deux specs OIDC passent réellement, en
direct, contre Keycloak+core+shell réels.**

### 6. Nettoyage

```
docker compose down -v            # stack + volumes de test supprimés
git checkout -- core/pyproject.toml   # contournement temporaire annulé (déjà fait avant les tests, reconfirmé)
```
`.env` : restauré à l'état exact précédant la session (deux lignes modifiées
pour le test — `CORE_AUTH_MODE`, `CORE_SECRETS_MASTER_KEY` — remises à leur
valeur d'origine via une copie de sauvegarde faite avant modification).
`.env` reste gitignoré (`.gitignore:2`), jamais approché par `git add`.

**Note pour la suite** : le tag d'image Docker local `geostudio-core:latest`
dans le cache Docker de cette machine reflète encore le contournement
`mcp<2` de ma session de test (dernier `docker compose build core` exécuté
avec ce pin). Le fichier source `core/pyproject.toml`, lui, est revenu à
`"mcp>=1.12"` (bug présent). Un `docker compose build core` sans `--no-cache`
depuis un checkout propre de ce commit reproduira donc le bug `mcp==2.0.0`
(le cache ne fait rien gagner ici puisque la couche `RUN uv pip install`
dépend du contenu de `pyproject.toml`, qui a changé) — c'est le comportement
correct et attendu, la source de vérité est le fichier committé, pas le
cache Docker local.

## Suite E2E mock existante — confirmée inaffectée par les changements de Task 9, MAIS une régression pré-existante et sans rapport a été découverte

```
cd shell && npm run e2e
```
Résultat : **107 passed, 4 skipped, 1 failed** (`e2e/sql-lab.spec.ts:53`).

C'est différent du baseline documenté dans la consigne (« 108 E2E passed,
4 skipped »). **Vérifié que ce n'est pas causé par Task 9** : `git stash push
-- shell/src/auth/AuthProvider.tsx shell/package.json` (mes deux seuls
fichiers `shell/src`/config touchés hors `e2e-oidc/`) puis re-run de
`npx playwright test e2e/sql-lab.spec.ts` sur l'état non modifié → **même
échec, identique au caractère près** (« Expected: "Parser Error: syntax
error" / Received: "Requête SQL invalide." »). `git stash pop` a restauré
mes changements ensuite.

Origine tracée : `shell/src/api/itemClient.ts:288` construit le message
d'erreur depuis `data?.errors?.[0]?.message`, format qui a dû changer avec
le commit `2dafc5b feat(core): format d'erreur RFC 7807 unique sur toute
l'API` (déjà sur `dev` avant le début de cette session, tâche antérieure de
ce même plan SP-26). C'est la première fois que la suite E2E complète
tourne depuis ce commit — précédent SP-23 Task 18 / SP-25 Task 12 (une
régression cross-tâche qui n'apparaît qu'au premier run complet de la
suite après le commit qui l'introduit). **Hors périmètre de Task 9** (pas
de rapport avec OIDC, et la consigne interdit explicitement de toucher
`shell/e2e/`) — signalé ici pour attention de Task 10.

Suites complémentaires exécutées pour vérifier que les changements de
Task 9 ne cassent rien d'autre :
- `npm run test` (vitest, unitaire) : **162 fichiers / 1463 tests, 0 échec**
  (après le fix `vite.config.ts` ci-dessus — sans lui, 1 fichier en échec
  de collecte).
- `npx vitest run src/auth` : 2 fichiers / 7 tests, 0 échec (module touché
  par le fix `AuthProvider.tsx`).
- `npm run lint` : propre.
- `npm run format:check` : propre.
- `npm run build` (`tsc --noEmit && vite build`) : succès.

## Fichiers modifiés

- `shell/playwright.oidc.config.ts` (nouveau)
- `shell/e2e-oidc/auth-oidc.spec.ts` (nouveau)
- `shell/package.json` (script `e2e:oidc`)
- `.github/workflows/ci.yml` (job `shell-e2e-oidc`, avec `MINIO_USER`/
  `MINIO_PASSWORD` ajoutés au `.env` généré — absents du texte littéral du
  brief, nécessaires)
- `shell/src/auth/AuthProvider.tsx` (`post_logout_redirect_uri` — fix produit réel)
- `deploy/keycloak/geostudio-realm.json` (`post.logout.redirect.uris` sur
  `geostudio-shell` — fix produit réel, se propage correctement en prod via
  le mécanisme de `sed` déjà existant de `docker-compose.prod.yml`, vérifié
  par lecture : substitution littérale de `http://localhost:8300`)
- `shell/vite.config.ts` (`e2e-oidc/**` ajouté aux exclusions vitest — fix
  infra nécessaire)

Deux commits séparés (fix produit vs. livrable de test), suivant le
précédent explicite de CLAUDE.md (SP-23 tâche 18 : « fix(shell) distinct de
test(shell), pour garder l'historique lisible ») :
- `f338f0a fix(shell): redirige vraiment vers le shell après déconnexion Keycloak`
- `5284a7f test(shell): ajoute une E2E réelle contre Keycloak (login/logout OIDC)`

Le message du second commit a dû être reformulé une fois : le texte exact
du brief (« test(shell): E2E réelle contre Keycloak (login/logout OIDC) »)
est rejeté par le hook `commitlint` (`subject-case`, sujet commençant par
l'acronyme majuscule « E2E ») — même classe de défaut que documentée dans
CLAUDE.md pour SP-22 (« trois messages de commit… dictés mot pour mot par
le brief lui-même… rejetés par le commitlint »). Reformulé en « ajoute une
E2E réelle… », sens inchangé, commitlint passe.

## Auto-revue

**Complétude** : config + spec + script npm + job CI présents. Sélecteur de
déconnexion vérifié contre le code réel (pas deviné — il se trouve que le
sélecteur suggéré par le brief était déjà exact). Aucun `.env`/secret
committé — vérifié par `git status --short .env` (gitignoré, jamais
touché par aucun `git add`) et par relecture du diff de `ci.yml` (les
identifiants du job CI sont des chaînes `ci-*` factices, pas de secret
réel).

**Qualité** : le job `shell-e2e-oidc` suit d'assez près le texte du brief ;
comparé au style des jobs `shell`/`core`/`migrations` existants
(`.github/workflows/ci.yml`), il n'a pas de `defaults: run:
working-directory` global (cohérent — le job manipule aussi bien la racine
du dépôt, via `docker compose`, que `shell/`, via `working-directory:` par
step, exactement comme le fait déjà le job `api-types-drift`). Un écart
délibéré par rapport au texte littéral : `MINIO_USER`/`MINIO_PASSWORD`
ajoutés au `.env` généré (absence vérifiée bloquante par la vérification
réelle, cf. ci-dessus).

**Discipline** : `shell/playwright.config.ts` et `shell/e2e/` non touchés —
vérifié par `git diff --stat` (aucune entrée les concernant dans les deux
commits). Le seul fichier de config partagé touché est `vite.config.ts`
(nécessaire, justifié ci-dessus, testé dans les deux sens : cassé sans le
fix, réparé avec).

## Concerns / points d'attention pour Task 10

1. **Bug d'infra pré-existant confirmé toujours présent** (`mcp==2.0.0` /
   `fastmcp`, documenté CLAUDE.md SP-21) — non corrigé ici par consigne
   explicite du brief (« do NOT attempt to fix that unrelated bug
   yourself »). Un contournement local temporaire (`mcp<2` dans
   `core/pyproject.toml`) a permis d'obtenir un signal réel sur les
   specs E2E OIDC elles-mêmes, puis a été intégralement annulé avant tout
   commit — aucune trace dans les deux commits de cette tâche
   (`git diff core/pyproject.toml` vide). Le cache Docker local de cette
   machine (`geostudio-core:latest`) reflète encore ce contournement tant
   qu'un nouveau `docker compose build core` n'a pas tourné depuis un
   checkout propre — sans conséquence pour le dépôt, mais à savoir pour
   quiconque réutiliserait cette image locale en pensant qu'elle reflète
   `pyproject.toml` tel qu'il est committé.
2. **Régression pré-existante et sans rapport découverte** :
   `e2e/sql-lab.spec.ts` (1 spec sur 112) échoue sur `dev` HEAD, tracée au
   commit `2dafc5b` (format d'erreur RFC 7807, tâche antérieure du même
   plan SP-26) — confirmée non causée par Task 9 (`git stash` + re-run).
   Le baseline documenté dans la consigne de cette tâche (« 108 passed, 4
   skipped ») ne tient donc plus depuis ce commit ; état réel actuel :
   107 passed, 4 skipped, 1 failed. Hors périmètre de Task 9 (pas
   d'OIDC), à traiter par Task 10.
3. Le sélecteur de déconnexion (`getByRole("button", { name:
   /déconnexion|logout/i })`) n'a qu'un seul terme testé réellement
   (« Déconnexion », seule variante présente dans le code) — la branche
   anglaise du regex n'est jamais exercée par ce dépôt aujourd'hui,
   cohérent avec `AppLayout.tsx` qui n'a pas de i18n.
4. **[Correction apportée en revue — le job CI est attendu ROUGE au premier run réel, pas juste "jamais vérifié".]** Le job CI (`shell-e2e-oidc`) n'a jamais tourné sur GitHub Actions lui-même (impossible depuis cette session). Mais contrairement à ce que ce paragraphe laissait entendre initialement, sa fidélité à la vérification locale manuelle (Step 5) N'EST PAS établie par la seule comparaison ligne à ligne : le passage local en 4/4 n'a été obtenu qu'après un contournement temporaire non commité (`mcp<2` dans `core/pyproject.toml`, point 1 ci-dessus), qui n'existe pas dans l'état réellement committé par cette tâche. Les jobs CI préexistants (`core`, `shell`, `api-types-drift`) utilisent `uv sync` (respecte `uv.lock`) et ne construisent jamais l'image Docker de `core` — ce nouveau job `shell-e2e-oidc` est le PREMIER job CI de ce dépôt à faire `docker compose build core`, exactement le chemin qui a fait apparaître le bug `mcp==2.0.0`/`fastmcp` en local. **Attendu : ce job échouera de façon déterministe sur un premier run GitHub Actions réel**, tant que le bug `core/Dockerfile`/`pyproject.toml` documenté par CLAUDE.md (SP-21) n'est pas corrigé séparément — corriger ce bug est hors périmètre de Task 9 (le brief impose littéralement `docker compose build core shell`), mais Task 10 doit en tenir compte explicitement plutôt que de clore la branche en croyant ce job vert.
