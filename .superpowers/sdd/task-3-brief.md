## Task 3: Data model + migration — `connector_secrets`

**Files:**
- Create: `core/app/secrets/models.py`
- Create: `core/alembic/versions/0019_connector_secrets.py`
- Modify: `core/app/db.py` (register the model in `core_table_names()`)
- Modify: `core/pyproject.toml` (`ignore_imports` entry for `app.db ->
  app.secrets.models`)
- Test: `core/tests/test_secrets_models.py`

**Interfaces:**
- Produces: `app.secrets.models.ConnectorSecret` (SQLAlchemy model:
  `id: str`, `tenant_id: str`, `name: str`, `kind: str`, `ciphertext:
  bytes`, `nonce: bytes`, `created_by: str`, `created_at: datetime`,
  `updated_at: datetime`, unique on `(tenant_id, name)`). Consumed by Task 4
  (`repository.py`) and Task 5 (`routes.py`'s `_to_response`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_secrets_models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app.db import init_db, make_engine, make_session_factory
from app.secrets.models import ConnectorSecret
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_connector_secrets_table_is_registered():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    assert sa_inspect(engine).has_table("connector_secrets")


def test_connector_secret_row_round_trip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        secret = ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="my-api", kind="bearer_token",
            ciphertext=b"cipher", nonce=b"nonce123456", created_by=user.id,
        )
        s.add(secret)
        s.commit()
        fetched = s.get(ConnectorSecret, "sec1")
        assert fetched.name == "my-api"
        assert fetched.kind == "bearer_token"
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


def test_connector_secret_unique_name_per_tenant():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        s.add(ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c1", nonce=b"n1", created_by=user.id,
        ))
        s.commit()
        s.add(ConnectorSecret(
            id="sec2", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c2", nonce=b"n2", created_by=user.id,
        ))
        with pytest.raises(IntegrityError):
            s.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.secrets.models'`.

- [ ] **Step 3: Implement `models.py`**

Create `core/app/secrets/models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorSecret(Base):
    __tablename__ = "connector_secrets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_connector_secrets_tenant_name"),
    )
```

- [ ] **Step 4: Register the model so `init_db()`/`create_all()` picks it up**

Modify `core/app/db.py` — in `core_table_names()`, add (alphabetically,
between `pipelines_models` and `sharing_models`):

```python
    from app.secrets import models as secrets_models  # noqa: F401
```

- [ ] **Step 5: Add the import-linter exemption**

Modify `core/pyproject.toml` — in the `ignore_imports` list (same
`[[tool.importlinter.contracts]]` block as Task 1 Step 4), add:

```toml
    "app.db -> app.secrets.models",
```

(This mirrors the 10 existing entries — `app.db` imports every module's
`models.py` to register it on `Base.metadata`, which the layers contract
would otherwise flag; every existing model module already has this exact
exemption.)

- [ ] **Step 6: Write the migration**

Create `core/alembic/versions/0019_connector_secrets.py`:

```python
"""app.secrets — connector_secrets (SP-15e)

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_secrets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connector_secrets_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("connector_secrets")
```

- [ ] **Step 7: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_models.py -v`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add core/app/secrets/models.py core/alembic/versions/0019_connector_secrets.py \
  core/app/db.py core/pyproject.toml core/tests/test_secrets_models.py
git commit -m "feat(core): secrets module — connector_secrets table + migration"
```

---

