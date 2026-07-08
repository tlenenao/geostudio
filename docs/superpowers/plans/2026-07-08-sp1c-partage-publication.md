# SP-1c — Partage & publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the cœur a real private/group/public sharing model (`groups`, `group_members`, `item_shares`) and a single authorization gate `can(user, action, item)`, then use it to actually enforce visibility on every existing `items`/`configs` route (today `GET /items?scope=all` and most `configs` read routes have **no** visibility enforcement at all — any authenticated tenant member can read any item, and several `configs` routes have no authentication dependency whatsoever). Also adds anonymous runtime access to published items (`/public/*`).

**Architecture:** A new `app.sharing` package sits **between** `app.items` and `app.auth` in the layering (`app.main` → `app.public` → `app.configs` → `app.items` → **`app.sharing`** → `app.auth` → `app.audit` → `app.users` → `app.tenants`). `app.sharing.authorization.can()` must never import `app.items` (that would be a lower layer importing a higher one), so it takes a small `ItemAccessFacts` dataclass (`id`, `tenant_id`, `owner_id`, `is_public`, `is_published`) instead of the `Item` ORM object — callers in `app.items`/`app.configs` (both above `sharing`) build this from a row they already fetched. A new `app.public` package sits **above** `app.configs` (it needs both `Config` and `Item` directly, and deliberately does not depend on `app.auth` at all — it is the cœur's only anonymous entry point). `GET /items/{id}/sharing` and `PUT /items/{id}/sharing` live in `app.items.routes` (not `app.sharing.routes`): they need to look up the `Item` itself, which `app.sharing` cannot do.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pytest, uv — no new dependency.

## Global Constraints

- `can(session, *, user_id, action, item: ItemAccessFacts) -> bool` is the **only** authorization gate (arbitrage A1). No route may implement its own visibility logic in parallel.
- 404 vs 403 (spec §2): item invisible in read (`can(read)` false) → **404** (anti-enumeration). Item visible in read but action refused → **403**.
- `is_public` (new, on `items`) = visible in the catalogue to all authenticated tenant members. `is_published` (existing, since SP-1b) = accessible **anonymously** at runtime. These are independent; neither implies the other. `scope=public` filters on `is_published` (unchanged from SP-1b — this is intentional, matches current shell behavior against GeoNode).
- Public sharing (`is_public=true`) is always read-only — no role selector in the existing `ShareDialog` UX. `share` action requires `editor`, same bar as `write`/`delete` (v0 has no separate "admin" role).
- Groups are tenant-scoped (`groups.tenant_id`), managed by the cœur (not Keycloak claims). No dedicated admin UI in v0 — `POST /groups` is open to any authenticated user, tightened later only if real misuse appears.
- Every table gets `tenant_id`, including the two join tables (`group_members`, `item_shares`) — the existing `configs`/`config_revisions` tables also carry a DB-level `tenant_id` column (added in SP-1a's migration 0002) even though their ORM models don't surface it; this plan's new tables surface `tenant_id` on the ORM model too, since `can()`'s group-membership queries use it as a defense-in-depth filter alongside the join.
- Cross-tenant references (a `groupId` from another tenant in a sharing PUT, a `userId` from another tenant in `POST /groups/{id}/members`) → **404**, never a leak of cross-tenant existence.
- Shell wiring (`itemClient.ts`, `ShareDialog.tsx`) is explicitly **out of scope** — that's SP-1d. This plan only has to keep the core's OpenAPI schema honest (regenerate `core/openapi.json` and `shell/src/api/generated/core-schema.d.ts`, per the existing CI drift check) — no shell behavior changes.
- Layering (import-linter, high → low): `app.main` → `app.public` → `app.configs` → `app.items` → `app.sharing` → `app.auth` → `app.audit` → `app.users` → `app.tenants` → `app.db`. This plan inserts `app.public` above `app.configs` and `app.sharing` between `app.items` and `app.auth`.
- Interfaces this plan consumes from SP-1a/SP-1b (already merged on `dev`): `app.db.get_session`, `app.auth.dependency.get_current_user(authorization, session) -> User`, `app.audit.writer.write_audit(session, *, tenant_id, actor_id, actor_kind, action, object_type, object_id, payload=None) -> None`, `app.users.models.User` (fields: `id`, `tenant_id`, `username`, ...), `app.items.models.Item` (fields: `id`, `tenant_id`, `owner_id`, `resource_type`, `title`, `abstract`, `keywords`, `thumbnail_key`, `is_published`, `created_at`, `updated_at`), `app.items.repository.{create_item, get_item, list_items, update_item, set_thumbnail_key, get_thumbnail_key}`, `app.items.schemas.{ItemRead, ItemPage, ItemUpdatePatch}`, `app.configs.repository.{create_config, get_config, get_config_by_item, update_config, list_revisions, rollback_config, ConfigRead, RevisionInfo}`.

---

### Task 1: `sharing` models, `items.is_public`, migration, layering

**Files:**
- Create: `core/app/sharing/__init__.py`, `core/app/sharing/models.py`
- Modify: `core/app/items/models.py` (add `is_public`)
- Create: `core/alembic/versions/0006_sharing.py`
- Modify: `core/alembic/env.py`
- Modify: `core/app/db.py` (`init_db`)
- Modify: `core/pyproject.toml` (import-linter layers)
- Create: `core/tests/test_sharing_models.py`

**Interfaces:**
- Consumes: `app.db.Base`.
- Produces: `app.sharing.models.{Group, GroupMember, ItemShare}`. `Group`: `id`, `tenant_id`, `name`, `created_at`. `GroupMember`: `group_id` (PK), `user_id` (PK), `tenant_id`. `ItemShare`: `item_id` (PK), `group_id` (PK), `tenant_id`, `role` (`"viewer"` | `"editor"`). `app.items.models.Item` gains `is_public: Mapped[bool]` (default `False`).

- [ ] **Step 1: Write the failing test**

`core/tests/test_sharing_models.py`:
```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, make_session_factory, init_db
from app.items import repository as items_repo
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_group_member_and_item_share_round_trip(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    bob = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-2",
        username="bob", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="Shared app",
    )

    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers")
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    session.flush()

    member = session.get(GroupMember, {"group_id": group.id, "user_id": bob.id})
    assert member is not None
    share = session.get(ItemShare, {"item_id": item.id, "group_id": group.id})
    assert share is not None
    assert share.role == "viewer"


def test_item_share_cascades_on_item_delete(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="Will be deleted",
    )
    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers")
    session.add(group)
    session.flush()
    session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    session.flush()

    from sqlalchemy import delete
    from app.items.models import Item

    session.execute(delete(Item).where(Item.id == item.id))
    session.flush()

    assert session.get(ItemShare, {"item_id": item.id, "group_id": group.id}) is None


def test_item_is_public_defaults_false(session):
    tenant = get_or_create_default_tenant(session)
    alice = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=alice.id,
        resource_type="app", title="X",
    )
    assert item.is_public is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_sharing_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sharing'`.

- [ ] **Step 3: Write the models**

`core/app/sharing/__init__.py`: empty file.

`core/app/sharing/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)


class ItemShare(Base):
    __tablename__ = "item_shares"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "viewer" | "editor"
```

- [ ] **Step 4: Add `is_public` to `Item`**

In `core/app/items/models.py`, add the column next to `is_published`:
```python
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 5: Register the new models in `init_db` and `alembic/env.py`**

In `core/app/db.py`'s `init_db`, add next to the other model imports:
```python
    from app.sharing import models as sharing_models  # noqa: F401
```

In `core/alembic/env.py`, add next to the other model imports:
```python
from app.sharing import models as sharing_models  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_sharing_models.py -v`
Expected: PASS.

- [ ] **Step 7: Write the migration**

`core/alembic/versions/0006_sharing.py`:
```python
"""groups, group_members, item_shares; items.is_public

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "group_members",
        sa.Column(
            "group_id", sa.String(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
    )
    op.create_table(
        "item_shares",
        sa.Column(
            "item_id", sa.String(),
            sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "group_id", sa.String(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("item_shares")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_column("items", "is_public")
```

- [ ] **Step 8: Add the `app.sharing` layer to the import-linter contract**

In `core/pyproject.toml`, change the `[[tool.importlinter.contracts]]` block:
```toml
[[tool.importlinter.contracts]]
name = "layered architecture"
type = "layers"
layers = [
    "app.main",
    "app.public",
    "app.configs",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
ignore_imports = [
    "app.db -> app.configs.models",
    "app.db -> app.items.models",
    "app.db -> app.audit.models",
    "app.db -> app.tenants.models",
    "app.db -> app.users.models",
    "app.db -> app.sharing.models",
]
```
(`app.public` has no code yet — Task 7 adds it. Declaring the layer now means Task 7 doesn't need to touch this contract again.)

- [ ] **Step 9: Run migration cycle against Postgres, then the full test suite and import-linter**

Run:
```bash
docker compose up -d postgis
cd core
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
uv run pytest
uv run lint-imports
```
Expected: migration cycle exits 0; `pytest` all green; `lint-imports` reports no contract violations (the `app.public` layer has no importing/imported modules yet, which is fine).

- [ ] **Step 10: Commit**

```bash
git add core/app/sharing core/app/items/models.py core/app/db.py core/alembic core/pyproject.toml core/tests/test_sharing_models.py
git commit -m "feat(core): add groups/group_members/item_shares tables and items.is_public"
```

---

### Task 2: `can()` — the single authorization gate, with the full test matrix

**Files:**
- Create: `core/app/sharing/repository.py`
- Create: `core/app/sharing/authorization.py`
- Create: `core/tests/test_sharing_authorization.py`

**Interfaces:**
- Consumes: `app.sharing.models.{Group, GroupMember, ItemShare}`, `app.users.models.User` (for tenant-scoped membership validation only).
- Produces: `app.sharing.repository.{has_group_role, create_group, list_groups, add_member, list_shares, replace_shares}`; `app.sharing.authorization.{ItemAccessFacts, can}`. `ItemAccessFacts` is a frozen dataclass with fields `id: str`, `tenant_id: str`, `owner_id: str`, `is_public: bool`, `is_published: bool` — this is what every later task (items/configs/public routes) constructs from an `Item` row to call `can()` without `app.sharing` ever importing `app.items`.

- [ ] **Step 1: Write the failing test — the full authorization matrix**

`core/tests/test_sharing_authorization.py`:
```python
import pytest

from app.db import make_engine, make_session_factory, init_db
from app.sharing.authorization import ItemAccessFacts, can
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def actors(session):
    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-owner",
        username="owner", email=None, first_name="", last_name="",
    )
    viewer = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-viewer",
        username="viewer", email=None, first_name="", last_name="",
    )
    editor = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-editor",
        username="editor", email=None, first_name="", last_name="",
    )
    stranger = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-stranger",
        username="stranger", email=None, first_name="", last_name="",
    )

    viewer_group = Group(id="viewers", tenant_id=tenant.id, name="Viewers")
    editor_group = Group(id="editors", tenant_id=tenant.id, name="Editors")
    session.add_all([viewer_group, editor_group])
    session.flush()
    session.add(GroupMember(group_id=viewer_group.id, user_id=viewer.id, tenant_id=tenant.id))
    session.add(GroupMember(group_id=editor_group.id, user_id=editor.id, tenant_id=tenant.id))
    session.flush()

    def make_item(item_id: str, *, is_public: bool = False, is_published: bool = False) -> ItemAccessFacts:
        session.add(ItemShare(
            item_id=item_id, group_id=viewer_group.id, tenant_id=tenant.id, role="viewer",
        ))
        session.add(ItemShare(
            item_id=item_id, group_id=editor_group.id, tenant_id=tenant.id, role="editor",
        ))
        session.flush()
        return ItemAccessFacts(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id,
            is_public=is_public, is_published=is_published,
        )

    return {
        "owner": owner, "viewer": viewer, "editor": editor, "stranger": stranger,
        "make_item": make_item,
    }


@pytest.mark.parametrize("action", ["read", "write", "delete", "share"])
def test_owner_can_do_everything(session, actors, action):
    item = actors["make_item"]("item-owner")
    assert can(session, user_id=actors["owner"].id, action=action, item=item) is True


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_group_viewer(session, actors, action, expected):
    item = actors["make_item"]("item-viewer")
    assert can(session, user_id=actors["viewer"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", True), ("delete", True), ("share", True)]
)
def test_group_editor(session, actors, action, expected):
    item = actors["make_item"]("item-editor")
    assert can(session, user_id=actors["editor"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_public_item_stranger(session, actors, action, expected):
    item = actors["make_item"]("item-public", is_public=True)
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is expected


@pytest.mark.parametrize(
    "action,expected", [("read", True), ("write", False), ("delete", False), ("share", False)]
)
def test_published_item_stranger(session, actors, action, expected):
    item = actors["make_item"]("item-published", is_published=True)
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is expected


@pytest.mark.parametrize("action", ["read", "write", "delete", "share"])
def test_stranger_with_no_relation_is_denied(session, actors, action):
    item = actors["make_item"]("item-private")
    assert can(session, user_id=actors["stranger"].id, action=action, item=item) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_sharing_authorization.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sharing.authorization'`.

- [ ] **Step 3: Write the repository (group-role query + group/share CRUD)**

`core/app/sharing/repository.py`:
```python
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.sharing.models import Group, GroupMember, ItemShare
from app.users.models import User


def has_group_role(
    session: Session, *, tenant_id: str, item_id: str, user_id: str, roles: set[str]
) -> bool:
    stmt = (
        select(ItemShare.role)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id == item_id,
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
            ItemShare.role.in_(roles),
        )
    )
    return session.scalar(stmt) is not None


def create_group(session: Session, *, tenant_id: str, name: str) -> Group:
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant_id, name=name)
    session.add(group)
    session.flush()
    session.refresh(group)
    return group


def list_groups(session: Session, *, tenant_id: str) -> list[Group]:
    return list(
        session.scalars(
            select(Group).where(Group.tenant_id == tenant_id).order_by(Group.created_at)
        ).all()
    )


def add_member(session: Session, *, tenant_id: str, group_id: str, user_id: str) -> bool:
    group = session.get(Group, group_id)
    if group is None or group.tenant_id != tenant_id:
        return False
    user_tenant = session.scalar(select(User.tenant_id).where(User.id == user_id))
    if user_tenant != tenant_id:
        return False
    existing = session.get(GroupMember, {"group_id": group_id, "user_id": user_id})
    if existing is None:
        session.add(GroupMember(group_id=group_id, user_id=user_id, tenant_id=tenant_id))
        session.flush()
    return True


def list_shares(session: Session, *, item_id: str) -> list[ItemShare]:
    return list(
        session.scalars(select(ItemShare).where(ItemShare.item_id == item_id)).all()
    )


def replace_shares(
    session: Session, *, tenant_id: str, item_id: str, shares: list[tuple[str, str]]
) -> bool:
    """Replace all group shares for one item. Returns False (no changes made)
    if any group_id doesn't belong to tenant_id — the caller must treat this
    as a 404 (never leak cross-tenant group existence)."""
    group_ids = [group_id for group_id, _role in shares]
    if group_ids:
        matching = session.scalar(
            select(func.count())
            .select_from(Group)
            .where(Group.tenant_id == tenant_id, Group.id.in_(group_ids))
        )
        if matching != len(set(group_ids)):
            return False

    session.execute(delete(ItemShare).where(ItemShare.item_id == item_id))
    for group_id, role in shares:
        session.add(ItemShare(item_id=item_id, group_id=group_id, tenant_id=tenant_id, role=role))
    session.flush()
    return True
```

- [ ] **Step 4: Write `can()`**

`core/app/sharing/authorization.py`:
```python
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.sharing.repository import has_group_role

Action = Literal["read", "write", "delete", "share"]


@dataclass(frozen=True)
class ItemAccessFacts:
    """Everything `can()` needs about one item, without importing
    `app.items.models.Item` (app.sharing sits below app.items in the
    layering — see plan Architecture). Callers build this from an Item row
    they already fetched."""

    id: str
    tenant_id: str
    owner_id: str
    is_public: bool
    is_published: bool


def can(session: Session, *, user_id: str, action: Action, item: ItemAccessFacts) -> bool:
    if item.owner_id == user_id:
        return True
    if action == "read":
        if item.is_public or item.is_published:
            return True
        return has_group_role(
            session, tenant_id=item.tenant_id, item_id=item.id, user_id=user_id,
            roles={"viewer", "editor"},
        )
    if action in ("write", "delete", "share"):
        return has_group_role(
            session, tenant_id=item.tenant_id, item_id=item.id, user_id=user_id,
            roles={"editor"},
        )
    return False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_sharing_authorization.py -v`
Expected: PASS — all matrix cases.

- [ ] **Step 6: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS. `app.sharing` importing `app.users.models` is a lower→lower import (both below `app.items`), already permitted by the layers contract without new `ignore_imports` entries.

- [ ] **Step 7: Commit**

```bash
git add core/app/sharing/repository.py core/app/sharing/authorization.py core/tests/test_sharing_authorization.py
git commit -m "feat(core): can() authorization gate with full read/write/delete/share matrix"
```

---

### Task 3: Enforce `can()` in `app.items` — real scope filtering + route checks

**Files:**
- Modify: `core/app/items/repository.py`
- Modify: `core/app/items/routes.py`
- Modify: `core/tests/test_items_repository.py`
- Modify: `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes: `app.sharing.authorization.{ItemAccessFacts, can}`, `app.sharing.models.{ItemShare, GroupMember}`.
- Produces: `app.items.repository.get_access_facts(session, *, tenant_id, item_id) -> ItemAccessFacts | None`. `list_items`'s `scope="shared"`/`scope="all"` now run real SQL predicates instead of an empty page / no filter.

- [ ] **Step 1: Write the failing tests — real scope filtering**

In `core/tests/test_items_repository.py`, replace `test_list_items_scope_shared_is_empty` with:
```python
def test_list_items_scope_shared_excludes_owned_items_with_no_shares(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Any")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert page.total == 0
    assert page.items == []


def test_list_items_scope_shared_and_all(session, tenant_and_user):
    from app.sharing.models import Group, GroupMember, ItemShare

    tenant, owner = tenant_and_user
    bob = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-bob",
        username="bob", email=None, first_name="", last_name="",
    )
    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers")
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=tenant.id))

    owned_by_owner = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Owner's"
    )
    shared_with_bob = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Shared"
    )
    session.add(ItemShare(item_id=shared_with_bob.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    public_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Public"
    )
    public_item.is_public = True
    invisible = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Invisible"
    )
    session.flush()

    shared_page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert shared_page.total == 1
    assert [i.title for i in shared_page.items] == ["Shared"]

    all_page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="all", page=1, page_size=12,
    )
    assert all_page.total == 2
    titles = {i.title for i in all_page.items}
    assert titles == {"Shared", "Public"}
    assert "Invisible" not in titles
    assert "Owner's" not in titles  # bob doesn't own it, isn't shared, not public

    # Pagination correctness (spec §7): a small page_size must still report the
    # true total and return exactly the items for that page, not an
    # in-memory-filtered approximation.
    first_of_two = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="all", page=1, page_size=1,
    )
    assert first_of_two.total == 2
    assert len(first_of_two.items) == 1


def test_get_access_facts(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")

    facts = repo.get_access_facts(session, tenant_id=tenant.id, item_id=item.id)
    assert facts is not None
    assert facts.owner_id == user.id
    assert facts.is_public is False
    assert facts.is_published is False


def test_get_access_facts_missing_returns_none(session, tenant_and_user):
    tenant, _ = tenant_and_user
    assert repo.get_access_facts(session, tenant_id=tenant.id, item_id="nope") is None
```
Add `from app.users.repository import get_or_create_user` to the top of the file if not already imported (it already is, per the existing `test_list_items_scope_mine`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: FAIL — `test_get_access_facts` with `AttributeError: module has no attribute 'get_access_facts'`; `test_list_items_scope_shared_and_all` with items appearing that shouldn't (scope=all currently has no filter).

- [ ] **Step 3: Implement `get_access_facts` and real scope filtering**

In `core/app/items/repository.py`, add the import and function:
```python
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
```
```python
def get_access_facts(session: Session, *, tenant_id: str, item_id: str) -> ItemAccessFacts | None:
    row = session.execute(
        select(Item.id, Item.tenant_id, Item.owner_id, Item.is_public, Item.is_published)
        .where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).first()
    if row is None:
        return None
    return ItemAccessFacts(
        id=row.id, tenant_id=row.tenant_id, owner_id=row.owner_id,
        is_public=row.is_public, is_published=row.is_published,
    )
```

Replace `list_items`'s scope handling — remove the early `if scope == "shared": return ItemPage(...)` guard and the `elif scope == "all"` no-op comment, replacing the whole scope block with:
```python
    query = select(Item, User.username).join(User, User.id == Item.owner_id).where(Item.tenant_id == tenant_id)
    if resource_type:
        query = query.where(Item.resource_type == resource_type)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))

    shared_exists = (
        select(ItemShare.item_id)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id == Item.id,
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == current_user_id,
            GroupMember.tenant_id == tenant_id,
        )
        .exists()
    )
    if scope == "mine":
        query = query.where(Item.owner_id == current_user_id)
    elif scope == "public":
        query = query.where(Item.is_published.is_(True))
    elif scope == "shared":
        query = query.where(Item.owner_id != current_user_id, shared_exists)
    elif scope == "all":
        query = query.where(
            or_(
                Item.owner_id == current_user_id,
                Item.is_public.is_(True),
                Item.is_published.is_(True),
                shared_exists,
            )
        )
```
(delete the old function's leading `if scope == "shared": return ItemPage(items=[], total=0, page=page, pageSize=page_size)` line and the trailing `# scope == "all": no extra filter (real visibility filtering arrives in SP-1c)` comment — both are superseded.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing tests — route-level enforcement**

In `core/tests/test_items_routes.py`, add a second user fixture helper and new tests:
```python
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _other_user(client, username="mallory"):
    with client.session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub=f"sub-{username}",
            username=username, email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(user)
    return user


def test_get_item_invisible_to_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.get(f"/items/{item_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_patch_item_by_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.patch(f"/items/{item_id}", json={"title": "hijacked"})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_patch_item_by_group_viewer_returns_403(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    item_id = _seed_item(client)
    bob = _other_user(client, "bob")
    with client.session_factory() as session:
        group = Group(id="g1", tenant_id=client.tenant.id, name="Reviewers")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: bob
    try:
        get_response = client.get(f"/items/{item_id}")
        patch_response = client.patch(f"/items/{item_id}", json={"title": "hijacked"})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert get_response.status_code == 200
    assert patch_response.status_code == 403


def test_upload_thumbnail_by_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    store = InMemoryThumbnailStore()
    client.app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: store
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.post(
            f"/items/{item_id}/thumbnail",
            files={"file": ("thumb.png", io.BytesIO(b"x"), "image/png")},
        )
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_routes.py -v`
Expected: FAIL — `test_get_item_invisible_to_non_owner_returns_404` and friends get 200 instead of 404/403 (no enforcement yet).

- [ ] **Step 7: Enforce `can()` in `items/routes.py`**

In `core/app/items/routes.py`, add the import:
```python
from app.sharing.authorization import can
```

Replace `get_item`:
```python
@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    result = repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result
```

Replace `update_item`:
```python
@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    item_id: str,
    patch: ItemUpdatePatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="write", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to modify this item")

    result = repo.update_item(
        session, tenant_id=user.tenant_id, item_id=item_id,
        title=patch.title, abstract=patch.abstract, keywords=patch.keywords,
        is_published=patch.isPublished,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")

    if patch.isPublished is True:
        action = "item.publish"
    elif patch.isPublished is False:
        action = "item.unpublish"
    else:
        action = "item.update"
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action=action, object_type="item", object_id=item_id, payload={},
    )
    return result
```

Replace `upload_thumbnail` and `read_thumbnail`:
```python
@router.post("/items/{item_id}/thumbnail", status_code=status.HTTP_204_NO_CONTENT)
def upload_thumbnail(
    item_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    store: ThumbnailStore = Depends(get_thumbnail_store),
) -> Response:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="write", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to modify this item")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    content = file.file.read()
    if len(content) > _MAX_THUMBNAIL_BYTES:
        raise HTTPException(status_code=413, detail="thumbnail too large")

    key = f"{item_id}.bin"
    store.upload(key, content, content_type)
    repo.set_thumbnail_key(session, tenant_id=user.tenant_id, item_id=item_id, thumbnail_key=key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/items/{item_id}/thumbnail")
def read_thumbnail(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    store: ThumbnailStore = Depends(get_thumbnail_store),
) -> Response:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    key = repo.get_thumbnail_key(session, tenant_id=user.tenant_id, item_id=item_id)
    if key is None:
        raise HTTPException(status_code=404, detail="no thumbnail")
    content, content_type = store.read(key)
    return Response(content=content, media_type=content_type)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_routes.py tests/test_items_repository.py -v`
Expected: PASS, including the pre-existing tests (all use the owner, so `can()` short-circuits `True`).

- [ ] **Step 9: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add core/app/items core/tests/test_items_repository.py core/tests/test_items_routes.py
git commit -m "feat(core): enforce can() on items routes; real SQL scope=shared/all filtering"
```

---

### Task 4: Enforce `can()` in `app.configs` routes

**Files:**
- Modify: `core/app/configs/routes.py`
- Modify: `core/tests/test_routes.py`

**Interfaces:**
- Consumes: `app.items.repository.get_access_facts`, `app.sharing.authorization.can`, `app.sharing.models.ItemShare` (for the delete helper's explicit cleanup, mirroring the existing explicit-delete-in-order style rather than relying only on the FK cascade).
- Produces: every `configs` route that touches an existing item now requires `get_current_user` and enforces `can()`; unauthorized/invisible → 404, visible-but-forbidden → 403.

- [ ] **Step 1: Write the failing tests**

The `client` fixture in this file doesn't expose `tenant` yet (only `test_items_routes.py`'s does). In `client()`'s fixture body, after `test_client.user = user`, add:
```python
    test_client.tenant = tenant  # type: ignore[attr-defined]
```

Now add a same-tenant non-owner helper, next to the existing `_other_tenant_user`:
```python
def _same_tenant_stranger(client) -> object:
    with client.session_factory() as session:
        stranger = get_or_create_user(
            session, tenant_id=client.tenant.id,
            oidc_sub="sub-stranger", username="stranger",
            email="stranger@example.com", first_name="Stranger", last_name="Doe",
        )
        session.commit()
        session.refresh(stranger)
    return stranger
```

And the tests (`get_or_create_user` is already imported at the top of this file, used by `_other_tenant_user`):
```python
def test_get_config_invisible_to_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/{created['id']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_put_config_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.put(f"/configs/{created['id']}", json=_config_body())
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_revisions_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/{created['id']}/revisions")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_rollback_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_delete_config_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.delete(f"/configs/{created['id']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, created["itemId"]) is not None


def test_get_config_by_item_invisible_to_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/by-item/{created['itemId']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_group_editor_can_update_config(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    created = _create(client)
    with client.session_factory() as session:
        editor = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-editor",
            username="editor", email=None, first_name="", last_name="",
        )
        group = Group(id="g1", tenant_id=client.tenant.id, name="Editors")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=editor.id, tenant_id=client.tenant.id))
        session.add(ItemShare(
            item_id=created["itemId"], group_id=group.id, tenant_id=client.tenant.id, role="editor",
        ))
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: editor
    try:
        response = client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: FAIL — all the `_stranger` tests get 200/200/200 instead of 404 (no enforcement yet); `test_group_editor_can_update_config` fails identically to a stranger case until enforcement exists, then would need the wiring to pass.

- [ ] **Step 3: Enforce `can()` in `configs/routes.py`**

In `core/app/configs/routes.py`, add the import:
```python
from app.sharing.authorization import can
```

Add a small local helper right after the imports (keeps every route's check to two lines instead of repeating the facts-lookup dance five times):
```python
def _require_access(
    session: Session, *, user: User, item_id: str, action: str
) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")
```

Update `_delete_config_and_item` to also clear `item_shares` (explicit, matching the existing explicit-delete-then-delete-parent style rather than relying only on the FK cascade):
```python
def _delete_config_and_item(session: Session, config_id: str, item_id: str, tenant_id: str) -> None:
    from sqlalchemy import delete
    from app.configs.models import ConfigRevision, Config
    from app.sharing.models import ItemShare

    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.execute(delete(Config).where(Config.id == config_id))
    session.execute(delete(ItemShare).where(ItemShare.item_id == item_id))
    session.execute(delete(Item).where(Item.id == item_id, Item.tenant_id == tenant_id))
    session.flush()
```

Replace `get_config`:
```python
@router.get("/configs/{config_id}", response_model=ConfigRead)
def get_config(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.get_config(session, config_id)
    if result is None or result.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=result.itemId, action="read")
    return result
```

Replace `update_config`:
```python
@router.put("/configs/{config_id}", response_model=ConfigRead)
def update_config(
    config_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="write")

    result = repo.update_config(session, config_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=config_id, payload={},
    )
    return result
```

Replace `list_revisions`:
```python
@router.get("/configs/{config_id}/revisions", response_model=list[RevisionInfo])
def list_revisions(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RevisionInfo]:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="read")
    return repo.list_revisions(session, config_id)
```

Replace `rollback_config`:
```python
@router.post("/configs/{config_id}/rollback", response_model=ConfigRead)
def rollback_config(
    config_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="write")

    result = repo.rollback_config(session, config_id, request.version)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.rollback", object_type="config", object_id=config_id,
        payload={"restored_version": request.version},
    )
    return result
```

Replace `delete_config`:
```python
@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config(session, config_id)
    if result is None or result.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=result.itemId, action="delete")

    _delete_config_and_item(session, config_id, result.itemId, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=config_id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=result.itemId, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Replace `get_config_by_item`:
```python
@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_access(session, user=user, item_id=item_id, action="read")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
```

Replace `update_config_by_item`:
```python
@router.put("/configs/by-item/{item_id}", response_model=ConfigRead)
def update_config_by_item(
    item_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_access(session, user=user, item_id=item_id, action="write")
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
```

Replace `delete_config_by_item`:
```python
@router.delete("/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    _require_access(session, user=user, item_id=item_id, action="delete")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=item_id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Replace `delete_item`:
```python
@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    _require_access(session, user=user, item_id=item_id, action="delete")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=item_id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: PASS, including the pre-existing cross-tenant tests (`_require_access`'s facts lookup is tenant-scoped, so a cross-tenant caller gets the same 404 they got before, now via `can()` instead of a bespoke `items_repo.get_item` check).

- [ ] **Step 5: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/routes.py core/tests/test_routes.py
git commit -m "feat(core): enforce can() on every configs route touching an item"
```

---

### Task 5: `GET`/`PUT /items/{id}/sharing`

**Files:**
- Create: `core/app/sharing/schemas.py`
- Modify: `core/app/items/repository.py` (`set_is_public`)
- Modify: `core/app/items/routes.py`
- Modify: `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes: `app.sharing.repository.{list_shares, replace_shares}`.
- Produces: `app.sharing.schemas.{Sharing, GroupShare}` (`Sharing = {public: bool, groups: GroupShare[]}`, `GroupShare = {groupId: str, role: "viewer"|"editor"}` — matches the shell's existing `Sharing` type in `shell/src/api/types.ts`, though wiring the shell itself is SP-1d). `app.items.repository.set_is_public(session, *, tenant_id, item_id, is_public) -> None`.

- [ ] **Step 1: Write the failing tests**

In `core/tests/test_items_routes.py`, add:
```python
def test_get_sharing_defaults_to_private(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}/sharing")
    assert response.status_code == 200
    assert response.json() == {"public": False, "groups": []}


def test_put_then_get_sharing_round_trips(client):
    from app.sharing.models import Group

    item_id = _seed_item(client)
    with client.session_factory() as session:
        session.add(Group(id="g1", tenant_id=client.tenant.id, name="Reviewers"))
        session.commit()

    put_response = client.put(
        f"/items/{item_id}/sharing",
        json={"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]},
    )
    assert put_response.status_code == 204

    get_response = client.get(f"/items/{item_id}/sharing")
    assert get_response.status_code == 200
    assert get_response.json() == {
        "public": True, "groups": [{"groupId": "g1", "role": "viewer"}],
    }


def test_put_sharing_with_unknown_group_returns_404(client):
    item_id = _seed_item(client)
    response = client.put(
        f"/items/{item_id}/sharing",
        json={"public": False, "groups": [{"groupId": "nope", "role": "viewer"}]},
    )
    assert response.status_code == 404


def test_put_sharing_writes_audit_log(client):
    from sqlalchemy import select
    from app.audit.models import AuditLog

    item_id = _seed_item(client)
    client.put(f"/items/{item_id}/sharing", json={"public": True, "groups": []})
    with client.session_factory() as session:
        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        assert "item.share" in actions


def test_get_sharing_invisible_to_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.get(f"/items/{item_id}/sharing")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_put_sharing_by_group_viewer_returns_403(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    item_id = _seed_item(client)
    bob = _other_user(client, "bob")
    with client.session_factory() as session:
        group = Group(id="g1", tenant_id=client.tenant.id, name="Reviewers")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: bob
    try:
        response = client.put(f"/items/{item_id}/sharing", json={"public": True, "groups": []})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_routes.py -v`
Expected: FAIL with 404 (no such route yet).

- [ ] **Step 3: Write the schema**

`core/app/sharing/schemas.py`:
```python
from typing import Literal

from pydantic import BaseModel


class GroupShare(BaseModel):
    groupId: str
    role: Literal["viewer", "editor"]


class Sharing(BaseModel):
    public: bool
    groups: list[GroupShare]
```

- [ ] **Step 4: Add `set_is_public` to items repository**

In `core/app/items/repository.py`, add:
```python
def set_is_public(session: Session, *, tenant_id: str, item_id: str, is_public: bool) -> None:
    item = session.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return
    item.is_public = is_public
    session.flush()
```

- [ ] **Step 5: Add the two routes**

In `core/app/items/routes.py`, add the imports:
```python
from app.sharing import repository as sharing_repo
from app.sharing.schemas import GroupShare, Sharing
```

Add the routes (after `read_thumbnail`):
```python
@router.get("/items/{item_id}/sharing", response_model=Sharing)
def get_sharing(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Sharing:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    shares = sharing_repo.list_shares(session, item_id=item_id)
    return Sharing(
        public=facts.is_public,
        groups=[GroupShare(groupId=s.group_id, role=s.role) for s in shares],
    )


@router.put("/items/{item_id}/sharing", status_code=status.HTTP_204_NO_CONTENT)
def set_sharing(
    item_id: str,
    body: Sharing,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="share", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to share this item")

    ok = sharing_repo.replace_shares(
        session, tenant_id=user.tenant_id, item_id=item_id,
        shares=[(g.groupId, g.role) for g in body.groups],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="group not found")
    repo.set_is_public(session, tenant_id=user.tenant_id, item_id=item_id, is_public=body.public)

    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.share", object_type="item", object_id=item_id,
        payload={"public": body.public, "groups": [g.model_dump() for g in body.groups]},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/sharing/schemas.py core/app/items/repository.py core/app/items/routes.py core/tests/test_items_routes.py
git commit -m "feat(core): GET/PUT /items/{id}/sharing"
```

---

### Task 6: Groups endpoints — `POST/GET /groups`, `POST /groups/{id}/members`

**Files:**
- Create: `core/app/sharing/routes.py`
- Modify: `core/app/main.py`
- Create: `core/tests/test_sharing_routes.py`

**Interfaces:**
- Consumes: `app.sharing.repository.{create_group, list_groups, add_member}`, `app.auth.dependency.get_current_user`, `app.audit.writer.write_audit`.
- Produces: `app.sharing.routes.router` wired into `create_app()`.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_sharing_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
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
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def test_create_and_list_groups(client):
    create = client.post("/groups", json={"name": "Reviewers"})
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Reviewers"

    listed = client.get("/groups")
    assert listed.status_code == 200
    assert [g["name"] for g in listed.json()] == ["Reviewers"]


def test_add_member(client):
    group_id = client.post("/groups", json={"name": "Reviewers"}).json()["id"]
    with client.session_factory() as session:
        bob = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-bob",
            username="bob", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(bob)

    response = client.post(f"/groups/{group_id}/members", json={"userId": bob.id})
    assert response.status_code == 204


def test_add_member_cross_tenant_user_returns_404(client):
    import uuid
    from app.tenants.models import Tenant

    group_id = client.post("/groups", json={"name": "Reviewers"}).json()["id"]
    with client.session_factory() as session:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other")
        session.add(other_tenant)
        session.flush()
        mallory = get_or_create_user(
            session, tenant_id=other_tenant.id, oidc_sub="sub-mallory",
            username="mallory", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(mallory)

    response = client.post(f"/groups/{group_id}/members", json={"userId": mallory.id})
    assert response.status_code == 404


def test_add_member_to_unknown_group_returns_404(client):
    with client.session_factory() as session:
        bob = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-bob",
            username="bob", email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(bob)
    response = client.post("/groups/nope/members", json={"userId": bob.id})
    assert response.status_code == 404


def test_create_group_writes_audit_log(client):
    from sqlalchemy import select
    from app.audit.models import AuditLog

    client.post("/groups", json={"name": "Reviewers"})
    with client.session_factory() as session:
        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        assert "group.create" in actions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_sharing_routes.py -v`
Expected: FAIL — 404 (no `/groups` route registered yet).

- [ ] **Step 3: Write the routes**

`core/app/sharing/routes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.sharing import repository as repo
from app.users.models import User

router = APIRouter()


class CreateGroupRequest(BaseModel):
    name: str


class GroupRead(BaseModel):
    id: str
    name: str


class AddMemberRequest(BaseModel):
    userId: str


@router.get("/groups", response_model=list[GroupRead])
def list_groups(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[GroupRead]:
    return [GroupRead(id=g.id, name=g.name) for g in repo.list_groups(session, tenant_id=user.tenant_id)]


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    body: CreateGroupRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupRead:
    group = repo.create_group(session, tenant_id=user.tenant_id, name=body.name)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="group.create", object_type="group", object_id=group.id,
        payload={"name": body.name},
    )
    return GroupRead(id=group.id, name=group.name)


@router.post("/groups/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_member(
    group_id: str,
    body: AddMemberRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    ok = repo.add_member(session, tenant_id=user.tenant_id, group_id=group_id, user_id=body.userId)
    if not ok:
        raise HTTPException(status_code=404, detail="group or user not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="group.add_member", object_type="group", object_id=group_id,
        payload={"userId": body.userId},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Wire the router into `main.py`**

In `core/app/main.py`, add the import and registration:
```python
from app.sharing import routes as sharing_routes
```
```python
    app.include_router(sharing_routes.router)
```
(next to `app.include_router(items_routes.router)`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_sharing_routes.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/app/sharing/routes.py core/app/main.py core/tests/test_sharing_routes.py
git commit -m "feat(core): POST/GET /groups, POST /groups/{id}/members"
```

---

### Task 7: `app.public` — anonymous runtime access to published items

**Files:**
- Create: `core/app/public/__init__.py`, `core/app/public/routes.py`
- Modify: `core/app/items/repository.py` (`get_published_item`)
- Modify: `core/app/main.py`
- Create: `core/tests/test_public_routes.py`

**Interfaces:**
- Consumes: `app.items.repository.get_published_item`, `app.configs.repository.get_config_by_item`. No `get_current_user` dependency anywhere in this module — this is the cœur's only anonymous entry point.
- Produces: `GET /public/items/{id}`, `GET /public/configs/by-item/{id}`.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_public_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.configs import routes as configs_routes
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.auth.dependency import get_current_user
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
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_config(client) -> dict:
    body = {
        "kind": "app",
        "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 4, "h": 4}]},
    }
    response = client.post("/configs", json={"title": "My App", "config": body})
    assert response.status_code == 201, response.text
    return response.json()


def test_public_get_published_item_requires_no_auth(client):
    created = _create_config(client)
    client.patch(f"/items/{created['itemId']}", json={"isPublished": True})

    # Deliberately clear the auth override to prove no Authorization header is needed.
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/items/{created['itemId']}")
    assert response.status_code == 200
    assert response.json()["title"] == "My App"


def test_public_get_unpublished_item_returns_404(client):
    created = _create_config(client)
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/items/{created['itemId']}")
    assert response.status_code == 404


def test_public_get_nonexistent_item_returns_404_same_as_unpublished(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items/does-not-exist")
    assert response.status_code == 404


def test_public_get_config_by_item_for_published_item(client):
    created = _create_config(client)
    client.patch(f"/items/{created['itemId']}", json={"isPublished": True})
    del client.app.dependency_overrides[get_current_user]

    response = client.get(f"/public/configs/by-item/{created['itemId']}")
    assert response.status_code == 200
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_public_get_config_by_item_for_unpublished_item_returns_404(client):
    created = _create_config(client)
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/configs/by-item/{created['itemId']}")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_public_routes.py -v`
Expected: FAIL — 404 for all (route doesn't exist / would 401 without the removed override once it does, if built wrong).

- [ ] **Step 3: Add `get_published_item` to items repository**

In `core/app/items/repository.py`, add:
```python
def get_published_item(session: Session, *, item_id: str) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.id == item_id, Item.is_published.is_(True))
    ).first()
    if row is None:
        return None
    item, owner_username = row
    return _to_read(item, owner_username)
```

- [ ] **Step 4: Write the public routes**

`core/app/public/__init__.py`: empty file.

`core/app/public/routes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.schemas import ItemRead

router = APIRouter(prefix="/public")


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_public_config_by_item(item_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    item = items_repo.get_published_item(session, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    result = configs_repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
```

- [ ] **Step 5: Wire the router into `main.py`**

In `core/app/main.py`, add the import and registration:
```python
from app.public import routes as public_routes
```
```python
    app.include_router(public_routes.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_public_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS — `app.public` importing `app.configs`/`app.items` is a top-layer-imports-lower-layers relationship, already declared in Task 1's contract.

- [ ] **Step 8: Commit**

```bash
git add core/app/public core/app/items/repository.py core/app/main.py core/tests/test_public_routes.py
git commit -m "feat(core): anonymous GET /public/items/{id} and /public/configs/by-item/{id}"
```

---

### Task 8: Acceptance regression test, OpenAPI regen, CI

**Files:**
- Create: `core/tests/test_sharing_acceptance.py`
- Modify (generated, not hand-edited): `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: everything built in Tasks 1–7.
- Produces: one end-to-end regression test tying together the spec's acceptance criteria (§8), plus a regenerated, drift-free OpenAPI schema.

- [ ] **Step 1: Write the acceptance regression test**

`core/tests/test_sharing_acceptance.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        alice = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-alice",
            username="alice", email=None, first_name="", last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = alice  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def test_item_shared_to_a_group_is_visible_to_members_and_invisible_to_others(client):
    """Roadmap SP-1 acceptance criterion, reproduced verbatim: an item shared
    to a group is visible to its members and invisible to everyone else."""
    created = client.post(
        "/configs",
        json={
            "title": "Confidential map",
            "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
        },
    ).json()
    item_id = created["itemId"]

    with client.session_factory() as session:
        member = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-member",
            username="member", email=None, first_name="", last_name="",
        )
        outsider = get_or_create_user(
            session, tenant_id=client.tenant.id, oidc_sub="sub-outsider",
            username="outsider", email=None, first_name="", last_name="",
        )
        group = Group(id="g1", tenant_id=client.tenant.id, name="Trusted")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=member.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()
        session.refresh(member)
        session.refresh(outsider)

    client.app.dependency_overrides[get_current_user] = lambda: member
    member_response = client.get(f"/items/{item_id}")
    client.app.dependency_overrides[get_current_user] = lambda: outsider
    outsider_response = client.get(f"/items/{item_id}")
    client.app.dependency_overrides[get_current_user] = lambda: client.user

    assert member_response.status_code == 200
    assert outsider_response.status_code == 404


def test_published_item_accessible_anonymously_unpublished_is_not(client):
    """Roadmap SP-1 acceptance criterion: a published item is accessible
    anonymously at runtime; a non-published one returns 404."""
    created = client.post(
        "/configs",
        json={
            "title": "Runtime app",
            "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
        },
    ).json()
    item_id = created["itemId"]

    del client.app.dependency_overrides[get_current_user]
    assert client.get(f"/public/items/{item_id}").status_code == 404

    client.app.dependency_overrides[get_current_user] = lambda: client.user
    client.patch(f"/items/{item_id}", json={"isPublished": True})
    del client.app.dependency_overrides[get_current_user]

    assert client.get(f"/public/items/{item_id}").status_code == 200
```

- [ ] **Step 2: Run the new test**

Run: `cd core && uv run pytest tests/test_sharing_acceptance.py -v`
Expected: PASS (everything it exercises was already built in Tasks 1–7; this is a pure integration check, no new production code).

- [ ] **Step 3: Regenerate the OpenAPI schema and shell TypeScript types**

Run:
```bash
cd core
uv run python scripts/export_openapi.py openapi.json
cd ../shell
npm run gen:api-types
git diff --stat -- ../core/openapi.json src/api/generated/core-schema.d.ts
```
Expected: both files show a diff (new `Sharing`, `GroupRead`, `/groups`, `/items/{id}/sharing`, `/public/*` schemas/paths appear); no manual edits needed since both are generated.

- [ ] **Step 4: Run the entire core suite, import-linter, and the Postgres migration cycle one last time**

Run:
```bash
cd core
uv run pytest
uv run lint-imports
docker compose up -d postgis
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic downgrade base
```
Expected: all green; migration cycle exits 0 both directions.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_sharing_acceptance.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "test(core): SP-1c acceptance regression; regenerate OpenAPI schema and TS types"
```
