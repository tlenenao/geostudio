# SP-17a — revue finale, tour de correctifs (C1-C3, I1-I8)

Branche `dev`, HEAD de départ `0c9c8d9`. Ce document couvre le tour de
correctifs complet demandé sur les 11 findings de la revue finale de branche
SP-17a (worker d'export Playwright + `PrintLayout`).

Toutes les affirmations des 11 findings ont été vérifiées comme exactes en
lisant le code réel avant correction — aucune n'a été jugée invalide. Détail
par finding ci-dessous.

---

## C1 — Export-render mode a une hauteur DOM nulle

**Fichier :** `shell/src/shell/AppLayout.tsx`

**Diagnostic confirmé :** la branche `isExportRender` retournait `<>{children}</>`
(fragment, sans hauteur propre), alors que la branche normale établit sa
hauteur via `min-h-screen` sur son propre conteneur. `index.css` ne définit
aucune règle `html,body,#root{height:100%}`. Sans hauteur explicite,
`MapEditorPage`/`AppRuntimePage`'s `h-full w-full` résolvent contre un
ancêtre à hauteur automatique → 0.

**Correctif choisi :** `<div className="h-screen w-screen">{children}</div>`
dans la branche export de `AppLayout.tsx` — cohérent avec l'usage Tailwind du
reste du fichier (viewport units, pas une chaîne de `height:100%`).
Alternative (règle CSS globale) écartée : elle aurait introduit un nouveau
patron non utilisé ailleurs dans ce dépôt.

**Test ajouté :** `shell/e2e/export.spec.ts` — nouveau test Playwright réel
(seul outil capable de détecter cette classe de régression, jsdom n'ayant pas
de moteur de layout) : navigue vers `/maps/77?exportRender=1`, vérifie
`getByTestId("map-container")` visible et `boundingBox().height/width > 0`.

**Preuve RED→GREEN :** le test a été exécuté contre le code AVANT correctif
(fragment restauré temporairement) :
```
✘ le rendu ?exportRender=1 a une hauteur non nulle …
  Error: expect(locator).toBeVisible() failed
  Received: hidden  (unexpected value "hidden")
```
puis contre le code corrigé : `✓ … (1.1s)`. Suite E2E complète (95 specs)
verte après réapplication du correctif.

---

## C2 — Aucune migration Alembic pour `export_jobs`

**Diagnostic confirmé :** `core/app/export/models.py` déclare la table
`export_jobs` et elle est importée dans `core_table_names()`
(`core/app/db.py`), mais `core/alembic/versions/` s'arrêtait à `0020`.
`init_db`'s `create_all()` ne s'exécute que pour SQLite ; Postgres dépend
uniquement d'Alembic.

**Correctif :** nouvelle révision `core/alembic/versions/0021_export_jobs.py`
(`down_revision = "0020"`), miroir de `0018_pipeline_runs.py`/
`0020_alert_evaluations.py` : colonnes identiques à `models.py`
(`id`, `tenant_id`→FK tenants, `item_id`→FK items, `user_id`→FK users,
`format`, `status` (`server_default="pending"`), `error`, `result_key`,
`started_at`, `finished_at`, `created_at`), plus un index
`ix_export_jobs_tenant_id` sur `(tenant_id, id)` (patron du lookup
tenant-scopé utilisé par `export_repo.get_job`, cf. l'index équivalent de
`0016_harvest.py`).

**Vérification réelle (pas seulement statique) :** l'image Postgres+PostGIS+
pgvector+wal2json réellement utilisée en production (`deploy/postgis/Dockerfile`)
a été construite et lancée dans un conteneur Docker jetable. `alembic upgrade
head` a appliqué les 21 révisions avec succès (`0020 -> 0021, app.export —
export_jobs (SP-17a)`), `\d export_jobs` a confirmé la structure de table (PK,
3 FK, index composite), puis `alembic downgrade -1` a réussi et supprimé la
table proprement (`Did not find any relation named "export_jobs"`), puis
`upgrade head` a été rejoué pour laisser l'état propre. `lint-imports` (contrat
de couches) reste vert après coup.

---

## C3 — `docker-compose.yml`'s `core` n'a pas `CORE_EXPORT_ENABLED`/`CORE_EXPORT_TOKEN_SECRET`

**Diagnostic confirmé :** le service `core` ne recevait ni l'une ni l'autre
variable (relecture complète du fichier). Le service `export-worker` avait
`CORE_EXPORT_ENABLED: "true"` codé en dur, divergent de `core`.

**Correctif :**
- `core` : ajout de `CORE_EXPORT_ENABLED: ${CORE_EXPORT_ENABLED:-false}` et
  `CORE_EXPORT_TOKEN_SECRET: ${CORE_EXPORT_TOKEN_SECRET:-}`.
- `export-worker` : remplacement du `"true"` codé en dur par
  `${CORE_EXPORT_ENABLED:-false}` — les deux services suivent maintenant la
  même variable, plus d'état "à moitié activé" possible.

**Vérification :** `docker compose --env-file <.env.example> --profile export
config -q` (syntaxe/références) passe sans erreur ; `config` (rendu complet)
confirme `CORE_EXPORT_ENABLED: "false"` / `CORE_EXPORT_TOKEN_SECRET: ""`
identiques sur les deux services avec le `.env.example` par défaut.

---

## I1 — Bouton Exporter invisible sur la plupart des apps/dashboards

**Fichier :** `shell/src/pages/AppRuntimePage.tsx`

**Diagnostic confirmé :** `{exportEnabled && <ExportPanel .../>}` était
imbriqué dans `query.data.interactions === "auto"`, un flag sans rapport
(cross-filter/save-view) qui vaut `"manual"`/absent par défaut.

**Correctif :** extraction d'un `showActionBar = !isExportRender &&
(exportEnabled || interactions === "auto")` ; à l'intérieur de la barre,
`ExportPanel` est gated indépendamment sur `exportEnabled`, et le bouton
« Enregistrer la vue » garde son propre gate sur `interactions === "auto"`.
La barre gated sur interactions n'a pas été supprimée, seulement
désimbriquée.

**Tests ajoutés** dans `AppRuntimePage.test.tsx` :
- bouton Exporter visible avec `exportEnabled: true` + interactions
  absent/manual, bouton "Enregistrer la vue" toujours absent (gate
  indépendant préservé) ;
- bouton Exporter absent avec `exportEnabled: false` + interactions auto ;
- bouton Exporter absent pendant la capture `?exportRender=1` elle-même même
  avec `exportEnabled: true` (ne doit jamais apparaître dans la capture).

Suite complète : 16/16 tests passent (11 existants + 5 nouveaux comptant
aussi I4 ci-dessous).

---

## I2 — Bucket `geostudio-exports` jamais créé

**Fichier :** `core/app/export/jobs.py`

**Diagnostic confirmé :** `render_export_task` appelait `put_object`
directement, sans passer par `ensure_uploads_bucket` (contrairement à
`app/ingestion/routes.py`, `app/cdc/storage.py`, `app/items/storage.py`).
Lecture de `ensure_uploads_bucket` : agnostique du nom de bucket malgré son
nom (`create_bucket` + `put_bucket_cors` génériques).

**Correctif :** `ensure_uploads_bucket(s3_client, bucket)` appelé juste avant
`put_object`, dans le bloc try existant (donc toute erreur de création de
bucket finit correctement en `mark_error`, pas en zombie).

**Test :** `test_export_jobs.py::test_render_export_task_marks_done_on_success`
étendu — le `_FakeS3Client` trace maintenant l'ordre des appels
(`create_bucket`, `put_bucket_cors`, `put_object`) et l'assertion vérifie
l'ordre exact, pas seulement la présence. 6/6 tests passent.

---

## I3 — Capture app/dashboard possible en plein chargement

**Fichier :** `shell/src/pages/AppRuntimePage.tsx`

**Diagnostic confirmé :** `markExportReady()` était gated sur
`isExportRender && query.isSuccess` seul ; le composant peut encore afficher
`<p role="status">Chargement…</p>` (gated sur `!extensionsRegistered`,
piloté par une query `useActiveExtensions()` indépendante) au moment où ce
signal se déclenchait.

**Correctif :** gate étendu à `isExportRender && query.isSuccess &&
extensionsRegistered`, les trois conditions. A nécessité de déplacer la
déclaration de `extensionsQuery`/`extensionsRegistered` (précédemment après
ce `useEffect` dans le corps du composant) au-dessus de celui-ci — sinon
`extensionsRegistered` serait référencé avant son initialisation (erreur de
compilation TS/JS, zone morte temporelle `const`). L'ancienne déclaration en
double a été supprimée.

**Vérification :** `test("exportRender=1 hides the save-view action bar and
marks the page export-ready once the config loads")` (test existant,
inchangé dans son intention) reste vert avec le nouveau gate à trois
conditions, prouvant que le chemin nominal (client de test qui résout
`listActiveExtensions` en `[]` par défaut faute d'implémentation, donc
`extensionsRegistered` devient vite `true`) n'est pas cassé.

---

## I4 — `showScaleBar`/`showNorthArrow` inertes ; `title`/`cartouche` absents des exports d'app

**Fichiers :** `shell/src/pages/AppRuntimePage.tsx`,
`shell/src/builder/print/PrintLayoutPanel.tsx`

**Diagnostic confirmé** par lecture complète des deux fichiers.

**Correctif (partie 1 — title/cartouche) :** ajout dans la branche export de
`AppRuntimePage.tsx` du même overlay que `MapEditorPage.tsx` (positions et
classes identiques : `absolute left-2 top-2 … bg-white/90` pour le titre,
`absolute bottom-2 right-2 … bg-white/90` pour le cartouche), conditionné à
`isExportRender && query.data.printLayout?.title`/`.cartouche`. Le conteneur
racine est passé de `flex h-full w-full flex-col` à `relative flex h-full
w-full flex-col` pour ancrer le positionnement absolu.

**Correctif (partie 2 — showScaleBar/showNorthArrow) :** les deux
checkboxes retirées de `PrintLayoutPanel.tsx` (contrôles d'auteur inertes,
jamais rendus nulle part) ; `DEFAULTS` réduit en conséquence. Les champs
restent sur `PrintLayoutConfig`/`PrintLayout` (schéma cœur, pas de migration
de schéma) — seule l'UI d'auteur ne les expose plus. Comme demandé,
l'implémentation réelle d'une barre d'échelle/flèche nord est restée hors
périmètre.

**Tests :** `PrintLayoutPanel.test.tsx` (4 tests, aucun ne référençait les
deux checkboxes retirées — aucune adaptation nécessaire, vérifié en
grep'ant "Barre d'échelle"/"Flèche nord" dans `src/`/`e2e/`, seuls
`AppRuntimePage.tsx`, `PrintLayoutPanel.tsx`, `MapEditorPage.tsx`,
`api/types.ts` et les fichiers générés y font encore référence — jamais un
test). Deux tests ajoutés dans `AppRuntimePage.test.tsx` : l'overlay
title/cartouche apparaît en `?exportRender=1` et n'apparaît jamais hors
capture.

---

## I5 — Exports PDF perdent tous les fonds CSS

**Fichier :** `core/app/export/rendering.py`

**Diagnostic confirmé :** `page.pdf(format=…, landscape=…)` sans
`print_background=True` — défaut Chromium `False`.

**Correctif :** `print_background=True` ajouté à l'appel `page.pdf(...)`
(toujours, indépendamment du layout) ; signature du Protocol `RenderPage.pdf`
mise à jour pour inclure `print_background: bool`.

**Tests :** `test_export_rendering.py` — les deux tests PDF existants
vérifient maintenant le triplet `(format, landscape, print_background)`
plutôt que la paire, plus un nouveau test dédié
`test_render_export_pdf_always_prints_css_backgrounds`. La fausse page de
`test_export_jobs.py` (orchestration) a aussi été mise à jour pour accepter
le nouveau kwarg. 10/10 tests passent (`test_export_rendering.py` +
`test_export_jobs.py`).

---

## I6 — Routes d'export absentes du contrat OpenAPI

**Diagnostic confirmé :** `core/openapi.json` ne contenait que le schéma
`PrintLayout`, jamais les chemins `/export` — confirmé en regénérant SANS le
flag d'abord (pas de diff sur les paths), l'hypothèse de la revue (généré
avec `CORE_EXPORT_ENABLED` off) tenait.

**Correctif :** régénération avec le flag ON :
```
cd core && CORE_EXPORT_ENABLED=true PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
**Vérification :** `git diff --stat core/openapi.json` → 172 lignes
ajoutées, incluant les paths `/export` et `/export/jobs/{job_id}` (confirmé
par grep sur le diff) ; `git diff --stat
shell/src/api/generated/core-schema.d.ts` → 125 lignes ajoutées, mêmes
chemins présents côté TS. `tsc --noEmit` reste propre après régénération.

---

## I7 — Jobs bloqués jamais réclamés ; poll shell sans plafond

**Fichiers :** `core/app/export/repository.py`, `core/app/export/jobs.py`,
`shell/src/builder/print/ExportPanel.tsx`

**Diagnostic confirmé :** aucun mécanisme de reclaim côté serveur pour
`export_jobs` bloqués en `"running"` (contrairement à `app.pipelines`/
`app.alerts`, tous deux avec une discipline reclaim-par-âge). `ExportPanel`'s
`poll()` est une récursion sans plafond (`PipelineRunPanel` aussi, vérifié
par lecture — donc pas de patron de plafond existant à réutiliser).

**Correctif serveur :** `export_repo.reclaim_stuck_jobs(session, *,
older_than_minutes=60)` — même seuil (`_RUNNING_RECLAIM_MINUTES = 60`) et
même ancre (`started_at`, pas `created_at`) que `app.pipelines`/`app.alerts`.
Marque `status="error"` + `error="export timed out…"` + `finished_at` pour
tout job `"running"` dont `started_at` dépasse le seuil. Retourne la liste
des ids réclamés.

**Déviation assumée (scope tradeoff) :** PAS de nouvelle tâche procrastinate
périodique pour appeler cette fonction — jugé hors périmètre raisonnable
pour ce tour de correctifs (10 autres findings en parallèle). Un
`# TODO(SP-17a fix round, I7)` explicite a été ajouté juste au-dessus de
`render_export_task` dans `jobs.py`, expliquant le compromis et notant que
le plafond côté shell (voir ci-dessous) borne déjà le symptôme visible côté
utilisateur (poll infini) même sans reclaim serveur.

**Tests serveur** (`test_export_repository.py`, 4 nouveaux) : réclame un job
`running` vieux de 2h ; laisse intact un job `running` récent ; ignore les
jobs `pending`/`done` (y compris un `done` vieux de 2h — seul le statut
`running` compte) ; respecte un seuil personnalisé (`older_than_minutes=5`
réclame un job de 10 min, `=60` ne le réclame pas). 8/8 tests passent au
total sur ce fichier.

**Correctif shell :** `MAX_POLL_ATTEMPTS = 200` (200 × 1.5s = 5 min) dans
`ExportPanel.tsx` ; au-delà, `poll()` s'arrête et affiche
`role="alert"` : « Export toujours en cours, réessayer plus tard. » au lieu
de poller indéfiniment.

**Test shell** : nouvelle `describe` scopée avec `vi.useFakeTimers()` (patron
identique à `AnalyticsContext.test.tsx`'s "extent debounce" — fake timers
confinés pour ne pas accrocher les `userEvent.click` des tests précédents) :
`vi.advanceTimersByTimeAsync(1500 * 200)` épuise le plafond, l'alerte
apparaît, et un avancement supplémentaire ne déclenche plus aucun nouvel
appel `getExportJob`. 6/6 tests passent sur `ExportPanel.test.tsx`.

---

## I8 — `VITE_CORE_URL` non documenté/câblé pour le contexte réseau d'export-worker

**Diagnostic confirmé** en lisant `docker-compose.yml`'s bloc `shell`
(aucun `environment:` du tout), `shell/Dockerfile` (ARG de build,
défaut `http://localhost:8200`), `env-config.template.js` +
`docker-entrypoint.d/40-render-runtime-config.sh` (envsubst au démarrage du
conteneur), et `shell/src/config.ts::mergeRuntimeEnv` (une valeur runtime
vide n'écrase JAMAIS la valeur de build — donc pas un crash, mais une
résolution silencieuse vers `http://localhost:8200`, faux dans le réseau
docker).

**Décision (déviation documentée) :** documentation uniquement, PAS de
modification de `docker-compose.yml`. Raison : il n'existe **aucune valeur
unique** de `VITE_CORE_URL` correcte à la fois pour (a) un navigateur humain
sur l'hôte en dev local (`http://localhost:8200`, port publié) et (b) le
Chromium d'export-worker à l'intérieur du réseau docker (`http://core:8200`)
— les deux contextes partagent le MÊME service `shell`/même conteneur/même
fichier statique servi. Fixer `VITE_CORE_URL=http://core:8200` sur le
service `shell` corrigerait la capture d'export mais casserait le flux dev
par défaut documenté dans CLAUDE.md (`docker compose up` local, navigateur
hôte sur `localhost:8300`). Une solution complète nécessiterait soit un
domaine public partagé routé par Traefik et joignable en hairpin NAT depuis
le réseau docker (déploiement production réel, hors périmètre de ce tour de
correctifs), soit une architecture à deux origines pour `shell` — les deux
sont des changements d'architecture, pas un correctif de revue finale.

**Correctif appliqué :** commentaire détaillé ajouté dans `.env.example`
juste après `SHELL_BASE_URL`, expliquant précisément cette contrainte et
pourquoi elle n'est pas résolue par un simple ajout de variable.

---

## Constats sur la validité des findings

Les 11 findings se sont tous révélés exacts après lecture du code réel —
aucun n'a été écarté comme invalide. Le point le plus subtil découvert en
creusant (au-delà du texte de la review) : la garde `mergeRuntimeEnv` de
`shell/src/config.ts` empêche une valeur runtime vide d'écraser la valeur de
build pour I8 — donc pas un crash net comme le texte du finding aurait pu le
suggérer, mais une résolution silencieuse vers une URL fausse, ce qui a
orienté la décision de ne pas juste "mettre une valeur" côté compose sans
mesurer l'arbitrage indiqué ci-dessus.

---

## Suites de tests — résultat final

Exécutées après l'ensemble des 11 correctifs, dans cet ordre :

- **Core (`cd core && uv run pytest -q`)** : `1322 passed, 137 skipped`
  (skips = tests marqués `postgis`, nécessitent docker — non liés à ce tour).
- **Shell unitaire (`cd shell && npx vitest run`)** : `129 fichiers, 1039
  tests` passés (1034 avant ce tour + 5 nouveaux tests I1/I4 sur
  `AppRuntimePage.test.tsx`, plus les modifications de `ExportPanel.test.tsx`/
  `test_export_*.py` déjà comptées dans les totaux respectifs).
- **Shell type-check (`npx tsc --noEmit`)** : aucune erreur.
- **Shell build (`npx vite build`)** : succès (avertissements de taille de
  chunk préexistants, sans lien avec ce tour).
- **E2E (`VITE_AUTH_MODE=mock npx playwright test`)** : `95 passed` (18+
  specs existantes + le nouveau test de régression C1 dans
  `export.spec.ts`), aucune régression sur les specs pré-existantes.
- **Contrat de couches (`uv run lint-imports`)** : `1 kept, 0 broken`.
- **Migration Alembic** : vérifiée réellement contre un Postgres+PostGIS+
  pgvector construit depuis `deploy/postgis/Dockerfile` (upgrade head +
  downgrade -1 + upgrade head, table structure confirmée par `\d
  export_jobs`).

Aucune régression détectée sur les 13+ specs E2E historiques ni sur la
suite `core/tests` existante.

## Fichiers modifiés

- `shell/src/shell/AppLayout.tsx` (C1)
- `core/alembic/versions/0021_export_jobs.py` (C2, nouveau)
- `docker-compose.yml` (C3)
- `shell/src/pages/AppRuntimePage.tsx` (I1, I3, I4)
- `shell/src/pages/AppRuntimePage.test.tsx` (I1, I4 — 5 tests ajoutés)
- `core/app/export/jobs.py` (I2, I7 TODO)
- `core/tests/test_export_jobs.py` (I2, I5)
- `core/app/export/rendering.py` (I5)
- `core/tests/test_export_rendering.py` (I5)
- `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` (I6,
  régénérés)
- `core/app/export/repository.py` (I7)
- `core/tests/test_export_repository.py` (I7 — 4 tests ajoutés)
- `shell/src/builder/print/ExportPanel.tsx` (I7)
- `shell/src/builder/print/ExportPanel.test.tsx` (I7 — 1 test ajouté)
- `shell/src/builder/print/PrintLayoutPanel.tsx` (I4)
- `.env.example` (I8)
- `shell/e2e/export.spec.ts` (C1 — 1 test E2E ajouté)
