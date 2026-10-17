# SP-L1a « Socle d'exécution » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fermer AUD-015, AUD-025, AUD-026, AUD-027 de l'audit `docs/revue/audit-2026-10-16/99-synthese.md` (lot L1a) : schéma procrastinate migrable, `defer()` qui n'orpheline plus de run/job, run vivant non déclaré périmé, jobs longs non tués brutalement.

**Architecture:** un helper unique `app/jobs/defer.py` (retry court puis 503) consommé par les 8 routes jumelles ; pour les pipelines, un échec définitif de mise en file marque le run `failed` tout de suite (plus de 409 pendant 60 min) ; un battement de cœur (`pipeline_runs.heartbeat_at`, thread du worker) remplace l'ancrage sur `started_at` du balayage ; arrêt gracieux par `stop_grace_period`/`terminationGracePeriodSeconds` + `preStop`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, procrastinate 3.9.0, pytest (DSN de test `postgresql+psycopg://`), docker-compose, Helm.

## Global Constraints

- `CORE_TEST_DATABASE_URL` doit pointer un postgis-test réel (sinon les tests `postgis` skippent) ; DSN en `postgresql+psycopg://`.
- Piège n°14 : lister les jumelles avant de clore chaque correctif (liste en Task 2).
- Migration Alembic : `tenant_id`/audit inchangés ; tester `upgrade`/`downgrade` sur base non vide (piège n°8). Prochaine révision : `0082` (head actuel `0081_geocode_jobs`).
- Régénérer OpenAPI + types TS si une route/un modèle exposé change (diff vide attendu ici : aucun champ exposé).
- Commits conventional en français, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Clôture : une ligne dans `CLAUDE.md § Livré`, entrée dans `docs/superpowers/2026-08-27-historique-execution-continu.md`, AUD-015/025/026/027 marqués fermés dans `docs/revue/2026-09-04-backlog.md` ; `scripts/check_claude_md_size.py` doit passer.

---

### Task 1: AUD-015 — migrer le schéma procrastinate au lieu de l'appliquer une fois

**Files:**
- Modify: `core/scripts/ensure_procrastinate_schema.py`
- Test: `core/tests/test_ensure_procrastinate_schema.py`

**Interfaces:**
- Produces: `ensure_schema(conninfo: str) -> list[str]` (noms des migrations appliquées) ; `main()` l'appelle. Table de suivi `gs_procrastinate_migrations(name text primary key, applied_at timestamptz default now())`.

Faits vérifiés : procrastinate 3.9.0 fournit `SchemaManager.get_migrations_path()` (dossier de `NN.NN.NN_NN_pre_*.sql` / `NN.NN.NN_50_post_*.sql`) mais aucune table de suivi. Ordre = tri lexicographique des noms (c'est la convention documentée : pre avant le déploiement du code, post après ; ici le worker est le seul consommateur et s'arrête pendant le démarrage, donc on applique tout dans l'ordre).

Baseline pour une base existante sans table de suivi : on ne connaît pas la version d'origine. On déduit par sondes (une migration est « déjà appliquée » si son artefact existe) — table `procrastinate_workers` ⇒ migrations ≤ `03.01.00` ; fonction `procrastinate_retry_failed_job_v1` ⇒ ≤ `03.04.00` (**l'implémenteur vérifie les noms réels d'artefact dans les `.sql` avant de coder** ; si une sonde n'est pas fiable, enregistrer comme baseline tout ce qui est antérieur à la première migration dont l'artefact manque).

- [ ] **Step 1: Test qui échoue** — dans `test_ensure_procrastinate_schema.py`, ajouter :

```python
@pytest.mark.postgis
def test_ensure_schema_applies_missing_migrations_once(pg_engine, monkeypatch):
    """Base au schéma ancien (sans suivi) : la 1re passe applique le manquant,
    la 2e n'applique rien."""
    from sqlalchemy import text

    from scripts.ensure_procrastinate_schema import ensure_schema

    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    with pg_engine.begin() as c:  # simule un schéma 3.0 : retire l'artefact heartbeat et le suivi
        c.execute(text("DROP TABLE IF EXISTS gs_procrastinate_migrations"))
        c.execute(text("DROP TABLE IF EXISTS procrastinate_workers CASCADE"))
    ensure_schema(conninfo)  # amorce (schéma déjà là) puis migre
    with pg_engine.begin() as c:
        assert c.execute(text("SELECT to_regclass('procrastinate_workers')")).scalar() is not None
    assert ensure_schema(conninfo) == []
```

- [ ] **Step 2:** `cd core && CORE_TEST_DATABASE_URL=... uv run pytest tests/test_ensure_procrastinate_schema.py -v` → FAIL (`ImportError: ensure_schema`).

- [ ] **Step 3: Implémenter** — dans `ensure_procrastinate_schema.py` : remplacer `main()` par

```python
def _migration_files() -> list[Path]:
    from procrastinate.schema import SchemaManager

    return sorted(Path(SchemaManager.get_migrations_path()).glob("*.sql"))


def ensure_schema(conninfo: str) -> list[str]:
    """Applique le schéma s'il manque, puis les migrations procrastinate pas
    encore suivies. Idempotent. Retourne les noms de migrations appliquées."""
    import psycopg

    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext('gs_procrastinate_schema'))")
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS gs_procrastinate_migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            fresh = not schema_is_applied(conninfo)
            if fresh:
                app = procrastinate.App(
                    connector=procrastinate.PsycopgConnector(
                        conninfo=conninfo, kwargs=dict(CONNECTION_KWARGS)
                    )
                )
                with app.open():
                    app.schema_manager.apply_schema()  # schéma courant = toutes les migrations incluses
            seen = {r[0] for r in conn.execute("SELECT name FROM gs_procrastinate_migrations")}
            files = _migration_files()
            if fresh or (not seen and _baseline_names(conn, files)):
                baseline = [f.name for f in files] if fresh else _baseline_names(conn, files)
                for n in baseline:
                    conn.execute(
                        "INSERT INTO gs_procrastinate_migrations(name) VALUES (%s) "
                        "ON CONFLICT DO NOTHING",
                        (n,),
                    )
                seen |= set(baseline)
            applied = []
            for f in files:
                if f.name in seen:
                    continue
                conn.execute(f.read_text())
                conn.execute("INSERT INTO gs_procrastinate_migrations(name) VALUES (%s)", (f.name,))
                applied.append(f.name)
            return applied
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext('gs_procrastinate_schema'))")


def _baseline_names(conn, files: list[Path]) -> list[str]:
    """Base ancienne sans suivi : migrations dont l'artefact existe déjà."""
    # ponytail: deux sondes (workers 03.01.00, retry_failed_job 03.04.00) ; une
    # migration future non sondée sera rejouée — la rendre idempotente ou ajouter une sonde.
    probes = {
        "03.01.00": "SELECT to_regclass('procrastinate_workers') IS NOT NULL",
        "03.04.00": "SELECT to_regproc('procrastinate_retry_failed_job_v1') IS NOT NULL",
    }
    present = {v: conn.execute(q).fetchone()[0] for v, q in probes.items()}
    out = []
    for f in files:
        v = f.name[:8]
        if v < "03.01.00" or present.get(v, False):
            out.append(f.name)
    return out


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    applied = ensure_schema(database_url)
    print(f"procrastinate: schéma à jour ({len(applied)} migration(s) appliquée(s)).")
```
(ajouter `from pathlib import Path`.) Corriger ensuite les sondes d'après les `.sql` réels (note ci-dessus) et faire passer `test_running_main_twice_never_raises`.

- [ ] **Step 4:** relancer le fichier de test → PASS. `uv run ruff check . && uv run ruff format --check .`
- [ ] **Step 5: Commit** — `fix(core): le schéma procrastinate est migré, plus seulement appliqué une fois (AUD-015)`

---

### Task 2: AUD-025 — `defer()` résilient, run non orphelin

**Files:**
- Create: `core/app/jobs/defer.py`
- Modify: `core/app/pipelines/service.py` (`default_task_deferrer`, `run_pipeline_service`, `retry_pipeline_run_service`), `core/app/pipelines/jobs.py:488` (balayage cron), `core/app/export/routes.py`, `core/app/appexport/routes.py`, `core/app/raster/routes.py`, `core/app/terrain3d/routes.py`, `core/app/tileset3d/routes.py`, `core/app/dataexport/routes.py`, `core/app/ingestion/routes.py` (les 7 deferrers « `X.defer(job_id=…, tenant_id=…)` »)
- Test: `core/tests/test_defer_resilient.py`, `core/tests/test_pipeline_defer_failure.py`

**Interfaces:**
- Produces: `defer_resilient(call: Callable[[], None], *, attempts: int = 3, delay: float = 0.2) -> None` — rejoue `call` avec attente croissante, puis lève `HTTPException(503, "File de jobs indisponible, réessayez.")`.

Jumelles listées (piège n°14) : les 8 sites de la ligne AUD-025 + `mcp/tools/pipelines.py:106` (passe par `run_pipeline_service`, couvert) + `alerts/service.py:73`, `geocoding/routes.py:138`, `harvest/routes.py:149`, `quality/routes.py:87`, `compliance/routes.py:88` (hors AUD-025 : les noter dans le backlog, ne pas les traiter ici).

- [ ] **Step 1: Test du helper** (`test_defer_resilient.py`)

```python
import pytest
from fastapi import HTTPException

from app.jobs.defer import defer_resilient


def test_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("pool fermé")

    defer_resilient(flaky, delay=0)
    assert len(calls) == 3


def test_gives_up_with_503():
    def down():
        raise RuntimeError("down")

    with pytest.raises(HTTPException) as e:
        defer_resilient(down, delay=0)
    assert e.value.status_code == 503
```

- [ ] **Step 2:** `uv run pytest tests/test_defer_resilient.py` → FAIL (module absent).
- [ ] **Step 3: Implémenter** `core/app/jobs/defer.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""`.defer()` procrastinate tolérant aux pannes brèves du pool (AUD-025)."""

import logging
import time
from collections.abc import Callable

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def defer_resilient(call: Callable[[], None], *, attempts: int = 3, delay: float = 0.2) -> None:
    for i in range(attempts):
        try:
            call()
            return
        except Exception:
            logger.warning("defer échoué (tentative %d/%d)", i + 1, attempts, exc_info=True)
            if i + 1 < attempts:
                time.sleep(delay * 2**i)
    raise HTTPException(status_code=503, detail="File de jobs indisponible, réessayez.")
```

- [ ] **Step 4:** test vert. Puis dans chacun des 7 deferrers non-pipeline, envelopper : `defer_resilient(lambda: X.defer(job_id=job_id, tenant_id=tenant_id))` (garder le comportement ; les balayages de reprise existants ramassent la ligne laissée `pending`).
- [ ] **Step 5: Test pipeline** (`test_pipeline_defer_failure.py`, marqueur `postgis`, patron de `tests/test_reclaim_pending_jobs.py`) : créer un pipeline, appeler `run_pipeline_service(..., defer_task=lambda *_: (_ for _ in ()).throw(RuntimeError("down")))` → attend `HTTPException` 503, le run est `failed` avec `error` contenant « mise en file », et un 2e `run_pipeline_service` avec un deferrer sain **réussit** (pas de 409).
- [ ] **Step 6: Implémenter** dans `pipelines/service.py` : remplacer `defer_task(run.id, user.tenant_id)` (et son jumeau dans `retry_pipeline_run_service`) par

```python
    try:
        defer_resilient(lambda: defer_task(run.id, user.tenant_id))
    except HTTPException:
        pipelines_repo.mark_failed(
            session, run_id=run.id, error="mise en file impossible : file de jobs indisponible"
        )
        session.commit()
        raise
```
Et dans `default_task_deferrer` laisser l'appel nu (la résilience est au site d'appel, pas dedans, pour ne pas la doubler). Dans `pipelines/jobs.py` (balayage cron, autour de la ligne 488) : `try: run_pipeline_task.defer(...) except Exception: mark_failed(...) ; commit ; logger.exception(...)` puis continuer la boucle.
- [ ] **Step 7:** `uv run pytest tests/test_pipeline_defer_failure.py tests/test_pipeline_jobs.py tests/test_jobs_api_defer_real.py -v` → PASS ; lancer aussi les tests de routes des 7 domaines (`-k "export or raster or terrain3d or tileset3d or dataexport or ingestion"`).
- [ ] **Step 8: Commit** — `fix(core): defer résilient et run marqué échoué si la file est indisponible (AUD-025)`

---

### Task 3: AUD-026 — battement de cœur des runs de pipeline

**Files:**
- Create: `core/alembic/versions/0082_pipeline_run_heartbeat.py`
- Modify: `core/app/pipelines/models.py` (colonne), `core/app/pipelines/repository.py` (`reclaim_stuck_runs`, nouveau `touch_heartbeat`), `core/app/pipelines/jobs.py` (`run_pipeline_task`)
- Test: `core/tests/test_pipeline_heartbeat.py`

**Interfaces:**
- Produces: `PipelineRun.heartbeat_at: datetime | None` ; `pipelines_repo.touch_heartbeat(session, *, run_id: str) -> None` ; `reclaim_stuck_runs` ancre un run `running|cancel_requested` sur `coalesce(heartbeat_at, started_at)`.

- [ ] **Step 1: Test** (`postgis` ou sqlite comme `test_pipeline_jobs.py`, suivre son patron de fixtures) : (a) run `running` avec `started_at` = il y a 2 h mais `heartbeat_at` = maintenant → `reclaim_stuck_runs(session)` retourne 0 ; (b) même run avec `heartbeat_at` il y a 2 h → retourne 1 et le run est `failed` ; (c) `touch_heartbeat` met `heartbeat_at` à ~now.
- [ ] **Step 2:** lancer → FAIL (colonne absente).
- [ ] **Step 3:** colonne `heartbeat_at = mapped_column(DateTime, nullable=True)` ; migration 0082 (`op.add_column("pipeline_runs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))`, `downgrade` = `drop_column`) ; `touch_heartbeat` = `UPDATE pipeline_runs SET heartbeat_at=now WHERE id=:id AND status IN ('running','cancel_requested')` ; dans `reclaim_stuck_runs`, premier `case` : `func.coalesce(PipelineRun.heartbeat_at, PipelineRun.started_at)` ; mettre à jour le commentaire `ponytail:` (le heartbeat existe désormais ; seuil applicable à un worker mort).
- [ ] **Step 4: Thread de battement** dans `run_pipeline_task`, autour de l'appel `run_pipeline(...)` :

```python
stop = threading.Event()

def _beat() -> None:
    while not stop.wait(60):
        try:
            with request_scoped_session(factory) as s:
                pipelines_repo.touch_heartbeat(s, run_id=run_id)
        except Exception:
            logger.warning("heartbeat run %s échoué", run_id, exc_info=True)

beat = threading.Thread(target=_beat, daemon=True, name=f"hb-{run_id}")
beat.start()
try:
    stats = run_pipeline(...)  # appel existant, inchangé
finally:
    stop.set()
```
(`import threading`.) Un battement échoué est seulement journalisé : le pire cas retombe sur l'ancien comportement.
- [ ] **Step 5: Test migration sur base non vide** (patron `tests/test_migration_0081_geocode_jobs.py`) : upgrade avec des runs existants, colonne `NULL`, downgrade OK.
- [ ] **Step 6:** `uv run pytest tests/test_pipeline_heartbeat.py tests/test_pipeline_jobs.py tests/test_migration_0082*.py -v` ; comparateur modèle↔Alembic (`-k "alembic or model"`) ; `ALTER TABLE pipeline_runs ADD COLUMN heartbeat_at timestamp` manuel sur `postgis-test` si besoin (piège SP-42).
- [ ] **Step 7: Commit** — `fix(core): le balayage ne clôt plus un run vivant grâce au battement de cœur (AUD-026)`

---

### Task 4: AUD-027 — arrêt gracieux des workers

**Files:**
- Modify: `docker-compose.yml` (services `worker`, `export-worker`), `deploy/helm/geostudio/templates/worker.yaml`, `deploy/helm/geostudio/templates/core.yaml`, `deploy/helm/geostudio/values.yaml`, `core/tests/test_deployability.py`
- Create: `deploy/helm/geostudio/templates/pdb.yaml` (si le chart n'en a pas — vérifier avec `grep -rl PodDisruptionBudget deploy/helm`)

**Interfaces:**
- Produces: variable `CORE_WORKER_STOP_GRACE` (défaut `300`, secondes) ; valeurs Helm `worker.terminationGracePeriodSeconds: 300`.

Fait à vérifier d'abord (piège n°3) : procrastinate reçoit SIGTERM et arrête gracieusement (`--shutdown-graceful-timeout`, défaut 30 s) avant d'annuler les jobs. Lire `uv run python -m procrastinate worker --help` et fixer `--shutdown-graceful-timeout` à `CORE_WORKER_STOP_GRACE` moins 30 s de marge.

- [ ] **Step 1: Test de déployabilité qui échoue** (`test_deployability.py`, suivre les règles existantes) : `docker compose config` résolu → `services.worker.stop_grace_period` ≥ `300s` et idem `export-worker` ; le chart Helm rend `terminationGracePeriodSeconds` sur le Deployment worker (si `helm` absent, test skip comme les autres).
- [ ] **Step 2:** lancer → FAIL.
- [ ] **Step 3:** compose : `stop_grace_period: ${CORE_WORKER_STOP_GRACE:-300}s` sur `worker` et `export-worker`, option `--shutdown-graceful-timeout ${CORE_WORKER_GRACEFUL:-270}` dans leur `command:` **sur la même ligne que `worker`** (règle `test_sh_c_commands_have_no_orphan_option_line`) ; documenter les deux variables dans `.env.example` (règle « toute substitution compose est documentée »). Helm : `terminationGracePeriodSeconds: {{ .Values.worker.terminationGracePeriodSeconds }}` + même option de commande ; `PodDisruptionBudget` `maxUnavailable: 1` pour `worker` et `core` si absent.
- [ ] **Step 4:** `uv run pytest tests/test_deployability.py -v` → PASS ; `docker compose config | grep -n stop_grace`.
- [ ] **Step 5: Commit** — `fix(deploy): arrêt gracieux des workers et budget d'interruption (AUD-027)`

---

### Task 5: clôture

- [ ] Revue finale de branche (opus), jumelles de Task 2 relues, `uv run pytest` complet (core), `uv run ruff check . && uv run ruff format --check . && uv run lint-imports`, E2E non concernés (aucun changement shell).
- [ ] Documents : `CLAUDE.md § Livré` (une ligne), historique d'exécution, backlog + synthèse d'audit (AUD-015/025/026/027 fermés ; AUD-029 reste ouvert : le reclaim ne libère toujours pas le slot du job `doing`), bilan de fonctionnalités régénéré si la santé change (`feature_health_cli.py --write`), `scripts/check_claude_md_size.py`.
- [ ] Commit `docs: clôture SP-L1a socle d'exécution`.
