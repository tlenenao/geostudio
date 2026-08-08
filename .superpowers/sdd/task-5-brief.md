### Task 5: `app/alerts/repository.py`

**Files:**
- Create: `core/app/alerts/repository.py`
- Test: `core/tests/test_alert_repository.py`

**Interfaces:**
- Consumes: `app.configs.repository.list_configs_by_kind` (existing), `AlertEvaluation` (Task 4).
- Produces: `create_evaluation(session, *, tenant_id, alert_rule_item_id) -> AlertEvaluation`, `mark_evaluated(session, *, evaluation_id, value, state, transitioned, error=None) -> None`, `get_latest_evaluation(session, *, tenant_id, alert_rule_item_id) -> AlertEvaluation | None`, `list_evaluations(session, *, tenant_id, alert_rule_item_id) -> list[AlertEvaluation]`, `list_due_rules(session) -> list[tuple[str, str]]` (item_id, tenant_id). Consumed by Task 9 (`app.alerts.jobs`) and Task 10 (`app.alerts.routes`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_repository.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _alert_body(dataset_item_id: str, *, refresh_policy=None) -> dict:
    body = {
        "kind": "alert",
        "alert": {
            "datasetItemId": dataset_item_id,
            "query": {"agg": "count"},
            "condition": {"expr": "value > 100"},
            "refreshPolicy": refresh_policy or {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }
    return body


def _seed_alert_rule(session, *, tenant_id, owner_id, dataset_item_id="ds-1", refresh_policy=None):
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="alert", title="Rule",
    )
    config = BuilderConfig.model_validate(_alert_body(dataset_item_id, refresh_policy=refresh_policy))
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_create_and_mark_evaluated_round_trip():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

        evaluation = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        assert evaluation.state == "pending"
        alerts_repo.mark_evaluated(
            s, evaluation_id=evaluation.id, value=150.0, state="firing", transitioned=True,
        )
        s.commit()

        latest = alerts_repo.get_latest_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        assert latest is not None
        assert latest.state == "firing"
        assert latest.value == 150.0


def test_list_due_rules_includes_a_rule_with_no_prior_evaluation():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

        due = alerts_repo.list_due_rules(s)
        assert (rule_id, tenant.id) in due


def test_list_due_rules_excludes_a_disabled_rule():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_alert_rule(
            s, tenant_id=tenant.id, owner_id=user.id,
            refresh_policy={"enabled": False, "cron": "*/5 * * * *"},
        )
        s.commit()

        assert alerts_repo.list_due_rules(s) == []


def test_list_due_rules_excludes_a_rule_evaluated_within_its_cron_interval():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        evaluation = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(s, evaluation_id=evaluation.id, value=1.0, state="ok", transitioned=False)
        s.commit()

        assert alerts_repo.list_due_rules(s) == []


def test_list_due_rules_reclaims_a_stuck_pending_evaluation():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        evaluation = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        # Simulate a stuck evaluation: created long ago, never marked.
        evaluation.created_at = datetime.now(timezone.utc) - timedelta(minutes=120)
        s.commit()

        assert (rule_id, tenant.id) in alerts_repo.list_due_rules(s)


def test_list_evaluations_orders_most_recent_first():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        first = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(s, evaluation_id=first.id, value=1.0, state="ok", transitioned=False)
        second = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(s, evaluation_id=second.id, value=2.0, state="firing", transitioned=True)
        s.commit()

        rows = alerts_repo.list_evaluations(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        assert [r.id for r in rows] == [second.id, first.id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_repository.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alerts.repository'`

- [ ] **Step 3: Write the implementation**

```python
# core/app/alerts/repository.py
# SPDX-License-Identifier: Apache-2.0
"""Mirrors app.pipelines.repository (SP-15a/h) exactly: "last evaluation"
is always derived from alert_evaluations (never a duplicated column on the
config), and list_due_rules reuses the same reclaim-by-age discipline as
list_due_pipelines — a "pending" evaluation older than
_PENDING_RECLAIM_MINUTES is presumed stuck and becomes eligible again."""
import uuid
from datetime import datetime, timedelta, timezone

import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.models import AlertEvaluation
from app.configs import repository as configs_repo

_PENDING_RECLAIM_MINUTES = 60


def create_evaluation(session: Session, *, tenant_id: str, alert_rule_item_id: str) -> AlertEvaluation:
    evaluation = AlertEvaluation(
        id=uuid.uuid4().hex, tenant_id=tenant_id, alert_rule_item_id=alert_rule_item_id,
        state="pending",
    )
    session.add(evaluation)
    session.flush()
    session.refresh(evaluation)
    return evaluation


def mark_evaluated(
    session: Session, *, evaluation_id: str, value: float | None, state: str, transitioned: bool,
    error: str | None = None,
) -> None:
    evaluation = session.get(AlertEvaluation, evaluation_id)
    if evaluation is None:
        return
    evaluation.value = value
    evaluation.state = state
    evaluation.transitioned = transitioned
    evaluation.error = error
    session.flush()


def get_evaluation(session: Session, *, tenant_id: str, evaluation_id: str) -> AlertEvaluation | None:
    return session.execute(
        select(AlertEvaluation).where(
            AlertEvaluation.id == evaluation_id, AlertEvaluation.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def get_latest_evaluation(
    session: Session, *, tenant_id: str, alert_rule_item_id: str,
) -> AlertEvaluation | None:
    return session.execute(
        select(AlertEvaluation)
        .where(
            AlertEvaluation.tenant_id == tenant_id,
            AlertEvaluation.alert_rule_item_id == alert_rule_item_id,
        )
        .order_by(AlertEvaluation.created_at.desc())
        .limit(1)
    ).scalars().first()


def list_evaluations(
    session: Session, *, tenant_id: str, alert_rule_item_id: str,
) -> list[AlertEvaluation]:
    rows = session.execute(
        select(AlertEvaluation)
        .where(
            AlertEvaluation.tenant_id == tenant_id,
            AlertEvaluation.alert_rule_item_id == alert_rule_item_id,
        )
        .order_by(AlertEvaluation.created_at.desc())
    ).scalars().all()
    return list(rows)


def list_due_rules(session: Session) -> list[tuple[str, str]]:
    """Cross-tenant sweep, consumed by sweep_alert_rules_task (app.alerts.jobs,
    Task 9). Never exposed via a route (same discipline as
    list_due_pipelines): the tuple carries tenant_id in clear."""
    now = datetime.now(timezone.utc)
    due: list[tuple[str, str]] = []
    for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="alert"):
        payload = config.alert
        if payload is None:
            continue
        policy = payload.refreshPolicy
        if not policy.enabled:
            continue
        latest = get_latest_evaluation(session, tenant_id=tenant_id, alert_rule_item_id=item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if latest.state == "pending":
            if (now - created_at) < timedelta(minutes=_PENDING_RECLAIM_MINUTES):
                continue
            due.append((item_id, tenant_id))
            continue
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_repository.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add core/app/alerts/repository.py core/tests/test_alert_repository.py
git commit -m "feat(core): SP-16b — app.alerts.repository (evaluations CRUD, list_due_rules)"
```

---

