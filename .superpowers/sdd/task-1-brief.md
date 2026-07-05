### Task 1: `items` table, migration, layering, and cascade-safe deletion plumbing

**Files:**
- Create: `core/app/items/__init__.py`, `core/app/items/models.py`
- Create: `core/alembic/versions/0005_items.py`
- Modify: `core/alembic/env.py`
- Modify: `core/app/db.py` (SQLite FK enforcement)
- Modify: `core/app/configs/models.py` (`item_id` becomes a real FK)
- Modify: `core/pyproject.toml` (`import-linter` layers)
- Create: `core/tests/test_items_models.py`
- Modify: `core/tests/test_configs_models.py` (or wherever `Config`/`item_id` is constructed in tests — see Step 6)

**Interfaces:**
- Consumes: `app.db.Base`, `app.tenants.models.Tenant` (FK target only), `app.users.models.User` (FK target only).
- Produces: `app.items.models.Item` with columns `id`, `tenant_id`, `owner_id`, `resource_type`, `title`, `abstract`, `keywords`, `thumbnail_key`, `is_published`, `created_at`, `updated_at`. `core/app/configs/models.py`'s `Config.item_id` becomes `Mapped[str]` (no longer `str | None`), a real FK with `ondelete="CASCADE"`.

- [ ] **Step 1: Write the failing test for the `Item` model**

`core/tests/test_items_models.py`:
```python
from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory, init_db
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_can_persist_and_load_item():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            user = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice", email=None, first_name="", last_name="",
            )
            item = Item(
                id="item-1", tenant_id=tenant.id, owner_id=user.id,
                resource_type="app", title="My App",
            )
            session.add(item)
            session.commit()

        with Session() as session:
            loaded = session.scalar(select(Item).where(Item.id == "item-1"))
            assert loaded is not None
            assert loaded.title == "My App"
            assert loaded.abstract == ""
            assert loaded.keywords == []
            assert loaded.is_published is False
            assert loaded.thumbnail_key is None
    finally:
        engine.dispose()


def test_base_metadata_has_items_table():
    assert "items" in Base.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_items_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.items'`.

- [ ] **Step 3: Write the model**

`core/app/items/__init__.py`: empty file.

`core/app/items/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)  # "app" | "dashboard" | "map"
    title: Mapped[str] = mapped_column(String, nullable=False)
    abstract: Mapped[str] = mapped_column(String, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 4: Register the model in `init_db()` and `alembic/env.py`**

In `core/app/db.py`'s `init_db()`, add alongside the existing imports:
```python
    from app.items import models as items_models  # noqa: F401
```
(before `Base.metadata.create_all(engine)`, same pattern as `configs`/`tenants`/`users`/`audit`.)

In `core/alembic/env.py`, add:
```python
from app.items import models as items_models  # noqa: F401
```

- [ ] **Step 5: Enable SQLite foreign-key enforcement (required for the cascade this plan relies on)**

`core/app/db.py` currently has no FK-pragma handling — SQLite ignores `ON DELETE CASCADE` and even basic FK integrity unless `PRAGMA foreign_keys = ON` is set per connection. Add this to `core/app/db.py`, near `make_engine`:

```python
from sqlalchemy import event


def make_engine(url: str) -> Engine:
    if "memory" in url and url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine = create_engine(url, connect_args=connect_args)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine
```

(This replaces the existing `if "memory" in url...` branch's body with the same logic, just restructured so both branches fall through to the shared FK-pragma wiring. Read the current `core/app/db.py` first and adapt precisely — don't duplicate the `StaticPool` logic.)

- [ ] **Step 6: Make `Config.item_id` a real, non-null FK**

In `core/app/configs/models.py`, change:
```python
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
```
to:
```python
    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
```
(Add `ForeignKey` to the existing `from sqlalchemy import ...` import line if not already there — check the file first.)

This changes `create_config(session, config, item_id: str | None)`'s signature implicitly (the DB column no longer accepts `None`) — **do not change the Python function signature in this task**, that's Task 3's job once callers actually pass a real item id. For now, existing tests that call `repo.create_config(session, ..., item_id=None)` (e.g. in `core/tests/test_repository.py`) will break; fix them by passing a real (even if fake-looking, e.g. `item_id="item-1"`) non-null string, since this task only touches schema, not the creation flow — check each call site in `test_repository.py` and update any `item_id=None` to a placeholder string id. This is a mechanical fix; do not invent new items rows for these — the FK constraint isn't yet enforced against real `items` rows in these particular tests since SQLite only checks the referenced table has *a* matching row if FK enforcement is on and the column has a FK — wait: since Step 5 turns FK enforcement ON, a `create_config` call with `item_id="item-1"` when no `items` row `"item-1"` exists will now raise an `IntegrityError` in SQLite too. Read `test_repository.py` and any other place calling `create_config`/constructing a `Config` directly, and for each one, insert a matching `Item` row first (using the same pattern as `test_items_models.py`'s fixture: `get_or_create_default_tenant` + `get_or_create_user` + a plain `Item(...)`) before calling `create_config`. Do this for every failing test — there is no shortcut here, the FK is now real.

- [ ] **Step 7: Update the import-linter layers contract**

In `core/pyproject.toml`'s `[[tool.importlinter.contracts]]` block, change:
```toml
layers = [
    "app.main",
    "app.configs",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```
to:
```toml
layers = [
    "app.main",
    "app.configs",
    "app.items",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```
(`app.items` sits directly below `app.configs` — `configs` may import `items`, `items` may not import `configs`.)

- [ ] **Step 8: Write the migration**

`core/alembic/versions/0005_items.py`:
```python
"""items table; configs.item_id becomes a real FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("abstract", sa.String(), nullable=False, server_default=""),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # No pre-existing `configs` rows are expected in any real deployment yet
    # (no prod cutover has happened — see A15). If a dev database has stale
    # rows from manual testing, reset it (`docker compose down -v` on
    # `postgis`) rather than migrating them: there is no real title/owner
    # data to reconstruct an `items` row from at the DB level.
    op.drop_column("configs", "item_id")
    op.add_column(
        "configs",
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("configs", "item_id")
    op.add_column("configs", sa.Column("item_id", sa.String(), nullable=True))
    op.drop_table("items")
```

- [ ] **Step 9: Run the model test to verify it passes**

Run: `cd core && uv run pytest tests/test_items_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 10: Fix the broken tests from Step 6, then run the full suite**

Run: `cd core && uv run pytest`
Expected: PASS — fix any remaining `item_id=None` or FK-violation failures per Step 6's instructions until this is green.

- [ ] **Step 11: Verify `lint-imports` still passes with the new layer**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 12: Run the migration round-trip against Postgres**

```bash
docker run -d --rm --name sp1b-migration-check -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis -p 55441:5432 postgis/postgis:16-3.4
# wait for pg_isready, then:
cd core
DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55441/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55441/gis uv run alembic downgrade base
docker rm -f sp1b-migration-check
```
Expected: both exit 0.

- [ ] **Step 13: Commit**

```bash
git add core/app/items/__init__.py core/app/items/models.py core/app/db.py core/app/configs/models.py core/alembic/env.py core/alembic/versions/0005_items.py core/pyproject.toml core/uv.lock core/tests/test_items_models.py core/tests/test_repository.py
git commit -m "feat(core): add items table; configs.item_id becomes a real cascading FK"
```

---

