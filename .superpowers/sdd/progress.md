# SP-15e — Coffre de secrets pour connecteurs externes — Progress Ledger

Plan: docs/superpowers/plans/2026-08-06-sp15e-connector-secrets-store.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@69e675a (HEAD au lancement).

Note : ce fichier remplace le ledger SP-15d (complet, READY TO MERGE, mergé
dans dev à d1c019d, documenté dans CLAUDE.md) — même fichier scratch
réutilisé par convention du dépôt ; contenu SP-15d préservé dans l'historique
git.

## Pré-vol

Scan des 5 tâches (1: crypto AES-GCM + layers list ; 2: schémas Pydantic
discriminés ; 3: modèle + migration `connector_secrets` ; 4: repository ; 5:
routes + admin gate + audit + wiring `app.main`) contre les Contraintes
Globales. Vérifié indépendamment contre l'état réel du repo avant dispatch :
- `core/pyproject.toml` layers list : ordre `app.harvest`/`app.pipelines`/
  `app.ingestion` confirmé identique au plan (lignes 78-80).
- `ignore_imports` : 10 entrées existantes confirmées, pattern à suivre pour
  `app.db -> app.secrets.models`.
- `alembic/versions/` : dernière révision `0018_pipeline_runs.py` confirmée
  — `down_revision = "0018"` du plan est correct.
- `core/app/main.py` : import block (ligne 29 `app.public`, ligne 30
  `app.schemas_routes`) et `app.include_router(extensions_routes.router)`
  (ligne 84) confirmés aux positions exactes citées par le plan ;
  `observability.setup()` bien la toute première ligne de `create_app()`.

Aucune contradiction trouvée entre les 5 tâches ou avec les Contraintes
Globales. Poursuite sans confirmation utilisateur (scan clean).

## Tasks

Base Task 1: 69e675a
Task 1: complete (commit 2b3f202, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
negligible — broad `except Exception` in `load_master_key()` is verbatim
plan-mandated code, not an implementer choice). `core/app/secrets/{__init__.py,crypto.py}`
confirmed byte-for-byte match to the plan's specified content by the
reviewer. `cryptography>=42.0` added as direct dependency (was already
transitive via `pyjwt[crypto]` at 49.0.0, version unchanged in `uv.lock`).
`app.secrets` inserted into import-linter layers list directly below
`app.harvest`/`app.pipelines`, confirmed via an independent `lint-imports`
run by the reviewer (1 kept, 0 broken). No key/plaintext material logged or
leaked in errors, confirmed by the reviewer. 6/6 tests passing.

**Note on scratch-file volatility**: `.superpowers/sdd/task-1-brief.md` was
found reverted to a stale prior-plan (SP-15d) file mid-review — root cause:
these files are git-tracked-despite-gitignore (see 10 pre-existing
`task-N-{brief,report}.md` from SP-15d, `git ls-files .superpowers/sdd/`),
and the implementer subagent's own git operations (not identified
precisely, no destructive command found in its self-report) appear to have
reset tracked-but-uncommitted changes to HEAD@69e675a at some point during
its run — `progress.md` was reverted identically at the same time. The
reviewer independently located and used the real plan file
(`docs/superpowers/plans/2026-08-06-sp15e-connector-secrets-store.md:94-327`)
instead, so the Task 1 verdict is unaffected. `task-1-brief.md` regenerated
correctly after the fact for the historical record.
`task-1-report.md` (written by the implementer via file tool after
whatever reset this) was NOT reverted — only files touched by `task-brief`/
this ledger were affected. Controller re-verifying `progress.md` content
after each future task dispatch as a precaution.

Base Task 2: 2b3f202
Task 2: complete (commit 8d269c5, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
negligible — `SECRET_PAYLOAD_ADAPTER` typed as bare `TypeAdapter` not
`TypeAdapter[SecretPayload]`, inherited verbatim from the plan itself, not
an implementer deviation). Discriminated union confirmed additive-by-
construction (new kind = new Pydantic variant, no migration), `api_key`
confirmed supporting both `header`/`query` placement (ArcGIS FS / WFS token
auth), zero coupling to Task 1's `crypto.py` confirmed by the reviewer via
grep. 9/9 tests passing. `progress.md` verified NOT reverted this round
(precaution from Task 1's note held).

Base Task 3: 8d269c5
Task 3: complete (commit 58e4276, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
informative — `created_at`/`updated_at` use Python-side `default`/`onupdate`
not DB-side `server_default`, plan-mandated, noted for whoever reviews
Task 4/5's repository layer). `ConnectorSecret` model + migration 0019
confirmed byte-for-byte matches to plan; `id` confirmed to have NO
server-side default (repository layer generates `uuid.uuid4().hex` in Task
4, not here); unique `(tenant_id, name)` confirmed identical in model and
migration; `down_revision="0018"` confirmed correct chain, no other
migration file touched; import-linter exemption confirmed exact format
match to the 10 pre-existing entries; FK target types (`tenants.id`,
`users.id`) confirmed both `String`, no mismatch. 3/3 tests passing (real
SQLite round-trip + real IntegrityError, not mocked), full suite 1051
passed/127 skipped, `lint-imports` 1 kept/0 broken. `progress.md` verified
NOT reverted this round.

Base Task 4: 58e4276
Task 4: complete (commit 55d4da4, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
informative — no audit_log write in this module, flagged for the Task 5
reviewer to confirm it's wired at the route layer instead, per plan design
[Task 4 is CRUD/decrypt-only, audit logging is explicitly Task 5's job]).
`create_secret` confirmed generating `id=uuid.uuid4().hex` in Python
(matches `pipelines/repository.py`'s `create_run` pattern), no DB-side
default. `get_secret_payload` signature confirmed exact
(`session, *, tenant_id, name) -> SecretPayload | None`) — load-bearing for
future SP-15f. All 3 read functions confirmed tenant-scoped in SQL (not
Python-side filtering). `get_secret_payload` confirmed calling the real
Task 1 `crypto.decrypt` + Task 2 `SECRET_PAYLOAD_ADAPTER`, no
reimplementation. 12/12 tests passing (real SQLite, real IntegrityError,
real AES-GCM round-trip for all 5 payload kinds incl. both `api_key`
placements). `progress.md` verified NOT reverted this round.

Base Task 5: 55d4da4
Task 5: complete (commit f8fbab5, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical, 0 Important, 1 Minor
plan-mandated — `app.secrets` import block in `main.py` breaks strict
alphabetical order vs. `app.schemas_routes`, but this exact placement is
verbatim from the plan's own code block, not an implementer deviation;
flagged only in case an isort/ruff check is part of CI). Response model
`ConnectorSecretOut` confirmed exactly 5 fields (id/name/kind/createdAt/
updatedAt), no ciphertext/nonce/value ever reachable. Only 3 routes exist
(POST/GET/DELETE, no GET-by-id, no PUT). `_require_admin` confirmed local
to routes.py, not extracted to a shared module. Audit payloads confirmed
carrying only name/kind (id via separate object_id param), verified against
real committed AuditLog rows via a fresh session. `CORE_SECRETS_MASTER_KEY`
test default confirmed correctly placed in conftest.py before any test
module imports app.main. Eager `load_master_key()` confirmed as the literal
next statement after `observability.setup()`, before any DB engine work.
Reviewer flagged 4 ⚠️ items resolved by cross-referencing this ledger's
earlier task reviews: repo tenant_id SQL-level filtering (Task 4 review),
crypto.load_master_key() KeyError behavior (Task 1 review/tests), layering
lint clean (Task 5's own full-suite run: 1075 passed/127 skipped/0 failed,
0 new failures), and `(tenant_id, name)` DB unique constraint existing
(Task 3 review — confirmed present, so the route's check-then-insert has a
DB backstop; a concurrent duplicate-name race would surface as an unhandled
500 rather than a clean 409, a narrow non-security edge case flagged for
the final review, not blocking). 12/12 new tests passing, full suite 1075
passed/127 skipped/0 failed (+24 tests vs. Task 4's 1051/127 baseline —
12 new + presumably some Task 3/4 interaction, no regressions), `lint-imports`
1 kept/0 broken. `progress.md` verified NOT reverted this round.

## 5 tâches de SP-15e complètes. Passage à la revue finale de branche.

## Revue finale de branche (opus, 69e675a..f8fbab5, 5 commits)

**Ready to merge: With fixes.** Toutes les contraintes globales vérifiées
sur l'ensemble du diff — invariants de sécurité tracés sur les 4 surfaces
de fuite possibles (réponse HTTP, message d'erreur, payload audit, logs) et
confirmés étanches ; isolation tenant confirmée au niveau SQL ; layering
import-linter confirmé cohérent avec les imports réels de `routes.py` ;
discipline de périmètre confirmée exacte (aucun outil MCP, aucun kind
BuilderConfig, aucun refactor du helper admin partagé, aucun câblage
consommateur SP-12/SP-15).

**1 Important trouvé et corrigé avant merge** : `CORE_SECRETS_MASTER_KEY`
non documenté dans `.env.example` et non câblé dans `docker-compose.yml` —
le nouveau check eager de `create_app()` (`secrets_crypto.load_master_key()`,
`KeyError` si absent) ferait boucler en crash le conteneur `core` sur le
chemin documenté `docker compose up -d` (CLAUDE.md). Gap plan-mandated (le
plan reconnaissait la nécessité opérateur sans jamais la matérialiser dans
le diff).

**2 Minor triés** : race check-then-insert sur nom dupliqué (500 au lieu de
409 sous concurrence, contrainte DB déjà correcte — corrigé
opportunément) ; perte du offset timezone après round-trip DB sur
`createdAt`/`updatedAt` (cosmétique, colonne `DateTime` non `timezone=True`,
non corrigé — hors périmètre, pas de fuite) ; ordre d'import non-alphabétique
dans `main.py` et annotation `TypeAdapter` non paramétrée dans `schemas.py`
(les deux verbatim du plan, non bloquants, CI ne fait pas tourner
isort/ruff-isort ici).

**Fix appliqué** (1 seul fix subagent couvrant les 2 points ensemble,
commit `d958d9b`) : `CORE_SECRETS_MASTER_KEY` documenté dans `.env.example`
(hint `openssl rand -base64 32`, valeur vide committée, pas de vraie clé) +
câblé dans `docker-compose.yml` (`core.environment`, sans défaut silencieux
— `${CORE_SECRETS_MASTER_KEY}` pas `${...:-x}`) ; `docker-compose.prod.yml`
confirmé NE PAS avoir besoin d'entrée séparée (`docker compose config`
validé base+prod fusionné, la var traverse par map-merge de compose) ;
`create_secret_route` : `IntegrityError` sur l'insert désormais traduite en
`HTTPException(409, ...)` identique au pre-check existant (conservé comme
fast-path), nouveau test `test_create_concurrent_duplicate_race_returns_409`
qui contourne réellement le pre-check (monkeypatch `get_secret_by_name` →
`None`) pour forcer le chemin `IntegrityError` réel. 13/13 tests du fichier
cible (12 existants + 1 nouveau), suite complète 1076 passed/127 skipped/0
failed, `lint-imports` 1 kept/0 broken.

**Re-revue du fix (opus, f8fbab5..d958d9b)** : les 2 findings marqués
Resolved indépendamment — reviewer a vérifié la valeur vide de la clé
(pas de vraie clé committée), l'absence de défaut silencieux dans compose,
que `docker-compose.prod.yml` n'a pas été touché (le report de validation
`docker compose config` pris comme preuve, cohérent avec le comportement de
merge documenté), le rollback de session confirmé via le pattern
`request_scoped_session` existant (pas de rollback explicite nécessaire
dans la route elle-même, le `except Exception: rollback()` du context
manager de session couvre le cas), le pre-check confirmé toujours en place
(le fix est un backstop, pas un remplacement), et le nouveau test confirmé
exercer réellement le vrai chemin `IntegrityError` (pas un re-test du
pre-check) — reviewer a lui-même exécuté `pytest tests/test_secrets_routes.py`
et confirmé 13 passed. Aucun nouveau problème introduit. **Ready to merge:
Yes.**

## SP-15e READY TO MERGE — HEAD=d958d9b, 6 commits (5 tâches + 1 fix de
revue finale sur 2 findings, 1 seul round de fix). 0 Critical/Important non
résolu sur l'ensemble de la branche. Nouveau module `core/app/secrets/`
(crypto AES-256-GCM, schémas Pydantic discriminés 5 kinds, modèle
`connector_secrets` + migration 0019, repository CRUD + decrypt-on-demand,
routes REST POST/GET/DELETE admin-only auditées) prêt à servir de fondation
pour de futurs consommateurs (SP-12 harvest connectors, SP-15 pipelines,
SP-15f exposition MCP des noms de secrets) sans qu'aucun de ces
consommateurs ne soit construit par ce plan. Prêt pour
`superpowers:finishing-a-development-branch`.
