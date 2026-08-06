# SP-15d — Pipeline : sidecar `qgis_process` (étage 2) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-06-sp15d-qgis-sidecar.md
Spec: docs/superpowers/specs/2026-08-06-sp15d-qgis-sidecar-design.md (si présent) — sinon design intégré au plan.
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@1c5eede (HEAD au lancement).

Note : ce fichier remplace le ledger SP-15c (complet, READY TO MERGE,
mergé dans dev, documenté dans CLAUDE.md) — même fichier scratch réutilisé
par convention du dépôt ; contenu SP-15c préservé dans l'historique git.

Infra locale vérifiée avant lancement :
- `postgis-test` déjà présent (port 5433, DB `gis_test`, user/pass `gis`/`gis`,
  `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test`).
- Docker disponible (29.4.3), accès réseau au registre Docker Hub confirmé
  (401 sur `/v2/` = attendu pour un pull anonyme, pas un blocage réseau).
- Pas encore de conteneur `qgis-worker` local — Task 4 devra le construire et
  le démarrer manuellement (`docker build` + `docker run -p 8300:8000 -v
  /scratch:/scratch`) pour que les tests marqués `qgis` des Tasks 4/5/8
  s'exécutent réellement plutôt que d'être skippés.

## Pré-vol

Scan des 8 tâches (1: allowlist gelée 50 algos + loader ; 2: modèle Pydantic
`TransformQgisParams`, 15e op ; 3: traçage SRID via `outputSrid` explicite ;
4: sidecar HTTP `qgis-worker` isolé + marker pytest `qgis` ; 5: dispatch
runtime — COPY GDAL avec SRS explicite -> sidecar -> ST_Read ; 6: route
catalogue + câblage env vars ; 7: compose profile `etl` ; 8: test
d'intégration bout-en-bout dissolve->writer.collection) contre les
Contraintes Globales (pas de changement shell/canvas, pas de
reader.connector/transform.sql, pas de migration DB, pas de changement de
comportement des 14 op existantes, tag d'image pinné partout, QT_QPA_PLATFORM
offscreen partout où qgis_process tourne, SRS explicite obligatoire sur tout
COPY GDAL alimentant transform.qgis, pas de conversion d'unité automatique,
grassprovider activé au build seulement, `grass:*` jamais `grass7:*`,
contrat exit-code/stdout/stderr du sidecar, root sur les deux images sans
USER directive, write_audit moot pour cette tâche, pas de "update" dans
Action).

Aucune contradiction trouvée entre les 8 tâches ou avec les Contraintes
Globales — plan explicitement vérifié contre un vrai conteneur
`qgis/qgis:release-3_34` et un vrai DuckDB pendant le design (préambule du
plan). Poursuite sans confirmation utilisateur (scan clean).

## Tasks

Base Task 1: 1c5eede

**Task 1 — 1er passage : BLOCKED (NEEDS_CONTEXT), pas de commit.**
L'implémenteur a découvert, en exécutant le script générateur pour de vrai
contre `qgis/qgis:release-3_34`, que 7 des 50 ids d'`ALLOWLIST_IDS` du plan
sont faux : `native:minimumboundinggeometry` et
`native:heatmapkerneldensityestimation` ont le mauvais préfixe de provider
(`qgis:` pas `native:`), `native:selectbyattribute` n'existe pas du tout en
tant qu'algorithme Processing (action GUI Desktop, pas exposée par
`qgis_process`), et les 4 ids `grass:r.*` ont le mauvais préfixe
(`grass7:*`, pas `grass:*`) — **ce dernier point contredit littéralement
l'affirmation "vérifiée" du plan lignes 72-75**. Contrôleur a re-vérifié
indépendamment les deux points les plus consequents (grass7 vs grass,
absence de selectbyattribute) contre le même conteneur pinné avant d'agir —
confirmé à l'identique. Décision humaine demandée (remplacement de
`native:selectbyattribute`, aucun équivalent direct) : **remplacer par
`native:polygonstolines`** (comble un vrai manque — conversion contours de
polygones en lignes — distinct des 49 autres op). Plan corrigé sur place
(`docs/superpowers/plans/2026-08-06-sp15d-qgis-sidecar.md`) : contrainte
globale grass7/grass, `ALLOWLIST_IDS` (script générateur), `EXPECTED_IDS`
(test), commentaire Dockerfile Task 4 ; `fetch_schema()` du générateur
étendu pour chaîner `qgis_process plugins enable grassprovider` dans le
MÊME appel de conteneur que les ids `grass7:*` (l'état du plugin ne
survit pas entre deux `docker run --rm` distincts — trouvaille de
l'implémenteur, également vérifiée). Brief Task 1 régénéré depuis le plan
corrigé avant re-dispatch.

**Task 1 — 2e passage (post-correctif) : complete (commit 7c950ac, review
clean au premier passage sur le brief corrigé — ✅ spec compliant, task
quality Approved, 0 Critical, 0 Important, 1 Minor négligeable —
`_type_id()` non testé unitairement en isolation [risque faible, outil
offline non exécuté au runtime]).** Les 7 corrections (2 préfixes qgis:, 4
préfixes grass7:, substitution native:selectbyattribute->native:polygonstolines)
confirmées cohérentes entre `ALLOWLIST_IDS`, le JSON généré et `EXPECTED_IDS`
du test — zéro dérive entre les trois. Déviation additionnelle de
l'implémenteur (non prévue par le brief, découverte lors de l'exécution
réelle) : `_type_id()`, un normaliseur pour le paramètre
`INTERPOLATION_DATA` de `qgis:tininterpolation`/`qgis:idwinterpolation`
dont le champ `"type"` est une chaîne brute au lieu du dict `{"id": ...}`
habituel — jugée correcte et bien scopée par le reviewer (contrat
`{"type": str}` préservé pour les 50 algorithmes, zéro `"unknown"` fuité,
vérifié par grep sur le JSON généré). 50/50 algorithmes récupérés pour de
vrai contre le conteneur pinné (pas de mock/fabrication), les 4 spot-checks
du plan vérifiés directement dans le diff. 6/6 tests du fichier cible,
1013 passed + 122 skipped sur la suite complète, 0 régression.

Base Task 2: 7c950ac
**Task 2 : complete (commit 596c1c8, 1 round de fix avant revue — pas un
rejet de reviewer, une correction du contrôleur avant dispatch de la revue
— review clean ensuite : ✅ spec compliant, task quality Approved, 0
Critical, 0 Important, 2 Minor négligeables — numéros de ligne du rapport
imprécis [narratif, sans impact code], import `QGIS_ALGORITHMS` local à la
méthode plutôt qu'au niveau module [prescrit par le brief, pas une
déviation]).** `TransformQgisParams` (3 champs, docstring verbatim),
validator `_check_allowlisted_and_required_params`, enregistrement
`OP_KINDS`/`OP_PARAMS` sans toucher aux 14 op existantes — tout confirmé
verbatim au brief corrigé. **Déviation trouvée et corrigée avant revue** :
1er passage de l'implémenteur avait substitué `native:convexhull` à
`gdal:warpreproject` dans le test `..._accepts_optional_output_srid` pour
contourner un échec de validation — le contrôleur a vérifié indépendamment
contre le JSON réel généré par Task 1 que `gdal:warpreproject` requiert en
réalité `DATA_TYPE`/`MULTITHREADING`/`RESAMPLING` (pas seulement
`TARGET_CRS`, qui est en fait optionnel) ; plan corrigé aux deux occurrences
(ce test-ci ET le test équivalent de Task 3, pas encore dispatché, qui
aurait heurté le même problème) ; implémenteur a rétabli `gdal:warpreproject`
avec les 4 params et amendé son commit (pas de commit intermédiaire visible
dans l'historique final, vérifié par le reviewer). Reviewer a vérifié
empiriquement la même donnée JSON de manière indépendante et confirmé les
exigences de chaque algorithme utilisé par les 6 nouveaux tests. 42/42 tests
du fichier cible (36 existants + 6 nouveaux), 0 régression.

Base Task 3: 596c1c8
Task 3: complete (commit 0149e19, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
informatif — double-validation Pydantic déjà présente dans le pattern
existant de `transform.reproject`, pas une régression introduite par cette
tâche). Nouvelle branche confirmée placée juste avant le fallthrough final
`return input_srid`, suit verbatim le pattern préexistant de
`transform.reproject` (`model_validate` + `rsplit(":",1)[1]` + `int()`).
Aucune autre branche touchée (buffer/reproject/intersection/countWithin/
join/h3Aggregate confirmées octet-identiques à la base). Sécurité du
`rsplit` vérifiée par le reviewer contre la contrainte regex `outputSrid`
de Task 2 (`^[A-Za-z]+:\d+$`). 29/29 tests du fichier cible (27 existants +
2 nouveaux), 0 régression.

Base Task 4: 0149e19
**Task 4 : complete (commit 3e2763c, 2 déviations autorisées par le
contrôleur avant la revue — pas des rejets de reviewer — review clean
ensuite : ✅ spec compliant, task quality Approved, 0 Critical, 0
Important, 2 Minor négligeables — absence de garde sur JSON malformé dans
`server.py` [verbatim du brief, non testé par le brief lui-même], route 404
non documentée dans l'interface du brief [inoffensif]).**

Contexte infra : `sudo` sur cette machine nécessite une authentification
interactive indisponible pour un subagent — **décision utilisateur** :
reporter la configuration de `/scratch` (chown) plutôt que la faire
maintenant. Step 5 exécuté en mode dégradé (build + smoke-test HTTP réel
sans montage `/scratch` inscriptible), **Step 9 (tests pytest réels contre
le sidecar) explicitement différé** — à reprendre dans une session future
avec accès sudo avant de s'appuyer sur le sidecar en production. Les 3
tests `qgis`-marqués skippent proprement en attendant (comportement voulu,
pas un échec).

**Déviation 1 (trouvée et corrigée par l'implémenteur, vérifiée
indépendamment par le contrôleur ET le reviewer)** : le Dockerfile du plan
plaçait `ENV QT_QPA_PLATFORM=offscreen` APRÈS le `RUN qgis_process plugins
enable grassprovider` — bug de build réel (`qt.qpa.xcb: could not connect
to display`, exit 134, les layers Docker s'appliquent dans l'ordre).
Implémenteur a réordonné (ENV avant RUN), rebuild confirmé réussi (log de
build avec grassprovider effectivement activé). Contrôleur a vérifié
`docker images`/`docker ps` (image présente, aucun conteneur de test qui
traîne). Reviewer a re-vérifié la sémantique des layers et l'absence de
ligne résiduelle incohérente.

**Déviation 2 (trouvée par l'implémenteur, root-cause tracée
indépendamment par le contrôleur, fix autorisé explicitement avant
exécution)** : `core/tests/test_pipeline_routes.py::test_get_pipelines_ops_returns_all_eight`
échouait déjà avant cette tâche — introduit par **Task 2** (premier échec
au commit 596c1c8, confirmé par `git stash`/checkout ciblé sur chaque SHA
intermédiaire), pas par Task 4. Même patron que SP-15c Task 1 (test qui
code en dur l'ensemble exact des op, cassé mécaniquement par l'ajout du 15e
op, hors liste de fichiers du brief qui l'a introduit). Corrigé maintenant
plutôt que laissé rouge jusqu'à Task 6 : renommage `..._all_eight` →
`..._all_fifteen`, `"transform.qgis"` ajouté à l'ensemble attendu, amendé
dans le même commit. Reviewer a vérifié indépendamment via `git show
596c1c8` que `transform.qgis` est un op réellement enregistré, et recompté
à la main l'ensemble à 15.

Suite complète repassée au vert après les 2 corrections : 1022 passed + 125
skipped, 0 échec (125 skipped = postgis existants + les 3 nouveaux qgis).
`server.py`/générateur/fixtures/test confirmés verbatim au brief par le
reviewer (contrat HTTP 200/403/502/504 tracé ligne à ligne contre les 3
tests).

Base Task 5: 3e2763c
**Task 5 : complete (commit f55bf5f, 1 déviation autorisée avant revue —
review clean ensuite : ✅ spec compliant, task quality Approved, 0
Critical, 0 Important, 1 Minor + 1 ⚠️ reporté pour plus tard).**

Contexte infra inchangé (cf. Task 4) : Step 5 du brief (test réel bout-en-
bout contre le sidecar) écrit mais **non exécuté** — skip propre confirmé
sans le sidecar, correction réelle différée à une session future avec
accès `sudo`/`/scratch`.

**Déviation (trouvée par l'implémenteur, vérifiée indépendamment)** : les
2 nouveaux payloads de test du brief (reader+transform seulement) violaient
un validator Pydantic préexistant et non lié à cette tâche
(`PipelinePayload._validate_graph`, `core/app/configs/schemas.py:207` :
"pipeline requires at least one writer node"). Implémenteur a ajouté un
nœud+edge `writer.export` minimal à chaque payload — contrôleur ET reviewer
ont vérifié indépendamment que (1) le validator existe réellement à cette
ligne, (2) c'est le même patron déjà établi par
`test_preview_h3_aggregate_requires_4326_reproject_first` (lignes 367-386),
et (3) le nœud writer est inerte pour ces tests (`up_to="t1"` déclenche un
retour anticipé dans `_execute_transform_chain` avant que le writer ne soit
jamais atteint) — n'affecte donc rien de ce que le test exerce/vérifie
réellement.

Guard `if not qgis_worker_url: raise` confirmé en toute première ligne de
`_execute_qgis_transform` (échec propre avant tout I/O fichier/réseau).
Option `SRS 'EPSG:{input_srid}'` du COPY confirmée présente. Ordre
`except httpx.TimeoutException` avant `except httpx.HTTPError` confirmé
correct (TimeoutException est une sous-classe de HTTPError). Chemin des 14
op existantes confirmé octet-identique (`compile_transform_sql` +
`CREATE TEMP VIEW` inchangés). `preview_pipeline`/`run_pipeline` confirmés
correctement threadés avec les 2 nouveaux kwargs. **⚠️ Point ouvert reporté
par le reviewer, à vérifier dans une session future avec sidecar réel** :
le round-trip GPKG via `qgis_process` préserve-t-il bien une colonne nommée
littéralement `geometry` (convention supposée par `preview_pipeline`/
`writer.collection`) ? Non vérifiable sans exécution réelle — à couvrir par
une assertion explicite sur le nom/la forme de colonne quand Step 5/6 sera
enfin exécuté pour de vrai (avant Task 8 si celui-ci doit s'appuyer sur ce
chemin en confiance). 1023 passed + 126 skipped sur la suite complète (+1
test réussi, +1 skip), 0 régression.

Base Task 6: f55bf5f
Task 6: complete (commit 1295502, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
négligeable — aucun test n'exerce le threading réel des env vars avec une
valeur non-défaut, conforme au brief qui ne le demandait pas). Route `GET
/pipelines/ops/qgis-algorithms` confirmée héritant du même gate
`CORE_ETL_ENABLED` que le reste du router (pas un second gate parallèle,
verrouillé explicitement par le 2e test 404). `preview_pipeline_route`/
`run_pipeline_task` confirmés threader les 2 nouveaux kwargs avec les
mêmes défauts (`""`/`600`) qui reproduisent exactement le comportement
préexistant pour tout pipeline sans nœud `transform.qgis`. Aucune autre
route/tâche perturbée. 1025 passed + 126 skipped sur la suite complète
(+2 tests), 0 régression.

Base Task 7: 1295502
Task 7: complete (commit 562101b, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding, aucun Minor bloquant — pas de
`depends_on` sur `qgis-worker` [correct, l'appel se fait au moment du job
via HTTP, pas au démarrage du conteneur]). Diff YAML pur, 1 seul fichier, 21
insertions. Les 4 contraintes globales vérifiées directement dans le diff
(pas seulement rapportées) : `profiles: ["etl"]` présent, aucune credential
DB, seuls `etl-scratch`+`gis-net` montés/attachés, aucun `USER` directive
introduit. Cohérence du port `http://qgis-worker:8000` vérifiée contre le
vrai `server.py` de Task 4. Blocs `environment`/`depends_on`/`networks`
préexistants de `worker` confirmés intacts, seule une nouvelle clé
`volumes:` insérée proprement. Validation réelle exécutée par
l'implémenteur : `docker compose config --quiet` (exit 0), `qgis-worker`
présent avec `--profile etl` / absent sans, build+smoke-test réel (5s de
uptime silencieux = succès, pas de crash-loop), teardown propre confirmé
(aucun conteneur qui traîne).

Base Task 8: 562101b
Task 8: complete (commit 0e01da5, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 2 Minor
négligeables — docstring du nouveau test n'a pas répété la mise en garde
`/scratch` [plan-mandated, verbatim du brief, pas une déviation de
l'implémenteur], redondance harmless `srid=4326` re-passé à
`dataclasses.replace`). Tâche pure test, aucun fichier de production touché
(`git diff --stat` hors le fichier de test confirmé vide). Reviewer a tracé
indépendamment le test contre le vrai code de production déjà mergé
(`_execute_qgis_transform`, `_write_collection`, validation
`TransformQgisParams`, schéma réel de `native:dissolve`) et confirmé le
test bien formé : géométrie des 2 carrés adjacents (bord partagé x=1)
correcte, params `{FIELD, SEPARATE_DISJOINT}` correspondent exactement au
schéma réel de l'allowlist, câblage collection/TableInfo cohérent avec les
monkeypatches, nettoyage/marqueurs identiques au patron établi du fichier.

Contexte infra inchangé : test marqué à la fois `postgis` (infra
disponible) et `qgis` (infra indisponible) — skip propre confirmé sans env
vars, **exécution réelle contre le sidecar différée** à une session future
avec accès `sudo`/`/scratch`. 1025 passed + 127 skipped sur la suite
complète (+1 skip), `lint-imports` clean (1 kept, 0 broken), 0 régression.

## 8 tâches de SP-15d complètes. Passage au check final.

**Point ouvert reporté pour la revue finale et pour l'utilisateur** :
l'affirmation centrale du plan — « `transform.qgis` fonctionne réellement
bout-en-bout contre un vrai sidecar `qgis_process` » — **reste non
vérifiée par exécution réelle** dans cette session (`sudo` interactif
indisponible pour configurer `/scratch`). Toute la logique de production a
été relue et vérifiée statiquement à chaque tâche (contrats HTTP,
round-trip DuckDB↔GDAL, gestion SRID/SRS, guard-rails d'erreur), et
l'implémenteur de Task 4 a confirmé le conteneur démarre et répond
correctement en HTTP réel (juste sans I/O fichier via `/scratch`). Mais les
3 tests `qgis`-marqués (Task 4), le test bout-en-bout de Task 5
(`computes_centroids`) et celui de Task 8 (`dissolve_then_write`) n'ont
jamais tourné pour de vrai. À exécuter dans une session future ayant accès
`sudo` avant de considérer SP-15d opérationnel en production.

## Check final (contrôleur, baseline indépendante)

`cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test
uv run pytest -q` → 1147 passed, 5 skipped (les 5 = exactement les tests
`qgis`-marqués des Tasks 4/5/8, postgis réel connecté). `uv run
lint-imports` → 1 kept, 0 broken. `cd shell && npx vitest run` → 121
fichiers, 933 tests passed (ce plan ne touche jamais `shell/`, vérifié en
pure régression). `npx tsc --noEmit` → clean. Baseline indépendante
confirmée avant dispatch de la revue finale.

## Revue finale de branche (opus, 1c5eede..0e01da5, 8 commits)

**Ready to merge: With fixes.** Les 12 contraintes globales vérifiées une
par une sur tout le diff (pas seulement par tâche) — toutes vertes,
y compris les 2 corrections documentées en cours d'exécution (grass7/grass,
test routes.py cassé par Task 2) confirmées correctement propagées
partout, **+ une 3e correction non documentée mais correcte trouvée** :
l'ordre `ENV`/`RUN` du Dockerfile (Task 4) — le reviewer confirme
indépendamment que c'est la bonne correction.

**1 Important trouvé et corrigé avant merge** : `_execute_qgis_transform`
ne renomme jamais la colonne géométrie après `ST_Read(out_path)`, alors que
tout le reste du fichier (chemin reader) impose la convention littérale
`geometry` dont dépendent `has_geometry`/`_write_export`/`_write_collection`.
GDAL nomme souvent la colonne géométrie GPKG `geom`, pas `geometry` — risque
réel de perte silencieuse de géométrie si jamais exécuté contre le vrai
sidecar. **1 Important non actionnable cette session** : les 5 tests
`qgis`-marqués n'ont jamais tourné pour de vrai (même limitation `sudo`)
— le reviewer juge que cela n'empêche pas le merge (feature doublement
verrouillée par défaut : `CORE_ETL_ENABLED=false` + profil compose `etl`)
mais **ne doit pas être activée en production avant qu'une session future
avec accès `sudo` fasse tourner les 5 tests pour de vrai**.

4 Minor négligeables triés (fuite scratch sur échec, absence de garde JSON
malformé côté sidecar, `response.json()` fragile sur erreur non-200,
`_type_id()` non testé isolément — ce dernier jugé acceptable, prouvé
indirectly par le JSON committé).

**Fix appliqué** : renommage robuste de la colonne géométrie (même patron
que le chemin reader) + 3 Minor de durcissement (cleanup scratch en
try/finally, garde JSON malformée côté sidecar → 400 propre,
`response.json()` client tolérant à un corps non-JSON). Dispatché comme 1
seul fix subagent couvrant les 4 points ensemble (commit d1c019d).

**Preuve empirique indépendante obtenue pendant le fix** : `git stash` +
repro directe hors pytest confirme que même le `COPY ... FORMAT GDAL DRIVER
GPKG` de DuckDB lui-même nomme sa colonne géométrie `geom`, jamais
`geometry` — la prémisse du Finding 1 n'était pas hypothétique, elle était
vraie à 100 % dès le premier retour GPKG, sidecar ou pas. 8 nouveaux tests
(4 dans `test_pipeline_runtime.py` sans sidecar réel requis — vrai COPY/
ST_Read DuckDB, `_QGIS_SCRATCH_ROOT` extrait uniquement pour rediriger vers
un `tmp_path` [`/scratch` appartient à root, inaccessible en écriture cette
session] ; 4 dans un nouveau fichier `test_qgis_worker_server_handler.py`
démarrant un vrai `ThreadingHTTPServer` sur port éphémère). RED→GREEN
démontré pour les 2 groupes via `git stash`/`git stash pop` ciblés.

**Re-revue du fix (opus, 0e01da5..d1c019d) : les 4 findings marqués
Resolved indépendamment** — reviewer a lui-même refait la repro DuckDB
(confirmé `geom`/`fid`, jamais `geometry`) et vérifié que la détection par
type (`.description[1].id == "geometry"`) reste robuste même avec un SRID
annoté dans le type (`GEOMETRY('EPSG:4326')`). `try/finally` confirmé
couvrir COPY+HTTP+matérialisation. Garde sidecar confirmée ne pas avaler
les requêtes bien formées (test de non-régression dédié). Aucune des 14 op
préexistantes touchée (diff ciblé confirmé). 2 points Minor résiduels
notés, hors périmètre des 4 findings, non bloquants (corps d'erreur JSON
valide mais non-objet ; collision de nom `geometry`/`geom` théorique,
absente de l'allowlist réelle). **Ready to merge: Yes.**

1155 passed + 5 skipped (postgis réel, les 5 = tests qgis-marqués toujours
différés), `lint-imports` 1 kept/0 broken, avant et après le fix.

## SP-15d READY TO MERGE — HEAD=d1c019d, 9 commits (8 tâches + 1 fix de
revue finale sur 4 findings, 1 seul round de fix). 0 Critical/Important non
résolu sur l'ensemble de la branche. **Point ouvert non bloquant pour
l'utilisateur, à traiter avant activation en production** : les 5 tests
`@pytest.mark.qgis` (3 Task 4, 1 Task 5, 1 Task 8) n'ont jamais tourné pour
de vrai cette session (`sudo` interactif indisponible pour configurer
`/scratch`) — à exécuter dans une session future avec accès sudo avant de
considérer `transform.qgis` vérifié de bout en bout contre un vrai
`qgis_process`. La feature reste doublement verrouillée par défaut
(`CORE_ETL_ENABLED=false` + profil compose `etl`), donc mergeable sans
risque pour toute instance existante. Prêt pour
`superpowers:finishing-a-development-branch`.
