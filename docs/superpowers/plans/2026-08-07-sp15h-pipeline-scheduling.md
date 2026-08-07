# SP-15h — Planification simple des pipelines — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A saved Pipeline can run itself on a recurring cron schedule, authored through a visual (no-cron-syntax-required) editor in the canvas, with zero new REST routes or MCP tools.

**Architecture:** Core: a new `PipelineRefreshPolicy {enabled, cron}` field on `PipelinePayload` (validated with `croniter` at the Pydantic level), a periodic procrastinate sweep task that lists due pipelines (cross-tenant scan of `kind="pipeline"` configs, "last run" derived from the existing `pipeline_runs` table, no new table) and defers `run_pipeline_task` — the exact same execution path as a manual run. Shell: a `PipelineScheduleEditor` component with 3 no-cron presets (interval/daily/weekly) plus a raw-cron escape hatch, wired into `PipelineBuilderPage`'s existing `draft`/`onSave` cycle — no separate save action.

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/procrastinate/croniter (`core/`), React/TypeScript/Vitest/Playwright (`shell/`).

## Global Constraints

- **Reference spec:** `docs/superpowers/specs/2026-08-07-sp15h-pipeline-scheduling-design.md` (read it first — this plan implements it verbatim).
- **No event triggers, no new MCP tool, no new REST route, no `transform.sql`, no gallery template.** `refreshPolicy` transits through the existing generic `PUT /configs/{id}` / `PUT /configs/by-item/{id}` — only `explain_pipeline`'s *output* gains a field, its signature does not change.
- **No separate operational table** (no `PipelineSchedule` à la `HarvestSource`). `refreshPolicy` lives inside the versioned `PipelinePayload` JSON; "last run" is derived from `pipeline_runs` via a new `get_latest_run` lookup — never duplicated into a new column.
- **No Alembic migration** — `refreshPolicy` is an optional field, `None` by default, backward-compatible with every already-saved pipeline.
- **Sweep granularity: 5 minutes**, not to-the-second — same class of limitation already accepted for CDC (10 min) and harvesting (15 min).
- **No "next run at" display in the UI** for this MVP — only the schedule's own fields (mode/cron) and the existing run history.
- **`croniter` becomes a direct dependency** of `core/pyproject.toml` (was already transitive via `procrastinate`).
- Every new/changed Python file keeps the project's `# SPDX-License-Identifier: Apache-2.0` header line.
- Docs/code comments in French, identifiers in English (project convention, `CLAUDE.md`).
- `core` tests run with `cd core && uv run pytest`; `shell` unit tests with `cd shell && npx vitest run <path>`; `shell` E2E with `cd shell && npx playwright test <file>` (auth already mocked via `playwright.config.ts`, no manual env needed).
- Commit after each task, conventional style (`feat(core): …`, `feat(shell): …`), one subject per commit.

---

## Task 1: `PipelineRefreshPolicy` schema + croniter validation

**Files:**
- Modify: `core/pyproject.toml`
- Modify: `core/app/configs/schemas.py`
- Modify: `core/tests/test_pipeline_config_schema.py`

**Interfaces:**
- Consumes: nothing new (pure schema addition).
- Produces: `PipelineRefreshPolicy` class (`core/app/configs/schemas.py`) with fields `enabled: bool`, `cron: str`; `PipelinePayload.refreshPolicy: PipelineRefreshPolicy | None = None`. Later tasks import this as `from app.configs.schemas import PipelineRefreshPolicy`.

- [ ] **Step 1: Add `croniter` as a direct dependency**

In `core/pyproject.toml`, inside the `dependencies = [...]` list of `[project]`, add this entry right after the `"cryptography>=42.0"` block (keep alphabetical-ish grouping consistent with the rest of the file, exact position does not matter — the list is not sorted):

```toml
    "croniter>=6.2",  # SP-15h : validation + calcul du prochain tick pour
                      # refreshPolicy des pipelines ; déjà dépendance
                      # transitive de procrastinate (utilisée en interne par
                      # @app.periodic), déclarée ici en directe car importée
                      # directement par app.configs et app.pipelines.
```

Run:
```bash
cd core && uv sync
```
Expected: completes without error; `core/uv.lock` is updated (git will show it as modified — that's expected, commit it in Step 5).

- [ ] **Step 2: Write the failing tests**

Append to `core/tests/test_pipeline_config_schema.py` (end of file, after `test_pipeline_edge_rejects_unknown_role`):

```python
def test_pipeline_refresh_policy_defaults_to_none():
    config = BuilderConfig.model_validate(_pipeline_body())
    assert config.pipeline.refreshPolicy is None


def test_pipeline_refresh_policy_accepts_valid_cron():
    body = _pipeline_body()
    body["pipeline"]["refreshPolicy"] = {"enabled": True, "cron": "*/15 * * * *"}
    config = BuilderConfig.model_validate(body)
    assert config.pipeline.refreshPolicy.enabled is True
    assert config.pipeline.refreshPolicy.cron == "*/15 * * * *"


def test_pipeline_refresh_policy_rejects_invalid_cron():
    body = _pipeline_body()
    body["pipeline"]["refreshPolicy"] = {"enabled": True, "cron": "not a cron"}
    with pytest.raises(ValidationError, match="invalid cron"):
        BuilderConfig.model_validate(body)


def test_pipeline_refresh_policy_requires_cron_even_when_disabled():
    # cron reste requis même enabled=False : ça permet à l'UI de toujours
    # pré-remplir un cron valide en mémoire quand l'auteur bascule le
    # toggle (design SP-15h §2.1).
    body = _pipeline_body()
    body["pipeline"]["refreshPolicy"] = {"enabled": False}
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: the 3 new tests referencing `refreshPolicy` FAIL with `AttributeError: 'PipelinePayload' object has no attribute 'refreshPolicy'` (first test) or similar — the field does not exist yet.

- [ ] **Step 4: Implement `PipelineRefreshPolicy`**

In `core/app/configs/schemas.py`, add the new class right before `class PipelinePayload(BaseModel):` (i.e. immediately after the closing of `class PipelineEdge`):

```python
class PipelineRefreshPolicy(BaseModel):
    enabled: bool = False
    cron: str

    @model_validator(mode="after")
    def _require_valid_cron(self) -> "PipelineRefreshPolicy":
        import croniter
        if not croniter.croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")
        return self
```

Then add the field to `PipelinePayload`, right after `edges: list[PipelineEdge] = Field(default_factory=list)`:

```python
    refreshPolicy: PipelineRefreshPolicy | None = None
```

`model_validator` is already imported in this file (used by `PipelinePayload._validate_graph` and `BookmarkPayload._require_non_empty_page_id`) — no new top-level import needed beyond the local `import croniter` inside the validator (kept local, matching this file's existing pattern of not needing `croniter` anywhere else at module scope).

- [ ] **Step 5: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: PASS, all tests including the 3 new ones.

Run the full pipeline-adjacent test files to check for regressions:
```bash
cd core && uv run pytest tests/test_pipeline_config_schema.py tests/test_repository.py -v
```
Expected: PASS (no regression — `refreshPolicy` is optional, every existing fixture omits it).

```bash
cd core && git add pyproject.toml uv.lock app/configs/schemas.py tests/test_pipeline_config_schema.py
git commit -m "feat(core): pipelines — PipelineRefreshPolicy schema (SP-15h)"
```

---

## Task 2: `configs_repo.list_configs_by_kind`

**Files:**
- Modify: `core/app/configs/repository.py`
- Modify: `core/tests/test_repository.py`

**Interfaces:**
- Consumes: `app.configs.models.Config`, `app.configs.schemas.BuilderConfig` (existing).
- Produces: `list_configs_by_kind(session: Session, kind: str) -> list[tuple[str, str, BuilderConfig]]` in `core/app/configs/repository.py` — each tuple is `(item_id, tenant_id, config)`. **Not** `ConfigRead` (which has no `tenant_id` field and is used as a public `response_model` elsewhere — deliberately not reused here to avoid ever leaking `tenant_id` through a route). Internal helper, consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_repository.py` (end of file, after `test_get_config_by_item_missing_returns_none`):

```python
def test_list_configs_by_kind_returns_matching_kind_only(session):
    tenant_id = _make_item(session, "item-app")
    repo.create_config(session, _config(kind="app"), item_id="item-app", tenant_id=tenant_id)
    session.add(Item(id="item-pipe", tenant_id=tenant_id, owner_id=session.execute(
        __import__("sqlalchemy").select(Item.owner_id).where(Item.id == "item-app")
    ).scalar_one(), resource_type="pipeline", title="placeholder"))
    session.commit()
    pipeline_config = BuilderConfig.model_validate({
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    })
    repo.create_config(session, pipeline_config, item_id="item-pipe", tenant_id=tenant_id)

    results = repo.list_configs_by_kind(session, kind="pipeline")
    assert [item_id for item_id, _, _ in results] == ["item-pipe"]
    assert results[0][1] == tenant_id
    assert results[0][2].kind == "pipeline"


def test_list_configs_by_kind_returns_empty_when_none_match(session):
    assert repo.list_configs_by_kind(session, kind="pipeline") == []


def test_list_configs_by_kind_returns_latest_revision(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(widget="map"), item_id="item-1", tenant_id=tenant_id)
    repo.update_config(session, created.id, _config(widget="table"), tenant_id=tenant_id)

    results = repo.list_configs_by_kind(session, kind="app")
    assert len(results) == 1
    assert results[0][2].layout.items[0].widget == "table"
```

The first test's `Item` insert reuses the existing tenant's owner rather than introducing a second `_make_item`-style helper (which would create a *second* tenant via `get_or_create_default_tenant` — not needed and would complicate the "same tenant, two kinds" assertion this test wants). Import `Item` is already available in this file (`from app.items.models import Item`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_repository.py -v -k list_configs_by_kind`
Expected: FAIL with `AttributeError: module 'app.configs.repository' has no attribute 'list_configs_by_kind'`.

- [ ] **Step 3: Implement `list_configs_by_kind`**

In `core/app/configs/repository.py`, add this function after `get_config_by_item` and before `update_config`:

```python
def list_configs_by_kind(session: Session, kind: str) -> list[tuple[str, str, BuilderConfig]]:
    """Scan cross-tenant (pas de filtre tenant_id) — réservé aux tâches
    système (balayage périodique, SP-15h), jamais exposé via une route :
    contrairement à ConfigRead (response_model public), le tuple retourné
    porte tenant_id en clair."""
    records = session.scalars(select(Config).where(Config.kind == kind)).all()
    result: list[tuple[str, str, BuilderConfig]] = []
    for record in records:
        if record.item_id is None:
            continue
        revision = _latest_revision(session, record.id)
        if revision is None:
            continue
        result.append((record.item_id, record.tenant_id, BuilderConfig.model_validate(revision.data)))
    return result
```

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_repository.py -v`
Expected: PASS, all tests including the 3 new ones.

```bash
cd core && git add app/configs/repository.py tests/test_repository.py
git commit -m "feat(core): configs — list_configs_by_kind (SP-15h)"
```

---

## Task 3: `pipelines_repo.get_latest_run`

**Files:**
- Modify: `core/app/pipelines/repository.py`
- Modify: `core/tests/test_pipeline_repository.py`

**Interfaces:**
- Consumes: `app.pipelines.models.PipelineRun` (existing).
- Produces: `get_latest_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun | None` in `core/app/pipelines/repository.py`. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_repository.py` (end of file, after `test_append_node_stat_scoped_to_tenant`):

```python
def test_get_latest_run_returns_none_when_no_runs():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        assert repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id) is None


def test_get_latest_run_returns_most_recent():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        second = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        latest = repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        assert latest is not None
        assert latest.id == second.id


def test_get_latest_run_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        assert repo.get_latest_run(s, tenant_id="other-tenant", pipeline_item_id=pipeline_item_id) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v -k get_latest_run`
Expected: FAIL with `AttributeError: module 'app.pipelines.repository' has no attribute 'get_latest_run'`.

- [ ] **Step 3: Implement `get_latest_run`**

In `core/app/pipelines/repository.py`, add this function after `list_runs` and before `mark_running`:

```python
def get_latest_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun | None:
    return session.execute(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    ).scalars().first()
```

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v`
Expected: PASS, all tests including the 3 new ones.

```bash
cd core && git add app/pipelines/repository.py tests/test_pipeline_repository.py
git commit -m "feat(core): pipelines — get_latest_run (SP-15h)"
```

---

## Task 4: `pipelines_repo.list_due_pipelines`

**Files:**
- Modify: `core/app/pipelines/repository.py`
- Modify: `core/tests/test_pipeline_repository.py`

**Interfaces:**
- Consumes: `configs_repo.list_configs_by_kind` (Task 2), `get_latest_run` (Task 3), `PipelineRefreshPolicy` (Task 1).
- Produces: `list_due_pipelines(session: Session) -> list[tuple[str, str]]` in `core/app/pipelines/repository.py` — each tuple is `(item_id, tenant_id)`. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_repository.py` (end of file, after the `get_latest_run` tests added in Task 3). First add two imports at the top of the file, right after `from app.pipelines import repository as repo`:

```python
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
```

Then add a small helper right after the existing `_make_pipeline_item` helper:

```python
def _make_pipeline_config(session, *, tenant_id, item_id, refresh_policy=None):
    body = {
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }
    if refresh_policy is not None:
        body["pipeline"]["refreshPolicy"] = refresh_policy
    config = BuilderConfig.model_validate(body)
    configs_repo.create_config(session, config, item_id=item_id, tenant_id=tenant_id)
```

Then append the tests:

```python
def test_list_due_pipelines_excludes_pipelines_without_refresh_policy():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(s, tenant_id=tenant.id, item_id=item_id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_excludes_disabled_policy():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s, tenant_id=tenant.id, item_id=item_id,
            refresh_policy={"enabled": False, "cron": "*/5 * * * *"},
        )
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_includes_never_run_enabled_pipeline():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s, tenant_id=tenant.id, item_id=item_id,
            refresh_policy={"enabled": True, "cron": "*/5 * * * *"},
        )
        s.commit()
        assert repo.list_due_pipelines(s) == [(item_id, tenant.id)]


def test_list_due_pipelines_excludes_pipeline_not_yet_due():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s, tenant_id=tenant.id, item_id=item_id,
            # cron quotidien a 02:00 ; le run le plus récent vient d'avoir
            # lieu -> le prochain tick est dans le futur, jamais dû.
            refresh_policy={"enabled": True, "cron": "0 2 * * *"},
        )
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_skips_run_already_in_progress():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s, tenant_id=tenant.id, item_id=item_id,
            refresh_policy={"enabled": True, "cron": "*/5 * * * *"},
        )
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        repo.mark_running(s, run_id=run.id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_reclaims_stale_running_run():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s, tenant_id=tenant.id, item_id=item_id,
            refresh_policy={"enabled": True, "cron": "*/5 * * * *"},
        )
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        repo.mark_running(s, run_id=run.id)
        # Simule un run planté depuis longtemps : recule created_at au-delà
        # du délai de reclaim (même seuil que le moissonnage, 60 min).
        run.created_at = datetime.now(timezone.utc) - timedelta(minutes=61)
        s.commit()
        assert repo.list_due_pipelines(s) == [(item_id, tenant.id)]
```

Add the missing imports at the top of `core/tests/test_pipeline_repository.py` (it currently only imports `datetime`-free helpers — check first: the file today has no `datetime` import at all):

```python
from datetime import datetime, timedelta, timezone
```

Add this as the first import line, before `from app.db import ...`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v -k list_due_pipelines`
Expected: FAIL with `AttributeError: module 'app.pipelines.repository' has no attribute 'list_due_pipelines'`.

- [ ] **Step 3: Implement `list_due_pipelines`**

In `core/app/pipelines/repository.py`:

1. Replace the current import block at the top of the file:
```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pipelines.models import PipelineRun
```
with:
```python
import uuid
from datetime import datetime, timedelta, timezone

import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.pipelines.models import PipelineRun
```

2. Add the reclaim constant near `_now()`, mirroring `app/harvest/repository.py`:
```python
_RUNNING_RECLAIM_MINUTES = 60
```

3. Add the function at the end of the file:

```python
def list_due_pipelines(session: Session) -> list[tuple[str, str]]:
    """Balayage cross-tenant des pipelines planifiés dus, consommé par
    run_pipeline_sweep_task (app.pipelines.jobs, SP-15h). "Dernier run"
    dérivé de pipeline_runs (jamais une colonne dupliquée) ; garde de
    concurrence par âge identique à app.harvest.repository.list_due_sources
    (_RUNNING_RECLAIM_MINUTES) — un run resté "running"/"queued" plus vieux
    que ce délai est présumé planté et redevient éligible."""
    now = datetime.now(timezone.utc)
    due: list[tuple[str, str]] = []
    for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="pipeline"):
        payload = config.pipeline
        if payload is None:
            continue
        policy = payload.refreshPolicy
        if policy is None or not policy.enabled:
            continue
        latest = get_latest_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if latest.status in ("queued", "running"):
            if (now - created_at) < timedelta(minutes=_RUNNING_RECLAIM_MINUTES):
                continue
            due.append((item_id, tenant_id))
            continue
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due
```

Layering note: `app.pipelines.repository` importing `app.configs.repository` follows the same allowed direction already used by `app.pipelines.jobs` (which imports `from app.configs import repository as configs_repo` today) — `app.pipelines` sits above `app.configs` in the layered-architecture contract (confirmed by the docstring at the top of `core/app/configs/pipeline_validation.py`).

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v`
Expected: PASS, all tests including the 6 new ones.

Run the import-linter to confirm no layering violation was introduced:
```bash
cd core && uv run lint-imports
```
Expected: PASS (`app.pipelines` importing `app.configs` is an already-allowed direction).

```bash
cd core && git add app/pipelines/repository.py tests/test_pipeline_repository.py
git commit -m "feat(core): pipelines — list_due_pipelines (SP-15h)"
```

---

## Task 5: `run_pipeline_sweep_task`

**Files:**
- Modify: `core/app/pipelines/jobs.py`
- Create: `core/tests/test_pipeline_sweep.py`

**Interfaces:**
- Consumes: `list_due_pipelines` (Task 4), `is_read_only_mode`/`is_etl_enabled` (`app.auth.dependency`, existing), `pipelines_repo.create_run` (existing), `run_pipeline_task` (existing).
- Produces: `run_pipeline_sweep_task` procrastinate task (queue `"etl"`, `@app.periodic(cron="*/5 * * * *")`) in `core/app/pipelines/jobs.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_sweep.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""run_pipeline_sweep_task (SP-15h) : balayage périodique des pipelines
planifiés. Pure SQLite (pas de postgis) — ce test vérifie la décision
"faut-il créer/déferer un run", pas l'exécution réelle d'un pipeline
(déjà couverte par test_pipeline_jobs.py::run_pipeline_task, postgis-marqué).
run_pipeline_task.defer est monkeypatché : le sweep n'a besoin de PROUVER
que run_pipeline_task a été sollicité avec les bons arguments, jamais de le
laisser tourner pour de vrai ici."""
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _pipeline_body(refresh_policy=None):
    body = {
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }
    if refresh_policy is not None:
        body["pipeline"]["refreshPolicy"] = refresh_policy
    return body


def _seed_due_pipeline(session, *, tenant_id, owner_id, item_id="pipe-1"):
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="pipeline", title="P",
    )
    config = BuilderConfig.model_validate(
        _pipeline_body({"enabled": True, "cron": "*/5 * * * *"})
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_sweep_defers_run_pipeline_task_for_a_due_pipeline(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert len(deferred) == 1
    assert deferred[0]["tenant_id"] == tenant.id
    with Session() as s:
        run = pipelines_repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        assert run is not None
        assert run.status == "queued"
        assert run.id == deferred[0]["run_id"]


def test_sweep_defers_nothing_when_no_pipeline_is_due(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="P",
        )
        config = BuilderConfig.model_validate(_pipeline_body())  # pas de refreshPolicy
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_short_circuits_in_read_only_mode(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_short_circuits_when_etl_disabled(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: False)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []
```

This test monkeypatches a not-yet-existing `pipeline_jobs._session_factory` helper — Step 3 introduces it (factored out of `run_pipeline_task`'s inline engine/session-factory construction so both tasks share one seam, and so this test can point it at the SQLite fixture instead of `DATABASE_URL`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_sweep.py -v`
Expected: FAIL — `AttributeError: module 'app.pipelines.jobs' has no attribute 'run_pipeline_sweep_task'` (and, once that's added, `has no attribute '_session_factory'`).

- [ ] **Step 3: Implement `run_pipeline_sweep_task`**

In `core/app/pipelines/jobs.py`:

1. Add to the imports (after `from app.configs.schemas import PipelinePayload`):
```python
from app.auth.dependency import is_etl_enabled, is_read_only_mode
```

2. Factor out a `_session_factory()` helper — add it right after the existing `logger = logging.getLogger(__name__)` line:
```python
def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)
```

3. In `run_pipeline_task`, replace its first two lines:
```python
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)
```
with:
```python
    session_factory = _session_factory()
```

4. Add the new task at the end of the file, after `run_pipeline_task`:

```python
@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def run_pipeline_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de planification de pipelines ignoré")
        return
    if not is_etl_enabled():
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = pipelines_repo.list_due_pipelines(session)
        for item_id, tenant_id in due:
            run = pipelines_repo.create_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)
            run_pipeline_task.defer(run_id=run.id, tenant_id=tenant_id)
```

The `is_etl_enabled()` guard here is load-bearing and specific to this task: REST/MCP routes are only *mounted* when `CORE_ETL_ENABLED` is on (gate happens once, at app construction), and `run_pipeline_task` is never enqueued except through those already-gated paths — but `@app.periodic` registers and fires independently of that flag. Without this explicit check, the sweep would keep creating runs even on an instance with `CORE_ETL_ENABLED=false`.

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_pipeline_sweep.py -v`
Expected: PASS, all 4 tests.

Run the existing pipeline jobs test file to confirm the `_session_factory` refactor didn't break `run_pipeline_task` (this one is postgis-marked — skip is fine if docker is unavailable, but if it is available, run it):
```bash
cd core && uv run pytest tests/test_pipeline_jobs.py -v
```
Expected: PASS (or SKIPPED if no docker/postgis — either is fine, it must not FAIL).

```bash
cd core && git add app/pipelines/jobs.py tests/test_pipeline_sweep.py
git commit -m "feat(core): pipelines — run_pipeline_sweep_task (SP-15h)"
```

---

## Task 6: `explain_pipeline` surfaces `refreshPolicy`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Modify: `core/tests/test_mcp_tools_pipeline.py`

**Interfaces:**
- Consumes: `PipelineRefreshPolicy` (Task 1).
- Produces: `explain_pipeline`'s response dict gains a `"refreshPolicy"` key (`dict | None`). No signature change (still takes only `pipelineId`).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_mcp_tools_pipeline.py`, after `test_explain_pipeline_by_owner_succeeds`:

```python
def test_explain_pipeline_includes_refresh_policy_when_set(app_client):
    client = app_client(etl_enabled=True)
    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))

        # refreshPolicy n'est pas un argument de create_pipeline (design
        # SP-15h §4 : transite par le PATCH de config générique, pas un
        # nouvel outil) — on le pose directement via configs_repo, comme le
        # ferait PUT /configs/by-item/{id}. model_validate (pas model_copy)
        # est nécessaire ici : model_copy(update=...) n'exécute aucun
        # validateur, donc refreshPolicy resterait un dict brut sans
        # .model_dump() — exactement ce qu'explain_pipeline appellerait et
        # ferait planter.
        with client.session_factory() as session:
            config = configs_repo.get_config_by_item(session, created["pk"])
            payload_dict = config.config.pipeline.model_dump(by_alias=True)
            payload_dict["refreshPolicy"] = {"enabled": True, "cron": "*/15 * * * *"}
            payload = PipelinePayload.model_validate(payload_dict)
            new_config = BuilderConfig(version=1, kind="pipeline", pipeline=payload)
            configs_repo.update_config(session, config.id, new_config, tenant_id=client.tenant.id)
            session.commit()

        result = call_tool(client, "explain_pipeline", {"pipelineId": created["pk"]})

    assert result["refreshPolicy"] == {"enabled": True, "cron": "*/15 * * * *"}


def test_explain_pipeline_refresh_policy_is_none_when_unset(app_client):
    client = app_client(etl_enabled=True)
    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))
        result = call_tool(client, "explain_pipeline", {"pipelineId": created["pk"]})

    assert result["refreshPolicy"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_pipeline.py -v -k refresh_policy`
Expected: FAIL — `test_explain_pipeline_refresh_policy_is_none_when_unset` fails with `KeyError: 'refreshPolicy'`; `test_explain_pipeline_includes_refresh_policy_when_set` fails the same way.

- [ ] **Step 3: Implement the field**

In `core/app/mcp/tools.py`, inside `explain_pipeline`, change the `return` statement:

```python
                return {
                    "title": item.title,
                    "nodes": [
                        {"id": n.id, "kind": n.kind, "op": n.op, "title": n.title}
                        for n in payload.nodes
                    ],
                    "edges": [{"from": e.from_, "to": e.to} for e in payload.edges],
                }
```
to:
```python
                return {
                    "title": item.title,
                    "nodes": [
                        {"id": n.id, "kind": n.kind, "op": n.op, "title": n.title}
                        for n in payload.nodes
                    ],
                    "edges": [{"from": e.from_, "to": e.to} for e in payload.edges],
                    "refreshPolicy": payload.refreshPolicy.model_dump() if payload.refreshPolicy else None,
                }
```

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd core && uv run pytest tests/test_mcp_tools_pipeline.py -v`
Expected: PASS, all tests including the 2 new ones.

```bash
cd core && git add app/mcp/tools.py tests/test_mcp_tools_pipeline.py
git commit -m "feat(core): mcp — explain_pipeline surfaces refreshPolicy (SP-15h)"
```

---

## Task 7: shell types — `PipelineRefreshPolicy`

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Consumes: nothing (pure type addition, mirrors Task 1's Pydantic shape).
- Produces: `PipelineRefreshPolicy` type; `PipelinePayload.refreshPolicy?: PipelineRefreshPolicy | null`. Consumed by Task 8/9.

No test file — this is a pure type-only change (TypeScript's `tsc --noEmit`, run in Task 9's build check, is the verification for type changes with no runtime behavior of their own).

- [ ] **Step 1: Add the type**

In `shell/src/api/types.ts`, add right after `export type PipelineEdge = {...};` and before `export type PipelinePayload = {...};`:

```typescript
export type PipelineRefreshPolicy = {
  enabled: boolean;
  cron: string;
};
```

- [ ] **Step 2: Add the field to `PipelinePayload`**

Change:
```typescript
export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
};
```
to:
```typescript
export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  refreshPolicy?: PipelineRefreshPolicy | null;
};
```

- [ ] **Step 3: Verify the project still typechecks, then commit**

Run: `cd shell && npx tsc --noEmit`
Expected: no new errors (existing `PipelinePayload` literals across the codebase — e.g. in tests — omit `refreshPolicy`, which is fine since the field is optional).

```bash
cd shell && git add src/api/types.ts
git commit -m "feat(shell): pipelines — PipelineRefreshPolicy type (SP-15h)"
```

---

## Task 8: `PipelineScheduleEditor` component

**Files:**
- Create: `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`
- Create: `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx`

**Interfaces:**
- Consumes: `PipelineRefreshPolicy` (Task 7).
- Produces: `PipelineScheduleEditor` React component (props: `value: PipelineRefreshPolicy | null`, `onChange: (next: PipelineRefreshPolicy | null) => void`); exported helpers `parseCron(cron: string): ScheduleForm` and `compileCron(form: ScheduleForm): string`; exported type `ScheduleForm`. Consumed by Task 9.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { PipelineRefreshPolicy } from "../../api/types";
import { PipelineScheduleEditor, compileCron, parseCron } from "./PipelineScheduleEditor";

test("parseCron recognizes the interval preset", () => {
  expect(parseCron("*/15 * * * *")).toEqual({ mode: "interval", minutes: "15" });
});

test("parseCron recognizes the daily preset", () => {
  expect(parseCron("0 2 * * *")).toEqual({ mode: "daily", time: "02:00" });
});

test("parseCron recognizes the weekly preset", () => {
  expect(parseCron("30 9 * * 1")).toEqual({ mode: "weekly", day: "1", time: "09:30" });
});

test("parseCron falls back to advanced for an unrecognized cron", () => {
  expect(parseCron("0 0 1 * *")).toEqual({ mode: "advanced", raw: "0 0 1 * *" });
});

test("compileCron round-trips each preset", () => {
  expect(compileCron({ mode: "interval", minutes: "10" })).toBe("*/10 * * * *");
  expect(compileCron({ mode: "daily", time: "02:00" })).toBe("0 2 * * *");
  expect(compileCron({ mode: "weekly", day: "1", time: "09:30" })).toBe("30 9 * * 1");
  expect(compileCron({ mode: "advanced", raw: "0 0 1 * *" })).toBe("0 0 1 * *");
});

test("toggle off by default, no fields shown when value is null", () => {
  render(<PipelineScheduleEditor value={null} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Planification automatique")).not.toBeChecked();
  expect(screen.queryByLabelText("Mode de planification")).not.toBeInTheDocument();
});

test("checking the toggle for the first time enables with a default cron", async () => {
  const onChange = vi.fn();
  render(<PipelineScheduleEditor value={null} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Planification automatique"));
  expect(onChange).toHaveBeenCalledWith({ enabled: true, cron: "*/15 * * * *" });
});

test("switching to daily mode and setting a time compiles the expected cron", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "daily");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "0 2 * * *" });
});

test("existing daily cron opens pre-filled in daily mode", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 2 * * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("daily");
  expect(screen.getByLabelText("Heure d'exécution")).toHaveValue("02:00");
});

test("an unrecognized existing cron opens in advanced mode with the raw value intact", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("advanced");
  expect(screen.getByLabelText("Expression cron")).toHaveValue("0 0 1 * *");
});

test("an invalid advanced cron shows an inline error", async () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  await userEvent.clear(screen.getByLabelText("Expression cron"));
  await userEvent.type(screen.getByLabelText("Expression cron"), "not a cron");
  expect(screen.getByRole("alert")).toHaveTextContent("Format cron invalide");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx`
Expected: FAIL — module `./PipelineScheduleEditor` does not exist yet.

- [ ] **Step 3: Implement the component**

Create `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { PipelineRefreshPolicy } from "../../api/types";

export type ScheduleForm =
  | { mode: "interval"; minutes: string }
  | { mode: "daily"; time: string }
  | { mode: "weekly"; day: string; time: string }
  | { mode: "advanced"; raw: string };

const DAY_LABELS = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
const ADVANCED_CRON_RE = /^\S+\s+\S+\s+\S+\s+\S+\s+\S+$/;
const INTERVAL_RE = /^\*\/(\d+) \* \* \* \*$/;
const DAILY_RE = /^(\d{1,2}) (\d{1,2}) \* \* \*$/;
const WEEKLY_RE = /^(\d{1,2}) (\d{1,2}) \* \* (\d)$/;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// Presets généré/reconnus par interpolation/regex simple — aucune librairie
// cron JS ajoutée (design SP-15h §5). Un cron qui ne matche aucun des 3
// presets ouvre en mode "avancé" avec la valeur brute intacte, sans perte,
// y compris pour un cron écrit à la main via MCP/REST.
export function parseCron(cron: string): ScheduleForm {
  const interval = cron.match(INTERVAL_RE);
  if (interval) return { mode: "interval", minutes: interval[1] };
  const weekly = cron.match(WEEKLY_RE);
  if (weekly) {
    return { mode: "weekly", day: weekly[3], time: `${pad(Number(weekly[2]))}:${pad(Number(weekly[1]))}` };
  }
  const daily = cron.match(DAILY_RE);
  if (daily) return { mode: "daily", time: `${pad(Number(daily[2]))}:${pad(Number(daily[1]))}` };
  return { mode: "advanced", raw: cron };
}

function splitTime(time: string): [string, string] {
  const [h, m] = time.split(":");
  return [String(parseInt(h, 10) || 0), String(parseInt(m, 10) || 0)];
}

export function compileCron(form: ScheduleForm): string {
  switch (form.mode) {
    case "interval": {
      const n = Math.max(1, parseInt(form.minutes, 10) || 1);
      return `*/${n} * * * *`;
    }
    case "daily": {
      const [h, m] = splitTime(form.time);
      return `${m} ${h} * * *`;
    }
    case "weekly": {
      const [h, m] = splitTime(form.time);
      return `${m} ${h} * * ${form.day}`;
    }
    case "advanced":
      return form.raw;
  }
}

export function PipelineScheduleEditor({
  value, onChange,
}: {
  value: PipelineRefreshPolicy | null;
  onChange: (next: PipelineRefreshPolicy | null) => void;
}) {
  const enabled = value?.enabled ?? false;
  const cron = value?.cron ?? "*/15 * * * *";
  const form = parseCron(cron);

  function setEnabled(next: boolean) {
    onChange({ enabled: next, cron });
  }
  function setForm(next: ScheduleForm) {
    onChange({ enabled, cron: compileCron(next) });
  }

  return (
    <div className="flex flex-col gap-2 border-t border-slate-200 pt-2">
      <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
        <input
          type="checkbox"
          aria-label="Planification automatique"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        Planification automatique
      </label>
      {enabled && (
        <div className="flex flex-col gap-2 text-xs">
          <label className="flex flex-col gap-1">
            Mode
            <select
              aria-label="Mode de planification"
              className="h-8 rounded border border-slate-300 px-2"
              value={form.mode}
              onChange={(e) => {
                const mode = e.target.value as ScheduleForm["mode"];
                if (mode === "interval") setForm({ mode: "interval", minutes: "15" });
                else if (mode === "daily") setForm({ mode: "daily", time: "02:00" });
                else if (mode === "weekly") setForm({ mode: "weekly", day: "1", time: "02:00" });
                else setForm({ mode: "advanced", raw: cron });
              }}
            >
              <option value="interval">Toutes les N minutes</option>
              <option value="daily">Quotidien</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="advanced">Cron avancé</option>
            </select>
          </label>
          {form.mode === "interval" && (
            <label className="flex flex-col gap-1">
              Toutes les combien de minutes
              <input
                aria-label="Intervalle en minutes"
                type="number"
                min={1}
                className="h-8 rounded border border-slate-300 px-2"
                value={form.minutes}
                onChange={(e) => setForm({ mode: "interval", minutes: e.target.value })}
              />
            </label>
          )}
          {form.mode === "daily" && (
            <label className="flex flex-col gap-1">
              Heure d&apos;exécution
              <input
                aria-label="Heure d'exécution"
                type="time"
                className="h-8 rounded border border-slate-300 px-2"
                value={form.time}
                onChange={(e) => setForm({ mode: "daily", time: e.target.value })}
              />
            </label>
          )}
          {form.mode === "weekly" && (
            <>
              <label className="flex flex-col gap-1">
                Jour
                <select
                  aria-label="Jour de la semaine"
                  className="h-8 rounded border border-slate-300 px-2"
                  value={form.day}
                  onChange={(e) => setForm({ mode: "weekly", day: e.target.value, time: form.time })}
                >
                  {DAY_LABELS.map((label, i) => (
                    <option key={label} value={i}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                Heure d&apos;exécution
                <input
                  aria-label="Heure d'exécution"
                  type="time"
                  className="h-8 rounded border border-slate-300 px-2"
                  value={form.time}
                  onChange={(e) => setForm({ mode: "weekly", day: form.day, time: e.target.value })}
                />
              </label>
            </>
          )}
          {form.mode === "advanced" && (
            <label className="flex flex-col gap-1">
              Expression cron
              <input
                aria-label="Expression cron"
                className="h-8 rounded border border-slate-300 px-2 font-mono"
                value={form.raw}
                onChange={(e) => setForm({ mode: "advanced", raw: e.target.value })}
              />
              {!ADVANCED_CRON_RE.test(form.raw) && (
                <p role="alert" className="text-red-600">Format cron invalide (5 champs attendus).</p>
              )}
            </label>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx`
Expected: PASS, all 11 tests.

```bash
cd shell && git add src/builder/pipeline/PipelineScheduleEditor.tsx src/builder/pipeline/PipelineScheduleEditor.test.tsx
git commit -m "feat(shell): pipelines — PipelineScheduleEditor (SP-15h)"
```

---

## Task 9: Wire `PipelineScheduleEditor` into `PipelineBuilderPage`

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `PipelineScheduleEditor` (Task 8), `draft.refreshPolicy: PipelineRefreshPolicy | null | undefined` (Task 7).
- Produces: `PipelineBuilderPage` renders the schedule editor for a persisted pipeline (`pk !== null`, same gate as `PipelineRunPanel`); a save failure sets a page-level `saveError` string, shown near the "Enregistrer" button.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/pages/PipelineBuilderPage.test.tsx`, after the last existing test (`persisted mode: Enregistrer calls savePipelineConfig with the current graph`):

```tsx
test("persisted mode: toggling planification then saving includes refreshPolicy in the saved payload", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByLabelText("Planification automatique")).toBeInTheDocument());

  await userEvent.click(screen.getByLabelText("Planification automatique"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledWith(
    "p-1", { ...payload, refreshPolicy: { enabled: true, cron: "*/15 * * * *" } },
  ));
});

test("persisted mode: loads an existing refreshPolicy pre-filled into the editor", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
    refreshPolicy: { enabled: true, cron: "0 2 * * *" },
  };
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload) });
  await waitFor(() => expect(screen.getByLabelText("Planification automatique")).toBeChecked());
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("daily");
  expect(screen.getByLabelText("Heure d'exécution")).toHaveValue("02:00");
});

test("unsaved mode: no schedule editor before the first save (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByLabelText("Planification automatique")).not.toBeInTheDocument();
});

test("persisted mode: a rejected save shows the server error message", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockRejectedValue(new Error("invalid cron expression: 'nope'"));
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("invalid cron expression"));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: FAIL — `screen.getByLabelText("Planification automatique")` not found (editor not wired in yet); the save-error test fails because no error is currently surfaced.

- [ ] **Step 3: Wire the editor in**

In `shell/src/pages/PipelineBuilderPage.tsx`:

1. Add the import, after the `PipelineRunPanel` import:
```typescript
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
```
And extend the existing type-only import line:
```typescript
import type { PipelineEdge, PipelineNode, PipelinePayload, PipelineRefreshPolicy, PipelineRun } from "../api/types";
```

2. Add a `saveError` state, right after the existing `const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);` line:
```typescript
  const [saveError, setSaveError] = useState<string | null>(null);
```

3. Add a `setRefreshPolicy` helper, right after the existing `setEdges` function:
```typescript
  function setRefreshPolicy(refreshPolicy: PipelineRefreshPolicy | null) {
    setDraft((d) => ({ ...d, refreshPolicy }));
  }
```

4. Change `onSave` to catch and surface errors:
```typescript
  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createPipeline.mutateAsync({ title: initialTitle ?? "", owner: username ?? "", pipeline: draft });
        navigate(`/pipelines/${item.pk}/edit`, { replace: true });
        return;
      }
      await savePipeline.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }
```

5. Render the error and the editor. Change:
```tsx
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{initialTitle ?? "Pipeline"}</h2>
          <Button size="sm" onClick={onSave} disabled={!valid || createPipeline.isPending || savePipeline.isPending}>
            Enregistrer
          </Button>
        </div>
```
to:
```tsx
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{initialTitle ?? "Pipeline"}</h2>
          <Button size="sm" onClick={onSave} disabled={!valid || createPipeline.isPending || savePipeline.isPending}>
            Enregistrer
          </Button>
        </div>
        {saveError && <p role="alert" className="text-red-600 text-xs">{saveError}</p>}
```

And change:
```tsx
        {pk !== null && <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />}
```
to:
```tsx
        {pk !== null && <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />}
        {pk !== null && (
          <PipelineScheduleEditor value={draft.refreshPolicy ?? null} onChange={setRefreshPolicy} />
        )}
```

- [ ] **Step 4: Run the tests to verify they pass, then run the full shell suite, then commit**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: PASS, all tests including the 4 new ones.

Run: `cd shell && npx vitest run`
Expected: PASS, full suite (no regression in other files touching `PipelinePayload` literals, since `refreshPolicy` is optional).

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` and `vite build` both succeed.

```bash
cd shell && git add src/pages/PipelineBuilderPage.tsx src/pages/PipelineBuilderPage.test.tsx
git commit -m "feat(shell): pipelines — wire PipelineScheduleEditor into the builder (SP-15h)"
```

---

## Task 10: E2E — plan a pipeline visually, save, reload, verify persistence

**Files:**
- Modify: `shell/e2e/pipeline-builder.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-9, exercised end-to-end through the real UI.
- Produces: nothing new — a spec-only change.

- [ ] **Step 1: Write the E2E test**

Append to `shell/e2e/pipeline-builder.spec.ts`, after the last existing test:

```typescript
test("un auteur planifie un pipeline existant sans écrire de cron à la main", async ({ page }) => {
  await mockCore(page);
  await mockPipelineFlow(page);

  let savedConfig: Record<string, unknown> = {
    kind: "pipeline",
    pipeline: {
      nodes: [
        { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "reader.collection" },
        { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "writer.collection" },
      ],
      edges: [{ id: "e1", from: "r1", to: "w1" }],
    },
  };
  await page.route("https://core.test/configs/by-item/pipe-1", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({ json: { id: "cfg-pipe1", itemId: "pipe-1", kind: "pipeline", config: savedConfig } });
    } else if (method === "PUT") {
      savedConfig = await route.request().postDataJSON();
      await route.fulfill({ json: { id: "cfg-pipe1", itemId: "pipe-1", kind: "pipeline", config: savedConfig } });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/pipelines/pipe-1/edit");
  await expect(page.getByText("reader.collection")).toBeVisible();

  await page.getByLabel("Planification automatique").check();
  await page.getByLabel("Mode de planification").selectOption("daily");
  await page.getByLabel("Heure d'exécution").fill("02:00");

  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.reload();
  await expect(page.getByText("reader.collection")).toBeVisible();
  await expect(page.getByLabel("Planification automatique")).toBeChecked();
  await expect(page.getByLabel("Mode de planification")).toHaveValue("daily");
  await expect(page.getByLabel("Heure d'exécution")).toHaveValue("02:00");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx playwright test pipeline-builder.spec.ts -g "planifie un pipeline existant"`
Expected: FAIL — `page.getByLabel("Planification automatique")` not found, since this is run against the current `main`/`dev` tree before any of Tasks 1-9 land. (If run *after* Tasks 1-9 are already merged in the working tree, it should already PASS at this point — in that case this step confirms the positive case directly; either outcome is consistent with TDD as long as you don't skip actually running it.)

- [ ] **Step 3: Run the test to verify it passes (after Tasks 1-9 are in place)**

Run: `cd shell && npx playwright test pipeline-builder.spec.ts`
Expected: PASS, all specs in the file (the 2 pre-existing ones plus this new one).

- [ ] **Step 4: Run the full E2E suite and commit**

Run: `cd shell && npm run e2e`
Expected: PASS, full suite (18+ spec files, no regression).

```bash
cd shell && git add e2e/pipeline-builder.spec.ts
git commit -m "test(e2e): pipelines — schedule a pipeline visually and verify persistence (SP-15h)"
```

---

## Final check

After Task 10, run the full three-tier verification one more time from a clean state, matching the project's standard commands (`CLAUDE.md`):

```bash
cd core && uv run pytest
cd shell && npm run test
cd shell && npm run e2e
cd shell && npm run build
```

Expected: all green (core: 606+ passed plus the ~15 new tests added by this plan, some postgis-marked tests skipped without docker; shell: 958+ passed plus the ~19 new tests; E2E: 18 spec files including the updated `pipeline-builder.spec.ts`; build clean).

Then update `CLAUDE.md`'s roadmap: move SP-15h from "reste : automatisation/déclencheurs au-delà de la planification simple" to a new "Fait" bullet (mirroring the SP-15a-g entries' style), and update the SP-15 "À venir" paragraph to note that only durable event triggers remain out of scope (unplanned, on-demand) — the M14 milestone note should be updated accordingly if this closes it (check whether the QGIS sidecar test-verification item from SP-15d is still the only other open item before declaring M14 fully reached).
