### Task 4: `AlertEvaluation` model + migration

**Files:**
- Create: `core/app/alerts/__init__.py` (empty)
- Create: `core/app/alerts/models.py`
- Create: `core/alembic/versions/0020_alert_evaluations.py`
- Test: `core/tests/test_alert_models.py`

**Interfaces:**
- Produces: `AlertEvaluation` ORM model (table `alert_evaluations`), consumed by Task 5 (`app/alerts/repository.py`).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_alert_models.py
# SPDX-License-Identifier: Apache-2.0
from app.alerts.models import AlertEvaluation
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_alert_evaluation_round_trips_through_sqlite():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="alert", title="High counts",
        )
        s.commit()

        evaluation = AlertEvaluation(
            id="eval-1", tenant_id=tenant.id, alert_rule_item_id=item.id,
            value=150.0, state="firing", transitioned=True, error=None,
        )
        s.add(evaluation)
        s.commit()

    with Session() as s:
        reloaded = s.get(AlertEvaluation, "eval-1")
        assert reloaded is not None
        assert reloaded.state == "firing"
        assert reloaded.transitioned is True
        assert reloaded.value == 150.0
        assert reloaded.error is None
        assert reloaded.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_models.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alerts'`

- [ ] **Step 3: Write the implementation**

```python
# core/app/alerts/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/alerts/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AlertEvaluation(Base):
    __tablename__ = "alert_evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    alert_rule_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String, nullable=False)
    transitioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

Check the alembic head revision, then write the migration:

Run: `cd core && uv run alembic heads`
Expected: `0019 (head)`

```python
# core/alembic/versions/0020_alert_evaluations.py
# SPDX-License-Identifier: Apache-2.0
"""app.alerts — alert_evaluations (SP-16b)

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_evaluations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("alert_rule_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("transitioned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alert_evaluations")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_models.py`
Expected: `1 passed`

Verify the migration itself applies cleanly against the real (postgis-marked) suite path used elsewhere in the repo — if a local Postgres is available via docker compose, run `cd core && uv run alembic upgrade head` and confirm no error; otherwise note this is covered by the `postgis`-marked CI job and move on (same caveat SP-15a/b noted for migrations tested primarily via SQLite `init_db` in unit tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/alerts/__init__.py core/app/alerts/models.py core/alembic/versions/0020_alert_evaluations.py core/tests/test_alert_models.py
git commit -m "feat(core): SP-16b — AlertEvaluation model + migration 0020"
```

---

