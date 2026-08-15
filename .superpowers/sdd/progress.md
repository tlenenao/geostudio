# SP-18c — Export d'apps : mode Autoporté — Progress Ledger

Plan: docs/superpowers/plans/2026-08-15-sp18c-export-mode-autoporte.md
Spec: docs/superpowers/specs/2026-08-15-sp18c-export-mode-autoporte-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note d'incident (Task 5)

Le subagent de fix de Task 5 a fait un `git add` large (probablement
`-A`/`.`) au lieu de cibler les fichiers modifiés, embarquant par
accident toutes les éditions concurrentes du ledger/scratch
(`progress.md`, `task-1..5-brief/report.md`) que le contrôleur était en
train de faire au même moment — un diff de 163 Ko au lieu de ~11 Ko.
Détecté à la génération du review-package (taille suspecte), corrigé par
`git reset --soft HEAD~1` puis re-commit ciblé (`6d2f352`, seulement
`items.py`+test) avant de dispatcher la re-revue. Aucune conséquence sur
le code ; à surveiller pour les prochains dispatches de fix (préciser
explicitement dans le prompt de scinder l'add).

## Note de reprise

Le `progress.md` trouvé au démarrage de cette session appartenait à SP-18b
(mode Connecté) — 9/9 tâches complètes, 0 Critical/Important non résolu,
mais jamais figé dans une sauvegarde `docs(sp18b): session ledger …` comme
les SP précédents (sp18a/sp16b/sp17a/sp17b/tileset3d) — 7e occurrence
documentée de cet oubli. Sauvegardé cette fois-ci avant d'écraser (commit
0db7ebb, `docs(sp18b): session ledger, task briefs/reports`) — attention :
un premier essai avec `git add -f .superpowers/sdd/` (répertoire entier)
a accidentellement mis en index ~850 fichiers scratch non trackés
(review-*.diff, fix-*-report.md de sessions bien antérieures) à cause du
`.gitignore` sur `.superpowers/` — annulé par `git reset --soft HEAD~1`
puis `git reset .superpowers/sdd/` avant de ne re-stager que les 16
fichiers réellement modifiés (avec `-f` par fichier, requis même pour des
fichiers déjà trackés sous ce `.gitignore`). Aucune conséquence durable,
mais à noter pour la prochaine session : ne jamais `git add -f` un
répertoire entier gitignoré, toujours lister les fichiers explicitement.

## Pre-flight plan review

Lu intégralement (14 tâches, code complet à chaque étape). Aucune
contradiction interne ni avec les Global Constraints. Signatures/contenus
réels vérifiés verbatim avant dispatch, aucune dérive trouvée :
`check_export_guard`/`guard.py` (mode="static"/"connected" existants
inchangés), `duckdb_conn.py` (open_connection/open_spatial_connection
existants), `bundler.py`/`jobs.py` (contenu pré-Task-7/8 exact),
`routes.py`'s `_SUPPORTED_MODES`, `app.collections.introspection`
(TableInfo/ColumnInfo, champs par défaut compatibles avec les tests),
`app.features.repository.select_features`/`app.features.rls.rls_scope`,
`app.collections.schema_json.table_info_to_schema`,
`app.analytics.aggregate` (AggregateRequestBody/UnknownAggregateField/
run_collection_aggregate/_dedup_cte — confirmé que des lignes toutes
`_lsn=0`/`op="insert"` avec pk uniques dédupliquent correctement, aucun
souci de correction avec le motif "instantané = un seul lot CDC
d'insertions"), `app.collections.repository.get_collection`/
`get_access_facts`, `core/pyproject.toml` markers, `tests/conftest.py`'s
`pg_engine`, shell `types.ts`'s `AppExportMode`,
`AppExportPanel.tsx`'s ligne de boutons. Le plan est exact, aucun écart.

Environnement de test préparé avant dispatch : conteneur `ci-postgres`
(image `geostudio-postgis-ci:latest`, build local depuis
`deploy/postgis`, `wal_level=logical`) démarré sur le port 5432 — miroir
exact de `.github/workflows/ci.yml`'s job `core` — pour que les tests
`@pytest.mark.postgis` (Tasks 4, 12) tournent réellement, pas seulement en
skip. `docker` confirmé disponible pour Task 12 (`@pytest.mark.docker`,
nouveau marker à enregistrer). `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test`
à passer à chaque `uv run pytest` de cette session.

## Tâches

Task 1: complete (commit f4c5508, review clean — 0 Critical/Important, 2
Minor cosmétiques). `check_export_guard` gagne `mode="standalone"` :
retombe dans la branche générale `is_public` pour `statistics` (même
levée de restriction que "connected"), et `_STRICT_WIDGET_MODES =
{"static", "standalone"}` applique l'allowlist de widgets builtin-only
(même restriction que "static"). 17 tests (le brief prédisait 18, simple
erreur de comptage du brief lui-même, pas un écart réel — 12 existants +
5 nouveaux). Reviewer a noté que seul 1 des 5 nouveaux tests échouait
réellement avant l'implémentation (le fallthrough `mode == "static"`
donnait déjà par accident la levée is_public à "standalone") — conforme
à la mise en garde du brief lui-même, pas une entorse TDD.
Task 2: complete (commit 4f75c88, review clean — 0 Critical/Important, 1
Minor plan-mandated). `open_local_connection()` ajouté à
`duckdb_conn.py` : charge uniquement `spatial` (aucun `httpfs`/`h3`/
`s3_*`), vérifié par un test exécutant réellement contre un vrai moteur
DuckDB (`_RecordingConnection` forward vers une connexion in-memory
réelle, pas un mock creux) les assertions positives ET négatives. 5
tests (le brief prédisait 6, simple erreur de comptage du brief — 4
existants + 1 nouveau, pas un écart réel). Minor noté par le reviewer :
corps identique à `open_spatial_connection()` (deux lignes, seul le
docstring diffère) — mandaté verbatim par le brief, pas un défaut de
l'implémenteur, non bloquant.
Task 3: complete (commit 7ecc571, review clean — 0 Critical/Important, 3
Minor cosmétiques). Nouveau module `app.appexport.manifest` :
`CollectionSnapshotEntry`/`write_manifest`/`read_manifest`, réutilise
`TableInfo`/`ColumnInfo` de `app.collections.introspection` tels quels
(vérifié octet-pour-octet inchangé par le reviewer). `write_manifest`
sérialise `ColumnInfo` via `asdict()` complet (couvre aussi
`max_length`/`enum_values`, non exercés par les tests du brief mais
transparents au round-trip) — plus robuste que littéralement spécifié.
2 tests, round-trip réel sur fichier (pas de mock). Minors notés
(casing JSON incohérent camelCase/snake_case, pas de version de
manifeste, erreurs non contextualisées sur JSON malformé) tous
mandatés verbatim par le brief lui-même ou hors périmètre de cette
tâche, non bloquants.
Task 4: complete (commit 5009aaf, review clean — 0 Critical/Important, 2
Minor hérités du brief). `write_snapshot` (nouveau module
`app.appexport.snapshot`) : même patron in-process que `freeze.py`
(introspect_table + select_features sous rls_scope), écrit chaque
collection référencée comme partition GeoParquet hive-partitionnée
(tenant_id=/collection_id=/dt=snapshot/) au format CDC (`ChangeRow`
op="insert"/lsn=0) via `write_geoparquet` existant. 4 tests
`@pytest.mark.postgis` **exécutés réellement** contre le conteneur
Postgres (confirmé par le rapport : `ModuleNotFoundError` réel avant
implémentation → `4 passed` réel après → `4 skipped` réel avec
`CORE_TEST_DATABASE_URL` retiré, écartant un faux positif). Risque
nommé explicitement au reviewer (précédent RLS de `freeze.py` en
SP-18a) : `rls_scope` confirmé correctement enveloppant toute la
pagination de lecture (`snapshot.py:67`), vérifié par lecture directe
de `app/features/rls.py`/`app/features/repository.py` — aucun bug
d'isolation trouvé. Zéro ligne → aucun fichier parquet mais entrée
manifeste `featureCount:0` conservée ; même collection référencée deux
fois → écrite une seule fois ; cap `max_records_per_source=50_000`
réutilisé tel quel. Minors hérités verbatim du brief (aucun test avec
géométrie réelle, aucun test cross-tenant explicite — mêmes lacunes que
le précédent `test_appexport_freeze.py`, pas une régression de cette
tâche), non bloquants.
Task 5: complete (commits 271fbfe + fix 6d2f352, review clean après fix
— 0 Critical/Important). `app.appexport.miniserver.items` (nouveau
module) : `FeaturePage`/`select_features`/`get_feature`, mirroir de
`app.features.repository` mais via SQL DuckDB contre un instantané
GeoParquet local. Identifiants (colonnes/table) toujours issus de
`TableInfo` (jamais de l'entrée utilisateur) et quotés via `_qi()` ;
valeurs risquées nommées au reviewer (`fid`, `bbox`, `geom_intersects`)
passées en paramètres liés `?` — aucune injection SQL trouvée ;
`tenant_id`/`collection_id`/`base_uri` interpolés en littéral SQL
échappé (`_sql_lit`) plutôt qu'en paramètre lié, mais reconnu conforme
au précédent déjà établi (`app/analytics/aggregate.py`), Minor non
bloquant. **1 Important trouvé et corrigé** : `_build_where` déréférençait
`table_info.geometry_column` sans garde quand `bbox`/`geom_intersects`
était fourni sur une collection non spatiale → `AttributeError` non
catché, atteignable depuis la future route Task 6 sur un endpoint
anonyme. Fixé par un garde-fou unique (`MissingGeometryColumn`, levé
avant tout `_qi(None)`) — même patron que `app.features.repository`'s
`FilterError` sur bbox. 7 tests (5+2), guard vérifié réellement atteint
via `select_features()` (pas testé en isolation sur `_build_where`).
Note laissée pour Task 6 : un appel spatial sur une collection sans
fichier parquet du tout retourne une page vide silencieusement (le
garde n'est jamais atteint) — comportement pré-existant, pas changé par
ce fix, mais à garder en tête côté route.
Task 6: complete (commit d7f8f48, review clean — 0 Critical/Important, 2
Minor). `app.appexport.miniserver.main` : mini-serveur FastAPI générique
(GET connection/config/collections[...]+items[...], POST aggregate,
mount statique en dernier). Confirmé réellement read-only (aucune route
d'écriture, `items.py` n'expose aucune fonction d'écriture), aucun CORS
(même origine que le shell servi), `DATA_DIR`/`RUNTIME_DIR` bien lus une
seule fois à l'import (constantes module-level, jamais relues dans un
handler). **Déviation approuvée par le contrôleur avant dispatch** (pas
une violation du plan — le brief a été rédigé avant que
`MissingGeometryColumn` (fix Task 5) n'existe) : `list_items` attrape
désormais cette exception et renvoie 400 au lieu de laisser propager un
500 nu — vérifié réellement câblé (try/finally connexion préservé) et
prouvé par un test réel via `TestClient`. Route `aggregate` n'a besoin
d'aucun ajout équivalent : elle a déjà sa propre garde via
`UnknownAggregateField` (module différent, même effet). 13 tests + 14
tests de dépendances (Tasks 2/3/5) sans régression. Minors : duplication
verbatim du patron try/finally sur 3 routes (mandaté par le brief), pas
de 400 sur un bbox malformé (silencieusement ignoré) — non bloquants.
Task 7: complete (commits c38f3c8 + fix 150ca28, review clean après fix
— 0 Critical/Important). `build_standalone_bundle_zip` ajouté à
`bundler.py` (fonction sœur de `build_bundle_zip`, inchangée). Tag
`:latest` non pinné confirmé verbatim, compose `./data:/data:ro` +
README « strictement lecture seule » vérifiés. **1 Important trouvé et
corrigé** : `os.walk(snapshot_dir)` sur un répertoire inexistant ne
levait rien (zip "réussi" mais incomplet, aucun signal d'erreur) — même
lacune que le brief lui-même, pas une déviation de l'implémenteur.
Fixé par un garde-fou en tête de fonction (`FileNotFoundError`, miroir
exact du précédent déjà établi une fonction plus haut dans le même
fichier pour `runtime_dir` manquant), vérifié ne rien changer au cas
légitime "répertoire existant sans sous-dossier snapshot/" (app sans
DataSources). 7 tests, nouveau test prouvant une vraie absence de
répertoire (jamais `mkdir()`é).
Task 8: complete (commit 1c13c7e, review clean — 0 Critical/Important, 2
Minor). `jobs.py` remplacé intégralement : `_build_zip_bytes` route
`mode="standalone"` vers `write_snapshot` (Task 4) + `build_
standalone_bundle_zip` (Task 7) dans un `tempfile.TemporaryDirectory()`
— vérifié : les deux appels se font bien à l'intérieur du bloc `with`
(le répertoire existe toujours, le garde-fou `FileNotFoundError` de
Task 7 ne peut pas se déclencher ici). Invariant "erreur → job 'error',
jamais 'running' zombie" confirmé préservé pour les trois modes (le
`try/except Exception` englobant enveloppe toujours `_build_zip_bytes`).
`_prepare_bundle_inputs` (static/connected) inchangé. 7 tests jobs +
28 tests de dépendances (Tasks 1/4/7, Postgres réel) sans régression.
Minors : la session DB reste ouverte un peu plus longtemps pour
static/connected aussi (effet de bord du refactor, aucune écriture dans
ce bloc donc aucun risque réel) ; couverture standalone limitée aux cas
"pas de source"/"garde rejette" spécifiés par le brief (la correction de
`write_snapshot` lui-même reste couverte par Task 4) — tous deux
mandatés par le brief, non bloquants.
Task 9: complete (commit 9bda1c8, review clean — 0 issues). `_SUPPORTED_
MODES` élargi à `{"static", "connected", "standalone"}` dans
`routes.py`, changement d'une ligne + 1 test miroir de son équivalent
"connected". Aucune dérive.
Task 10: complete (commit 913e906, review clean — 0 issues).
`deploy/appexport-standalone/Dockerfile` : build multi-stage réel
(Node → shell export runtime, Python → mini-serveur), vérifié construit
pour de vrai (`docker build` complet, image 482MB confirmée via `docker
images`, pas un stub). Reviewer a tracé le graphe d'imports transitif
réel du mini-serveur (`main.py`→`items.py`→`manifest.py`→
`introspection.py`) et confirmé la liste pip (fastapi/uvicorn/pydantic/
duckdb/sqlalchemy) exactement suffisante, aucune dépendance en trop
(pas de psycopg/dlt/Playwright). Seule l'extension DuckDB `spatial`
installée (pas `httpfs`/`h3`, cohérent avec `open_local_connection`).
`index.export.html`→`index.html` renommé (StaticFiles sert index.html).
`ENV APPEXPORT_STANDALONE_DATA_DIR`/`RUNTIME_DIR` vérifiés correspondre
exactement aux valeurs lues par `main.py`. Aucune donnée propre à un
export copiée dans l'image (seul `/data` monté au runtime).
Task 11: complete (commit c496bba, review clean — 0 issues).
`release.yml` : 4e entrée de matrice (`geostudio-appexport-standalone`,
context `.`, dockerfile `deploy/appexport-standalone/Dockerfile`) +
`file:` explicite ajouté à `docker/build-push-action` pour les 4
entrées. Math de résolution de chemin vérifiée pour les 4 (les 3
existantes restent des no-op strict, cohérent avec leur défaut implicite
d'avant). 7 lignes, aucun autre contenu touché. Aucun tag `v*.*.*`
jamais poussé sur ce dépôt — seul le parse YAML est vérifiable ici, gap
documenté et assumé (même nature que le précédent SP-15d/qgis).
Task 12: complete (commit 1dda9c0, review clean — 0 Critical/Important,
2 Minor). Preuve E2E réelle et non mockée : build Docker local (jamais
un pull, tag `:e2e-test`), conteneur à froid (bind mount frais depuis un
vrai `write_snapshot`/`build_standalone_bundle_zip` sur une vraie
collection Postgres), round-trip HTTP réel (config JSON, `/items`,
`/aggregate`, `/`), teardown garanti par `try/finally`. **Les deux
directions de skip vérifiées pour de vrai** (pas seulement documentées
best-effort, conformément à l'exigence explicite du plan/précédent
SP-17a Task 6) : sans `CORE_TEST_DATABASE_URL` → SKIPPED réel ; `docker`
rendu introuvable via une édition chirurgicale de PATH (vérifiée par une
sonde `shutil.which` directe, `sudo mv` indisponible dans ce sandbox) →
SKIPPED réel mentionnant docker. Suite complète 1711 passed/5 skipped,
`lint-imports` clean. Un test flaky préexistant sans rapport
(`test_report_repository.py`, dépendant de l'heure) investigué et
confirmé indépendant du diff par le reviewer lui-même (ré-exécuté hors
de la fenêtre de bord cron, passe) — pas une esquive, code source de la
mécanique cron lue et confirmée. Reviewer a aussi vérifié tous les
signatures de production référencées (write_snapshot, create_collection,
insert_feature, etc.) contre le code réel. Minors : TOCTOU négligeable
sur le port éphémère (pattern préexistant), le build Docker de ce run a
bénéficié du cache de Task 10 (pas un build from-scratch, n'invalide pas
la contrainte "jamais de pull") — non bloquants.
Task 13: complete (commit 9ef1037, review clean — 0 issues).
`AppExportMode` élargi à `"static" | "connected" | "standalone"` dans
`types.ts`, une ligne. `tsc --noEmit` propre. Aucune dérive.
Task 14: complete (commit 1a27847, review clean — 0 issues). Bouton
« Autoporté » ajouté à `AppExportPanel` (3e bouton, `onChooseMode("standalone")`),
réutilisant tel quel le mécanisme `pendingWarningMode` déjà généralisé en
SP-18b Task 8. 3 lignes composant + 16 lignes test. 1 nouveau test + 4
existants (5/5), suite complète shell 1188/1188, `tsc --noEmit` propre.
Aucune dérive. **SP-18c fonctionnellement complet (14/14 tâches).**

## Revue finale de branche (round 1)

Diff `0db7ebb..HEAD` (16 commits, 14 tâches + 2 fix de revue de tâche
Task 5/Task 7), hors `.superpowers/`. Vérifié les 9 classes de bugs
récurrentes de l'historique du dépôt (câblage docker-compose inerte,
base path/assets relatifs du bundle, garde de widgets sur layout
top-level, isolation RLS/tenant, gestion d'erreur/jobs zombie, câblage
CI, audit_log, DoS/ressources non bornées, construction de chemin/SQL
sur route dynamique) contre le code réel (pas seulement contre le texte
du plan) : **0 Critical, 0 Important**. Notamment vérifié octet pour
octet que `deploy/appexport-standalone/Dockerfile`'s `ENV
APPEXPORT_STANDALONE_DATA_DIR`/`RUNTIME_DIR` correspondent aux défauts
lus par `miniserver/main.py` et au montage `./data:/data:ro` généré par
`bundler.py` ; que le stage Node du Dockerfile réutilise
`build:export-runtime` donc hérite du fix `base: "./"` de SP-18a (C1) ;
que `write_snapshot` ne mélange jamais tenant/collection (aucun
paramètre de requête n'atteint le chemin GeoParquet, toujours dérivé du
manifeste serveur) ; que `max_records_per_source` et le plafond
`limit=1000` de `list_items` sont réellement appliqués (pas seulement
déclarés). Point FYI (pas un bug) : `test_appexport_standalone_e2e.py`
est le premier test `@pytest.mark.docker` du dépôt — tourne réellement
en CI (job `core`, Docker déjà disponible pour Postgres), ajoute
quelques minutes de CI (build Docker complet dans le test) mais aucune
dépendance manquante. Rappel non nouveau : `write_snapshot` ignore
`DataSource.query` comme `freeze_config` (SP-18a) — déjà suivi en non
bloquant, s'applique désormais aussi au mode standalone.

**SP-18c clos : 0 Critical/Important non résolu au merge.**
