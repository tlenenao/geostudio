# SP-18b — Export d'apps : mode Connecté — Progress Ledger

Plan: docs/superpowers/plans/2026-08-15-sp18b-export-mode-connecte.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Le `progress.md` trouvé au démarrage de cette session appartenait à SP-18a
(mécanisme commun + mode Statique) — 13 tâches complètes, tous commits
présents sur `dev` (vérifié par `git log`), mais jamais figé dans une
sauvegarde `docs(sp18a): session ledger …` comme les SP précédents
(sp16b/sp17a/sp17b/tileset3d) — vraisemblablement oublié en fin de session.
Écrasé ici pour ce plan-ci (6e occurrence documentée de cette collision de
fichier scratch réutilisé). Le contenu SP-18a n'est pas perdu : tous ses
commits sont dans `git log` (aef99cf..1b535cf), et son résumé complet est
déjà dans CLAUDE.md (`### Fait`). Pas de re-sauvegarde de son ledger —
hors périmètre de cette session, pas demandé.

## Pre-flight plan review

Lu intégralement (9 tâches, code complet à chaque étape). Aucune
contradiction interne ni avec les Global Constraints. Toutes les
signatures que le plan suppose (côté cœur : `check_export_guard`,
`build_bundle_zip`, `create_job`, `_SUPPORTED_MODES`, `_EXPORT_PATH_RE`/
imports de `main.py` ; côté shell : `AppExportMode`, `createItemClient`
opts shape, `AppExportPanel.tsx`, `entry.tsx`) vérifiées verbatim contre
le code réel avant dispatch — aucune dérive trouvée, le plan est exact.

## Tâches

Task 1: complete (commit 3dc1e3e, review clean — 0 Critical/Important, 1
Minor). `check_export_guard` gagne `mode: str` obligatoire ;
`mode="static"` vérifié octet-pour-octet inchangé par le reviewer (trace
du flux de contrôle contre la version pré-diff) ; `mode="connected"` lève
la restriction `statistics` (même garde `is_public` que `features`) et
saute entièrement l'allowlist de widgets — vérifié par les 4 nouveaux
tests. Note du reviewer (non bloquante, hors périmètre de cette tâche,
attendu par le séquencement du plan) : `jobs.py` (seul appelant
production) est temporairement cassé entre Task 1 et Task 3 (`TypeError`
sur `mode` manquant, capté par le `except Exception` générique → job
"error", jamais un crash) — sera réparé par Task 3.
Task 2: complete (commit 3a6b4c4, review clean — 0 Critical/Important, 1
Minor cosmétique sur le style de signature multi-lignes). `build_bundle_zip`
gagne `connection: dict | None = None` ; défaut `None` vérifié
octet-pour-octet inchangé (seul nouveau code : branche `if connection is
not None`, no-op sinon) par le test de régression explicite du brief.
Task 3: complete (commit 17608be, review clean — 0 Critical/Important, 2
Minor). `build_app_export_task` répare la casse intermédiaire attendue de
Task 1 : lit `job.mode` (champ déjà existant sur le modèle), passe
`mode=mode` à `check_export_guard` (Task 1) et branche via
`_prepare_bundle_inputs` sur `build_bundle_zip(..., connection=...)`
(Task 2) — les deux points d'intégration vérifiés par le reviewer
signature-par-signature contre le code réel. Invariant "toute exception
inattendue → job 'error', jamais 'running' bloqué" confirmé préservé (le
try/except existant enveloppe tout le nouveau code). Test connecté
utilise un espion sur le vrai `build_bundle_zip` (pas un mock complet) —
chemin d'assemblage du zip réellement exercé.
Task 4: complete (commit 726ce98, review clean — 0 Critical/Important/
Minor). `_SUPPORTED_MODES` élargi de `{"static"}` à
`{"static", "connected"}` dans `routes.py`, changement d'une ligne + 2
tests (invalide devient "bogus", nouveau test accepte "connected").
Aucune dérive.
Task 5: complete (commits 585aa39 + a9638b6 fix, re-revue clean). Middleware
CORS étroit, gardé par `is_appexport_enabled()`, évalué une fois à
`create_app()`. **1 Important réel trouvé et corrigé** — arbitré avec
Tanguy (finding "plan-mandated" : le code littéral du plan contredisait sa
propre contrainte globale) : `_APPEXPORT_CORS_PATH_RE` du plan matchait
par chemin seul, sans méthode, donc CORS-exposait aussi `POST
/collections` (admin), `GET /collections/candidates` (admin, matché car
`(/[^/]+)?` traitait "candidates" comme un id), `PATCH`/`DELETE
/collections/{id}`, et les verbes d'écriture sur `.../items[/{fid}]` —
aucun de ces 7 endpoints n'est dans l'allowlist du plan ("exactement les
endpoints anonymes-capables... jamais toute l'API"). Pas d'exploit réel
(`Access-Control-Allow-Headers` n'inclut jamais `Authorization`, un
navigateur ne peut pas compléter un appel cross-origin authentifié vers
ces routes), mais contraire à l'intention explicite. Corrigé par
`_APPEXPORT_CORS_RULES` (paires regex+méthode, une par endpoint de
l'allowlist) appliquées à la branche réponse réelle ; la branche preflight
OPTIONS reste path-only par design (le navigateur ne connaît pas encore
la méthode réelle au moment du preflight — asymétrie acceptée, pas un
bug). Exclusion de `/collections/candidates` par lookahead négatif
`(?!candidates$)`. 2 tests de régression ajoutés (`POST /collections`,
`GET /collections/candidates` sans header), vérifiés par le re-reviewer
comme testant l'absence de header indépendamment du statut HTTP réel (pas
un faux positif via 401/404 précoce). Suite complète : 1527 passed/148
skipped/0 failed. Re-revue a tracé à la main les 7 endpoints cibles +
tous les cas de sur-match nommés contre le code final — 0
Critical/Important.
Task 6: complete (commit b6b59b3, review clean — 0 issues). `AppExportMode`
élargi de `"static"` à `"static" | "connected"` dans types.ts, une ligne.
Aucune dérive.
Task 7: complete (commit 6d6344f, review clean — 0 Critical/Important, 1
Minor). `entry.tsx` détecte le mode Connecté par la présence de
`geostudio-connection.json` (fetch → 200 = Connecté, 404 = Statique
inchangé). **Contrainte de sécurité critique vérifiée indépendamment par
le reviewer** contre le code réel (pas seulement le rapport) : `getToken:
() => undefined` codé en dur, jamais câblé sur `useAuth().getAccessToken`
(qui renvoie le littéral "mock-token" en mode mock, confirmé
`useAuth.ts:24`) — sinon chaque lecture anonyme du mode Connecté
recevrait un 401 (`get_current_user_optional` exige un token valide dès
qu'un header `Authorization` est présent, jamais de repli anonyme sur un
token invalide). `enableMockAuth()` reste inconditionnel dans les deux
modes (nécessaire pour `useAuth()` via `ActionConditionBridge`,
indépendant du `getToken` ci-dessus). Pas de `pageId`/`onNavigate` fixé
(régression SP-18a C3 évitée) ; `QueryClientProvider` présent. Note
auto-signalée par l'implémenteur et vérifiée par le reviewer :
`npm run build:export-runtime` n'exécute pas `tsc --noEmit` (seul le
script `build` le fait) — `npx tsc --noEmit` lancé séparément pour
combler ce trou de preuve.
Task 8: complete (commit 7c4d224, review clean — 0 issues). Second bouton
"Connecté" dans le dialogue de choix de mode ; `pendingWarningMode:
AppExportMode | null` remplace `showWriteWarning: boolean`, corrigeant le
bug latent SP-18a où le bouton "Exporter quand même" appelait toujours
`runExport("static")` peu importe le mode qui avait déclenché
l'avertissement — invisible avec un seul mode, aurait silencieusement
exporté Statique au lieu de Connecté dès qu'un second bouton existerait.
Fix vérifié réel par le reviewer : `runExport(pendingWarningMode)`
(jamais un mode codé en dur), test de régression exerçant un vrai clic
DOM (Connecté → avertissement → "quand même" → assertion sur l'appel
`createAppExport(..., "connected")`).
Task 9: complete (commit 0f6355f, review clean — 0 Critical/Important, 2
Minor). Preuve E2E finale de la fonctionnalité SP-18b entière : deux vrais
serveurs HTTP sur ports éphémères distincts (bundle exporté + "faux cœur"),
Chromium réel via Playwright navigue vers le bundle, données du faux cœur
("Alpha") rendues via un vrai fetch cross-origin, assertion qu'aucun
header `Authorization` n'a jamais atteint le faux cœur. **Rejoué
indépendamment par le reviewer** (pas seulement confiance sur le rapport)
: PASS réel confirmé (236ms, pas un skip), tracé contre le code source
réel (`buildFeaturesUrl`/`_fetchGeoJsonFeatures` dans itemClient.ts,
`getToken` de entry.tsx) pour confirmer que le test exerce vraiment le
chemin qu'il prétend prouver, pas quelque chose qui passerait
trivialement.

## Plan SP-18b terminé — 9/9 tâches, 0 Critical/Important non résolu
(1 Important trouvé et corrigé sur Task 5, arbitré avec Tanguy comme
"plan-mandated" puisque le code littéral du plan contredisait sa propre
contrainte globale). Passage à la revue finale de branche.

## Revue finale de branche (Opus, c45e669..0f6355f)

0 Critical, 4 Important, 9 Minor. Points forts confirmés indépendamment :
câblage docker-compose correct dès le premier coup (CORE_BASE_URL et
CORE_APPEXPORT_ENABLED déjà sur `core` ET `worker`, contrairement aux 3
précédents SP-17a/SP-17b/tileset3d) ; pas de dérive OpenAPI/TS (mode est
un `str`/set runtime, pas un enum de schéma, et la CI ne régénère jamais
avec le flag actif) ; le fix CORS de Task 5 re-vérifié indépendamment
comme correct. 4 Important :
- **I1** — `loadConnection()` dans `entry.tsx` cassait tout bundle
  Statique sur un hébergeur SPA-fallback (nginx `try_files`, Netlify,
  Firebase répondent 200+HTML à un fichier absent au lieu d'un 404) —
  régression totale d'un mode déjà livré, causée par un chemin de code
  Connecté seul.
- **I2** — le garde Connecté autorise les widgets tiers, mais
  `entry.tsx` ne les enregistre jamais (contrairement au shell normal) —
  **arbitré avec Tanguy** : câbler `listActiveExtensions()` dans
  `entry.tsx` plutôt que revenir sur l'allowlist du garde.
- **I3** — endpoint CORS manquant (`GET /public/items`, widget Gallery
  builtin).
- **I4** — `.env.example` obsolète sur les deux flags concernés.

## Fixes finaux (3 rounds)

Round 1 (commit 2bb31af) : les 4 Important + M5/M7 pliés dedans. Suite
complète 1529 passed/148 skipped/0 failed, tsc clean, build export
réussi, 10/10 CORS tests.

Round 2 — **re-revue (Opus) a trouvé et reproduit un Critical réel
introduit par le fix I2 lui-même** : `listActiveExtensions()` non gardé
dans `entry.tsx` faisait échouer tout le bootstrap sur un 404
`/extensions` (E2E `connected-export.spec.ts` — lancée par CI —
reproduite en échec pour de vrai par le reviewer, pas seulement déduite).
Corrigé (commit 084f0ca) par try/catch tolérant ; E2E re-jouée et PASS
confirmé indépendamment.

Round 3 — re-revue a trouvé que le try/catch du round 2 était trop large
(avalait aussi les bugs internes à `registerExtensionWidget`, contraire
à sa propre intention et au self-review du round 2). Corrigé (commit
30fd6a7) : le fetch seul est dans le try, la boucle `.forEach` en
dehors — vérifié par lecture directe du diff (contrôleur, sans
sous-agent supplémentaire vu la taille du changement) : correspond
exactement au finding.

**0 Critical/Important non résolu au merge**, sur 3 rounds de revue
finale de branche.
