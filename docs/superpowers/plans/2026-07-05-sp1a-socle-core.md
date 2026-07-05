# SP-1a — Socle du cœur (tenants, users, JWT OIDC, audit, frontières) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `core/` real authentication (JWT OIDC, with a mock mode mirroring the shell's `VITE_AUTH_MODE=mock`), a `tenants`/`users`/`audit_log` schema managed by Alembic, a package layout with an enforced layering contract, and CI that regenerates the shell's TypeScript types from the core's OpenAPI schema.

**Architecture:** `core/app` is restructured from a flat module list into domain packages (`tenants`, `users`, `audit`, `auth`, `configs`) connected through a strict layering contract enforced by `import-linter`. Alembic becomes the source of truth for schema changes, starting with a baseline revision that captures the existing `configs`/`config_revisions` tables, followed by one revision per new table. Authentication is a FastAPI dependency (`get_current_user`) that either validates a real JWT against Keycloak's JWKS or, in mock mode, resolves a fixed mock user — in both cases it JIT-provisions the `User` row.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PyJWT[crypto], import-linter, pytest, uv (Python); openapi-typescript, npm (TypeScript tooling for the CI drift check); GitHub Actions.

## Global Constraints

- `tenant_id` and an `audit_log` entry on every table/write, from the first migration (CLAUDE.md rule) — this migration adds `tenant_id` to the two existing tables (`configs`, `config_revisions`) as well as every new one.
- Single real tenant in v0: slug `"default"`, resolved by `app.tenants.repository.get_or_create_default_tenant`.
- Mock auth username is exactly `"mockuser"` — must match `MOCK_STATE.username` in `shell/src/auth/useAuth.ts` so `/me` is consistent across shell and core in e2e.
- `CORE_AUTH_MODE` defaults to `"oidc"` when unset (fail-safe: never silently mock in an unconfigured deployment).
- Layering contract (import-linter, high → low, a module may only import from strictly lower layers): `app.main`, `app.configs`, `app.auth`, `app.audit`, `app.users`, `app.tenants`. `app.db` sits below all of them (not part of the domain layers, imported by everyone).
- No new heavy dependency for JWT: `PyJWT[crypto]` (not `python-jose`), reusing `httpx` transitively via `PyJWKClient`.
- Fast unit tests keep using SQLite in-memory + `Base.metadata.create_all` (`app.db.init_db`), as today. Alembic `upgrade`/`downgrade` round-trips are verified against a real Postgres in CI, not in the SQLite unit-test suite.
- Spec of record: `docs/superpowers/specs/2026-07-05-sp1a-socle-core-design.md`.

---

### Task 1: Alembic baseline for the existing schema

**Files:**
- Modify: `core/pyproject.toml`
- Create: `core/alembic.ini`
- Create: `core/alembic/env.py`
- Create: `core/alembic/versions/0001_baseline.py`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: existing `app.models.Config`, `app.models.ConfigRevision` (flat module, not yet restructured — that happens in Task 2).
- Produces: a working `alembic upgrade head` / `alembic downgrade base` cycle against Postgres, and a CI job (`migrations`) that runs it. Later tasks each add one more revision file and, if they touch `env.py`'s imports, edit the same file.

- [ ] **Step 1: Add `alembic` to core's dependencies**

Edit `core/pyproject.toml`, in the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "httpx>=0.27",
    "psycopg[binary]>=3.1",
    "alembic>=1.13",
]
```

Run: `cd core && uv sync`
Expected: `alembic` installed into `core/.venv`.

- [ ] **Step 2: Create `alembic.ini`**

```ini
[alembic]
script_location = alembic

[loggers]
keys = root,sqlalchemy,alembic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handlers]
keys = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatters]
keys = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Create `alembic/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app import models as legacy_models  # noqa: F401 — registers Config/ConfigRevision on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create the baseline revision `alembic/versions/0001_baseline.py`**

```python
"""baseline: configs, config_revisions

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "configs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "config_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("config_id", sa.String(), sa.ForeignKey("configs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("config_revisions")
    op.drop_table("configs")
```

- [ ] **Step 5: Create the CI workflow with a `migrations` job**

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:

jobs:
  migrations:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_USER: gis
          POSTGRES_PASSWORD: gis
          POSTGRES_DB: gis
        ports: ["5432:5432"]
        options: >-
          --health-cmd="pg_isready -U gis" --health-interval=5s --health-timeout=5s --health-retries=10
    defaults:
      run:
        working-directory: core
    env:
      DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run alembic upgrade head
      - run: uv run alembic downgrade base
```

- [ ] **Step 6: Run the migration cycle locally against the compose Postgres**

Run:
```bash
docker compose up -d postgis
cd core
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
```
Expected: both commands exit 0; `upgrade head` creates `configs`/`config_revisions`; `downgrade base` drops them.

- [ ] **Step 7: Run the existing pytest suite to confirm nothing broke**

Run: `cd core && uv run pytest`
Expected: PASS (unchanged — Alembic is additive, unit tests still use `init_db`/SQLite).

- [ ] **Step 8: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/alembic.ini core/alembic/env.py core/alembic/versions/0001_baseline.py .github/workflows/ci.yml
git commit -m "feat(core): add Alembic with a baseline migration for configs/config_revisions"
```

---

### Task 2: Restructure `app/` into a `configs` package; move `get_session` to `app.db`

**Files:**
- Create: `core/app/configs/__init__.py`, `core/app/configs/models.py`, `core/app/configs/schemas.py`, `core/app/configs/repository.py`, `core/app/configs/routes.py`
- Modify: `core/app/db.py`
- Modify: `core/app/main.py`
- Delete: `core/app/models.py`, `core/app/schemas.py`, `core/app/repository.py`, `core/app/routes.py`
- Modify: `core/tests/test_models.py` → rename to `core/tests/test_configs_models.py`
- Modify: `core/tests/test_repository.py`, `core/tests/test_schemas.py`, `core/tests/test_routes.py`, `core/tests/test_main_wiring.py`
- Modify: `core/alembic/env.py`

**Interfaces:**
- Consumes: nothing new — pure move of existing code.
- Produces: `app.configs.models.{Config, ConfigRevision}`, `app.configs.schemas.BuilderConfig` (and its nested types), `app.configs.repository.{create_config, get_config, get_config_by_item, update_config, list_revisions, rollback_config, delete_config, ConfigRead, RevisionInfo}`, `app.configs.routes.router` with `get_item_client` (unchanged) — `get_session` moves to `app.db.get_session`, which every later package (`auth`, `configs`) imports from there instead.

- [ ] **Step 1: Move the four files into `app/configs/` verbatim (git mv preserves history)**

```bash
cd core
mkdir -p app/configs
touch app/configs/__init__.py
git mv app/models.py app/configs/models.py
git mv app/schemas.py app/configs/schemas.py
git mv app/repository.py app/configs/repository.py
git mv app/routes.py app/configs/routes.py
```

- [ ] **Step 2: Fix internal imports in the moved files**

In `app/configs/repository.py`, change:
```python
from app.models import Config, ConfigRevision
from app.schemas import BuilderConfig
```
to:
```python
from app.configs.models import Config, ConfigRevision
from app.configs.schemas import BuilderConfig
```

In `app/configs/routes.py`, change:
```python
from app import repository as repo
from app.geonode import ItemClient, StubItemClient
from app.repository import ConfigRead, RevisionInfo
from app.schemas import BuilderConfig
```
to:
```python
from app.configs import repository as repo
from app.geonode import ItemClient, StubItemClient
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.db import get_session
```
and delete the local definition of `get_session` (now imported from `app.db` — see Step 3).

- [ ] **Step 3: Move `get_session` from `configs/routes.py` to `app/db.py`**

`app/configs/routes.py` currently defines:
```python
def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")
```
Delete this from `configs/routes.py` (imported from `app.db` per Step 2 instead). Add the same function to the end of `app/db.py`:
```python
from collections.abc import Iterator


def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")
```
(Add `from collections.abc import Iterator` to `app/db.py`'s existing imports.)

- [ ] **Step 4: Update `app/main.py`**

```python
import logging
import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import db
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session

    geonode_url = os.environ.get("GEONODE_BASE_URL")
    geonode_token = os.environ.get("GEONODE_TOKEN")
    if geonode_url and geonode_token:
        from app.geonode import GeoNodeItemClient

        geonode_client = GeoNodeItemClient(geonode_url, geonode_token)
        app.dependency_overrides[configs_routes.get_item_client] = lambda: geonode_client
    else:
        logging.getLogger("uvicorn.error").warning(
            "GEONODE_BASE_URL/GEONODE_TOKEN not set; item creation uses the in-memory stub."
        )

    app.include_router(configs_routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Update `alembic/env.py`'s model import**

Change:
```python
from app import models as legacy_models  # noqa: F401 — registers Config/ConfigRevision on Base.metadata
```
to:
```python
from app.configs import models as configs_models  # noqa: F401 — registers Config/ConfigRevision on Base.metadata
```

- [ ] **Step 6: Update the test files**

`core/tests/test_models.py` → rename to `core/tests/test_configs_models.py`, change:
```python
from app.models import Config, ConfigRevision
```
to:
```python
from app.configs.models import Config, ConfigRevision
```
(rest of the file unchanged).

`core/tests/test_repository.py`, change:
```python
from app import repository as repo
from app.schemas import BuilderConfig
```
to:
```python
from app.configs import repository as repo
from app.configs.schemas import BuilderConfig
```

`core/tests/test_schemas.py`, change both occurrences of `from app.schemas import ...` to `from app.configs.schemas import ...`.

`core/tests/test_routes.py`, change:
```python
from app.main import create_app
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app import routes
```
to:
```python
from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app.configs import routes
```
and in the `client` fixture, change:
```python
    app.dependency_overrides[routes.get_session] = override_session
    app.dependency_overrides[routes.get_item_client] = lambda: stub
```
to:
```python
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[routes.get_item_client] = lambda: stub
```

`core/tests/test_main_wiring.py`, change:
```python
from app.main import create_app
from app import routes
from app.geonode import GeoNodeItemClient, StubItemClient
```
to:
```python
from app.main import create_app
from app.configs import routes
from app.geonode import GeoNodeItemClient, StubItemClient
```
(the two test bodies reference `routes.get_item_client`, unchanged — no further edits needed).

- [ ] **Step 7: Run the full test suite**

Run: `cd core && uv run pytest`
Expected: PASS — same tests, same count, only the import paths changed.

- [ ] **Step 8: Commit**

```bash
git add core/app core/tests core/alembic
git commit -m "refactor(core): move configs code into app/configs, get_session into app/db"
```

---

### Task 3: `tenants` package + migration

**Files:**
- Create: `core/app/tenants/__init__.py`, `core/app/tenants/models.py`, `core/app/tenants/repository.py`
- Create: `core/alembic/versions/0002_tenants.py`
- Modify: `core/alembic/env.py`
- Create: `core/tests/test_tenants.py`

**Interfaces:**
- Consumes: `app.db.Base`.
- Produces: `app.tenants.models.Tenant` (fields: `id`, `slug`, `name`, `created_at`); `app.tenants.repository.get_or_create_default_tenant(session: Session) -> Tenant`, idempotent by slug `"default"`.

- [ ] **Step 1: Write the failing test**

`core/tests/test_tenants.py`:
```python
from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant


def test_get_or_create_default_tenant_is_idempotent():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            first = get_or_create_default_tenant(session)
            assert first.slug == "default"

        with Session() as session:
            second = get_or_create_default_tenant(session)
            assert second.id == first.id
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_tenants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tenants'`.

- [ ] **Step 3: Write the model**

`core/app/tenants/__init__.py`: empty file.

`core/app/tenants/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 4: Write the repository**

`core/app/tenants/repository.py`:
```python
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tenants.models import Tenant

DEFAULT_TENANT_SLUG = "default"


def get_or_create_default_tenant(session: Session) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    if tenant is not None:
        return tenant
    tenant = Tenant(id=uuid.uuid4().hex, slug=DEFAULT_TENANT_SLUG, name="Default")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_tenants.py -v`
Expected: PASS.

- [ ] **Step 6: Register the model in `alembic/env.py`**

Add, next to the `configs` import:
```python
from app.tenants import models as tenants_models  # noqa: F401
```

- [ ] **Step 7: Write the migration and add `tenant_id` to the existing tables**

`core/alembic/versions/0002_tenants.py`:
```python
"""tenants table; tenant_id on configs/config_revisions

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "default"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    tenants_table = sa.table(
        "tenants",
        sa.column("id", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        tenants_table,
        [{
            "id": DEFAULT_TENANT_ID,
            "slug": "default",
            "name": "Default",
            "created_at": datetime.now(timezone.utc),
        }],
    )

    for table in ("configs", "config_revisions"):
        op.add_column(table, sa.Column("tenant_id", sa.String(), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '{DEFAULT_TENANT_ID}'")
        op.alter_column(table, "tenant_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_tenant", table, "tenants", ["tenant_id"], ["id"]
        )


def downgrade() -> None:
    for table in ("config_revisions", "configs"):
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
    op.drop_table("tenants")
```

- [ ] **Step 8: Run the migration cycle against Postgres**

Run:
```bash
docker compose up -d postgis
cd core
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
```
Expected: both exit 0; `upgrade head` leaves `tenants` with one row (`slug="default"`) and `configs`/`config_revisions` with a non-null `tenant_id` column.

- [ ] **Step 9: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add core/app/tenants core/tests/test_tenants.py core/alembic
git commit -m "feat(core): add tenants table and get_or_create_default_tenant"
```

---

### Task 4: `users` package + migration (JIT provisioning target)

**Files:**
- Create: `core/app/users/__init__.py`, `core/app/users/models.py`, `core/app/users/repository.py`
- Create: `core/alembic/versions/0003_users.py`
- Modify: `core/alembic/env.py`
- Create: `core/tests/test_users.py`

**Interfaces:**
- Consumes: `app.tenants.models.Tenant` (FK target only, referenced by string in the migration, no Python import needed).
- Produces: `app.users.models.User` (fields: `id`, `tenant_id`, `oidc_sub`, `username`, `email`, `first_name`, `last_name`, `created_at`, `updated_at`); `app.users.repository.get_or_create_user(session: Session, *, tenant_id: str, oidc_sub: str, username: str, email: str | None, first_name: str, last_name: str) -> User` — creates on first call, refreshes `username`/`email`/`first_name`/`last_name` on subsequent calls (IdP is the source of truth).

- [ ] **Step 1: Write the failing test**

`core/tests/test_users.py`:
```python
from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_get_or_create_user_creates_then_refreshes():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            created = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice", email="alice@example.com",
                first_name="Alice", last_name="Doe",
            )
            assert created.username == "alice"

        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            refreshed = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice2", email="alice@example.com",
                first_name="Alice", last_name="Doe",
            )
            assert refreshed.id == created.id
            assert refreshed.username == "alice2"
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_users.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.users'`.

- [ ] **Step 3: Write the model**

`core/app/users/__init__.py`: empty file.

`core/app/users/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "oidc_sub", name="uq_users_tenant_oidc_sub"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    oidc_sub: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, default="")
    last_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 4: Write the repository**

`core/app/users/repository.py`:
```python
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.users.models import User


def get_or_create_user(
    session: Session,
    *,
    tenant_id: str,
    oidc_sub: str,
    username: str,
    email: str | None,
    first_name: str,
    last_name: str,
) -> User:
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.oidc_sub == oidc_sub)
    )
    if user is None:
        user = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            oidc_sub=oidc_sub,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
    else:
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
    session.commit()
    session.refresh(user)
    return user
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_users.py -v`
Expected: PASS.

- [ ] **Step 6: Register the model in `alembic/env.py`**

Add:
```python
from app.users import models as users_models  # noqa: F401
```

- [ ] **Step 7: Write the migration**

`core/alembic/versions/0003_users.py`:
```python
"""users table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("oidc_sub", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_users_tenant_oidc_sub", "users", ["tenant_id", "oidc_sub"]
    )


def downgrade() -> None:
    op.drop_table("users")
```

- [ ] **Step 8: Run the migration cycle against Postgres**

Run:
```bash
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
```
Expected: both exit 0.

- [ ] **Step 9: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add core/app/users core/tests/test_users.py core/alembic
git commit -m "feat(core): add users table and JIT get_or_create_user"
```

---

### Task 5: `audit` package + migration

**Files:**
- Create: `core/app/audit/__init__.py`, `core/app/audit/models.py`, `core/app/audit/writer.py`
- Create: `core/alembic/versions/0004_audit_log.py`
- Modify: `core/alembic/env.py`
- Create: `core/tests/test_audit.py`

**Interfaces:**
- Consumes: nothing (FKs to `tenants`/`users` are string references in the migration, no Python import).
- Produces: `app.audit.models.AuditLog`; `app.audit.writer.write_audit(session: Session, *, tenant_id: str, actor_id: str | None, actor_kind: str, action: str, object_type: str, object_id: str, payload: dict | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

`core/tests/test_audit.py`:
```python
from sqlalchemy import select

from app.audit.models import AuditLog
from app.audit.writer import write_audit
from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant


def test_write_audit_persists_a_row():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            write_audit(
                session,
                tenant_id=tenant.id,
                actor_id="user-1",
                actor_kind="user",
                action="config.create",
                object_type="config",
                object_id="config-1",
                payload={"title": "My App"},
            )

        with Session() as session:
            rows = session.scalars(select(AuditLog)).all()
            assert len(rows) == 1
            assert rows[0].action == "config.create"
            assert rows[0].payload == {"title": "My App"}
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.audit'`.

- [ ] **Step 3: Write the model**

`core/app/audit/__init__.py`: empty file.

`core/app/audit/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_kind: Mapped[str] = mapped_column(String, nullable=False)  # "user" | "agent" | "system"
    action: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    object_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 4: Write the writer**

`core/app/audit/writer.py`:
```python
from sqlalchemy.orm import Session

from app.audit.models import AuditLog


def write_audit(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None,
    actor_kind: str,
    action: str,
    object_type: str,
    object_id: str,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_kind=actor_kind,
            action=action,
            object_type=object_type,
            object_id=object_id,
            payload=payload or {},
        )
    )
    session.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_audit.py -v`
Expected: PASS.

- [ ] **Step 6: Register the model in `alembic/env.py`**

Add:
```python
from app.audit import models as audit_models  # noqa: F401
```

- [ ] **Step 7: Write the migration**

`core/alembic/versions/0004_audit_log.py`:
```python
"""audit_log table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_kind", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
```

- [ ] **Step 8: Run the migration cycle against Postgres, then the full pytest suite**

Run:
```bash
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
cd core && uv run pytest
```
Expected: migrations exit 0; full suite PASS.

- [ ] **Step 9: Commit**

```bash
git add core/app/audit core/tests/test_audit.py core/alembic
git commit -m "feat(core): add audit_log table and write_audit helper"
```

---

### Task 6: `auth` package — JWT validation, mock mode, `get_current_user`

**Files:**
- Create: `core/app/auth/__init__.py`, `core/app/auth/dependency.py`
- Modify: `core/pyproject.toml`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Create: `core/tests/test_auth.py`

**Interfaces:**
- Consumes: `app.db.get_session`, `app.tenants.repository.get_or_create_default_tenant`, `app.users.repository.get_or_create_user`, `app.users.models.User`.
- Produces: `app.auth.dependency.get_current_user(authorization: str = Header(default=""), session: Session = Depends(get_session)) -> User` — the single FastAPI dependency every authenticated route will use from Task 7 onward.

- [ ] **Step 1: Add `PyJWT[crypto]` to core's dependencies**

Edit `core/pyproject.toml`:
```toml
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "httpx>=0.27",
    "psycopg[binary]>=3.1",
    "alembic>=1.13",
    "pyjwt[crypto]>=2.8",
]
```

Run: `cd core && uv sync`
Expected: `pyjwt`/`cryptography` installed.

- [ ] **Step 2: Write the failing tests (mock mode + real JWT)**

`core/tests/test_auth.py`:
```python
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app.auth import dependency
from app.db import make_engine, make_session_factory, init_db


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_mock_mode_resolves_mockuser(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    user = dependency.get_current_user(authorization="Bearer anything", session=session)
    assert user.username == "mockuser"


def test_missing_bearer_prefix_raises_401(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="not-a-bearer-token", session=session)
    assert exc_info.value.status_code == 401


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def test_oidc_mode_validates_and_provisions_user(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(
        {
            "sub": "sub-123",
            "aud": "geostudio-core",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "given_name": "Alice",
            "family_name": "Doe",
        },
        private_key,
        algorithm="RS256",
    )
    monkeypatch.setattr(dependency, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    user = dependency.get_current_user(authorization=f"Bearer {token}", session=session)
    assert user.username == "alice"
    assert user.email == "alice@example.com"


def test_oidc_mode_rejects_wrong_audience(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    from fastapi import HTTPException

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(
        {"sub": "sub-123", "aud": "someone-else"}, private_key, algorithm="RS256"
    )
    monkeypatch.setattr(dependency, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 4: Write `app/auth/dependency.py`**

```python
import os

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def _jwks_client() -> jwt.PyJWKClient:
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get(
        "CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"
    )
    return jwt.PyJWKClient(jwks_url, lifespan=600)


def get_current_user(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User:
    tenant = get_or_create_default_tenant(session)

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")

    if _mock_mode():
        return get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=os.environ["CORE_OIDC_AUDIENCE"],
        )
    except jwt.PyJWKClientError as exc:
        raise HTTPException(status_code=503, detail="identity provider unreachable") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        email=claims.get("email"),
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
    )
```

`core/app/auth/__init__.py`: empty file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_auth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Add the new env vars to `.env.example` and `docker-compose.yml`**

Add to `.env.example`, in a new section:
```
# ─── Cœur : mode d'authentification ──────────────────────
# "mock" pour dev/e2e (aucun accès réseau à Keycloak requis) ; "oidc" en usage réel.
CORE_AUTH_MODE=mock
CORE_OIDC_ISSUER=http://keycloak:8080/realms/geostudio
CORE_OIDC_AUDIENCE=geostudio-core
```

In `docker-compose.yml`, the `core` service already has an `environment` block
(just `DATABASE_URL`) — add the three new keys to it:
```yaml
  core:
    build: ./core
    environment:
      DATABASE_URL: postgresql+psycopg://gis:${PG_PASSWORD}@pgbouncer:6432/gis
      CORE_AUTH_MODE: ${CORE_AUTH_MODE:-mock}
      CORE_OIDC_ISSUER: ${CORE_OIDC_ISSUER:-http://keycloak:8080/realms/geostudio}
      CORE_OIDC_AUDIENCE: ${CORE_OIDC_AUDIENCE:-geostudio-core}
    ports:
      - "8200:8200"
    networks: [gis-net]
    depends_on: [pgbouncer]
    restart: unless-stopped
```

- [ ] **Step 7: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/auth core/pyproject.toml core/uv.lock core/tests/test_auth.py .env.example docker-compose.yml
git commit -m "feat(core): JWT OIDC authentication with a mock mode mirroring the shell"
```

---

### Task 7: Wire `get_current_user` and `write_audit` into the `configs` routes

**Files:**
- Modify: `core/app/configs/routes.py`
- Modify: `core/tests/test_routes.py`

**Interfaces:**
- Consumes: `app.auth.dependency.get_current_user`, `app.audit.writer.write_audit`, `app.tenants.repository.get_or_create_default_tenant`, `app.users.repository.get_or_create_user`.
- Produces: every mutating `configs` endpoint now requires a resolved `User` and writes one `audit_log` row per mutation, with actions `config.create`, `config.update`, `config.delete`, `config.rollback`.

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_routes.py`, replacing the `client` fixture to provision and inject a real user, and adding an audit assertion. Replace the existing fixture:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.audit.models import AuditLog
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app.configs import routes
from app.auth.dependency import get_current_user
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from sqlalchemy import select


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    stub = StubItemClient()

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="alice@example.com",
            first_name="Alice", last_name="Doe",
        )

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[routes.get_item_client] = lambda: stub
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.stub = stub  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()
```

Then add a new test at the end of the file:
```python
def test_create_config_writes_audit_log(client):
    created = _create(client)
    with client.session_factory() as session:
        rows = session.scalars(select(AuditLog)).all()
        assert len(rows) == 1
        assert rows[0].action == "config.create"
        assert rows[0].actor_id == client.user.id
        assert rows[0].object_id == created["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: FAIL — `test_create_config_writes_audit_log` fails (`AuditLog` table empty, no dependency wired yet); the other tests still pass since the route doesn't require `get_current_user` yet.

- [ ] **Step 3: Wire the dependency and audit writes into `app/configs/routes.py`**

```python
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as repo
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.db import get_session
from app.geonode import ItemClient, StubItemClient
from app.users.models import User

router = APIRouter()

_default_item_client = StubItemClient()


def get_item_client() -> ItemClient:
    return _default_item_client


class CreateConfigRequest(BaseModel):
    title: str
    owner: str
    config: BuilderConfig


class RollbackRequest(BaseModel):
    version: int


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    item_id = items.create_item(
        title=request.title, type=request.config.kind, owner=request.owner
    )
    result = repo.create_config(session, request.config, item_id=item_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.create", object_type="config", object_id=result.id,
        payload={"title": request.title, "kind": request.config.kind},
    )
    return result


@router.get("/configs/{config_id}", response_model=ConfigRead)
def get_config(config_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.put("/configs/{config_id}", response_model=ConfigRead)
def update_config(
    config_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.update_config(session, config_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=config_id, payload={},
    )
    return result


@router.get("/configs/{config_id}/revisions", response_model=list[RevisionInfo])
def list_revisions(
    config_id: str, session: Session = Depends(get_session)
) -> list[RevisionInfo]:
    return repo.list_revisions(session, config_id)


@router.post("/configs/{config_id}/rollback", response_model=ConfigRead)
def rollback_config(
    config_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.rollback_config(session, config_id, request.version)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.rollback", object_type="config", object_id=config_id,
        payload={"restored_version": request.version},
    )
    return result


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, config_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=config_id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str, session: Session = Depends(get_session)
) -> ConfigRead:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.put("/configs/by-item/{item_id}", response_model=ConfigRead)
def update_config_by_item(
    item_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config_by_item(session, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="config not found")
    result = repo.update_config(session, existing.id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=existing.id, payload={},
    )
    return result


@router.delete("/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, result.id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

(`Iterator` import kept only if still used elsewhere in the file — it is not anymore, drop it: the final `from collections.abc import Iterator` line at the top of the file should be deleted since `get_session` no longer lives here.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: PASS — all tests including `test_create_config_writes_audit_log`.

- [ ] **Step 5: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/routes.py core/tests/test_routes.py
git commit -m "feat(core): require authentication and write audit_log on configs mutations"
```

---

### Task 8: `GET /me`

**Files:**
- Create: `core/app/auth/routes.py`
- Modify: `core/app/main.py`
- Create: `core/tests/test_me.py`

**Interfaces:**
- Consumes: `app.auth.dependency.get_current_user`.
- Produces: `GET /me` → `{id, tenantId, username, email, firstName, lastName}`. Not consumed by the shell yet (SP-1d).

- [ ] **Step 1: Write the failing test**

`core/tests/test_me.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="alice@example.com",
            first_name="Alice", last_name="Doe",
        )

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    yield test_client
    engine.dispose()


def test_get_me_returns_the_resolved_user(client):
    response = client.get("/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert body["firstName"] == "Alice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_me.py -v`
Expected: FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Write `app/auth/routes.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependency import get_current_user
from app.users.models import User

router = APIRouter()


class MeResponse(BaseModel):
    id: str
    tenantId: str
    username: str
    email: str | None
    firstName: str
    lastName: str


@router.get("/me", response_model=MeResponse)
def get_me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
    )
```

- [ ] **Step 4: Register the router in `app/main.py`**

Add the import:
```python
from app.auth import routes as auth_routes
```
and, next to `app.include_router(configs_routes.router)`, add:
```python
    app.include_router(auth_routes.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_me.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/app/auth/routes.py core/app/main.py core/tests/test_me.py
git commit -m "feat(core): add GET /me"
```

---

### Task 9: `import-linter` contract for module boundaries

**Files:**
- Modify: `core/pyproject.toml`

**Interfaces:**
- Consumes: the package layout produced by Tasks 2–8.
- Produces: a `lint-imports` command that passes on the current tree and fails if a lower-layer package imports a higher one.

- [ ] **Step 1: Add `import-linter` as a dev dependency and the contract**

Edit `core/pyproject.toml`:
```toml
[dependency-groups]
dev = [
    "pytest>=8.2",
    "import-linter>=2.0",
]

[tool.importlinter]
root_package = "app"

[[tool.importlinter.contracts]]
name = "layered architecture"
type = "layers"
layers = [
    "app.main",
    "app.configs",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

Run: `cd core && uv sync`
Expected: `import-linter` installed.

- [ ] **Step 2: Run the linter to confirm it passes on the current tree**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 3: Prove the contract actually catches a violation**

Temporarily add `from app.configs import routes  # noqa` to `core/app/tenants/repository.py`, run `cd core && uv run lint-imports`, confirm it reports the contract as broken (a lower layer importing a higher one), then remove the line.

- [ ] **Step 4: Run the full pytest suite (unaffected by this task)**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/pyproject.toml core/uv.lock
git commit -m "chore(core): enforce module layering with import-linter"
```

---

### Task 10: `export_openapi.py` script

**Files:**
- Create: `core/scripts/export_openapi.py`
- Create: `core/tests/test_export_openapi.py`

**Interfaces:**
- Consumes: `app.main.create_app`.
- Produces: a CLI (`python scripts/export_openapi.py <output_path>`) that writes the FastAPI OpenAPI schema to a JSON file without needing a running server or database — used by Task 11's CI job.

- [ ] **Step 1: Write the failing test**

`core/tests/test_export_openapi.py`:
```python
import json

from scripts.export_openapi import main


def test_main_writes_valid_openapi_json(tmp_path):
    output = tmp_path / "openapi.json"
    main(str(output))

    with open(output) as f:
        schema = json.load(f)

    assert schema["openapi"].startswith("3.")
    assert "/configs" in schema["paths"]
    assert "/me" in schema["paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_openapi.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`.

- [ ] **Step 3: Write the script**

`core/scripts/__init__.py`: empty file.

`core/scripts/export_openapi.py`:
```python
import json
import sys

from app.main import create_app


def main(output_path: str) -> None:
    app = create_app()
    with open(output_path, "w") as f:
        json.dump(app.openapi(), f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
```

- [ ] **Step 4: Ensure `pytest` can import `scripts` (pythonpath already includes `.`)**

`core/pyproject.toml` already sets `pythonpath = ["."]` under `[tool.pytest.ini_options]` — no change needed there. Confirm `core/scripts/__init__.py` exists (Step 3).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_export_openapi.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full pytest suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/scripts core/tests/test_export_openapi.py
git commit -m "feat(core): add export_openapi.py for the OpenAPI-to-TS CI pipeline"
```

---

### Task 11: shell — `openapi-typescript` generation

**Files:**
- Modify: `shell/package.json`
- Create: `shell/src/api/generated/core-schema.d.ts` (initial committed version)

**Interfaces:**
- Consumes: `core/openapi.json` (produced locally by Task 10's script).
- Produces: `npm run gen:api-types` in `shell/` — regenerates `shell/src/api/generated/core-schema.d.ts` from a local `core/openapi.json`. Not yet consumed by any shell code (that's SP-1d's `CoreItemClient`) — this task only wires the generation pipeline and commits its current output.

- [ ] **Step 1: Add `openapi-typescript` as a devDependency and the npm script**

Edit `shell/package.json`, add to `scripts`:
```json
    "gen:api-types": "openapi-typescript ../core/openapi.json -o src/api/generated/core-schema.d.ts"
```
and to `devDependencies`:
```json
    "openapi-typescript": "^7.4.0"
```

Run: `cd shell && npm install`
Expected: `openapi-typescript` added to `node_modules` and `package-lock.json`.

- [ ] **Step 2: Generate the core's OpenAPI schema and the TS types**

Run:
```bash
mkdir -p shell/src/api/generated
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` created; `shell/src/api/generated/core-schema.d.ts` created with TypeScript types matching the core's current routes (`/configs`, `/me`, `/health`, …).

- [ ] **Step 3: Confirm the shell still builds and tests pass**

Run: `cd shell && npm run build && npm run test`
Expected: PASS (the generated file is inert — nothing imports it yet).

- [ ] **Step 4: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/api/generated/core-schema.d.ts core/openapi.json
git commit -m "feat(shell): generate TypeScript types from the core's OpenAPI schema"
```

---

### Task 12: CI — `core` tests/lint job and OpenAPI→TS drift check

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `uv run pytest`, `uv run lint-imports` (Task 9), `uv run python scripts/export_openapi.py` (Task 10), `npm run gen:api-types` (Task 11).
- Produces: two new CI jobs, `core` (tests + import-linter) and `api-types-drift` (fails if the committed `core-schema.d.ts` no longer matches the core's OpenAPI schema).

- [ ] **Step 1: Add the `core` job to `.github/workflows/ci.yml`**

```yaml
  core:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: core
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest
      - run: uv run lint-imports
```

- [ ] **Step 2: Add the `api-types-drift` job**

```yaml
  api-types-drift:
    runs-on: ubuntu-latest
    needs: core
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: uv sync
        working-directory: core
      - run: uv run python scripts/export_openapi.py openapi.json
        working-directory: core
      - run: npm ci
        working-directory: shell
      - run: npm run gen:api-types
        working-directory: shell
      - run: git diff --exit-code -- shell/src/api/generated/core-schema.d.ts
```

- [ ] **Step 3: Verify the full workflow file is valid YAML and the drift check is currently green**

Run locally (simulating the CI steps):
```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --exit-code -- shell/src/api/generated/core-schema.d.ts
```
Expected: exit 0 (no diff — Task 11 already committed the up-to-date file).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run core tests/import-linter and check OpenAPI-to-TS drift"
```

---

## Self-review notes

- **Spec coverage:** Alembic + baseline (Task 1); tenants/users/audit/frontières packages (Tasks 3–5, 9); JWT OIDC + mock mode (Task 6); wiring into existing mutations (Task 7); `GET /me` (Task 8); CI OpenAPI→TS (Tasks 10–12). All six bullets of the spec's §1 content list and the §8 acceptance criteria have a corresponding task.
- **Type consistency checked:** `get_or_create_default_tenant(session) -> Tenant`, `get_or_create_user(session, *, tenant_id, oidc_sub, username, email, first_name, last_name) -> User`, `write_audit(session, *, tenant_id, actor_id, actor_kind, action, object_type, object_id, payload=None)`, `get_current_user(authorization, session) -> User` — used with identical signatures in Tasks 6, 7, 8.
- **Not covered here (by design, per spec's Hors périmètre):** `items`/`groups`/`item_shares` tables, shell wiring of `CoreItemClient`, removal of `app/geonode.py` — these belong to SP-1b/c/d and have their own specs already written.
