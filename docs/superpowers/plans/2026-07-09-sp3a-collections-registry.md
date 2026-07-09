# SP-3a — Registre de collections, introspection, rôle admin : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le cœur gère un registre de collections PostGIS éditables (déclaration admin, introspection de schéma, partage, RLS générée) — première sous-phase de la spec [SP-3](../specs/2026-07-09-sp3-collections-features-design.md). Le CRUD de features OGC est SP-3b ; la bascule shell est SP-3c (plans séparés, écrits à leur lancement).

**Architecture:** Nouveau module `app/collections` (registre + introspection + DDL RLS), extension de `app/sharing` (`can()` généralisé, `CollectionShare` à côté d'`ItemShare`), extension de `app/auth`/`app/users` (rôle admin). Introspection et applicateur DDL sont des dépendances FastAPI injectables : les tests SQLite les remplacent par des fakes, les tests marqués `postgis` utilisent les vrais sur une base PostGIS jetable.

**Tech Stack:** FastAPI + SQLAlchemy 2 sync + Alembic (existant), SQL brut paramétré pour le DDL (pas de geoalchemy2), pytest (SQLite in-memory + marqueur `postgis`), import-linter.

## Global Constraints

- Commandes : `cd core && uv run pytest` (tests), `uv run lint-imports` (frontières). Tout doit passer à la fin de **chaque** tâche.
- TDD : test rouge d'abord, implémentation minimale, test vert, commit.
- Commits conventional en français : `feat(core): …`, `test(core): …` ; petits, un sujet.
- Code/identifiants en **anglais**, docs/messages en **français**.
- `tenant_id` sur toute nouvelle table ; toute mutation écrit dans `audit_log` via `write_audit(session, *, tenant_id, actor_id, actor_kind, action, object_type, object_id, payload)` (`app/audit/writer.py`), même transaction.
- Les repositories ne font que `flush()` — jamais de `commit()` (la frontière transactionnelle est `request_scoped_session`).
- Motif « 404 avant 403 » : lecture refusée → 404 ; écriture refusée sur objet lisible → 403.
- Identifiants SQL toujours quotés via le preparer SQLAlchemy — jamais d'interpolation brute.
- Aucune nouvelle dépendance Python.
- Env : `CORE_ADMIN_SUBS` (bootstrap admin), `CORE_TEST_DATABASE_URL` (tests postgis). En mode `CORE_AUTH_MODE=mock`, le user mock est admin.

---

### Task 1: Infrastructure de test PostGIS (marqueur `postgis`)

**Files:**
- Create: `core/tests/conftest.py`
- Create: `core/tests/test_postgis_infra.py`
- Modify: `core/pyproject.toml` (section `[tool.pytest.ini_options]` — la créer si absente)
- Modify: `.github/workflows/ci.yml` (job `core`)

**Interfaces:**
- Produces: fixtures pytest `pg_engine` (Engine session-scoped sur `CORE_TEST_DATABASE_URL`, skip si absent) et `pg_session_factory` ; marqueur `postgis`. Les tâches 7, 8, 10 en dépendent.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_postgis_infra.py
import pytest
from sqlalchemy import text


@pytest.mark.postgis
def test_postgis_available(pg_engine):
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version()")).scalar()
    assert version is not None
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_postgis_infra.py -v`
Expected: ERROR `fixture 'pg_engine' not found`

- [ ] **Step 3: Implémenter conftest + marqueur**

```python
# core/tests/conftest.py
"""Fixtures partagées. Les fixtures SQLite restent locales à chaque fichier
(pattern existant) ; ce conftest ne porte que l'infra PostGIS optionnelle."""
import os

import pytest
from sqlalchemy import create_engine, text

from app.db import make_session_factory


@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    engine = create_engine(url)
    # Le rôle RLS existe dans la base de test (idempotent) : les tests DDL
    # (task 8) en ont besoin, et la migration 0008 le crée en vrai déploiement.
    with engine.begin() as conn:
        conn.execute(text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gis_rls') "
            "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;"
        ))
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_session_factory(pg_engine):
    return make_session_factory(pg_engine)
```

```toml
# core/pyproject.toml — ajouter (ou compléter) :
[tool.pytest.ini_options]
markers = [
    "postgis: nécessite un PostGIS réel (CORE_TEST_DATABASE_URL) ; skippé sinon",
]
```

- [ ] **Step 4: Vérifier le skip local puis le passage sur PostGIS**

Run: `cd core && uv run pytest tests/test_postgis_infra.py -v`
Expected: SKIPPED (`CORE_TEST_DATABASE_URL non défini`)

Run (si un PostGIS local est disponible, sinon la CI validera) :
`CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test uv run pytest tests/test_postgis_infra.py -v`
Expected: PASS

- [ ] **Step 5: Câbler la CI**

Dans `.github/workflows/ci.yml`, job `core` : ajouter le service PostGIS (même image que le job `migrations`) et la variable d'env, pour que les tests `postgis` s'exécutent en CI :

```yaml
  core:
    # … steps existants inchangés …
    services:
      postgis:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_USER: gis
          POSTGRES_PASSWORD: gis
          POSTGRES_DB: gis_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U gis" --health-interval 5s
          --health-timeout 5s --health-retries 10
    env:
      CORE_TEST_DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis_test
```

(Adapter à la structure YAML réelle du job — conserver ses steps et clés existants.)

- [ ] **Step 6: Suite complète + commit**

Run: `cd core && uv run pytest`
Expected: tous les tests existants PASS, le nouveau SKIPPED (ou PASS avec DB locale).

```bash
git add core/tests/conftest.py core/tests/test_postgis_infra.py core/pyproject.toml .github/workflows/ci.yml
git commit -m "test(core): infra de test PostGIS optionnelle (marqueur postgis, CI)"
```

---

### Task 2: Migration 0008 + modèles (`users.is_admin`, `collections`, `collection_shares`, rôle `gis_rls`)

**Files:**
- Modify: `core/app/users/models.py`
- Create: `core/app/collections/__init__.py` (vide)
- Create: `core/app/collections/models.py`
- Modify: `core/app/sharing/models.py` (ajout `CollectionShare` à côté d'`ItemShare`)
- Modify: `core/app/db.py` (`init_db` importe les nouveaux modèles)
- Modify: `core/pyproject.toml` (layers import-linter + `ignore_imports`)
- Create: `core/alembic/versions/0008_collections_admin.py`
- Test: `core/tests/test_collections_models.py`

**Interfaces:**
- Produces: `Collection` (`app.collections.models`) — colonnes : `id, tenant_id, owner_id, table_name, title, description, pk_column, geometry_column, geometry_type, srid, is_public, editable, created_at, updated_at` ; `CollectionShare` (`app.sharing.models`) — `collection_id, group_id, role` (PK composite) ; `User.is_admin: bool`. Consommés par toutes les tâches suivantes.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_collections_models.py
from app.db import init_db, make_engine, make_session_factory
from app.collections.models import Collection
from app.sharing.models import CollectionShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_collection_row_roundtrip():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        session.add(Collection(
            id="incidents", tenant_id=tenant.id, owner_id=user.id,
            table_name="incidents", title="Incidents", pk_column="id",
            geometry_column="geom", geometry_type="Point", srid=4326,
        ))
        session.commit()
        row = session.get(Collection, "incidents")
        assert row.is_public is False and row.editable is True


def test_user_is_admin_defaults_false():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        assert user.is_admin is False


def test_collection_share_composite_pk():
    Session = _session_factory()
    with Session() as session:
        assert {c.name for c in CollectionShare.__table__.primary_key.columns} == {
            "collection_id", "group_id",
        }
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_models.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'app.collections'`

- [ ] **Step 3: Implémenter modèles + migration**

```python
# core/app/users/models.py — ajouter à la classe User :
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
# (+ importer Boolean depuis sqlalchemy)
```

```python
# core/app/collections/models.py
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", name="uq_collections_tenant_table"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, défaut = table_name
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    pk_column: Mapped[str] = mapped_column(String, nullable=False)
    geometry_column: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String, nullable=True)
    srid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

```python
# core/app/sharing/models.py — ajouter (mêmes conventions qu'ItemShare) :
class CollectionShare(Base):
    __tablename__ = "collection_shares"

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "viewer" | "editor"
```

`core/app/db.py` — dans `init_db`, ajouter l'import :
```python
    from app.collections import models as collections_models  # noqa: F401
```

`core/pyproject.toml` — contrat layers : insérer `"app.collections",` entre
`"app.public",` et `"app.configs",` ; ajouter dans `ignore_imports` :
`"app.db -> app.collections.models",`.

```python
# core/alembic/versions/0008_collections_admin.py
"""users.is_admin, collections, collection_shares, rôle gis_rls

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "collections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("pk_column", sa.String(), nullable=False),
        sa.Column("geometry_column", sa.String(), nullable=True),
        sa.Column("geometry_type", sa.String(), nullable=True),
        sa.Column("srid", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "table_name", name="uq_collections_tenant_table"),
    )
    op.create_table(
        "collection_shares",
        sa.Column("collection_id", sa.String(),
                  sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.String(),
                  sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
    )
    # Rôle non-propriétaire pour la RLS (spec §2/§5) — Postgres uniquement,
    # idempotent (la base de test CI et un redéploiement peuvent l'avoir déjà).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gis_rls') "
            "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;"
        )
        op.execute("GRANT gis_rls TO current_user")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP OWNED BY gis_rls")
        op.execute("DROP ROLE IF EXISTS gis_rls")
    op.drop_table("collection_shares")
    op.drop_table("collections")
    op.drop_column("users", "is_admin")
```

- [ ] **Step 4: Vérifier**

Run: `cd core && uv run pytest tests/test_collections_models.py -v && uv run lint-imports`
Expected: 3 PASS ; contrat layers OK.

- [ ] **Step 5: Commit**

```bash
git add core/app/users/models.py core/app/collections core/app/sharing/models.py \
  core/app/db.py core/pyproject.toml core/alembic/versions/0008_collections_admin.py \
  core/tests/test_collections_models.py
git commit -m "feat(core): modèles collections/collection_shares, users.is_admin, migration 0008"
```

---

### Task 3: Bootstrap admin (`CORE_ADMIN_SUBS`) et helpers repository

**Files:**
- Modify: `core/app/users/repository.py`
- Modify: `core/app/auth/dependency.py`
- Test: `core/tests/test_admin_bootstrap.py`

**Interfaces:**
- Produces: `get_or_create_user(..., bootstrap_admin: bool = False)` (promotion à la volée, **jamais** de rétrogradation par env) ; `set_admin(session, *, tenant_id, user_id, is_admin) -> User | None` ; `count_admins(session, *, tenant_id) -> int` ; `list_users(session, *, tenant_id, page, page_size) -> tuple[list[User], int]`. Consommés par les tâches 5 et 10.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_admin_bootstrap.py
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import count_admins, get_or_create_user, set_admin


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def _user(session, sub="sub-1", bootstrap_admin=False):
    tenant = get_or_create_default_tenant(session)
    return get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub=sub, username=sub,
        email=None, first_name="", last_name="", bootstrap_admin=bootstrap_admin,
    )


def test_bootstrap_promotes(session):
    user = _user(session, bootstrap_admin=True)
    assert user.is_admin is True


def test_bootstrap_never_demotes(session):
    user = _user(session, bootstrap_admin=True)
    again = _user(session, bootstrap_admin=False)  # sub retiré de l'env ensuite
    assert again.id == user.id and again.is_admin is True


def test_set_admin_and_count(session):
    tenant = get_or_create_default_tenant(session)
    user = _user(session)
    assert count_admins(session, tenant_id=tenant.id) == 0
    updated = set_admin(session, tenant_id=tenant.id, user_id=user.id, is_admin=True)
    assert updated.is_admin is True
    assert count_admins(session, tenant_id=tenant.id) == 1
    assert set_admin(session, tenant_id=tenant.id, user_id="nope", is_admin=True) is None
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_admin_bootstrap.py -v`
Expected: FAIL `TypeError: got an unexpected keyword argument 'bootstrap_admin'`

- [ ] **Step 3: Implémenter**

```python
# core/app/users/repository.py — modifier get_or_create_user et ajouter :
def get_or_create_user(
    session: Session, *, tenant_id: str, oidc_sub: str, username: str,
    email: str | None, first_name: str, last_name: str,
    bootstrap_admin: bool = False,
) -> User:
    # … corps existant inchangé, avec en plus, avant le flush() final :
    if bootstrap_admin and not user.is_admin:
        # Promotion par env uniquement — la rétrogradation passe par set_admin()
        # (retirer un sub de CORE_ADMIN_SUBS ne doit pas destituer silencieusement).
        user.is_admin = True
    session.flush()
    session.refresh(user)
    return user


def set_admin(session: Session, *, tenant_id: str, user_id: str, is_admin: bool) -> User | None:
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    )
    if user is None:
        return None
    user.is_admin = is_admin
    session.flush()
    return user


def count_admins(session: Session, *, tenant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant_id, User.is_admin.is_(True)
        )
    )


def list_users(
    session: Session, *, tenant_id: str, page: int, page_size: int
) -> tuple[list[User], int]:
    base = select(User).where(User.tenant_id == tenant_id)
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    users = list(session.scalars(
        base.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
    ).all())
    return users, total
# (+ importer func depuis sqlalchemy)
```

```python
# core/app/auth/dependency.py — ajouter :
def _admin_subs() -> set[str]:
    raw = os.environ.get("CORE_ADMIN_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}

# Dans get_current_user, branche mock : bootstrap_admin=True (spec : le user
# mock est admin) ; branche oidc : bootstrap_admin=claims["sub"] in _admin_subs().
```

- [ ] **Step 4: Vérifier**

Run: `cd core && uv run pytest tests/test_admin_bootstrap.py tests/test_auth.py -v`
Expected: PASS (les tests auth existants restent verts — le user mock devient admin, aucun test existant n'asserte le contraire ; si l'un le fait, l'adapter explicitement dans ce commit).

- [ ] **Step 5: Commit**

```bash
git add core/app/users/repository.py core/app/auth/dependency.py core/tests/test_admin_bootstrap.py
git commit -m "feat(core): rôle admin — bootstrap CORE_ADMIN_SUBS, set_admin/count_admins/list_users"
```

---

### Task 4: `can()` généralisé (AccessFacts, `kind`, `actor_is_admin`)

**Files:**
- Modify: `core/app/sharing/authorization.py`
- Modify: `core/app/sharing/repository.py`
- Test: `core/tests/test_collections_authorization.py`

**Interfaces:**
- Consumes: `CollectionShare` (task 2).
- Produces: `AccessFacts` (mêmes champs qu'`ItemAccessFacts`, qui devient un alias) ; `can(session, *, user_id, action, item, kind="item"|"collection", actor_is_admin=False) -> bool` ; `has_collection_group_role(session, *, tenant_id, collection_id, user_id, roles) -> bool`. Consommés par les tâches 6, 9 (et SP-3b).

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_collections_authorization.py
import uuid

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.sharing.authorization import AccessFacts, can
from app.sharing.models import CollectionShare, Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="o",
                                   username="owner", email=None, first_name="", last_name="")
        other = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="x",
                                   username="other", email=None, first_name="", last_name="")
        session.commit()
        yield session, tenant, owner, other


def _facts(tenant, owner, *, public=False):
    return AccessFacts(id="col-1", tenant_id=tenant.id, owner_id=owner.id,
                       is_public=public, is_published=False)


def _share(session, tenant, user, role):
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g", created_by=user.id)
    session.add(group)
    session.add(GroupMember(group_id=group.id, user_id=user.id, tenant_id=tenant.id))
    session.add(CollectionShare(collection_id="col-1", group_id=group.id,
                                tenant_id=tenant.id, role=role))
    session.flush()


@pytest.mark.parametrize("action,expected", [
    ("read", True), ("write", True), ("delete", True), ("share", True),
])
def test_admin_full_rights_on_collections(env, action, expected):
    session, tenant, owner, other = env
    facts = _facts(tenant, owner)
    assert can(session, user_id=other.id, action=action, item=facts,
               kind="collection", actor_is_admin=True) is expected


def test_admin_gets_nothing_extra_on_items(env):
    # Anti-régression SP-1 : le flag admin ne s'applique qu'aux collections.
    session, tenant, owner, other = env
    facts = _facts(tenant, owner)
    assert can(session, user_id=other.id, action="write", item=facts,
               kind="item", actor_is_admin=True) is False


@pytest.mark.parametrize("role,action,expected", [
    ("viewer", "read", True), ("viewer", "write", False),
    ("editor", "read", True), ("editor", "write", True), ("editor", "share", True),
])
def test_collection_group_roles(env, role, action, expected):
    session, tenant, owner, other = env
    _share(session, tenant, other, role)
    facts = _facts(tenant, owner)
    assert can(session, user_id=other.id, action=action, item=facts,
               kind="collection") is expected


def test_stranger_reads_public_collection_only(env):
    session, tenant, owner, other = env
    assert can(session, user_id=other.id, action="read",
               item=_facts(tenant, owner, public=True), kind="collection") is True
    assert can(session, user_id=other.id, action="read",
               item=_facts(tenant, owner), kind="collection") is False


def test_item_share_does_not_leak_to_collections(env):
    # Un ItemShare sur le même id ne doit pas ouvrir la collection (tables séparées).
    session, tenant, owner, other = env
    from app.sharing.models import ItemShare
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g2", created_by=other.id)
    session.add(group)
    session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
    session.add(ItemShare(item_id="col-1", group_id=group.id, tenant_id=tenant.id, role="editor"))
    session.flush()
    assert can(session, user_id=other.id, action="write",
               item=_facts(tenant, owner), kind="collection") is False
```

(Adapter les constructeurs `Group`/`GroupMember`/`ItemShare` aux colonnes réelles de `app/sharing/models.py` si elles diffèrent — vérifier le fichier avant d'écrire.)

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_authorization.py -v`
Expected: FAIL `ImportError: cannot import name 'AccessFacts'`

- [ ] **Step 3: Implémenter**

```python
# core/app/sharing/authorization.py — remplacer le contenu par :
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.sharing.repository import has_collection_group_role, has_group_role

Action = Literal["read", "write", "delete", "share"]
ObjectKind = Literal["item", "collection"]


@dataclass(frozen=True)
class AccessFacts:
    """Everything `can()` needs about one object, without importing the model
    (app.sharing sits below app.items and app.collections in the layering).
    Callers build this from a row they already fetched."""

    id: str
    tenant_id: str
    owner_id: str
    is_public: bool
    is_published: bool


# Rétro-compatibilité : les routes items/configs existantes importent ce nom.
ItemAccessFacts = AccessFacts


def can(
    session: Session, *, user_id: str, action: Action, item: AccessFacts,
    kind: ObjectKind = "item", actor_is_admin: bool = False,
) -> bool:
    # Le rôle admin ne court-circuite QUE les collections (spec SP-3 §2) :
    # la sémantique de partage des items (SP-1, testée) ne bouge pas.
    if kind == "collection" and actor_is_admin:
        return True
    if item.owner_id == user_id:
        return True

    if kind == "item":
        role_check = lambda roles: has_group_role(  # noqa: E731
            session, tenant_id=item.tenant_id, item_id=item.id,
            user_id=user_id, roles=roles,
        )
    else:
        role_check = lambda roles: has_collection_group_role(  # noqa: E731
            session, tenant_id=item.tenant_id, collection_id=item.id,
            user_id=user_id, roles=roles,
        )

    if action == "read":
        if item.is_public or item.is_published:
            return True
        return role_check({"viewer", "editor"})
    if action in ("write", "delete", "share"):
        return role_check({"editor"})
    return False
```

```python
# core/app/sharing/repository.py — ajouter :
def has_collection_group_role(
    session: Session, *, tenant_id: str, collection_id: str, user_id: str, roles: set[str]
) -> bool:
    stmt = (
        select(CollectionShare.role)
        .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
        .where(
            CollectionShare.collection_id == collection_id,
            CollectionShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
            CollectionShare.role.in_(roles),
        )
    )
    return session.scalar(stmt) is not None
# (+ importer CollectionShare depuis app.sharing.models)
```

- [ ] **Step 4: Vérifier (nouveaux tests + matrice SP-1 intacte)**

Run: `cd core && uv run pytest tests/test_collections_authorization.py tests/test_sharing_authorization.py -v`
Expected: PASS partout (la matrice items existante ne change pas).

- [ ] **Step 5: Commit**

```bash
git add core/app/sharing/authorization.py core/app/sharing/repository.py \
  core/tests/test_collections_authorization.py
git commit -m "feat(core): can() généralisé — AccessFacts, kind item|collection, admin sur collections"
```

---

### Task 5: Endpoints `/users` (listing + promotion admin)

**Files:**
- Modify: `core/app/auth/routes.py`
- Test: `core/tests/test_users_admin_routes.py`

**Interfaces:**
- Consumes: `list_users`, `set_admin`, `count_admins` (task 3) ; `write_audit`.
- Produces: `GET /users?page=&pageSize=` → `{"users": [{"id","username","isAdmin"}], "total"}` (admin) ; `PATCH /users/{id}` body `{"isAdmin": bool}` → user JSON (admin ; 409 si dernier admin rétrogradé). Les routes vivent dans `app/auth/routes.py` (contrainte layers : `users` est sous `auth`).

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_users_admin_routes.py
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_users_requires_admin(env):
    app, client, _, admin, regular = env
    _as(app, regular)
    assert client.get("/users").status_code == 403
    _as(app, admin)
    body = client.get("/users").json()
    assert body["total"] == 2
    assert {u["username"] for u in body["users"]} == {"admin", "regular"}


def test_promote_then_demote(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    r = client.patch(f"/users/{regular.id}", json={"isAdmin": True})
    assert r.status_code == 200 and r.json()["isAdmin"] is True
    r = client.patch(f"/users/{regular.id}", json={"isAdmin": False})
    assert r.status_code == 200 and r.json()["isAdmin"] is False


def test_last_admin_cannot_be_demoted(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.patch(f"/users/{admin.id}", json={"isAdmin": False}).status_code == 409


def test_patch_unknown_user_404_and_non_admin_403(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    assert client.patch("/users/nope", json={"isAdmin": True}).status_code == 404
    _as(app, regular)
    assert client.patch(f"/users/{admin.id}", json={"isAdmin": False}).status_code == 403


def test_promotion_is_audited(env):
    app, client, Session, admin, regular = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"isAdmin": True})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "user.promote" in actions
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_users_admin_routes.py -v`
Expected: FAIL — `GET /users` → 404 (route inexistante ; l'assertion 403 échoue).

- [ ] **Step 3: Implémenter dans `app/auth/routes.py`**

```python
# core/app/auth/routes.py — ajouts (conserver GET /me existant) :
from pydantic import BaseModel

from app.audit.writer import write_audit
from app.users.repository import count_admins, list_users, set_admin


class UserAdminPatch(BaseModel):
    isAdmin: bool


def _require_admin(user):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _user_json(user) -> dict:
    return {"id": user.id, "username": user.username, "isAdmin": user.is_admin}


@router.get("/users")
def get_users(
    page: int = 1, pageSize: int = 50,
    user=Depends(get_current_user), session=Depends(get_session),
):
    _require_admin(user)
    users, total = list_users(session, tenant_id=user.tenant_id, page=page, page_size=pageSize)
    return {"users": [_user_json(u) for u in users], "total": total}


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str, body: UserAdminPatch,
    user=Depends(get_current_user), session=Depends(get_session),
):
    _require_admin(user)
    # Requête directe sur le modèle User autorisée ici : `auth` est au-dessus
    # de `users` dans le layering.
    from sqlalchemy import select

    from app.users.models import User as UserModel

    target = session.scalar(select(UserModel).where(
        UserModel.tenant_id == user.tenant_id, UserModel.id == user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not body.isAdmin and target.is_admin and count_admins(
            session, tenant_id=user.tenant_id) == 1:
        raise HTTPException(status_code=409, detail="cannot demote the last admin")
    updated = set_admin(session, tenant_id=user.tenant_id, user_id=user_id,
                        is_admin=body.isAdmin)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="user.promote" if body.isAdmin else "user.demote",
        object_type="user", object_id=user_id, payload={"isAdmin": body.isAdmin},
    )
    return _user_json(updated)
```

- [ ] **Step 4: Vérifier**

Run: `cd core && uv run pytest tests/test_users_admin_routes.py -v && uv run lint-imports`
Expected: 5 PASS ; layers OK.

- [ ] **Step 5: Commit**

```bash
git add core/app/auth/routes.py core/tests/test_users_admin_routes.py
git commit -m "feat(core): endpoints /users — listing et promotion admin, garde du dernier admin"
```

---

### Task 6: Module collections — registre (repository, routes, garde-fous, audit)

**Files:**
- Create: `core/app/collections/introspection.py` (types + interface seulement — l'implémentation Postgres est task 7)
- Create: `core/app/collections/repository.py`
- Create: `core/app/collections/schemas.py`
- Create: `core/app/collections/routes.py`
- Modify: `core/app/auth/dependency.py` (ajout `get_current_user_optional`)
- Modify: `core/app/main.py` (include router)
- Test: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes: `can`/`AccessFacts` (task 4), modèles (task 2), `write_audit`.
- Produces:
  - `TableInfo` / `ColumnInfo` (dataclasses, `app.collections.introspection`) :
    `ColumnInfo(name, type, required, max_length=None, enum_values=None)` avec
    `type ∈ {"string","integer","number","boolean","date","datetime","enum","unsupported"}` ;
    `TableInfo(table_name, pk_column, geometry_column, geometry_type, srid, columns)`.
  - Dépendances FastAPI overridables : `get_introspector()` → `Callable[[Session, str], TableInfo]`
    (lève `TableNotFound`/`UnsupportedTable(reason)`) et `get_ddl_applier()` →
    `Callable[[Session, str], None]` (no-op par défaut hors Postgres ; task 8 fournit le vrai).
  - Routes : `POST /collections {tableName, title?, description?, isPublic?}` (admin) → 201 ;
    `GET /collections` → `{"collections": [...]}` (anonyme : publiques seulement) ;
    `GET /collections/{cid}` → détail | 404 ; `PATCH /collections/{cid}` (owner/admin) ;
    `DELETE /collections/{cid}` (admin) → 204.
  - `get_current_user_optional` (`app.auth.dependency`) : `User | None` (pas de header → None).
  - Repository : `create_collection`, `get_collection`, `get_access_facts(col) -> AccessFacts`,
    `list_visible_collections(session, *, tenant_id, user_id, is_admin) -> list[Collection]`,
    `delete_collection`. Consommés par tasks 7–10 et SP-3b.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_collections_routes.py
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INCIDENTS = TableInfo(
    table_name="incidents", pk_column="id", geometry_column="geom",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INCIDENTS


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    ddl_calls: list[str] = []
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: ddl_calls.append(table)
    )
    client = TestClient(app)
    return app, client, Session, admin, regular, ddl_calls


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_register_requires_admin(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, regular)
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 403


def test_register_and_get(env):
    app, client, _, admin, _regular, ddl_calls = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "incidents", "title": "Incidents"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "incidents" and body["geometryType"] == "Point"
    assert ddl_calls == ["incidents"]  # la RLS est appliquée à l'enregistrement
    assert client.get("/collections/incidents").status_code == 200


def test_register_unknown_table_400_and_duplicate_409(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    assert client.post("/collections", json={"tableName": "nope"}).status_code == 400
    client.post("/collections", json={"tableName": "incidents"})
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 409


def test_register_core_table_refused(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    # La denylist (Base.metadata + alembic_version) court-circuite AVANT l'introspection.
    assert client.post("/collections", json={"tableName": "items"}).status_code == 400
    assert client.post("/collections", json={"tableName": "alembic_version"}).status_code == 400


def test_private_collection_hidden_from_stranger_and_anonymous(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 404
    assert client.get("/collections").json()["collections"] == []
    app.dependency_overrides.pop(get_current_user)  # anonyme
    assert client.get("/collections").json()["collections"] == []
    assert client.get("/collections/incidents").status_code == 404


def test_public_collection_visible_to_anonymous(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    body = client.get("/collections").json()
    assert [c["id"] for c in body["collections"]] == ["incidents"]


def test_patch_and_delete(env):
    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.patch("/collections/incidents", json={"title": "Renommé", "isPublic": True})
    assert r.status_code == 200 and r.json()["title"] == "Renommé"
    _as(app, regular)
    assert client.delete("/collections/incidents").status_code == 403
    _as(app, admin)
    assert client.delete("/collections/incidents").status_code == 204
    assert client.get("/collections/incidents").status_code == 404


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch("/collections/incidents", json={"title": "X"})
    client.delete("/collections/incidents")
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    for expected in ("collection.create", "collection.update", "collection.delete"):
        assert expected in actions
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: FAIL `ModuleNotFoundError` (introspection/routes inexistants).

- [ ] **Step 3: Implémenter**

```python
# core/app/collections/introspection.py
"""Types d'introspection + exceptions. L'implémentation Postgres réelle
(pg_catalog) arrive dans introspection_pg (task 7) ; les routes reçoivent
l'introspecteur par dépendance injectable."""
from dataclasses import dataclass, field
from typing import Callable, Literal

from sqlalchemy.orm import Session

FieldType = Literal[
    "string", "integer", "number", "boolean", "date", "datetime", "enum", "unsupported"
]


class TableNotFound(Exception):
    pass


class UnsupportedTable(Exception):
    """Table existante mais non enregistrable (PK composite, 2 géométries,
    vue matérialisée…) — reason est montré tel quel dans le 400."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: FieldType
    required: bool
    max_length: int | None = None
    enum_values: list[str] | None = None


@dataclass(frozen=True)
class TableInfo:
    table_name: str
    pk_column: str
    geometry_column: str | None
    geometry_type: str | None
    srid: int | None
    columns: list[ColumnInfo] = field(default_factory=list)


Introspector = Callable[[Session, str], TableInfo]
```

```python
# core/app/collections/repository.py
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.sharing.authorization import AccessFacts
from app.sharing.models import CollectionShare, GroupMember


def get_access_facts(col: Collection) -> AccessFacts:
    return AccessFacts(
        id=col.id, tenant_id=col.tenant_id, owner_id=col.owner_id,
        is_public=col.is_public, is_published=False,
    )


def get_collection(session: Session, *, tenant_id: str, collection_id: str) -> Collection | None:
    return session.scalar(select(Collection).where(
        Collection.tenant_id == tenant_id, Collection.id == collection_id))


def create_collection(session: Session, *, tenant_id: str, owner_id: str, table_name: str,
                      title: str, description: str, is_public: bool,
                      pk_column: str, geometry_column: str | None,
                      geometry_type: str | None, srid: int | None) -> Collection:
    col = Collection(
        id=table_name, tenant_id=tenant_id, owner_id=owner_id, table_name=table_name,
        title=title, description=description, is_public=is_public, pk_column=pk_column,
        geometry_column=geometry_column, geometry_type=geometry_type, srid=srid,
    )
    session.add(col)
    session.flush()
    return col


def list_visible_collections(
    session: Session, *, tenant_id: str, user_id: str | None, is_admin: bool
) -> list[Collection]:
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not is_admin:
        if user_id is None:
            stmt = stmt.where(Collection.is_public.is_(True))
        else:
            shared_ids = (
                select(CollectionShare.collection_id)
                .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
                .where(GroupMember.user_id == user_id,
                       CollectionShare.tenant_id == tenant_id)
            )
            stmt = stmt.where(
                Collection.is_public.is_(True)
                | (Collection.owner_id == user_id)
                | Collection.id.in_(shared_ids)
            )
    return list(session.scalars(stmt.order_by(Collection.title)).all())


def delete_collection(session: Session, col: Collection) -> None:
    session.delete(col)
    session.flush()
```

```python
# core/app/collections/schemas.py
from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    tableName: str = Field(min_length=1, max_length=63)
    title: str | None = None
    description: str = ""
    isPublic: bool = False


class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    isPublic: bool | None = None
    editable: bool | None = None
```

```python
# core/app/collections/routes.py
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as repo
from app.collections.introspection import (
    Introspector, TableNotFound, UnsupportedTable,
)
from app.collections.schemas import CollectionCreate, CollectionPatch
from app.db import Base, get_session
from app.sharing.authorization import can

router = APIRouter()

CORE_TABLES = frozenset(Base.metadata.tables) | {"alembic_version"}


def get_introspector() -> Introspector:  # overridé en test ; task 7 branche le vrai
    from app.collections.introspection_pg import introspect_table
    return introspect_table


def get_ddl_applier() -> Callable[[Session, str], None]:  # task 8 branche le vrai
    from app.collections.ddl import apply_collection_ddl
    return apply_collection_ddl


def _collection_json(col) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": col.editable,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
    }


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _get_readable(session, user, collection_id):
    """404 avant 403 : une collection illisible est indistinguable d'une absente."""
    col = None
    if user is not None:
        col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    else:
        from app.tenants.repository import get_or_create_default_tenant
        tenant = get_or_create_default_tenant(session)
        col = repo.get_collection(session, tenant_id=tenant.id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    readable = can(
        session, user_id=user.id if user else "", action="read",
        item=repo.get_access_facts(col), kind="collection",
        actor_is_admin=bool(user and user.is_admin),
    )
    if not readable:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


@router.post("/collections", status_code=201)
def register_collection(
    body: CollectionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
):
    _require_admin(user)
    if body.tableName in CORE_TABLES:
        raise HTTPException(status_code=400, detail="core table cannot be registered")
    if repo.get_collection(session, tenant_id=user.tenant_id, collection_id=body.tableName):
        raise HTTPException(status_code=409, detail="table already registered")
    try:
        info = introspect(session, body.tableName)
    except TableNotFound:
        raise HTTPException(status_code=400, detail="table not found in schema public")
    except UnsupportedTable as exc:
        raise HTTPException(status_code=400, detail=exc.reason)
    apply_ddl(session, info.table_name)
    col = repo.create_collection(
        session, tenant_id=user.tenant_id, owner_id=user.id, table_name=info.table_name,
        title=body.title or info.table_name, description=body.description,
        is_public=body.isPublic, pk_column=info.pk_column,
        geometry_column=info.geometry_column, geometry_type=info.geometry_type,
        srid=info.srid,
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.create", object_type="collection", object_id=col.id,
                payload={"tableName": col.table_name})
    return _collection_json(col)


@router.get("/collections")
def list_collections(
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    cols = repo.list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin),
    )
    return {"collections": [_collection_json(c) for c in cols]}


@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    return _collection_json(_get_readable(session, user, collection_id))


@router.patch("/collections/{collection_id}")
def patch_collection(
    collection_id: str, body: CollectionPatch,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    if not can(session, user_id=user.id, action="write", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="write access required")
    for attr, value in (("title", body.title), ("description", body.description),
                        ("is_public", body.isPublic), ("editable", body.editable)):
        if value is not None:
            setattr(col, attr, value)
    session.flush()
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.update", object_type="collection", object_id=col.id,
                payload=body.model_dump(exclude_none=True))
    return _collection_json(col)


@router.delete("/collections/{collection_id}", status_code=204)
def unregister_collection(
    collection_id: str,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    _require_admin(user)  # après le 404 : un non-admin qui la voit reçoit 403
    repo.delete_collection(session, col)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.delete", object_type="collection", object_id=collection_id,
                payload={})
```

```python
# core/app/auth/dependency.py — ajouter :
def get_current_user_optional(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User | None:
    """Comme get_current_user, mais renvoie None sans header (accès anonyme
    aux collections publiques — URLs OGC stables, spec SP-3 §2)."""
    if not authorization.startswith("Bearer "):
        return None
    return get_current_user(authorization=authorization, session=session)
```

`core/app/main.py` — ajouter `from app.collections import routes as collections_routes`
et `app.include_router(collections_routes.router)` (avant le mount MCP).

**Note test anonyme :** quand un test fait `app.dependency_overrides.pop(get_current_user)`,
`get_current_user_optional` reprend son implémentation réelle → pas de header envoyé
par `TestClient` → `None`. C'est le chemin voulu. En revanche l'override de
`get_current_user` ne couvre PAS `get_current_user_optional` : ajouter dans le
helper `_as()` du test l'override des deux dépendances :

```python
def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
```
(et `pop` des deux pour l'anonyme — corriger le test du Step 1 en conséquence).

- [ ] **Step 4: Vérifier**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v && uv run lint-imports`
Expected: 8 PASS ; layers OK (`collections` n'importe que sharing/auth/audit/db/tenants — tous en dessous).

- [ ] **Step 5: Commit**

```bash
git add core/app/collections core/app/auth/dependency.py core/app/main.py \
  core/tests/test_collections_routes.py
git commit -m "feat(core): registre de collections — enregistrement admin, visibilité can(), audit"
```

---

### Task 7: Introspection Postgres réelle + endpoint `/schema`

**Files:**
- Create: `core/app/collections/introspection_pg.py`
- Create: `core/app/collections/schema_json.py`
- Modify: `core/app/collections/routes.py` (route `GET /collections/{cid}/schema`)
- Test: `core/tests/test_schema_json.py` (pur), `core/tests/test_introspection_pg.py` (postgis)

**Interfaces:**
- Consumes: `TableInfo`/`ColumnInfo`/exceptions (task 6), fixtures `pg_engine` (task 1).
- Produces: `introspect_table(session, table_name) -> TableInfo` (`introspection_pg`) ;
  `table_info_to_schema(info: TableInfo) -> dict` (`schema_json`) — le contrat JSON de la
  spec §3 (`{"collection", "pk", "geometry": {...}|None, "fields": [...]}`), `tenant_id`
  et la PK exclus des `fields`. Consommé par SP-3b (validation) et SP-4 (formulaires).

- [ ] **Step 1: Tests purs du mapping (rouges)**

```python
# core/tests/test_schema_json.py
from app.collections.introspection import ColumnInfo, TableInfo
from app.collections.schema_json import table_info_to_schema


def _info(columns):
    return TableInfo(table_name="incidents", pk_column="id", geometry_column="geom",
                     geometry_type="Point", srid=4326, columns=columns)


def test_schema_shape():
    schema = table_info_to_schema(_info([
        ColumnInfo(name="titre", type="string", required=True, max_length=200),
        ColumnInfo(name="gravite", type="enum", required=False,
                   enum_values=["faible", "moyenne", "haute"]),
    ]))
    assert schema == {
        "collection": "incidents",
        "pk": "id",
        "geometry": {"column": "geom", "type": "Point", "srid": 4326},
        "fields": [
            {"name": "titre", "type": "string", "required": True, "maxLength": 200},
            {"name": "gravite", "type": "enum", "required": False,
             "values": ["faible", "moyenne", "haute"]},
        ],
    }


def test_pk_and_tenant_id_excluded():
    schema = table_info_to_schema(_info([
        ColumnInfo(name="id", type="integer", required=False),
        ColumnInfo(name="tenant_id", type="string", required=True),
        ColumnInfo(name="titre", type="string", required=True),
    ]))
    assert [f["name"] for f in schema["fields"]] == ["titre"]


def test_no_geometry():
    info = TableInfo(table_name="notes", pk_column="id", geometry_column=None,
                     geometry_type=None, srid=None,
                     columns=[ColumnInfo(name="txt", type="string", required=False)])
    assert table_info_to_schema(info)["geometry"] is None
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_schema_json.py -v`
Expected: FAIL `ModuleNotFoundError: app.collections.schema_json`

- [ ] **Step 3: Implémenter le mapping pur**

```python
# core/app/collections/schema_json.py
from app.collections.introspection import TableInfo


def table_info_to_schema(info: TableInfo) -> dict:
    fields = []
    for col in info.columns:
        if col.name in (info.pk_column, "tenant_id", info.geometry_column):
            continue
        entry: dict = {"name": col.name, "type": col.type, "required": col.required}
        if col.max_length is not None:
            entry["maxLength"] = col.max_length
        if col.enum_values is not None:
            entry["values"] = col.enum_values
        fields.append(entry)
    geometry = None
    if info.geometry_column:
        geometry = {"column": info.geometry_column, "type": info.geometry_type,
                    "srid": info.srid}
    return {"collection": info.table_name, "pk": info.pk_column,
            "geometry": geometry, "fields": fields}
```

Run: `uv run pytest tests/test_schema_json.py -v` → PASS. Commit intermédiaire :

```bash
git add core/app/collections/schema_json.py core/tests/test_schema_json.py
git commit -m "feat(core): mapping introspection -> schéma JSON des collections"
```

- [ ] **Step 4: Tests d'introspection réelle (postgis, rouges)**

```python
# core/tests/test_introspection_pg.py
import pytest
from sqlalchemy import text

from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_session_factory, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_incidents"))
        conn.execute(text("DROP TYPE IF EXISTS t_gravite"))
        conn.execute(text("CREATE TYPE t_gravite AS ENUM ('faible','moyenne','haute')"))
        conn.execute(text("""
            CREATE TABLE t_incidents (
                id serial PRIMARY KEY,
                titre varchar(200) NOT NULL,
                gravite t_gravite,
                date_incident date,
                resolu boolean DEFAULT false,
                payload jsonb,
                geom geometry(Point, 4326)
            )"""))
    with pg_session_factory() as session:
        yield session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_incidents"))
        conn.execute(text("DROP TYPE IF EXISTS t_gravite"))


def test_introspects_types(pg_session):
    info = introspect_table(pg_session, "t_incidents")
    assert info.pk_column == "id"
    assert info.geometry_column == "geom"
    assert info.geometry_type == "Point" and info.srid == 4326
    by_name = {c.name: c for c in info.columns}
    assert by_name["titre"].type == "string" and by_name["titre"].required is True
    assert by_name["titre"].max_length == 200
    assert by_name["gravite"].type == "enum"
    assert by_name["gravite"].enum_values == ["faible", "moyenne", "haute"]
    assert by_name["date_incident"].type == "date"
    assert by_name["resolu"].type == "boolean"
    assert by_name["resolu"].required is False  # NOT NULL absent / défaut présent
    assert by_name["payload"].type == "unsupported"  # jsonb hors périmètre v1


def test_unknown_table(pg_session):
    with pytest.raises(TableNotFound):
        introspect_table(pg_session, "nope_table")


def test_composite_pk_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_composite"))
        conn.execute(text("CREATE TABLE t_composite (a int, b int, PRIMARY KEY (a, b))"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_composite")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_composite"))
```

- [ ] **Step 5: Implémenter l'introspection Postgres**

```python
# core/app/collections/introspection_pg.py
"""Introspection réelle : information_schema + geometry_columns + pg_enum.
Toutes les requêtes sont paramétrées — le nom de table est une *valeur* ici,
jamais un identifiant interpolé."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.introspection import (
    ColumnInfo, FieldType, TableInfo, TableNotFound, UnsupportedTable,
)

_TYPE_MAP: dict[str, FieldType] = {
    "text": "string", "character varying": "string", "character": "string",
    "integer": "integer", "bigint": "integer", "smallint": "integer",
    "numeric": "number", "double precision": "number", "real": "number",
    "boolean": "boolean", "date": "date",
    "timestamp with time zone": "datetime", "timestamp without time zone": "datetime",
}

_GEOM_TYPES = {
    "POINT": "Point", "LINESTRING": "LineString", "POLYGON": "Polygon",
    "MULTIPOINT": "MultiPoint", "MULTILINESTRING": "MultiLineString",
    "MULTIPOLYGON": "MultiPolygon",
}


def introspect_table(session: Session, table_name: str) -> TableInfo:
    exists = session.execute(text(
        "SELECT relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = :t"
    ), {"t": table_name}).scalar()
    if exists is None:
        raise TableNotFound(table_name)
    if exists != "r":  # vue, matview, foreign table…
        raise UnsupportedTable("only plain tables can be registered")

    pk_rows = session.execute(text(
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass AND i.indisprimary"
    ), {"t": table_name}).scalars().all()
    if len(pk_rows) == 0:
        raise UnsupportedTable("table has no primary key")
    if len(pk_rows) > 1:
        raise UnsupportedTable("composite primary keys are not supported")
    pk_column = pk_rows[0]

    geom_rows = session.execute(text(
        "SELECT f_geometry_column, type, srid FROM geometry_columns "
        "WHERE f_table_schema = 'public' AND f_table_name = :t"
    ), {"t": table_name}).all()
    if len(geom_rows) > 1:
        raise UnsupportedTable("multiple geometry columns are not supported")
    geometry_column = geometry_type = srid = None
    if geom_rows:
        geometry_column = geom_rows[0][0]
        # geometry_columns renvoie le type en MAJUSCULES ("POINT") ; on normalise
        # vers la casse GeoJSON via une table de correspondance explicite.
        raw = geom_rows[0][1]
        geometry_type = _GEOM_TYPES.get(raw, raw)
        srid = geom_rows[0][2]

    col_rows = session.execute(text(
        "SELECT column_name, data_type, udt_name, is_nullable, column_default, "
        "character_maximum_length, is_identity "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
    ), {"t": table_name}).all()

    columns: list[ColumnInfo] = []
    for name, data_type, udt_name, is_nullable, default, max_len, is_identity in col_rows:
        if name == geometry_column:
            continue
        enum_values = None
        if data_type == "USER-DEFINED":
            enum_values = session.execute(text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :ty ORDER BY e.enumsortorder"
            ), {"ty": udt_name}).scalars().all()
            ftype: FieldType = "enum" if enum_values else "unsupported"
            enum_values = list(enum_values) or None
        else:
            ftype = _TYPE_MAP.get(data_type, "unsupported")
        required = (
            is_nullable == "NO" and default is None and is_identity != "YES"
        )
        columns.append(ColumnInfo(name=name, type=ftype, required=required,
                                  max_length=max_len, enum_values=enum_values))

    return TableInfo(table_name=table_name, pk_column=pk_column,
                     geometry_column=geometry_column, geometry_type=geometry_type,
                     srid=srid, columns=columns)
```

- [ ] **Step 6: Route `/schema`**

Ajouter dans `core/app/collections/routes.py` :

```python
from app.collections.schema_json import table_info_to_schema


@router.get("/collections/{collection_id}/schema")
def get_collection_schema(
    collection_id: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
):
    col = _get_readable(session, user, collection_id)
    info = introspect(session, col.table_name)
    return table_info_to_schema(info)
```

Et dans `core/tests/test_collections_routes.py`, ajouter :

```python
def test_schema_endpoint_uses_introspector(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    schema = client.get("/collections/incidents/schema").json()
    assert schema["pk"] == "id"
    assert schema["fields"] == [{"name": "titre", "type": "string", "required": True}]
```

- [ ] **Step 7: Vérifier**

Run: `cd core && uv run pytest tests/test_schema_json.py tests/test_collections_routes.py -v`
Expected: PASS (les tests `postgis` passent en CI ou avec `CORE_TEST_DATABASE_URL` local).
Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_introspection_pg.py -v` (si DB locale)
Expected: 3 PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/collections/introspection_pg.py core/app/collections/routes.py \
  core/tests/test_introspection_pg.py core/tests/test_collections_routes.py
git commit -m "feat(core): introspection Postgres réelle + GET /collections/{id}/schema"
```

---

### Task 8: DDL RLS à l'enregistrement

**Files:**
- Create: `core/app/collections/ddl.py`
- Test: `core/tests/test_collections_ddl.py` (postgis)

**Interfaces:**
- Consumes: fixtures postgis (task 1), rôle `gis_rls` (task 2/conftest).
- Produces: `apply_collection_ddl(session, table_name) -> None` — ajoute `tenant_id`,
  active la RLS, (re)crée la policy `tenant_isolation`, GRANT au rôle `gis_rls`
  (table + séquence de la PK). Branché sur `get_ddl_applier` (task 6). SP-3b s'appuiera
  sur `SET LOCAL ROLE gis_rls` + `SET LOCAL app.tenant_id` pour le CRUD.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_collections_ddl.py
import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls"))
        conn.execute(text(
            "CREATE TABLE t_rls (id serial PRIMARY KEY, titre text, "
            "geom geometry(Point, 4326))"))
    yield "t_rls"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls"))


def test_ddl_adds_tenant_and_rls(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        cols = session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 't_rls'")).scalars().all()
        assert "tenant_id" in cols
        rls = session.execute(text(
            "SELECT relrowsecurity FROM pg_class WHERE relname = 't_rls'")).scalar()
        assert rls is True
        policies = session.execute(text(
            "SELECT policyname FROM pg_policies WHERE tablename = 't_rls'")).scalars().all()
        assert "tenant_isolation" in policies


def test_ddl_is_idempotent(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        apply_collection_ddl(session, pg_table)  # ne doit pas lever
        session.commit()


def test_rls_blocks_wrong_tenant(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text(
            "INSERT INTO t_rls (titre, tenant_id) VALUES ('a', 'default')"))
        session.commit()
    with pg_session_factory() as session:
        # Sous le rôle RLS avec le bon tenant : la ligne est visible.
        session.execute(text("SET LOCAL ROLE gis_rls"))
        session.execute(text("SET LOCAL app.tenant_id = 'default'"))
        assert session.execute(text("SELECT count(*) FROM t_rls")).scalar() == 1
    with pg_session_factory() as session:
        # Mauvais tenant : rien à lire, et l'écriture est rejetée par WITH CHECK.
        session.execute(text("SET LOCAL ROLE gis_rls"))
        session.execute(text("SET LOCAL app.tenant_id = 'other'"))
        assert session.execute(text("SELECT count(*) FROM t_rls")).scalar() == 0
        import sqlalchemy.exc
        with pytest.raises(sqlalchemy.exc.DBAPIError):
            session.execute(text(
                "INSERT INTO t_rls (titre, tenant_id) VALUES ('b', 'default')"))
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… cd core && uv run pytest tests/test_collections_ddl.py -v`
(ou laisser la CI si pas de DB locale — dans ce cas exécuter les steps 2–4 d'un bloc et valider sur la CI)
Expected: FAIL `ModuleNotFoundError: app.collections.ddl`

- [ ] **Step 3: Implémenter**

```python
# core/app/collections/ddl.py
"""DDL par collection (spec SP-3 §2/§5, arbitrage A3) : tenant_id + RLS +
GRANTs au rôle non-propriétaire gis_rls. Idempotent — ré-enregistrer une table
ou rejouer un seed ne casse rien. Les identifiants sont quotés via le preparer
SQLAlchemy (le nom vient du registre, mais la défense vaut pour tout appelant)."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def _qi(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


def apply_collection_ddl(session: Session, table_name: str) -> None:
    t = _qi(session, table_name)
    stmts = [
        f"ALTER TABLE public.{t} ADD COLUMN IF NOT EXISTS tenant_id text "
        "NOT NULL DEFAULT 'default'",
        f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS tenant_isolation ON public.{t}",
        f"CREATE POLICY tenant_isolation ON public.{t} "
        "USING (tenant_id = current_setting('app.tenant_id')) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id'))",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{t} TO gis_rls",
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    # Les INSERT sous gis_rls doivent pouvoir tirer la séquence de la PK (serial).
    seq = session.execute(
        text("SELECT pg_get_serial_sequence(:t, a.attname) FROM pg_index i "
             "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
             "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass "
             "AND i.indisprimary"),
        {"t": table_name},
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
```

- [ ] **Step 4: Vérifier**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_collections_ddl.py -v`
Expected: 3 PASS (sinon : pousser et lire la CI — les tests postgis y tournent).

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/ddl.py core/tests/test_collections_ddl.py
git commit -m "feat(core): DDL RLS par collection — tenant_id, policy tenant_isolation, grants gis_rls"
```

---

### Task 9: Partage des collections (`GET/PUT /collections/{cid}/sharing`)

**Files:**
- Modify: `core/app/collections/routes.py`
- Modify: `core/app/collections/repository.py`
- Test: `core/tests/test_collections_sharing_routes.py`

**Interfaces:**
- Consumes: `CollectionShare`, `can`, schémas `Sharing`/`GroupShare` de `app/sharing/schemas.py` (réutilisés tels quels — vérifier leur forme exacte avant d'écrire et aligner les assertions).
- Produces: `GET /collections/{cid}/sharing` → `{"public": bool, "groups": [{"groupId","role"}]}` ; `PUT` (même corps, sémantique remplace-tout) — owner ou admin. `set_collection_sharing(session, *, tenant_id, collection_id, public, groups)` dans le repository.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_collections_sharing_routes.py
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INCIDENTS = TableInfo(
    table_name="incidents", pk_column="id", geometry_column="geom",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INCIDENTS


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="equipe",
                      created_by=admin.id)
        s.add(group)
        s.add(GroupMember(group_id=group.id, user_id=regular.id, tenant_id=tenant.id))
        group_id = group.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None
    )
    client = TestClient(app)
    return app, client, Session, admin, regular, group_id


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user

# (Adapter les constructeurs Group/GroupMember aux colonnes réelles de
#  app/sharing/models.py si elles diffèrent — vérifier le fichier avant d'écrire.)


def test_share_grants_read_to_group_member(env):
    app, client, Session, admin, regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 404
    _as(app, admin)
    r = client.put("/collections/incidents/sharing",
                   json={"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]})
    assert r.status_code == 200
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 200
    assert [c["id"] for c in client.get("/collections").json()["collections"]] == ["incidents"]


def test_put_sharing_replaces_all(env):
    app, client, _, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.put("/collections/incidents/sharing",
               json={"public": False, "groups": [{"groupId": group_id, "role": "viewer"}]})
    client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    body = client.get("/collections/incidents/sharing").json()
    assert body == {"public": True, "groups": []}


def test_sharing_requires_owner_or_admin(env):
    app, client, _, admin, regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    _as(app, regular)  # lisible (publique) mais pas partageable
    r = client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403


def test_share_is_audited(env):
    app, client, Session, admin, _regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        assert "collection.share" in list(s.scalars(select(AuditLog.action)))
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_sharing_routes.py -v`
Expected: FAIL — `GET/PUT /collections/incidents/sharing` → 404/405.

- [ ] **Step 3: Implémenter**

```python
# core/app/collections/repository.py — ajouter :
from sqlalchemy import delete

from app.sharing.models import CollectionShare


def get_collection_sharing(session: Session, *, tenant_id: str, collection_id: str) -> list[CollectionShare]:
    return list(session.scalars(select(CollectionShare).where(
        CollectionShare.tenant_id == tenant_id,
        CollectionShare.collection_id == collection_id,
    )).all())


def set_collection_sharing(
    session: Session, *, tenant_id: str, collection_id: str,
    groups: list[tuple[str, str]],  # [(group_id, role)]
) -> None:
    session.execute(delete(CollectionShare).where(
        CollectionShare.tenant_id == tenant_id,
        CollectionShare.collection_id == collection_id,
    ))
    for group_id, role in groups:
        session.add(CollectionShare(collection_id=collection_id, group_id=group_id,
                                    tenant_id=tenant_id, role=role))
    session.flush()
```

```python
# core/app/collections/routes.py — ajouter :
from pydantic import BaseModel


class GroupShareIn(BaseModel):
    groupId: str
    role: str  # "viewer" | "editor" — valider : raise 422 sinon (validator pydantic)


class SharingIn(BaseModel):
    public: bool
    groups: list[GroupShareIn]


@router.get("/collections/{collection_id}/sharing")
def get_sharing(collection_id: str, user=Depends(get_current_user),
                session: Session = Depends(get_session)):
    col = _get_readable(session, user, collection_id)
    if not can(session, user_id=user.id, action="share", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="share access required")
    shares = repo.get_collection_sharing(session, tenant_id=user.tenant_id,
                                         collection_id=col.id)
    return {"public": col.is_public,
            "groups": [{"groupId": s.group_id, "role": s.role} for s in shares]}


@router.put("/collections/{collection_id}/sharing")
def put_sharing(collection_id: str, body: SharingIn, user=Depends(get_current_user),
                session: Session = Depends(get_session)):
    col = _get_readable(session, user, collection_id)
    if not can(session, user_id=user.id, action="share", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="share access required")
    col.is_public = body.public
    repo.set_collection_sharing(
        session, tenant_id=user.tenant_id, collection_id=col.id,
        groups=[(g.groupId, g.role) for g in body.groups],
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.share", object_type="collection", object_id=col.id,
                payload={"public": body.public,
                         "groups": [g.model_dump() for g in body.groups]})
    return {"public": col.is_public,
            "groups": [{"groupId": g.groupId, "role": g.role} for g in body.groups]}
```

(Si `app/sharing/schemas.py` expose déjà `Sharing`/`GroupShare` avec exactement
cette forme, les importer au lieu de redéclarer `SharingIn`/`GroupShareIn` — DRY ;
vérifier le fichier au moment d'écrire.)

- [ ] **Step 4: Vérifier**

Run: `cd core && uv run pytest tests/test_collections_sharing_routes.py tests/test_collections_authorization.py -v && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/collections core/tests/test_collections_sharing_routes.py
git commit -m "feat(core): partage des collections — groupes x rôles, public, audité"
```

---

### Task 10: Script de seed des collections de démo

**Files:**
- Create: `core/scripts/seed_demo.py`
- Test: `core/tests/test_seed_demo.py` (postgis)

**Interfaces:**
- Consumes: `introspect_table`, `apply_collection_ddl`, `create_collection`, `get_or_create_user`, `get_or_create_default_tenant`.
- Produces: `python -m scripts.seed_demo [--owner USERNAME]` (env `DATABASE_URL`) — déclare `incidents` et `points_interet` comme collections éditables publiques si les tables existent ; idempotent ; fonction `seed(session, owner_username=None) -> list[str]` importable pour les tests.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_seed_demo.py
import pytest
from sqlalchemy import text

from app.db import Base
from scripts.seed_demo import seed

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_core(pg_engine, pg_session_factory):
    # Base jetable : tables du cœur + tables de démo, nettoyées après.
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS incidents (id serial PRIMARY KEY, "
            "titre text NOT NULL, geom geometry(Point, 4326))"))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS points_interet (id serial PRIMARY KEY, "
            "nom text NOT NULL, geom geometry(Point, 4326))"))
    yield pg_session_factory
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS incidents, points_interet CASCADE"))
    Base.metadata.drop_all(pg_engine)


def test_seed_registers_demo_collections(pg_core):
    with pg_core() as session:
        created = seed(session)
        session.commit()
    assert set(created) == {"incidents", "points_interet"}
    with pg_core() as session:
        rows = session.execute(text(
            "SELECT id, is_public, editable FROM collections ORDER BY id")).all()
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("incidents", True, True), ("points_interet", True, True)]


def test_seed_is_idempotent(pg_core):
    with pg_core() as session:
        seed(session)
        session.commit()
    with pg_core() as session:
        assert seed(session) == []  # déjà enregistrées : rien à faire
```

- [ ] **Step 2: Vérifier l'échec**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_seed_demo.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.seed_demo` (ou skip sans DB — CI fera foi).

- [ ] **Step 3: Implémenter**

```python
# core/scripts/seed_demo.py
"""Déclare les tables de démo comme collections éditables publiques.
Idempotent — utilisable à chaque démarrage d'environnement de démo.

Usage : DATABASE_URL=postgresql+psycopg://… uv run python -m scripts.seed_demo [--owner alice]
"""
import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import TableNotFound
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection, get_collection
from app.db import make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

DEMO_TABLES = {"incidents": "Incidents", "points_interet": "Points d'intérêt"}


def _owner(session: Session, tenant_id: str, username: str | None) -> User:
    if username:
        user = session.scalar(select(User).where(
            User.tenant_id == tenant_id, User.username == username))
        if user is None:
            raise SystemExit(f"owner '{username}' introuvable")
        return user
    admin = session.scalar(select(User).where(
        User.tenant_id == tenant_id, User.is_admin.is_(True)))
    if admin:
        return admin
    subs = [s.strip() for s in os.environ.get("CORE_ADMIN_SUBS", "").split(",") if s.strip()]
    if not subs:
        raise SystemExit("aucun admin : définir CORE_ADMIN_SUBS ou passer --owner")
    return get_or_create_user(session, tenant_id=tenant_id, oidc_sub=subs[0],
                              username=subs[0], email=None, first_name="", last_name="",
                              bootstrap_admin=True)


def seed(session: Session, owner_username: str | None = None) -> list[str]:
    tenant = get_or_create_default_tenant(session)
    owner = _owner(session, tenant.id, owner_username)
    created: list[str] = []
    for table, title in DEMO_TABLES.items():
        if get_collection(session, tenant_id=tenant.id, collection_id=table):
            continue
        try:
            info = introspect_table(session, table)
        except TableNotFound:
            print(f"table '{table}' absente — ignorée")
            continue
        apply_collection_ddl(session, table)
        create_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, table_name=table,
            title=title, description="Collection de démonstration", is_public=True,
            pk_column=info.pk_column, geometry_column=info.geometry_column,
            geometry_type=info.geometry_type, srid=info.srid,
        )
        created.append(table)
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=None)
    args = parser.parse_args()
    engine = make_engine(os.environ["DATABASE_URL"])
    Session = make_session_factory(engine)
    with Session() as session:
        created = seed(session, owner_username=args.owner)
        session.commit()
    print(f"collections créées : {created or 'aucune (déjà en place)'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Vérifier**

Run: `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_seed_demo.py -v` (ou CI)
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scripts/seed_demo.py core/tests/test_seed_demo.py
git commit -m "feat(core): script de seed des collections de démo (idempotent)"
```

---

### Task 11: Contrat OpenAPI→TS, lint final, doc d'état

**Files:**
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `CLAUDE.md` (section « État » : SP-3a livré ; compte de tests core)

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: contrat OpenAPI committé incluant `/collections*` et `/users*` — le job CI `api-types-drift` reste vert.

- [ ] **Step 1: Régénérer le contrat**

Run:
```bash
cd core && uv run python scripts/export_openapi.py
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` modifiés (nouveaux paths `/collections`, `/collections/{collection_id}`, `/collections/{collection_id}/schema`, `/collections/{collection_id}/sharing`, `/users`, `/users/{user_id}`).

- [ ] **Step 2: Vérification complète**

Run:
```bash
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm run test && npm run build
```
Expected: tout PASS (le shell ne consomme pas encore ces endpoints — la bascule est SP-3c ; `build` garantit que les types générés compilent).

- [ ] **Step 3: Mettre à jour CLAUDE.md**

Dans la section « État au … » : ajouter une ligne « SP-3a livré (registre de
collections, introspection, rôle admin, RLS) — SP-3b (CRUD features OGC) à
lancer avec son spike RLS/PgBouncer » ; rafraîchir le compte de tests core.

- [ ] **Step 4: Commit final**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts CLAUDE.md
git commit -m "chore(core): contrat OpenAPI/TS régénéré — endpoints collections et users (SP-3a)"
```

---

## Couverture spec → tâches (auto-vérification)

| Exigence de la spec (SP-3a) | Tâche(s) |
|---|---|
| Migration 0008 (is_admin, collections, collection_shares, rôle gis_rls) | 2 |
| Bootstrap `CORE_ADMIN_SUBS`, mock admin, jamais de rétrogradation par env | 3 |
| `PATCH /users` + garde dernier admin + audit `user.promote/demote` | 5 |
| `can()` généralisé, admin limité aux collections (anti-régression items) | 4 |
| Enregistrement admin + garde-fous (table du cœur, PK, géométries, 409) | 6, 7 |
| Visibilité (owner/admin/groupes/public/anonyme), 404 avant 403 | 6, 9 |
| Introspection vivante + `GET /schema` (contrat SP-4), types v1 bornés | 7 |
| RLS générée par collection (tenant_id, policy, grants, idempotence) | 8 |
| Audit de toutes les mutations | 5, 6, 9 |
| Seed démo `incidents`/`points_interet` (idempotent, publiques) | 10 |
| Infra de test PostGIS + CI ; OpenAPI→TS à jour | 1, 11 |

Hors SP-3a (rappel) : endpoints `/items` OGC des features, landing/conformance,
`SET LOCAL ROLE` dans le chemin CRUD, extent spatial dans la description de
collection → **SP-3b** ; bascule shell, retrait pg_featureserv → **SP-3c**.
