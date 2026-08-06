# SP-15f — `reader.connector` dlt (REST + Postgres) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-06-sp15f-reader-connector-dlt.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@c3d8b58 (HEAD au lancement).

## Pré-vol

Scan des 5 tâches contre les Contraintes Globales + vérification indépendante
contre l'état réel du repo avant dispatch :
- `core/pyproject.toml` : `httpx>=0.27` ligne 11 confirmée (point d'insertion
  `requests`/`dlt` après elle) ; layers list `app.harvest`(84)/`app.pipelines`(85)/
  `app.secrets`(86) confirmée, `app.analytics` absente de la liste (donc pas de
  contrainte à modifier).
- `core/app/pipelines/ops/schemas.py` : `OP_KINDS`/`OP_PARAMS` actuels (15 ops)
  confirmés identiques au bloc "avant" du plan ; `TransformQgisParams` bien la
  dernière classe avant `OP_KINDS`.
- `core/app/harvest/egress.py` : shape confirmée (httpx-based), justifie la
  duplication demandée par le plan pour `requests`.
- `core/app/secrets/repository.py` : `get_secret_payload(session, *, tenant_id, name) -> SecretPayload | None`
  confirmé exact.
- `core/app/secrets/schemas.py` : 5 payloads confirmés avec les noms de champs
  exacts utilisés par le plan (`location`/`key`/`value`, `token`, `username`/
  `password`, `tokenUrl`/`clientId`/`clientSecret`, `dsn`).
- `core/app/analytics/sql_sandbox.py` : `parse_ast`, `validate_select_only`,
  `SqlSandboxError` confirmés ; `app/pipelines/expr_validation.py` confirmé
  utilisant déjà le même mécanisme.
- `core/app/pipelines/runtime.py` : bloc `_prepare()` "avant" (lignes 192-206)
  confirmé identique caractère pour caractère au bloc que le plan demande de
  remplacer.
- `core/tests/conftest.py` : fixture `pg_engine` confirmée avec skip propre si
  `CORE_TEST_DATABASE_URL` absent.
- `core/app/pipelines/config_validation.py` : boucle générique
  `for _op in OP_PARAMS: register_pipeline_node_validator(...)` confirmée —
  aucune modif nécessaire pour les 2 nouveaux ops.
- `core/Dockerfile` : confirmé n'installant que via `pyproject.toml`, pas de
  liste dupliquée à maintenir.

Aucune contradiction trouvée. Poursuite sans confirmation utilisateur (scan clean).

## Tasks

Base Task 1: c3d8b58
Task 1: complete (commit 7f3e7e2, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important réel, 1 Important
signalé sur une contrainte que LE CONTRÔLEUR avait ajoutée de son propre
chef dans le prompt de dispatch ("ne doit toucher aucun autre fichier") —
absente du texte réel du plan. L'implémenteur a dû mettre à jour
`test_pipeline_routes.py::test_get_pipelines_ops_returns_all_fifteen`
(renommé `_seventeen`, 15→17) pour satisfaire l'étape 5 du plan elle-même
("full pipelines test suite... all pass"), le plan n'ayant pas anticipé ce
test à compte fixe. Le reviewer a lui-même conclu "gap in the plan's file
list rather than implementer overreach" et vérifié qu'aucune autre
assertion de comptage à froid ne restait obsolète ailleurs — résolu par le
contrôleur sans escalade, ce n'est pas une vraie violation du plan).
49/49 tests passing (test_pipeline_ops_schemas.py), régression complète
143 passed/10 skipped.

Base Task 2: 7f3e7e2
Task 2: complete (commit 85f71c6, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 2 Minor
négligeables — note résiduelle TOCTOU DNS-rebinding absente du docstring du
nouveau module (héritée verbatim du bloc de code du plan, pas une omission
de l'implémenteur) ; commentaire de la constante d'allowlist sur 3 lignes
physiques au lieu d'1 (lettre de la contrainte, pas son intention)). Garde
`requests`-based confirmée distincte de `app.harvest.egress` (httpx-based),
`CORE_PIPELINES_EGRESS_ALLOWLIST` distinct de `CORE_HARVEST_EGRESS_ALLOWLIST`
confirmé. 14/14 tests passing (7-way parametrize + 7 tests nommés — le "8
passed" du plan comptait les définitions de fonction, pas les items
pytest collectés, pas un défaut de code), régression complète 1097
passed/127 skipped. `lint-imports` propre (module sans dépendance interne).

Base Task 3: 85f71c6
Task 3: complete (commits 9b6d1df + fix 35e595e, 1 round de fix). Review
initiale : ✅ spec compliant, task quality "Needs fixes" — 1 Important réel
trouvé (plan-mandated) : `_build_auth()` ne passait pas la session gardée
SSRF à `OAuth2ClientCredentials`, dlt utilisant alors sa propre session non
gardée pour l'échange de jeton (obtain_token()) — un secret
`oauth2_client_credentials` avec `tokenUrl` interne aurait contourné la
garde SSRF, seul des 4 kinds de secret concerné (bearer/api_key/basic_auth
protégés car ils décorent la session déjà gardée plutôt que de faire leur
propre requête). Non couvert par les 9 tests initiaux. Fix : `session=
build_guarded_session()` ajouté à la construction `OAuth2ClientCredentials`
+ 1 test de régression (tokenUrl loopback interdit, remonte
`EgressBlockedError` via `__cause__` — dlt enveloppe dans
`PipelineStepFailed`/`ResourceExtractionError`). Re-revue : fix vérifié
indépendamment contre le source dlt réellement installé (`obtain_token()`
utilise bien `self.session.post(...)`), test de régression confirmé non
tautologique (échouerait avec `ConnectionError` sans le fix, pas
`EgressBlockedError`). **Ready to merge: Yes** sur ce fix.
Deux déviations du texte littéral du brief, toutes deux vérifiées légitimes
par le reviewer initial : `SinglePagePaginator()` explicite au lieu de
`None` (supprime un warning dlt, aucun changement de comportement) ; fixture
de test `_create_secret` corrigée pour utiliser un vrai `user.id` au lieu du
littéral `"u1"` du brief (violait la FK réelle `users.id` sur
`ConnectorSecret.created_by`) — fix de fixture de test pur, aucun code de
prod ni assertion changée. Toutes les API dlt du brief vérifiées contre
dlt 1.29.1 réellement installé via `inspect`. 1 Minor non bloquant (`offset`
paginator lève un `KeyError` brut au lieu de `ConnectorRuntimeError` si
`limit` manque — hérité verbatim du brief, flagué pour Task 5's reviewer
car `runtime.py` traduit spécifiquement `ConnectorRuntimeError`).
10/10 + 14/14 tests passing après fix, 1106+ suite complète sans régression
avant fix.

Base Task 4: 35e595e
Task 4: complete (commit dfd2bb2, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 3 Minor
négligeables — import `SqlSandboxError` inutilisé dans le fichier de test,
placement d'import mi-fichier avec `# noqa: E402`, paramètre `pg_engine`
de `_pg_dsn` non utilisé dans le corps). `materialize_postgres_connector`
confirmé réutilisant réellement `_run_dlt_and_attach` (pas de duplication),
ordre validation SELECT-only → résolution secret confirmé exact, disposal
`engine.dispose()` confirmé garanti sur tous les chemins (`finally`).
Tests exécutés contre un vrai conteneur `postgis-test` (127.0.0.1:5433,
disponible dans cet environnement) — pas skippés. 2 déviations
auto-signalées par l'implémenteur, vérifiées légitimes : `_pg_dsn` du brief
utilisait `str(pg_engine.url)` qui masque le mot de passe (`***`,
casserait l'auth réelle) → lit `CORE_TEST_DATABASE_URL` directement comme
`conftest.py` ; `_create_secret` du brief omettait l'argument `user`
(FK `created_by`, même problème que Task 3). 14/14 tests passing, suite
complète 1233 passed/5 skipped (skips pré-existants qgis), sans régression.

Base Task 5: dfd2bb2
Task 5: complete (commit 7341d35, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
plan-mandated — `test_run_pipeline_reader_connector_rest_never_leaks_secret_value`
assertion (`"s3cr3t-leak-check" not in str(rows)`) est quasi tautologique
avec l'implémentation actuelle (le token n'atteint `rows` par aucun chemin
plausible) ; la vraie vérification qui compte est l'assertion d'en-tête
`httpserver.expect_request(headers={"Authorization": "Bearer ..."})` —
verbatim du brief, pas un défaut d'exécution de cette tâche, flagué pour la
revue finale comme note qualité sur le plan lui-même, pas à corriger ici).
Dispatch `_prepare()` confirmé fidèle à la forme exacte du brief, motif de
traduction `ConnectorRuntimeError`→`PipelineRuntimeError` confirmé
structurellement identique au motif préexistant pour `ValueError` (pas
seulement "lève aussi PipelineRuntimeError"). `reader.collection` confirmé
inchangé caractère pour caractère (seul `view_name` mutualisé entre
branches). Claim SRID placeholder 4326 vérifié (pas juste accepté) :
aucune colonne géométrie dans les vues connecteur, DuckDB lèverait une
erreur de binder franche, pas un résultat faux silencieux.
3 déviations auto-signalées, toutes vérifiées comme de vrais défauts dans
le CODE DE TEST DU PLAN lui-même (pas de l'implémenteur) : fusion de deux
imports (cosmétique) ; 2 tests du brief sans nœud writer alors que
`PipelinePayload` exige au moins un writer (`app/configs/schemas.py:207-208`)
— aurait levé une `ValidationError` avant même d'atteindre le runtime ;
littéral `created_by="u1"` violant la FK réelle `users.id` (même défaut que
Tasks 3/4). `config_validation.py` confirmé n'avoir eu besoin d'aucune
modif — vérifié indépendamment, pas supposé. 1237 passed/5 skipped (suite
complète, régression zéro), `lint-imports` 1 kept/0 broken.

## 5 tâches de SP-15f complètes. Passage à la revue finale de branche.

## Revue finale de branche (opus, c3d8b58..7341d35, 6 commits)

**Ready to merge: With fixes.** Cœur sécurité confirmé sain et bien testé :
couverture SSRF sur les 4 kinds d'auth REST (y compris le chemin OAuth2
déjà corrigé en Task 3), bornage SELECT-only, non-fuite de secrets,
télémétrie coupée, nettoyage scratch garanti.

**1 Important trouvé et corrigé** : les échecs survenant PENDANT
l'extraction dlt elle-même (notamment un blocage SSRF sur l'URL de
DONNÉES, pas seulement l'URL de jeton OAuth2 déjà testée) n'étaient pas
traduits en `ConnectorRuntimeError` — ils s'échappaient en exception dlt
brute (`PipelineStepFailed`/`ResourceExtractionError`), contournant la
traduction `ConnectorRuntimeError`→`PipelineRuntimeError` de `runtime.py`
et ressortant en 500 opaque/« erreur interne » au lieu d'une erreur propre
— le pire signal d'erreur pour le cas le plus sensible en sécurité de toute
la fonctionnalité.

**4 Minor triés, non corrigés (tradeoffs acceptés/documentés)** : test
`..._never_leaks_secret_value` quasi tautologique (l'assertion qui compte
est ailleurs dans le même test, hérité du plan) ; garde SELECT-only ne peut
pas arrêter un `SELECT` d'une fonction qui écrit côté serveur distant
(hérité, heuristique documentée comme non-garantie par le design §5.2, la
vraie frontière de confiance est le DSN admin) ; aucune borne de
lignes/taille sur l'extraction connecteur (cohérent avec les lecteurs
existants, pas une régression) ; `CORE_PIPELINES_EGRESS_ALLOWLIST` non
documenté dans `.env.example` (même trou que `CORE_HARVEST_EGRESS_ALLOWLIST`,
pas une régression mais corrigé opportunément avec l'Important ci-dessus).

**Fix appliqué** (1 seul fix subagent couvrant l'Important + le test de
régression associé + le doc `.env.example`, commit `0b92ede`) :
`_run_dlt_and_attach` (helper partagé par les deux connecteurs) enveloppe
désormais `pipeline.run()` + le bloc ATTACH/SELECT/DETACH dans un
`try/except Exception` qui remonte la chaîne de causes
(`__cause__`/`__context__`, garde anti-cycle par `id()`) pour détecter un
`EgressBlockedError` enfoui et le traduire en
`ConnectorRuntimeError(f"egress blocked: {cause}")` ; les autres échecs en
`ConnectorRuntimeError(f"reader.connector extraction failed: {exc}")` ;
une `ConnectorRuntimeError` déjà levée à l'intérieur du bloc traverse
inchangée (pas de double-enveloppe). Nouveau test de régression : URL de
données pointée sur `127.0.0.1:1` avec la vraie garde active (pas la
fixture autouse qui la neutralise), prouve que le blocage SSRF sur l'URL
de DONNÉES (pas seulement OAuth2) remonte bien en `ConnectorRuntimeError`.
`.env.example` documenté pour `CORE_PIPELINES_EGRESS_ALLOWLIST`.
38/38+2 skipped (fichiers ciblés), suite complète 1238 passed/5 skipped,
zéro régression.

**Re-revue du fix (opus, 7341d35..0b92ede)** : portée exacte du `try`
confirmée (englobe bien `pipeline.run()`, où la garde SSRF s'exécute
réellement via l'adapter `requests`, pas au moment de la construction du
`RESTClient`/session, qui est pré-vol) ; garde `except ConnectorRuntimeError:
raise` confirmée sans double-enveloppe (rien dans le bloc englobé ne lève
`ConnectorRuntimeError` aujourd'hui — tous les raises pré-vol s'exécutent
avant l'appel à `_run_dlt_and_attach`) ; test de régression confirmé non
tautologique (aurait échoué avant le fix — type d'exception brute, pas
`ConnectorRuntimeError`) ; aucune fuite de secret dans les nouveaux
messages d'erreur (vérifié pour les deux branches) ; portée du fix limitée
aux 4 fichiers attendus, code des Tasks 1-5 déjà approuvé non altéré au-delà
du fix. 1 Minor signalé (le `except Exception` générique traduit aussi un
vrai bug interne en 400 plutôt qu'en 500 — compromis acceptable, `raise …
from exc` préserve la trace). **Ready to merge: Yes.**

## SP-15f READY TO MERGE — HEAD=0b92ede, 7 commits (5 tâches + 1 fix Task 3
+ 1 fix de revue finale, 2 rounds de fix au total sur toute la branche).
0 Critical/Important non résolu sur l'ensemble de la branche. Deux nouveaux
ops de lecture `reader.connector.rest`/`reader.connector.postgres` dans le
moteur de pipeline no-code, authentifiés par nom via le coffre de secrets
SP-15e, matérialisation dlt réelle (extraction/normalisation/inférence de
schéma) vers DuckDB scratch, garde SSRF dupliquée pour `requests`, garde
SELECT-only à l'exécution pour Postgres. Premier consommateur réel du
coffre SP-15e (anticipé mais non construit jusqu'ici). Prêt pour
`superpowers:finishing-a-development-branch`.
