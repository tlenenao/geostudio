# SP-15a — Pipeline : socle headless + capacité optionnelle — Progress Ledger

Plan: docs/superpowers/plans/2026-08-05-sp15a-pipeline-socle.md
Spec: docs/superpowers/specs/2026-08-05-sp15a-pipeline-socle-design.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@837faa9 (HEAD au lancement).

Note : ce fichier remplace le ledger SP-14n (complet, READY TO MERGE,
HEAD=3012192, déjà mergé/documenté dans CLAUDE.md) — même fichier scratch
réutilisé par convention du dépôt ; contenu SP-14n préservé dans l'historique
git (commits 837faa9 et antérieurs).

Postgis : conteneur jetable `postgis-test` (127.0.0.1:5433/gis_test) relancé
(`docker start postgis-test`), déjà debout depuis SP-12/SP-14n. Utilisé pour
les tâches 8 et 9 (`pytest.mark.postgis`).

## Pré-vol

Scan des 11 tâches (1: CORE_ETL_ENABLED flag ; 2: BuilderConfig kind=pipeline ;
3: op catalogue 8 ops ; 4: validation structurelle graphe + guard ETL ;
5: validation par nœud ; 6: validation expr SQL bornée + compilateur DAG ;
7: PipelineRun model + migration + repo ; 8: runtime DuckDB ; 9: job
procrastinate ; 10: routes REST + wiring + import-linter ; 11: outils MCP)
contre les Contraintes Globales (topologie linéaire+join only, pas de
fusion/push-down, frontière validation forme vs sémantique bornée à
l'exécution, position de couche app.pipelines entre app.harvest et
app.ingestion, CORE_ETL_ENABLED lu une fois par surface pas par ligne,
en-tête SPDX partout, commentaires FR pour le "pourquoi") :

Aucune contradiction réelle trouvée. Deux endroits se corrigent en ligne dans
le texte du plan lui-même (Task 4 Step 4 : ordre du guard ETL précisé après
un premier jet ; Task 10 Step 4 : import `is_etl_enabled` dans main.py
précisé après un premier jet) — pas des contradictions à arbitrer, juste la
version finale à suivre. Une duplication mandatée par le plan
(`runtime.py::_qi` dupliquant `compiler.py::_qi`, 2 lignes) est justifiée
explicitement dans le commentaire du plan lui-même (éviter un import
inter-module d'un nom privé `_`-préfixé) — laissée passer sans arbitrage.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 837faa9
Task 1: complete (commit 33f36b7, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
`.env.example` sans en-tête SPDX (convention préexistante du dépôt, aucun
fichier de config n'en porte, pas une régression introduite ici), citation
"design SP-15a §3" dans le docstring vérifiée exacte (pas une référence
fantôme). `is_etl_enabled()` mirror fidèle de `is_read_only_mode()` (lecture
env à chaque appel, pas de cache — vérifié explicitement car les tâches
suivantes en dépendent pour l'isolation par monkeypatch). `GET /instance`
gagne `etlEnabled` de façon additive. Reviewer a vérifié indépendamment
qu'aucun autre endroit (core/ ou shell/src/) n'a d'assertion exact-dict sur
`/instance` qui aurait cassé silencieusement. 15/15 tests (4 nouveaux +
2 corrigés + suite test_read_only_mode.py inchangée). Commit ne contient que
les 5 fichiers listés par le brief, aucun scope creep.

Base Task 2: 33f36b7
Task 2: complete (commit b68e069, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
`PipelineNode.kind` réutilise le nom "kind" déjà porté par `BuilderConfig`
(vocabulaire du design, pas un défaut), ordre de validation du graphe
(ids→edges→reader→writer) ne rapporte que la première violation (hors
périmètre de cette tâche, shape-only). `PipelinePayload._validate_graph`
confirmé n'inspecter que `node.id`/`node.kind`/`edge.from_`/`edge.to` —
jamais `node.params` (frontière shape-vs-sémantique respectée, vérifiée
explicitement par le reviewer). `PipelineNode.x`/`y`/`PipelineEdge.when`
confirmés inertes (présents, defaults corrects, non référencés dans la
validation). Reviewer a vérifié que les 4 branches préexistantes de
`_require_kind_payload` (app/dashboard/site, map, dataset, bookmark) sont
inchangées byte-for-byte. Test "ids dupliqués" confirmé isoler réellement
la bonne invariante (pas un faux positif d'une autre vérification). 7/7
tests nouveaux, 16/16 suite dataset/configs (0 régression).

Base Task 3: b68e069
Task 3: complete (commit 3c5c0e3, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant). Transcription pure
(implémenteur haiku, code littéral complet du brief) — reviewer a confirmé
byte-for-byte les 4 fichiers (2 `__init__.py` + `ops/schemas.py` + test).
Écart de comptage relevé et résolu : le texte du plan annonçait "11 tests"
mais le fichier de test littéral en compte réellement 15 (1 + 8 paramétrés +
5 + 1) — coquille préexistante dans la prose du plan, pas un défaut de
l'implémenteur, qui a bien 15/15. Frontière forme/sémantique confirmée :
`TransformFilterParams.expr`/`TransformDeriveParams.expr`/
`TransformAggregateParams.metrics` restent des champs `str`/`dict[str,str]`
bruts, aucun validateur n'inspecte le contenu des expressions (SQL bornée
validée seulement à l'exécution, Task 6). `lint-imports` toujours clean
(`app.pipelines` sans dépendance à ce stade). 15/15 tests nouveaux, 914
passed + 114 skipped suite complète (0 régression).

Base Task 4: 3c5c0e3
Task 4: complete (commit a44c3b8, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
docstring de `pipeline_validation.py` entièrement en anglais (hérité verbatim
du brief lui-même, qui reprend le précédent anglophone `dataset_validation.py`
— pas une déviation de l'implémenteur, note pour de futurs briefs), DFS
récursif de `_check_acyclic` sans limite d'itération explicite (sans risque
pratique compte tenu de la topologie linéaire+join du MVP). Frontière de
couche vérifiée : aucun import `app.pipelines` dans `pipeline_validation.py`
ni `routes.py` (le module `app.pipelines` n'existe même pas encore comme
package Python complet à ce stade — seulement `ops/`). Ordre guard-first
confirmé être la version finale corrigée du brief (pas le premier jet montré
dans sa prose). Reviewer a tracé à la main le DFS 3-couleurs sur le graphe
cyclique du test et confirmé que l'ordre acyclique-avant-topologie est
réellement porteur (le graphe de test a aussi 2 arêtes entrantes, donc
l'ordre des checks déterminait quel message d'erreur sortait). Fenêtre
"unknown op" 422 confirmée intentionnelle et temporaire (aucun validateur
réel enregistré avant Task 5). 5/5 tests nouveaux, 22/22 régression ciblée,
919 passed + 114 skipped suite complète, lint-imports clean (0 régression).

Base Task 5: a44c3b8
Task 5: complete (commit fe82563, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 3 Minor négligeables —
branche "unknown op" redondante dans `config_validation.py` (déjà
interceptée en amont par Task 4, filet défensif inoffensif), aucun test
n'exerce le chemin permission-lecture de `transform.join.withCollectionId`
(fidèle au fichier de test littéral du brief, lacune de couverture pas une
déviation), commentaires anglais dans `config_validation.py` (miroir
délibéré de `dataset_validation.py` préexistant, convention héritée pas une
régression). Déviation légitime signalée par l'implémenteur et vérifiée
indépendamment par le reviewer : les 3 `INSERT INTO collections` bruts du
brief omettaient `created_at`/`updated_at` (défauts Python-side de l'ORM,
jamais appliqués par un INSERT SQL brut) — ajout de `CURRENT_TIMESTAMP` aux
3 fixtures, aucun code de production touché. Les 3 signatures réelles
(`get_collection`, `get_access_facts`, `can()`) vérifiées caractère pour
caractère contre le code actuel, toutes conformes au brief. Parité de
message not-found/not-readable confirmée (anti-fuite d'existence de
collection). `writer.collection` confirmé vérifier permission ET
`editable` sans court-circuit. 5/5 + 5/5 tests, 34/34 régression ciblée,
924 passed + 114 skipped suite complète, lint-imports clean (0 régression).

Base Task 6: fe82563
Task 6: complete (commit 4b45ec0, review clean au premier passage — ✅ spec
compliant, task quality Approved, 1 Important non-bloquant + 0 Minor). Écart
de comptage supplémentaire (12 tests réels vs. "11" annoncé par la prose du
plan) — même schéma que Task 3, coquille préexistante du plan, pas un
défaut. Reviewer a tracé à la main l'AST de la tentative d'injection
`"1) UNION SELECT password FROM users--"` : survit à `validate_select_only`
(SET_OPERATION_NODE autorisé) mais est bloquée par `collect_table_refs` sur
la référence `users` — confirmé end-to-end (AST + exception imprimés), pas
un rejet accidentel par une erreur de syntaxe non liée. Pureté de
`compiler.py` confirmée (aucun import duckdb, aucune connexion dans aucune
signature). `_qi` confirmé doubler les guillemets échappés. `topological_order`
tracé à la main sur le test de cycle 2-nœuds (Kahn's algorithm, `ordered`
reste vide, lève bien "acyclic").

**Finding Important signalé, arbitré par l'humain** : `validate_bounded_expr`
ne rejette que les références `BASE_TABLE` — les fonctions table
(`read_csv`, `pragma_database_list`) et les fonctions scalaires
(`current_setting`) passent au travers, plus étroit que la promesse du
design §5.1 ("aucune fonction de lecture de fichier"). Plan-mandated (code
transcrit verbatim du brief, qui est le code exact du plan) — pas une
déviation de l'implémenteur. Reviewer a vérifié empiriquement que le
`_lock_down` déjà prévu par Task 8 (`enable_external_access=false`) neutralise
les vecteurs les plus graves (lecture fichier, introspection DB) ; seule
`current_setting()` reste exploitable sous lockdown (fuite de config session
DuckDB, pas de données utilisateur ni de fichier). Arbitrage humain : accepté
tel quel, aucun fix dispatché — à documenter comme suivi non bloquant dans
CLAUDE.md (même palier de confiance que SQL Lab, SP-11c) une fois la branche
mergée, pas pendant l'exécution des tâches restantes. 17/17 tests (5+12),
lint-imports clean (0 régression).

Base Task 7: 4b45ec0
Task 7: complete (commits 3d2841a + 8ebcb8b séparé, review clean au premier
passage — ✅ spec compliant, task quality Approved, 0 finding bloquant, 2
Minor héritées verbatim du brief — pas de scoping tenant_id sur
`mark_running`/`mark_succeeded`/`mark_failed` [note pour Task 10 : vérifier
l'autorisation en amont dans les routes], tolérance ordre/ensemble dans le
test `list_runs_ordered`). Deux déviations signalées par l'implémenteur,
vérifiées indépendamment par le reviewer comme légitimes (pas de contour de
problème, pas de scope creep) : (1) le test littéral du brief utilisait un
`pipeline_item_id="item-1"` fictif sans ligne `Item` réelle + session via
`Base.metadata.create_all()` — reviewer a reproduit les deux modes d'échec
réels (`NoReferencedTableError` en isolation, `IntegrityError` FK en suite
complète, ce dépôt active `PRAGMA foreign_keys=ON`) puis confirmé le fix
(`init_db()` + `_make_pipeline_item` créant un vrai User+Item, mirror de
`test_harvest_repository.py`) préserve les 6 noms/assertions/intentions de
test, seule la fixture change ; (2) commit séparé `8ebcb8b` (1 ligne,
`core/app/db.py::core_table_names()`) corrige une lacune latente réelle —
reviewer a vérifié indépendamment qu'aucun chemin d'import réel de
`app/main.py` n'atteint `app.pipelines.models` sans ce fix (une instance
SQLite dev/démo fraîche n'aurait jamais eu la table `pipeline_runs`),
confirmé par un revert temporaire + suite complète toujours verte (947
passed, lacune non testée mais réelle). Modèle confirmé référencer
`items.id` (pas de table `pipelines` séparée, conforme au design §4.1).
Chaîne de migration confirmée propre (`0018`, down_revision `0017`, tête
unique). 6/6 tests, 947 passed + 114 skipped suite complète (0 régression).

Base Task 8: 8ebcb8b
Task 8: complete (commit 2bd44c8, review clean au premier passage sur opus —
✅ spec compliant, task quality Approved, 0 finding bloquant, 4 Minor
négligeables — `AssertionError` brut au lieu de `PipelineRuntimeError` si
`writer.export` tourne sans `s3_client` [note pour Task 9], imports inutilisés
dans le fichier de test, classe `_FakeCollections` morte héritée du brief,
f-strings sans placeholder cosmétiques). Tâche la plus volumineuse et la plus
sensible du plan (écriture réelle de features via `insert_feature`/`rls_scope`)
— 7 signatures externes réutilisées (`open_connection`, `_dedup_cte`/
`_has_any_file`, `insert_feature`, `rls_scope`, `validate_feature`,
`introspect_table`) toutes vérifiées conformes, aucune dérive. 4 défauts
réels trouvés et corrigés par l'implémenteur (pas seulement transcrits),
tous vérifiés indépendamment par le reviewer opus contre le code source
actuel : (1) `_materialize_reader` utilisait `CREATE TEMP VIEW` (paresseux,
ré-exécute `read_parquet()` à chaque requête) au lieu de `CREATE TEMP TABLE`
— incompatible avec son propre design deux-passes (`_lock_down` coupe l'accès
externe juste après), confirmé par le même choix déjà fait dans
`app.analytics.sql_sandbox._materialize` ; correctement scopé aux
readers/joins seulement, les VIEW des transforms restent inchangées (pas de
remplacement en masse). (2) `SELECT *` sur la source CDC faisait fuiter les
colonnes de bookkeeping (`_op`/`_lsn`/`_ts`) et les colonnes virtuelles Hive
(`tenant_id`/`collection_id`/`dt`) dans les `properties` d'un `writer.collection`,
rejetées par `validate_feature` comme `unknown_property` — corrigé par une
liste de colonnes explicite (pk + colonnes déclarées + géométrie renommée) +
retrait des noms réservés de la collection cible avant écriture ; reviewer a
vérifié que rien n'est perdu (toutes les colonnes utilisateur déclarées
restent présentes) et que `insert_feature` ignore de toute façon pk/tenant_id
hors de son itération sur `_property_columns`. (3) Assertion de test
`pop_double == 40` pour id=1 était une erreur arithmétique du brief
(pop=10×2=20, pas 40) — comportement de l'implémentation confirmé correct,
seule l'assertion littérale était fausse. (4) 5 bugs confinés aux
fixtures/setup du test postgis (littéraux booléens `0,1` invalides sur
Postgres, `created_at`/`updated_at` NOT NULL sans défaut SQL sur un INSERT
brut, import `app.items` manquant pour enregistrer `Item` sur `Base.metadata`
en exécution isolée `-m postgis`, monkeypatch `table_name` figé cassant la
cible du writer, grants `gis_rls` manquants sur une table créée sans
`apply_collection_ddl`) — chacun vérifié par le reviewer contre le code réel
(modèles, `validate_feature`, `ddl.py`). Ordre deux-passes
matérialiser-puis-verrouiller confirmé préservé ; défense en profondeur
linéaire+join confirmée présente à l'exécution (`predecessor_id` assert).
Test postgis exécuté pour de vrai contre le conteneur `postgis-test` (pas
skippé) par l'implémenteur ET indépendamment par le reviewer — 3/3 passed,
conteneur nettoyé après coup dans les deux cas. 3/3 tests (2 non-postgis +
1 postgis réel), 57 passed + 1 skipped régression ciblée, lint-imports clean.

Base Task 9: 2bd44c8
Task 9: complete (commit 6ada6c6, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor informationnel
— limite résiduelle partagée avec SP-6a (`run_ingestion_task`) : si
`mark_failed` lui-même lève pendant son propre commit, l'exception remonte
non attrapée et le run reste bloqué "running" ; risque préexistant accepté,
pas une régression de cette tâche, hors périmètre MVP). Premier câblage
bout-en-bout réel des Tasks 2-9 à travers un worker procrastinate réel.
Les 6 signatures externes réutilisées toutes vérifiées conformes, aucune
dérive de code (seulement dérive de fixture de test, 4 bugs Postgres
identiques à ceux déjà résolus dans le test de Task 8 — littéraux booléens,
`created_at`/`updated_at` sur INSERT brut, import `app.items` manquant pour
enregistrer `Item` sur `Base.metadata`, grants `gis_rls` manquants — plus
un `keywords` NOT NULL supplémentaire propre à `items`). Préoccupation de
Task 8 (AssertionError brut du `writer.export` catché par le `except
Exception` final) résolue avec un 3e test ajouté (pas seulement raisonnée) :
reviewer a confirmé le test force un vrai `AssertionError` via monkeypatch
sur `pipeline_jobs.run_pipeline` (le nom réellement appelé par
`run_pipeline_task`) et vérifie `status == "failed"` — pas tautologique,
échouerait si la clause manquait ou était mal ordonnée. Ordre transactionnel
interne (mark_running / exécution / mark_succeeded-ou-failed, chacun dans sa
propre session) confirmé mirror fidèle de `run_ingestion_task` (SP-6a).
Queue `"etl"` cohérente entre `jobs.py` et `docker-compose.yml`,
`import_paths` confirmé enregistrer réellement la tâche (test dédié
`test_import_paths_registers_all_domain_tasks`, pas une illusion in-process).
3/3 tests postgis réels (exécutés deux fois par l'implémenteur + une fois
par le reviewer, conteneur systématiquement nettoyé), 949 passed + 118
skipped (SQLite) / 118 passed (postgis) suite complète (0 régression).

Base Task 10: 6ada6c6
Task 10: complete (commit 7f96035, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor cosmétique —
`test_run_route_defers_job_and_returns_run_id` ne vérifie jamais réellement
que le `fake_deferrer` a été appelé, le seul chemin de succès du test
[404 sur pipeline inexistant] retourne avant d'atteindre `defer_task` ;
lacune divulguée explicitement par le commentaire du brief lui-même, pas
masquée par l'implémenteur ; aucun test dans toute la suite n'exerce le
chemin HTTP heureux bout-en-bout create→commit→defer→202, mais le nom du
test sur-promet par rapport à ce qu'il vérifie réellement). Première tâche
du plan à ajouter `app.pipelines` à la liste `layers` d'import-linter —
déviation nécessaire signalée par l'implémenteur et vérifiée indépendamment
par le reviewer comme légitime, pas du contournement : l'ajout du layer a
exposé que `app.db.core_table_names()` importe déjà paresseusement
`app.pipelines.models` (ajouté par Task 7/commit 8ebcb8b, pas par cette
tâche), correspondance 1:1 confirmée entre les 10 entrées `ignore_imports`
préexistantes et les 10 imports paresseux de `core_table_names()` — la
11e entrée ajoutée suit exactement le même patron, pas un patron nouveau.
Reviewer a vérifié la position de couche par grep exhaustif de tous les
imports `app.pipelines/*.py` : rien n'importe `app.harvest`/`app.mcp`/
`app.public`/`app.main` (tout au-dessus dans le nouvel ordre), conforme à la
justification du plan. Guard `is_etl_enabled()` confirmé lu une seule fois
à `create_app()`, pas par requête. 404 en mode ETL désactivé confirmé être
une preuve univoque d'absence de route (endpoint sans dépendance
d'authentification). 5/5 tests, lint-imports clean (1 kept, 0 broken),
952 passed + 120 deselected — première exécution conjointe des Tasks 1-10
(0 régression).

Base Task 11: 7f96035
Task 11: complete (commit ef4cad9 puis fix 06ca019, 1 round de fix — ❌
Critical trouvé au premier passage, ✅ après fix). Dernière tâche du plan.
Déviation légitime signalée par l'implémenteur : le brief appelait
`validate_pipeline_payload` directement dans `create_pipeline` (lève
`HTTPException`, invisible pour `/mcp` monté en app ASGI séparée hors des
handlers FastAPI) — ajout d'un helper `_validate_pipeline` mirroring
`_validate_dataset`/`_validate_bookmark` déjà présents dans le même fichier
(conversion HTTPException→ValueError), amélioration stricte de cohérence
sans changement de comportement sur les chemins testés, vérifiée par le
reviewer. `READ_ONLY_TOOLS` confirmé inchangé (6 entrées, `create_pipeline`
s'auto-garde en inline, `run_pipeline` ne fait que différer un job — même
raisonnement que `run_analytics_query`).

**Critical trouvé et corrigé** : `explain_pipeline` (code verbatim du brief,
pas une déviation de l'implémenteur) ne vérifiait aucun accès en lecture
avant de renvoyer le graphe complet d'un pipeline — n'importe quel
utilisateur authentifié du même tenant pouvait lire le graphe de n'importe
quel pipeline, y compris sans partage/rôle, violant la porte unique
`can(user, action, object)` de CLAUDE.md. Repéré par contraste direct avec
son sibling `run_pipeline` dans le même diff, qui fait la vérification
correctement. Fix dispatché sans arbitrage humain (pas de conflit avec une
contrainte du plan — le fix aligne juste `explain_pipeline` sur le pattern
déjà correct de `run_pipeline`) : ajout du check `can(action="read")` +
remplacement de l'`AssertionError` brut par un `ValueError("pipeline not
found")` cohérent (pas de fuite d'existence entre "n'existe pas" et "accès
refusé"). Re-review a vérifié empiriquement (pas seulement statiquement) :
checkout du code pré-fix, re-exécution du nouveau test "stranger" — la faille
se reproduit réellement (renvoie le graphe complet sans erreur), puis
confirmé corrigée après restauration du fix. 3 tests ajoutés (propriétaire
réussit, étranger rejeté, id inexistant même message) — cas positif ET
négatif couverts, pas de sur-correction. 1 Minor résiduel sur le fix lui-même
— triple quasi-duplication du pattern facts+can dans le fichier
(`_require_access`, `run_pipeline`, `explain_pipeline`), défendable (messages
d'erreur différents), à surveiller si un 4e appelant apparaît.

**Finding Important signalé pour la revue finale** : aucun test de ce fichier
n'exerçait le corps des outils avant le fix (seulement présence/absence
d'enregistrement) — c'est précisément pourquoi le Critical est passé
inaperçu ; contraste avec `test_mcp_tools_dataset_create.py` qui teste déjà
les chemins négatifs/autorisation. Les 3 tests ajoutés par le fix comblent
ce trou pour `explain_pipeline` spécifiquement, mais le patron reste à
appliquer si de futurs outils MCP suivent le même brief-first workflow.

7 signatures externes vérifiées conformes (aucune dérive). Suite complète
finale : 957 passed + 120 deselected (0 régression) — clôt les 11 tâches de
SP-15a. Prête pour la revue finale de branche.

## Revue finale de branche (opus, 837faa9..06ca019, 13 commits) — 2 Important,
0 Critical. Baseline indépendante confirmée : 957 passed + 120 deselected
(non-postgis), 118 passed + 959 deselected (postgis), lint-imports clean,
pas de ruff configuré (pas un trou de lint, import-linter est le seul
linter configuré). Checklist croisée toute verte : ordre `_lock_down` avant
toute SQL de transform confirmé (disposition Task 6 toujours valide) ; pas
de sibling bug au Critical de Task 11 sur `run_pipeline`/`create_pipeline`
(REST + MCP) ; `CORE_ETL_ENABLED` lu une fois à la construction pour le
montage routes ET l'enregistrement MCP, dans le même appel `create_app()`
— aucune fenêtre d'incohérence ; topologie linéaire+join validée à la
sauvegarde sur tous les chemins d'écriture (REST + MCP `create_pipeline`),
défense en profondeur atteignable à l'exécution ; cohérence not-found/not-
authorized confirmée entre Task 5/10/11 ; isolation tenant bout-en-bout
confirmée (partition Hive + `rls_scope`) ; limite résiduelle Task 9
(`mark_failed` qui lève) confirmée inchangée, toujours hors périmètre.

**2 Important trouvés, même cause racine, fix consolidé dispatché** :
`_materialize_reader` renomme la géométrie en `"geometry"` mais la garde en
type DuckDB `GEOMETRY` brut, renvoyé par le client Python comme `bytes` WKB.
Seul `_write_collection` la convertit déjà (`ST_AsGeoJSON`). (1)
`preview_pipeline`/`POST /pipelines/{id}/preview` : 500 pour tout pipeline
dont la collection lue a une colonne géométrie — `jsonable_encoder` tente de
décoder les `bytes` en UTF-8 et lève `UnicodeDecodeError`. Invisible tâche
par tâche : le test Task 8 ne lit jamais le champ géométrie, le test Task 10
n'exerce que les 404. (2) `writer.export` : branche `geojson` lève
`TypeError` (bytes non sérialisables JSON) — run correctement marqué
"failed" (pas zombie) mais l'export ne fonctionne jamais ; en plus, la
branche geojson mettait `"geometry": None` en dur indépendamment du bug
bytes ; branche `csv` n'écrit pas d'erreur mais écrit le repr Python des
bytes dans la colonne géométrie (valeur inutilisable). Fix dispatché en un
seul lot (pas un fix par finding) : conversion `ST_AsGeoJSON` au point
d'extraction finale des deux fonctions (mirror de `_write_collection`, sans
toucher `_materialize_reader` ni `compiler.py` — Phase 1 n'a aucune op de
transform spatiale, donc l'encodage n'est nécessaire qu'aux deux frontières
de sortie, pas à travers les vues intermédiaires).

Fix (commit d10a30a) re-review clean — les deux findings confirmés
réellement corrigés, vérification empirique (checkout pré-fix + re-run des
3 nouveaux tests, échec reproduit exactement comme prédit —
`AssertionError` sur bytes WKB bruts vs objet GeoJSON attendu pour preview,
`TypeError` bytes-non-sérialisables pour l'export geojson, repr Python des
bytes dans la cellule CSV — puis restauration du fix, tests verts).
`_write_collection`/`_materialize_reader`/`compiler.py` confirmés
non-modifiés par le diff (mirroring sans collatéral). 3 tests ajoutés, 0
duplication de la géométrie dans `properties` pour l'export geojson. Suite
complète : 960 passed + 120 deselected (non-postgis), 4 passed + 5
deselected (postgis réel, `_write_collection` toujours fonctionnel).
Conteneur `postgis-test` laissé propre.

## **SP-15a READY TO MERGE** — HEAD=d10a30a, 15 commits (11 tâches + 1 fix
Task 11 [Critical, authorization bypass `explain_pipeline`] + 1 fix revue
finale [2 Important, sérialisation géométrie preview/export]), 2 rounds de
fix au total sur toute la branche, chacun re-revu clean avec vérification
empirique (checkout pré-fix). Suite complète finale : 960 passed + 120
deselected (SQLite/non-postgis), 118+ passed (postgis réel, exécuté
plusieurs fois avec succès tout au long de l'exécution — Tasks 2, 8, 9, et
la revue finale). lint-imports clean tout au long. Aucun Critical/Important
non résolu. Suivi non bloquant à documenter séparément (hors périmètre de
cette session d'exécution, décision humaine déjà prise) : gap
`validate_bounded_expr`/`current_setting()` de Task 6, à noter dans
CLAUDE.md « Suivis non bloquants » une fois la branche mergée. Prêt pour
`superpowers:finishing-a-development-branch`.
