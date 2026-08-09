# SP-17a — Worker d'export Playwright & `PrintLayout` — Progress Ledger

Plan: docs/superpowers/plans/2026-08-08-sp17a-worker-export-print.md
Design: docs/superpowers/specs/2026-08-08-sp17a-worker-export-print-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@232ff92 (HEAD au lancement, juste après commit du plan).

## Pré-vol

Scan des 14 tâches + Global Constraints contre l'état réel du repo avant
dispatch, tous les points vérifiés matchent le texte du plan :
- `core/app/configs/schemas.py` : fin de `AlertRulePayload`/début de
  `BuilderConfig` ligne ~316, littéraux `kind` confirmés (Task 1).
- `core/app/auth/dependency.py` : `is_etl_enabled()` L26, `get_current_user`
  L59 (Task 2, Task 4).
- `core/app/instance/routes.py` : contenu actuel `{"readOnly", "etlEnabled"}`
  confirmé identique au texte "avant" du plan (Task 2).
- `core/app/main.py` : `_EXPORT_PATH_RE` L38, `include_router` pipelines
  conditionnel L105-106, `read_only_guard` L68+ (Task 7).
- `core/app/jobs.py` : `import_paths` confirmé, dernier élément
  `"app.alerts.jobs"` (Task 13).
- `core/app/ingestion/storage.py` : `generate_presigned_put_url` présent,
  pas encore de GET (Task 5).
- `core/pyproject.toml` : deps liste confirmée (`openpyxl` avant les
  `opentelemetry-*`), contrat import-linter `layers` confirmé
  (`app.harvest`, `app.pipelines`, `app.alerts`, `app.secrets`, ...) — Task 13
  insère `app.export` entre `app.harvest`/`app.pipelines` et `app.alerts`.
- `shell/src/api/types.ts` : `InstanceInfo` L35, `MapConfig` L64, `AppConfig`
  L414 confirmés (Task 2, Task 8).
- `shell/src/api/itemClient.ts` : `getMapConfig`/`saveMapConfig`/
  `getAppConfig`/`saveAppConfig` aux lignes attendues (Task 8).

Aucune contradiction trouvée entre tâches ni avec les Global Constraints.
Note de placement délibérée dans le plan (Task 4, jeton d'export dans
`app.auth` pas `app.export`, pour respecter le sens du contrat de couches)
vérifiée cohérente avec le contrat réel.

## Tasks (14)

1. `PrintLayout` — schéma cœur + régénération OpenAPI/TS — core+shell
2. Capacité `CORE_EXPORT_ENABLED` — core+shell
3. Table `export_jobs` + repository — core
4. Jeton d'export HS256 dans `app.auth` + extension `get_current_user` — core
5. Presigned GET S3 + rendu pur `render_export` — core
6. Job procrastinate `render_export_task` — core
7. Routes REST `POST /export` + `GET /export/jobs/{id}` — core
8. Shell — types + itemClient (printLayout round-trip, ExportJob)
9. `PrintLayoutPanel` + intégration builders — shell
10. Mode `exportRender` (chrome d'impression + signal de disponibilité) — shell
11. `ExportPanel` (bouton + dialogue + poll) + intégration — shell
12. Bootstrap d'auth — dérogation `exportToken` — shell
13. Infra — `export-worker` (Dockerfile, compose, import-linter, deps) — core+infra
14. E2E — export depuis la visionneuse de carte — shell

## Status

Base Task 1: 232ff92
Task 1: complete (commit 2655508, review Approved au premier passage).
`PrintLayout` + `BuilderConfig.printLayout` conformes mot pour mot au
brief (littéraux `pageSize`/`orientation` exacts), aucune validation
croisée ajoutée (correct, optionnel pour tous les kinds). OpenAPI/TS
régénérés proprement, diff isolé au nouveau schéma. 5/5 tests nouveaux,
suite complète 1277 passed/137 skipped, aucune régression.

Base Task 2: 2655508
Task 2: complete (commit 474b6e9, review Approved au premier passage).
`is_export_enabled()` miroir exact de `is_etl_enabled()`. Shell : brief
suggérait un harnais de test (`hooks.test.ts`/`ItemClientContext`) qui ne
correspondait pas à la réalité (`hooks.test.tsx` existe déjà, patron
`ItemClientProvider`/`makeWrapper`) — implémenteur a suivi le vrai
patron du dépôt, vérifié par le reviewer comme exerçant réellement le
chemin fallback. 1 déviation hors liste de fichiers du brief, vérifiée
nécessaire par le reviewer (grep indépendant confirmant que 2 tests
préexistants faisaient une égalité stricte sur `/instance` sans
`exportEnabled`, motif déjà établi lors de l'introduction d'`etlEnabled`)
: `test_etl_enabled_flag.py`/`test_read_only_mode.py` mis à jour. 4/4
tests core nouveaux, 2/2 tests shell nouveaux, suite complète core
1281/137 skipped, shell 1001 tests/124 fichiers, tsc+vite build propre.

Base Task 3: 474b6e9
Task 3: complete (commit a101546, review Approved au premier passage).
`ExportJob` modèle + repository (create/get/mark_running/mark_done/
mark_error) miroir structurel byte-pour-byte de `app/alerts/repository.py`.
Littéraux de statut exacts vérifiés ("pending"/"running"/"done"/"error",
pas de mismatch type SP-16b). 1 déviation hors liste de fichiers du brief
vérifiée nécessaire par le reviewer : import `app.export.models` dans
`app/db.py` (nécessaire pour `Base.metadata.create_all()` en SQLite,
motif identique aux 9 imports frères). Test file dévie du brief brut
(remplace des ids bare string par de vraies lignes tenant/user/item) —
justifié : le modèle déclare de vrais `ForeignKey` + SQLite
`PRAGMA foreign_keys=ON`, le test brut du brief aurait échoué en FK.
4/4 tests, suite complète 1285 passed/137 skipped.

Base Task 4: a101546
Task 4: complete (commits 3e46f0c, ffa19a8, 1 round de fix, review
Approved en round 2). `app.auth.export_tokens` (mint/decode HS256) +
extension `get_current_user` conformes au brief : claims sans `item_id`,
révocation TTL seul (~2 min, pas d'usage unique), placement dans
`app.auth` (pas `app.export`) vérifié cohérent avec l'ordre des couches
import-linter. 1 Critical trouvé en revue (pas plan-mandaté, bug réel
dans le code dicté) : `_secret()` fait `os.environ["CORE_EXPORT_TOKEN_SECRET"]`
sans garde, `decode_export_token` n'attrapait que `jwt.PyJWTError` — un
`KeyError` non catché s'échappait jusqu'à un 500 Starlette brut. Repro
indépendant du reviewer : n'importe quel appelant non authentifié
envoyant un JWT HS256 auto-forgé (`jwt.encode(..., "n'importe quoi",
algorithm="HS256")`, aucun secret réel requis) vers n'importe quelle
route protégée par `get_current_user` fait planter le process — état par
défaut de toute instance aujourd'hui puisque `CORE_EXPORT_TOKEN_SECRET`
n'est jamais positionné avant Task 13. Fix (ffa19a8) :
`except (jwt.PyJWTError, KeyError)`. Re-revue a vérifié en profondeur que
le fix ferme exactement la faille (relecture du corps du `try`, aucun
autre `KeyError` légitime n'y a sa place) ET a reproduit elle-même RED
(revert temporaire de l'except, re-run des 2 nouveaux tests → même trace
`KeyError` que le rapport initial) puis GREEN (restauration, 14/14 +
73/73 suite auth) — pas seulement fait confiance au rapport. `mint_export_token`
laissé sans garde équivalente (même faille théorique côté mint) jugé non
bloquant : aucun appelant en production dans le périmètre de cette tâche
(vérifié par `git grep`), deviendra pertinent seulement quand Task 6/13
câblera le worker — 1 Minor de suivi noté pour Task 6.

Base Task 5: ffa19a8
Task 5: complete (commit f27baf0, review Approved au premier passage).
`generate_presigned_get_url` miroir de `generate_presigned_put_url`.
`render_export` pure (aucun import Playwright/S3 vérifié), mapping
pageSize→upper()/orientation→landscape vérifié correct contre le schéma
`PrintLayout` réel, exclusivité PNG/PDF vérifiée (jamais les deux
branches). 1 déviation mineure du texte littéral du brief (réutilisation
du fixture `_FakeS3Client` existant du fichier au lieu d'un nouveau
`MagicMock`) jugée justifiée par le reviewer, pas un problème de
conformité. 4/4 tests nouveaux, suite complète 1303 passed/137 skipped.
1 Minor de suivi noté (pas de validation runtime du littéral `format`,
retombe silencieusement en branche pdf) — non bloquant, à garder en tête
pour Task 6.

Base Task 6: f27baf0
Task 6: complete (commits 95e5a4c, c994e94, 1 round de fix, review
Approved en round 2). `render_export_task` — orchestration DB+S3+
Playwright+jeton, conforme au brief (décorateur `@app.task(queue="export")`,
garde `is_export_enabled()` avant tout travail, transitions de statut
exactes, construction d'URL `{SHELL_BASE_URL}/{route}/{item_id}?
exportToken=...&exportRender=1` vérifiée). 3 déviations trouvées ET
corrigées par l'implémenteur lui-même (pas en boucle de revue) : fuite
réelle du driver Playwright (`sync_playwright().start()` jamais apparié
à `.stop()`) confirmée empiriquement (corrompait le Runner anyio caché
d'autres tests async dans la même session) ; 2 fixs test-only (longueur
de secret déclenchant un warning promu en erreur, motif identique à
Task 4 ; lectures identity-map SQLAlchemy périmées produisant des faux
négatifs). Question KeyError de `mint_export_token` (notée en suivi
Task 4) confirmée sans risque : `except Exception` englobant route déjà
vers `mark_error`, jamais un crash. 1 Important trouvé en revue (le fix
de fuite de l'implémenteur ne couvrait que succès/échec de rendu, pas un
échec DANS `_launch_and_navigate` elle-même — lancement Chromium,
navigation, timeout `wait_for_selector`, le mode d'échec Playwright le
plus réaliste en prod) : fix (c994e94) restructure `_launch_and_navigate`
en un seul chemin `except Exception` couvrant les 5 points d'échec
possibles + `finally` imbriqué côté appelant (un échec de `close()` ne
saute plus le `stop()` du driver). Re-revue a tracé à la main les 5
branches ET vérifié que le nouveau test régression fake les vrais
internes Playwright (pas juste `_launch_and_navigate` mocké en bloc comme
le test "navigation_failure" existant) — confirmé par diff contre la
version pré-fix que ce test aurait échoué avant, passe après. 4/4 tests
orchestration + 1 test Chromium réel guardé (PASSED — `playwright install
--with-deps` a échoué faute de sudo comme SP-15d, mais `playwright install
chromium` seul a suffi), suite complète 1309 passed/137 skipped.

Base Task 7: c994e94
Task 7: complete (commits dea7bc0, 103fa70, 1 round de fix, review
Approved en round 2). Routes `POST /export`/`GET /export/jobs/{id}`
conformes : 404 jamais 403 vérifié sur les deux branches (facts=None et
lecture refusée), miroir exact de `_require_pipeline_access` ; montage
conditionnel `is_export_enabled()` à la construction ; exemption
`_EXPORT_PATH_RE` élargie sans régression des motifs SP-16a existants ;
commit avant `defer_task` ; `write_audit` conforme. 1 Important trouvé
en revue, plan-mandaté (code dicté par le brief, pas une déviation de
l'implémenteur) : le client S3 de `GET /export/jobs/{id}` lisait
`os.environ[...]` en dur (motif worker, pas motif route) au lieu du
patron établi `get_s3_client()` injectable de `app/ingestion/routes.py`
— `KeyError`→500 brut si S3 non configuré, ET branche "done"/resultUrl
totalement non testée (aucun test ne menait un job à `status="done"`).
Fix (103fa70) : migration vers `get_s3_client` réutilisé tel quel +
nouveau test menant réellement un job à "done" via `mark_done` direct,
override de dépendance (pas de vraies env vars). Effet de bord assumé et
vérifié sain par le reviewer : `Depends(...)` FastAPI s'évalue pour
CHAQUE appel de la route (pas seulement les jobs "done"), donc le client
S3 devient désormais requis même pour lire un job "pending" — cohérent
avec le patron déjà établi (les 2 routes S3 de `app/ingestion/routes.py`
sont pareillement eager), aucune régression sur les tests des statuts
non-done (fixture partagée mise à jour). `app.export` toujours absent du
contrat de couches import-linter — confirmé pré-existant et hors
périmètre (Task 13 le couvre explicitement). 8/8 tests fichier, suite
complète 1317 passed/137 skipped.

Base Task 8: 103fa70
Task 8: complete (commit c056bce, review Approved au premier passage).
Première tâche shell. Point critique du brief (risque de perte
silencieuse de `printLayout` à la sauvegarde, motif déjà trouvé en revue
SP-16a/SP-16b) vérifié fermé pour `saveMapConfig` ET `saveAppConfig` :
tests asserent sur le vrai corps de requête capturé (pas juste la valeur
de retour), dont un test ciblant précisément le mode d'échec exact
(`body.map.printLayout` doit être `undefined`). L'implémenteur a trouvé
ET corrigé un vrai bug pré-existant non anticipé par le texte du brief :
l'ancien `saveMapConfig` faisait `map: config` (wrap de l'objet entier,
pas d'énumération de champs comme `saveAppConfig`) — le code de
remplacement du brief (énumération explicite) corrige ça de facto, le
reviewer a vérifié la ligne supprimée dans le diff pour confirmer la
caractérisation exacte. `createExport`/`getExportJob` conformes.
Littéraux `ExportFormat`/`ExportJobStatus` exacts, une seule définition.
6 tests nouveaux, suite complète 124 fichiers/1007 tests, tsc+vite build
propres. 1 Minor de couverture noté (`cartouche` jamais testé) — non
bloquant.

Base Task 9: c056bce
Task 9: complete (commit 98e479c, review Approved au premier passage).
`PrintLayoutPanel` composant contrôlé vérifié conforme au patron
`PipelineScheduleEditor` (pas de `useState` interne divergent, chaque
changement passe par un helper `patch()` unique émettant un objet
complet) — reviewer a lu `PipelineScheduleEditor` réel pour confirmer.
Littéraux `pageSize`/`orientation` exacts dans les contrôles UI. Câblage
vérifié dans le flux draft/save existant des deux pages (pas de
mécanisme parallèle). 1 déviation du nom d'helper de test du brief
(`renderEditor(client)` réel vs `renderMapEditorPage({client, pk})`
supposé) vérifiée fidèle, non affaiblissante. 2 Minor plan-mandatés
notés (un titre de test ne correspondant pas exactement à son corps ;
une assertion intermédiaire moins probante qu'elle ne le prétend) — tous
deux hérités du brief lui-même, non bloquants, l'assertion finale du
test reste solide. Suite complète 125 fichiers/1012 tests, tsc+vite
build propres.

Base Task 10: c056bce
Task 10: complete (commits f2b35a8, e4fa46a, 1 round de fix, review
Approved en round 2). Contrat DOM inter-tâches (`data-export-ready` sur
`document.body`, match exact `exportRender=1`, `MapView.onReady` via
`map.once("idle", ...)`) vérifié octet pour octet contre le sélecteur
Playwright déjà livré en Task 6 (`page.wait_for_selector('[data-export-
ready="true"]', ...)`). L'implémenteur a trouvé ET corrigé un vrai bug
du code dicté par le plan lui-même : `MapView` rendait déjà sa propre
`MapLegend` à la même position que l'overlay `showLegend` de l'export —
`showLegend:false` n'aurait jamais masqué la légende préexistante,
`showLegend:true` l'aurait dupliquée — fix via nouvelle prop `hideLegend`
sur `MapView`. 1 Critical trouvé en revue (pas plan-mandaté) : la route
`/maps/:pk` est imbriquée sous `ProtectedLayout`→`AppLayout`, qui rend
toujours son header (branding, bouton "Déconnexion") et sa nav — le
early-return exportRender de `MapEditorPage` ne contrôle que son propre
rendu, jamais `AppLayout` au-dessus dans l'arbre. Chaque export de carte
aurait visiblement montré le chrome applicatif complet + un bouton de
déconnexion. Invisible aux tests existants (`MapEditorPage.test.tsx`
montait la page nue sous un `MemoryRouter`, jamais via le vrai
`AppLayout`/`ProtectedLayout`). `AppRuntimePage` non affecté (sa route
est hors `ProtectedLayout`). Fix (e4fa46a) : `AppLayout` lui-même
consulte `useIsExportRender()` et saute son chrome tout en gardant
`RequireAuth` intact au-dessus (vérifié explicitement compatible avec le
futur contournement d'auth `exportToken` de Task 12). Nouveau test
d'intégration réel dans `routes.test.tsx` (arbre de routes réel, pas de
mock d'`AppLayout`/`RequireAuth`) prouvant l'absence du chrome avec
`exportRender=1` ET sa présence sans — re-revue a tracé l'arbre de
composants réel et confirmé via `git show` que le test aurait échoué sur
le code pré-fix. 127 fichiers/1025 tests, tsc+vite build propres.

Base Task 11: e4fa46a
Task 11: complete (commit bc0f406, review Approved au premier passage).
`ExportPanel` (bouton/dialogue/poll) vérifié conforme aux deux règles de
style non négociables : boucle poll manuelle `async`/`setTimeout` (pas
`useQuery`), miroir structurel confirmé contre `PipelineRunPanel` réel
(lu en entier par le reviewer, pas seulement le diff) ; les deux chemins
d'erreur fetch (échec `createExport` ET échec `getExportJob` en cours de
poll) remontent en `role="alert"`, jamais avalés. Isolation export-render
vérifiée structurelle dans les deux pages (le panneau est dans un arbre
JSX inatteignable pendant la capture). 3 déviations vérifiées exactes :
(1) un vrai bug dans le code d'exemple du brief lui-même (message
d'erreur brut `e.message` qui aurait fait échouer le propre test 3 du
brief) corrigé par un message générique — reviewer a confirmé que c'est
le fix, pas un affaiblissement du test, qui fait passer le test inchangé
du brief ; (2) garde `mountedRef`/nettoyage de timer ajoutée au-delà du
patron `PipelineRunPanel`/`ImportFileButton` réels (aucun des deux n'a de
garde d'unmount) — vérifiée comme un renforcement autonome, pas une
incohérence bloquante ; (3) 2 tests au-delà des 3 du brief (poll
lui-même en échec, unmount en cours de poll) jugés justifiés vu l'accent
du brief sur la correction de la boucle de poll. 5 tests nouveaux, suite
complète 128 fichiers/1030 tests, tsc+vite build propres.

Base Task 12: bc0f406
Task 12: complete (commits 3f5d711, 091e505, 1 round de fix, review
Approved en round 2). Dérogation `exportToken` : bypass `RequireAuth`
vérifié étroitement scopé (présence seule, pas de condition plus large),
frontière de sécurité réelle confirmée entièrement côté cœur (aucune
validation de jeton côté shell). 2 déviations vérifiées : (1)
`getToken` lit `window.location.search` directement (pas
`useSearchParams()`) car `AppShell` rend `<BrowserRouter>` en JSX plutôt
que d'être imbriqué dedans — confirmé par inspection directe, équivalent
fonctionnel car `BrowserRouter` (pas `HashRouter`) partage la même
source History API ; (2) `useAuth.ts` non modifié, vérifié correct (la
logique de cette tâche ne vit ni dans ce fichier ni ailleurs que
`RequireAuth.tsx`/`App.tsx`). 1 Important trouvé en revue : aucune
couverture de test sur `buildExportAwareToken`, le mécanisme littéral
qui décide si un appel API porte le jeton d'export ou le jeton normal —
une inversion accidentelle de priorité (`??`) serait passée inaperçue
partout dans la suite. Fix (091e505) : extraction dans un module pur
`shell/src/auth/exportAwareToken.ts` (nécessaire, pas stylistique —
importer `App.tsx` directement casse sous jsdom via `maplibre-gl`/
`loadConfig`, même contrainte que `App.test.tsx` préexistant) + 2 tests
réels (`window.history.pushState`). Re-revue a diffé la logique extraite
contre l'originale (identique), ET mutation-testé le fix elle-même
(inversion temporaire de l'opérateur `??` → le test échoue exactement
comme prédit, puis restauration) — pas seulement fait confiance au
rapport. 3 Minor non bloquants confirmés inchangés (edge case chaîne
vide, littéral dupliqué, `it` vs `test`). Suite complète 129 fichiers/
1033 tests, tsc+vite build propres.

Base Task 13: 091e505
Task 13: complete (commit cf20c72, review Approved au premier passage).
`app.export` inséré dans le contrat de couches import-linter juste après
`app.alerts` + `app.db -> app.export.models` en ignore_imports ;
`app.export.jobs` ajouté à `import_paths` procrastinate ; Dockerfile
`export-worker` miroir de `core/Dockerfile` + Chromium ; service compose
profil `export` (variables d'env vérifiées correspondre exactement aux
lectures réelles du code par le reviewer). `lint-imports` : 0 violation
(vérifié indépendamment par le reviewer, aucune fuite de couche des
tâches précédentes). `test_jobs.py` non modifié — vérifié correct par
lecture directe (pas d'assertion sur la liste exhaustive, motif déjà
établi pour `app.pipelines.jobs`/`app.alerts.jobs`). Build Docker réel
tenté et réussi (pas seulement `config -q`) — logs concrets avec numéros
d'étape et durées, Chromium/FFmpeg/Chrome Headless Shell téléchargés et
installés, ~44s. Suite complète 1317 passed/137 skipped.

Base Task 14: cf20c72
Task 14: complete (commit 0c9c8d9, review Approved au premier passage).
`export.spec.ts` — dernière tâche du plan. Chaque assertion identifiée
comme zone à risque par le brief (piège documenté CLAUDE.md/SP-16b :
POST prouvé sans vérifier son contenu) tracée par le reviewer jusqu'à un
vrai contrôle de contenu : corps `POST /export` deep-checké
(`{itemId:"77",format:"pdf"}`) contre le vrai contrat `itemClient.ts` ET
contre l'interaction UI réelle ; séquence de poll réaliste (transition
`running`→`done` prouvée par `pollCount>=2`, pas un court-circuit) ;
assertion finale sur le vrai `href` contre le `resultUrl` mocké exact ;
scénario capacité désactivée vérifié retirer le bouton du DOM
(`toHaveCount(0)`), pas juste visuellement caché. Adaptation de fixture
(`/maps/map-1` fictif du brief → `/maps/77` réel via création UI)
vérifiée fidèle à 2 specs sœurs existantes (`map-editor.spec.ts`,
`dataset-export.spec.ts`/`alert-rule.spec.ts`), pas un raccourci
inventé. 2/2 tests nouveaux, suite E2E complète 94/94 (92 préexistants +
2 nouveaux), aucune régression. 2 Minor cosmétiques non bloquants.

## TOUTES LES 14 TÂCHES COMPLÈTES. Passage à la revue finale de branche.

Revue finale de branche (232ff92..0c9c8d9, 19 commits, 61 fichiers, sur
opus) : suites complètes relancées indépendamment par le reviewer (core
1317/137 skipped, lint-imports propre, shell 1033/129 fichiers + tsc
propre, E2E export.spec.ts 2/2). Littéraux vérifiés sans dérive de bout
en bout (statut, format, pageSize/orientation, 4 env vars) — la classe
de bug SP-16b ne s'est pas reproduite. Contrat DOM `data-export-ready`
vérifié octet pour octet. **3 Critical trouvés**, tous des coutures
invisibles à une revue scopée par tâche :
- **C1** (pas plan-mandaté, vrai bug) : le mode export a une hauteur
  DOM nulle — `AppLayout` en mode export ne rend que `{children}` sans
  le conteneur `min-h-screen` qui établissait la hauteur, `MapView`/
  `AppRuntimePage` sont en `h-full` contre une chaîne de parents auto-
  height (`body > div#root`, aucune règle `height:100%` dans
  `index.css`). Mesuré empiriquement dans un vrai Chromium headless :
  0px vs 653px. Toute capture PNG/PDF serait vide. Invisible car jsdom
  n'a pas de moteur de layout et l'E2E ne navigue jamais réellement
  avec `exportRender=1`.
- **C2** (plan-mandaté — Task 3 ne mentionne aucune migration) : aucune
  révision Alembic pour `export_jobs`, la table n'existe jamais sur
  Postgres (SQLite seul dans `init_db`). `POST /export` échouerait en
  prod avec `UndefinedTable`.
- **C3** (plan-mandaté — Task 13 Step 6 ne spécifie que le bloc d'env
  du worker) : `docker-compose.yml` ne donne `CORE_EXPORT_ENABLED` ni
  `CORE_EXPORT_TOKEN_SECRET` au service `core` — routeur jamais monté
  (404) et, même une fois monté, le token d'export ne pourrait jamais
  être décodé côté cœur (401 systématique masquant l'échec).

**8 Important** (I1-I8) : bouton Export invisible sur la plupart des
apps/dashboards (`AppRuntimePage` l'imbrique sous une condition de
feature non liée) ; bucket S3 jamais créé (`ensure_uploads_bucket`
jamais appelé) ; capture app/dashboard possible pendant le chargement
(garde `extensionsRegistered` manquante) ; `printLayout.showScaleBar`/
`showNorthArrow` inertes + `title`/`cartouche` jamais rendus en export
app ; PDF sans `print_background=True` (fonds CSS perdus) ; routes
export absentes de l'OpenAPI régénéré (flag off au moment de la
génération) ; aucun reclaim de job bloqué en "running" + poll shell non
borné ; `VITE_CORE_URL` non documenté/câblé pour le contexte réseau
interne du worker. **9 Minor** notés (bypass RequireAuth plus large que
nécessaire, jeton dans la query string à documenter comme risque
accepté, incohérence de défaut `showLegend`, export capture le config
sauvegardé pas le brouillon, dialogue sans récap printLayout, kinds
non-map/app acceptés en POST sans validation, 404 vs 403 attendu par le
design, `S3_EXPORTS_BUCKET` absent de `.env.example`, Dockerfile copie
des fichiers inutilisés).

**Ready to merge: No** — bloqué sur C1/C2/C3.

**Arbitrage utilisateur obtenu** : corriger les 3 Critical + 8 Important
maintenant, en un seul subagent de fix (pas un fixeur par finding), puis
re-dispatcher la revue finale sur le diff mis à jour.

Fix round 1 (commit d76b953) : les 11 findings traités en un seul
subagent. C1 : `AppLayout.tsx` branche export enveloppe désormais
`{children}` dans `h-screen w-screen`, nouveau test E2E régression
(RED avant/GREEN après vérifiés). C2 : migration Alembic `0021_
export_jobs.py`, upgrade+downgrade vérifiés contre un vrai conteneur
Postgres+PostGIS+pgvector construit depuis le Dockerfile du dépôt. C3 :
`core` reçoit désormais `CORE_EXPORT_ENABLED`/`CORE_EXPORT_TOKEN_SECRET`,
`export-worker` suit la même variable au lieu de `"true"` en dur. I1-I6
corrigés directement (ExportPanel dé-imbriqué de la condition
`interactions`, bucket S3 assuré, garde `extensionsRegistered` ajoutée,
overlay titre/cartouche ajouté à l'export app + checkboxes inertes
retirées de `PrintLayoutPanel`, `print_background=True` ajouté au PDF,
OpenAPI/TS régénérés avec le flag actif). I7 : `reclaim_stuck_jobs`
ajouté (ancre `started_at`, 60min, testé) + poll shell plafonné à 200
tentatives — **déviation assumée** : pas de tâche periodique câblée
pour appeler le reclaim (TODO explicite, arbitrage de portée). I8 :
**déviation assumée** — documentation seule dans `.env.example` plutôt
que câblage compose, car aucune valeur unique de `VITE_CORE_URL` ne
convient à la fois au navigateur host en dev et au Chromium interne du
worker partageant la même image `shell`. Suites complètes : core 1322
passed/137 skipped, shell 129 fichiers/1039 tests, E2E 95/95, tsc+vite
build propres, lint-imports propre.

Re-revue finale (232ff92..d76b953, sur opus) : les 11 findings vérifiés
un par un contre le code réel (pas seulement le rapport) — C1 fermé pour
le chemin carte (mesuré empiriquement dans un vrai Chromium, 0px→720px),
mais le commentaire du fix prétend à tort couvrir aussi le chemin app
(la route `/apps/:pk` est hors `AppLayout`, donc non affectée — pas un
trou fonctionnel, juste une inexactitude de commentaire, notée Minor).
C2/C3/I1-I7 vérifiés fermés avec preuve concrète (migration comparée
colonne par colonne au modèle réel, ordre bucket-avant-upload vérifié
dans le test, etc.). I7 confirmé honnêtement partiel (TODO visible, pas
dissimulé). **I8 confirmé NON fermé** : le reviewer a tracé le mécanisme
`envsubst`/`env-config.js` de bout en bout et prouvé que le service
`shell` du compose ne passe aucune variable d'environnement — la doc
ajoutée ne donne aucun levier réel à l'opérateur, l'export ne peut pas
réussir contre la stack compose par défaut aujourd'hui.

**2 nouveaux Critical trouvés**, introduits par/exposés par le fix round
lui-même, ratés par les deux passes précédentes :
- **Nouveau Critical 1** : le job CI `api-types-drift` échouerait — le
  fix I6 a régénéré `openapi.json` avec `CORE_EXPORT_ENABLED=true`, mais
  l'étape CI régénère sans ce flag (62 routes vs 64 committées) —
  reproduit par le reviewer en rejouant exactement les étapes CI.
  Précédent existant qui pointe dans l'autre sens : `/pipelines` (flag
  `CORE_ETL_ENABLED`) est délibérément absent du spec committé.
- **Nouveau Critical 2** : le job CI `core` échouerait — le test
  `@pytest.mark.playwright` de Task 6 n'a pas de garde de skip et le job
  CI n'installe jamais Chromium ; reproduit empiriquement par le
  reviewer (`PLAYWRIGHT_BROWSERS_PATH` vide → le test ÉCHOUE, ne skip
  pas), contredisant la docstring du marker lui-même ("skippé sinon").

**1 Important confirmé non fermé** : I8 (`VITE_CORE_URL`) — le fix
minimal proposé par le reviewer (transmettre la variable dans le
service `shell` du compose, valeur par défaut inchangée) ne change rien
par défaut mais rend le mécanisme runtime réellement fonctionnel.

7 Minor notés (commentaire C1 imprécis, géométrie d'impression non
dérivée de pageSize/orientation, kind non validé à la création du job,
pas de fail-fast sur secret vide, export-worker sans OTel, reclaim
cross-tenant en Python plutôt qu'en SQL, pas de mise à jour CLAUDE.md).

**Ready to merge: With fixes** (2 nouveaux Critical + 1 Important à
corriger avant la passe finale).

Fix round 2 (commit 15ff461) : Critical 1 (api-types-drift) corrigé via
Option A — `openapi.json`/`core-schema.d.ts` revenus à l'exclusion des
routes `/export`, régénérés sans `CORE_EXPORT_ENABLED`, alignés sur le
précédent `CORE_ETL_ENABLED`/pipelines déjà établi (vérifié :
`itemClient.createPipelineItem` etc. sont eux aussi typés à la main).
Étapes CI rejouées deux fois, `git diff --exit-code` passe. Critical 2
(garde skip Playwright) corrigé — fixture `chromium_available` ajoutée
dans `conftest.py`, miroir de `pg_engine`/`qgis_worker_url`, vérifie
l'existence du binaire Chromium. Vérifié : SKIPPED avec
`PLAYWRIGHT_BROWSERS_PATH` vide, PASSED normalement sinon. Important
(VITE_CORE_URL) corrigé avec un vrai changement de code (pas seulement
de la doc) — variable transmise au service `shell` du compose (défaut
inchangé, no-op par défaut, vérifié). Suites complètes : core
1322/137 skipped, lint-imports propre, shell 1039 tests, tsc+vite build
propres, E2E 95/95.

Re-revue finale round 3 (232ff92..15ff461, sur opus) : les 3 fixes du
round 2 vérifiés fermés avec reproduction indépendante — étapes CI
`api-types-drift` rejouées (spec régénérée byte-identique au committé,
diff purement additif : seul le schéma PrintLayout de Task 1, aucune
route export, aucune régression collatérale), garde `chromium_available`
testée dans les deux sens (SKIPPED avec `PLAYWRIGHT_BROWSERS_PATH` vide,
PASSED sinon, les 5 autres tests du fichier non affectés), mécanisme
`VITE_CORE_URL` tracé jusqu'au bout (bit exécutable de l'entrypoint
vérifié, 3 états d'env testés). **0 nouveau Critical, 1 nouveau
Important** : `SHELL_BASE_URL` avait exactement le même défaut inerte
que celui que ce round venait de corriger pour `VITE_CORE_URL` — en dur
dans `docker-compose.yml` alors que `.env.example` le documente comme
surchargeable. Corrigé directement (pas de subagent, motif trivial déjà
prouvé) : `${SHELL_BASE_URL:-http://shell:8300}`, commit eeaa044,
`docker compose --profile export config` revérifié (valeur par défaut
résolue inchangée). Reste 6 Minor déjà notés en round 2, re-triés par le
round 3 avec preuve supplémentaire (secret vide échoue fermé côté PyJWT,
pas de bypass) — tous non bloquants, à documenter dans CLAUDE.md.

**Ready to merge: With fixes → maintenant Yes** après le fix direct
ci-dessus (motif identique déjà vérifié par la revue round 3, pas de
nouvelle revue jugée nécessaire pour un changement d'une ligne).

CLAUDE.md mis à jour (commit dc1a0b8) : entrée Fait SP-17a détaillée,
ligne SP-17 mise à jour (socle livré, reste ReportSchedule), "impression"
retirée du reste de la vision post-v0.1, Minor différés listés en suivi
non bloquant.

## REVUE FINALE APPROUVÉE (3 rounds, 0 Critical/Important non résolu au
merge). Passage à superpowers:finishing-a-development-branch.
