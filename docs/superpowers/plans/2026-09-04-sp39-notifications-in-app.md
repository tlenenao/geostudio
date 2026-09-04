# Notifications in-app (SP-39) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ferme le chantier 4.19 — un run de pipeline (ou tout autre job des 4 autres familles) en échec est signalé dans une cloche persistante du shell même si l'utilisateur a quitté le panneau de suivi, via une nouvelle table `notifications` écrite côté cœur à chaque état terminal.

**Architecture:** Nouveau domaine `core/app/notifications/` (modèle, dépôt, routes self-service) écrit en best-effort par les 5 tâches procrastinate existantes (ingestion, pipeline, export, export d'app, rapport) sans jamais faire échouer leur propre statut ; le shell sonde `GET /notifications/unread-count` (React Query, `refetchInterval`) depuis une cloche montée dans `TopBar`, et réutilise le routeur d'ouverture d'item déjà existant (`useOpenItem`) pour la navigation au clic.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (cœur), React + React Query + Radix (`ui/kit/Popover`/`Badge`) côté shell. Aucune nouvelle dépendance.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-04-sp39-notifications-in-app-design.md` — toute divergence avec ce plan se résout en faveur du texte le plus récemment approuvé par Tanguy (ce plan), sauf contradiction manifeste, auquel cas s'arrêter et demander.
- Écriture de notification **best-effort, jamais bloquante** : chaque site d'écriture (tâches 4-8) utilise un bloc `try/except` **séparé** de celui qui committe `mark_done`/`mark_error`/`mark_succeeded`/`mark_failed` — voir `core/app/db.py::request_scoped_session` (l.88-103) : toute exception dans le même bloc `with` fait `rollback()` de **tout**, y compris le statut du job déjà écrit.
- Toute route/hook auto-généré (`response_model`, types TS) suit exactement les conventions déjà en place dans `core/app/roles/` et `shell/src/api/hooks.ts` (`useUsers`/`useUpdateUserRole`) — pas de nouveau patron.
- Docs et identifiants de test en français (CLAUDE.md). Code/identifiants techniques en anglais.
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), un sujet par commit.
- Après CHAQUE tâche touchant `shell/`, lancer `npm run test` (pas seulement le fichier modifié) — piège n°6 de CLAUDE.md (régression croisée invisible à un run scopé). Après chaque tâche touchant `core/`, lancer `uv run pytest` scopé au module concerné a minima.
- Régénération OpenAPI/types TS obligatoire dès qu'une route change (piège n°1 CLAUDE.md) — faite explicitement en Tâche 9, avant les tâches shell qui en dépendent.

---

## Task 1: Modèle + migration + enregistrement du module

**Files:**
- Create: `core/app/notifications/__init__.py` (vide)
- Create: `core/app/notifications/models.py`
- Create: `core/alembic/versions/0031_notifications.py`
- Modify: `core/app/db.py:58-59` (liste `core_table_names()`)
- Modify: `core/pyproject.toml:197-229` (contrat `[tool.importlinter]`)
- Test: `core/tests/test_notifications_migration.py`

**Interfaces:**
- Produces: `Notification` (colonnes : `id`, `tenant_id`, `recipient_user_id`, `kind`, `status`, `item_id`, `item_resource_type`, `item_title`, `error_message`, `created_at`, `read_at`), `NotificationPreference` (`user_id` PK, `tenant_id`, `value`, `updated_at`) — consommés par la Tâche 2.

- [ ] **Step 1: Écrire le modèle**

```python
# core/app/notifications/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/notifications/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_created",
            "tenant_id",
            "recipient_user_id",
            "created_at",
        ),
        Index(
            "ix_notifications_recipient_unread",
            "tenant_id",
            "recipient_user_id",
            "read_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # "ingestion" | "pipeline" | "export" | "appexport" | "report"
    status: Mapped[str] = mapped_column(String, nullable=False)
    # "success" | "failure"
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    item_resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    item_title: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False, default="all")
    # "all" | "failures_only" | "none"
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 2: Enregistrer le module dans `core_table_names()`**

`core/app/db.py:58-59` — insérer entre `mapicons` et `pipelines` (ordre alphabétique déjà en place) :

```diff
     from app.mapicons import models as mapicons_models  # noqa: F401
+    from app.notifications import models as notifications_models  # noqa: F401
     from app.pipelines import models as pipelines_models  # noqa: F401
```

Sans cette ligne, `Base.metadata.create_all()` (chemin SQLite/tests) ne connaît pas les deux nouvelles tables — c'est la SEULE liste qui les enregistre pour ce chemin (vérifié : `app.appexport`/`app.reports`/etc. y figurent tous).

- [ ] **Step 3: Écrire la migration Alembic**

```python
# core/alembic/versions/0031_notifications.py
# SPDX-License-Identifier: Apache-2.0
"""app.notifications — notifications + notification_preferences (chantier
4.19, docs/superpowers/specs/2026-09-04-sp39-notifications-in-app-design.md)

Deux tables neuves, aucune donnée existante à migrer (contrairement à
0030_roles.py) : create_table/drop_table suffisent dans les deux sens.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("recipient_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "item_id",
            sa.String(),
            sa.ForeignKey("items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("item_resource_type", sa.String(), nullable=True),
        sa.Column("item_title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["tenant_id", "recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["tenant_id", "recipient_user_id", "read_at"],
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("value", sa.String(), nullable=False, server_default="all"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
```

- [ ] **Step 4: Ajouter `app.notifications` au contrat de couches**

`core/pyproject.toml`, bloc `layers = [...]` (l.200-229) — insérer entre `"app.ingestion"` et `"app.dcat"` (vérifié : `app.notifications` doit être en dessous des 5 familles émettrices qui l'importeront — `pipelines`, `reports`, `export`, `appexport`, `ingestion`, toutes au-dessus dans cette liste — et au-dessus d'`app.items`/`app.auth`, dont il a besoin) :

```diff
     "app.ingestion",
+    "app.notifications",
     "app.dcat",
```

- [ ] **Step 5: Test — la migration s'applique et se défait sur une base SQLite fraîche (fumée rapide ; le test réel contre Postgres non-vide est en Tâche 12)**

```python
# core/tests/test_notifications_migration.py
# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import Base, make_engine


def test_notifications_tables_created_via_create_all():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    from app.notifications import models  # noqa: F401 -- enregistre sur Base.metadata

    Base.metadata.create_all(engine)
    tables = inspect(engine).get_table_names()
    assert "notifications" in tables
    assert "notification_preferences" in tables
```

- [ ] **Step 6: Lancer les vérifications**

```bash
cd core && uv run pytest tests/test_notifications_migration.py -v
uv run lint-imports
uv run alembic heads   # doit afficher 0031 (pas d'embranchement)
```
Expected: tests PASS, `lint-imports` propre, une seule tête `0031`.

- [ ] **Step 7: Commit**

```bash
git add core/app/notifications/__init__.py core/app/notifications/models.py \
  core/alembic/versions/0031_notifications.py core/app/db.py core/pyproject.toml \
  core/tests/test_notifications_migration.py
git commit -m "feat(core): ajoute les tables notifications/notification_preferences (SP-39)"
```

---

## Task 2: Dépôt (`app/notifications/repository.py`)

**Files:**
- Create: `core/app/notifications/repository.py`
- Test: `core/tests/test_notifications_repository.py`

**Interfaces:**
- Consumes: `Notification`, `NotificationPreference` (Tâche 1).
- Produces (consommés par la Tâche 3 — routes — et les Tâches 4-8 — sites d'écriture) :
  - `create_notification(session, *, tenant_id, recipient_user_id, kind, status, item_id, item_resource_type, item_title, error_message=None) -> Notification`
  - `list_notifications(session, *, tenant_id, recipient_user_id, preference, page, page_size) -> tuple[list[Notification], int]`
  - `count_unread_notifications(session, *, tenant_id, recipient_user_id, preference) -> int`
  - `mark_notification_read(session, *, tenant_id, recipient_user_id, notification_id) -> Notification | None`
  - `mark_all_notifications_read(session, *, tenant_id, recipient_user_id, preference) -> None`
  - `get_notification_preference(session, *, tenant_id, user_id) -> str`
  - `set_notification_preference(session, *, tenant_id, user_id, value) -> str`

- [ ] **Step 1: Écrire les tests (RED)**

```python
# core/tests/test_notifications_repository.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.notifications import repository as notifications_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    other_user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="b",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    session.commit()
    return session, tenant, user, other_user


def _create(session, *, tenant_id, recipient_user_id, status="success", kind="pipeline"):
    return notifications_repo.create_notification(
        session,
        tenant_id=tenant_id,
        recipient_user_id=recipient_user_id,
        kind=kind,
        status=status,
        item_id=None,
        item_resource_type="pipeline",
        item_title="Pipeline test",
    )


def test_create_notification_writes_all_fields(env):
    session, tenant, user, _other = env
    n = notifications_repo.create_notification(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        kind="export",
        status="failure",
        item_id=None,
        item_resource_type="map",
        item_title="Carte X",
        error_message="boom",
    )
    session.commit()
    assert n.id is not None
    assert n.kind == "export"
    assert n.status == "failure"
    assert n.error_message == "boom"
    assert n.read_at is None


def test_list_notifications_orders_most_recent_first_and_isolates_recipient(env):
    session, tenant, user, other_user = env
    first = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    second = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    _create(session, tenant_id=tenant.id, recipient_user_id=other_user.id)
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="all",
        page=1,
        page_size=20,
    )
    assert total == 2
    assert [r.id for r in rows] == [second.id, first.id]


def test_list_notifications_failures_only_filter(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="failures_only",
        page=1,
        page_size=20,
    )
    assert total == 1
    assert rows[0].id == failure.id


def test_list_notifications_none_preference_returns_nothing(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="none",
        page=1,
        page_size=20,
    )
    assert rows == []
    assert total == 0


def test_count_unread_matches_filter_and_read_state(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="all"
        )
        == 2
    )
    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
        )
        == 1
    )

    notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=failure.id
    )
    session.commit()
    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
        )
        == 0
    )


def test_mark_notification_read_is_idempotent_and_scoped_to_recipient(env):
    session, tenant, user, other_user = env
    n = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    assert (
        notifications_repo.mark_notification_read(
            session, tenant_id=tenant.id, recipient_user_id=other_user.id, notification_id=n.id
        )
        is None
    )
    first = notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=n.id
    )
    session.commit()
    assert first.read_at is not None
    second = notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=n.id
    )
    assert second.read_at == first.read_at


def test_mark_all_notifications_read_respects_preference_filter(env):
    session, tenant, user, _other = env
    success = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    notifications_repo.mark_all_notifications_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
    )
    session.commit()
    session.refresh(success)
    session.refresh(failure)
    assert success.read_at is None
    assert failure.read_at is not None


def test_notification_preference_defaults_to_all_and_round_trips(env):
    session, tenant, user, _other = env
    assert (
        notifications_repo.get_notification_preference(session, tenant_id=tenant.id, user_id=user.id)
        == "all"
    )
    notifications_repo.set_notification_preference(
        session, tenant_id=tenant.id, user_id=user.id, value="failures_only"
    )
    session.commit()
    assert (
        notifications_repo.get_notification_preference(session, tenant_id=tenant.id, user_id=user.id)
        == "failures_only"
    )
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_notifications_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.repository'`

- [ ] **Step 3: Implémenter le dépôt**

```python
# core/app/notifications/repository.py
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.notifications.models import Notification, NotificationPreference


def create_notification(
    session: Session,
    *,
    tenant_id: str,
    recipient_user_id: str,
    kind: str,
    status: str,
    item_id: str | None,
    item_resource_type: str | None,
    item_title: str,
    error_message: str | None = None,
) -> Notification:
    notification = Notification(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        recipient_user_id=recipient_user_id,
        kind=kind,
        status=status,
        item_id=item_id,
        item_resource_type=item_resource_type,
        item_title=item_title,
        error_message=error_message,
    )
    session.add(notification)
    session.flush()
    return notification


def _scope(base, *, preference: str):
    if preference == "failures_only":
        return base.where(Notification.status == "failure")
    return base


def list_notifications(
    session: Session,
    *,
    tenant_id: str,
    recipient_user_id: str,
    preference: str,
    page: int,
    page_size: int,
) -> tuple[list[Notification], int]:
    if preference == "none":
        return [], 0
    base = select(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_user_id == recipient_user_id,
    )
    base = _scope(base, preference=preference)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.scalars(
            base.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total


def count_unread_notifications(
    session: Session, *, tenant_id: str, recipient_user_id: str, preference: str
) -> int:
    if preference == "none":
        return 0
    base = select(func.count()).select_from(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_user_id == recipient_user_id,
        Notification.read_at.is_(None),
    )
    base = _scope(base, preference=preference)
    return session.scalar(base) or 0


def mark_notification_read(
    session: Session, *, tenant_id: str, recipient_user_id: str, notification_id: str
) -> Notification | None:
    notification = session.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.id == notification_id,
        )
    )
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.flush()
    return notification


def mark_all_notifications_read(
    session: Session, *, tenant_id: str, recipient_user_id: str, preference: str
) -> None:
    if preference == "none":
        return
    base = select(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_user_id == recipient_user_id,
        Notification.read_at.is_(None),
    )
    base = _scope(base, preference=preference)
    now = datetime.now(UTC)
    for notification in session.scalars(base).all():
        notification.read_at = now
    session.flush()


def get_notification_preference(session: Session, *, tenant_id: str, user_id: str) -> str:
    pref = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
        )
    )
    return pref.value if pref is not None else "all"


def set_notification_preference(
    session: Session, *, tenant_id: str, user_id: str, value: str
) -> str:
    pref = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
        )
    )
    if pref is None:
        pref = NotificationPreference(user_id=user_id, tenant_id=tenant_id, value=value)
        session.add(pref)
    else:
        pref.value = value
    session.flush()
    return pref.value
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_notifications_repository.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/notifications/repository.py core/tests/test_notifications_repository.py
git commit -m "feat(core): dépôt app.notifications (SP-39)"
```

---

## Task 3: Schémas + routes self-service + enregistrement

**Files:**
- Create: `core/app/notifications/schemas.py`
- Create: `core/app/notifications/routes.py`
- Modify: `core/app/main.py` (import + `include_router`)
- Test: `core/tests/test_notifications_routes.py`

**Interfaces:**
- Consumes: fonctions de dépôt (Tâche 2).
- Produces: `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `GET /notifications/preference`, `PATCH /notifications/preference` — consommées par le shell (Tâches 10-11) après régénération OpenAPI (Tâche 9).

- [ ] **Step 1: Écrire les tests (RED)**

```python
# core/tests/test_notifications_routes.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.notifications import repository as notifications_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        other_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), Session, tenant, user, other_user


@pytest.fixture()
def client():
    return _make_client()


def test_get_notifications_returns_only_the_caller_s_own(client):
    api, Session, tenant, user, other_user = client
    with Session() as s:
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="pipeline",
            status="failure",
            item_id=None,
            item_resource_type="pipeline",
            item_title="Pipeline A",
        )
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=other_user.id,
            kind="pipeline",
            status="failure",
            item_id=None,
            item_resource_type="pipeline",
            item_title="Pipeline B",
        )
        s.commit()

    res = api.get("/notifications")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["notifications"][0]["itemTitle"] == "Pipeline A"


def test_unread_count_reflects_current_preference(client):
    api, Session, tenant, user, _other = client
    with Session() as s:
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="export",
            status="success",
            item_id=None,
            item_resource_type="map",
            item_title="Carte",
        )
        s.commit()

    assert api.get("/notifications/unread-count").json() == {"count": 1}
    patch = api.patch("/notifications/preference", json={"value": "failures_only"})
    assert patch.status_code == 200
    assert api.get("/notifications/unread-count").json() == {"count": 0}


def test_patch_preference_rejects_unknown_value(client):
    api, *_ = client
    res = api.patch("/notifications/preference", json={"value": "bogus"})
    assert res.status_code == 400


def test_mark_read_then_read_all(client):
    api, Session, tenant, user, _other = client
    with Session() as s:
        n1 = notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="report",
            status="success",
            item_id=None,
            item_resource_type="report",
            item_title="Rapport",
        )
        notifications_repo.create_notification(
            s,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="appexport",
            status="failure",
            item_id=None,
            item_resource_type="app",
            item_title="App",
        )
        s.commit()
        n1_id = n1.id

    read_res = api.post(f"/notifications/{n1_id}/read")
    assert read_res.status_code == 200
    assert read_res.json()["readAt"] is not None
    assert api.get("/notifications/unread-count").json() == {"count": 1}

    all_res = api.post("/notifications/read-all")
    assert all_res.status_code == 204
    assert api.get("/notifications/unread-count").json() == {"count": 0}


def test_mark_read_unknown_id_is_404(client):
    api, *_ = client
    res = api.post("/notifications/does-not-exist/read")
    assert res.status_code == 404
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_notifications_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.schemas'` (ou 404 sur les routes, `app.notifications.routes` n'existe pas encore).

- [ ] **Step 3: Écrire les schémas**

```python
# core/app/notifications/schemas.py
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: str
    kind: str
    status: str
    itemId: str | None
    itemResourceType: str | None
    itemTitle: str
    errorMessage: str | None
    createdAt: str
    readAt: str | None


class NotificationPage(BaseModel):
    notifications: list[NotificationRead]
    total: int
    page: int
    pageSize: int


class UnreadCount(BaseModel):
    count: int


class NotificationPreferenceRead(BaseModel):
    value: str


class NotificationPreferencePatch(BaseModel):
    value: str
```

- [ ] **Step 4: Écrire les routes**

```python
# core/app/notifications/routes.py
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.notifications.models import Notification
from app.notifications.repository import (
    count_unread_notifications,
    get_notification_preference,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    set_notification_preference,
)
from app.notifications.schemas import (
    NotificationPage,
    NotificationPreferencePatch,
    NotificationPreferenceRead,
    NotificationRead,
    UnreadCount,
)
from app.users.models import User

router = APIRouter()

_VALID_PREFERENCE_VALUES = {"all", "failures_only", "none"}


def _notification_json(notification: Notification) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        kind=notification.kind,
        status=notification.status,
        itemId=notification.item_id,
        itemResourceType=notification.item_resource_type,
        itemTitle=notification.item_title,
        errorMessage=notification.error_message,
        createdAt=notification.created_at.isoformat(),
        readAt=notification.read_at.isoformat() if notification.read_at is not None else None,
    )


@router.get("/notifications", response_model=NotificationPage)
def get_notifications(
    page: int = 1,
    pageSize: int = 20,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationPage:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    notifications, total = list_notifications(
        session,
        tenant_id=user.tenant_id,
        recipient_user_id=user.id,
        preference=preference,
        page=page,
        page_size=pageSize,
    )
    return NotificationPage(
        notifications=[_notification_json(n) for n in notifications],
        total=total,
        page=page,
        pageSize=pageSize,
    )


@router.get("/notifications/unread-count", response_model=UnreadCount)
def get_unread_count(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> UnreadCount:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    count = count_unread_notifications(
        session, tenant_id=user.tenant_id, recipient_user_id=user.id, preference=preference
    )
    return UnreadCount(count=count)


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def post_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationRead:
    notification = mark_notification_read(
        session,
        tenant_id=user.tenant_id,
        recipient_user_id=user.id,
        notification_id=notification_id,
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return _notification_json(notification)


@router.post("/notifications/read-all", status_code=204)
def post_notifications_read_all(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> None:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    mark_all_notifications_read(
        session, tenant_id=user.tenant_id, recipient_user_id=user.id, preference=preference
    )


@router.get("/notifications/preference", response_model=NotificationPreferenceRead)
def get_preference(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> NotificationPreferenceRead:
    value = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    return NotificationPreferenceRead(value=value)


@router.patch("/notifications/preference", response_model=NotificationPreferenceRead)
def patch_preference(
    body: NotificationPreferencePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationPreferenceRead:
    if body.value not in _VALID_PREFERENCE_VALUES:
        raise HTTPException(status_code=400, detail=f"unknown preference value: {body.value}")
    value = set_notification_preference(
        session, tenant_id=user.tenant_id, user_id=user.id, value=body.value
    )
    return NotificationPreferenceRead(value=value)
```

- [ ] **Step 5: Enregistrer le routeur dans `main.py`**

Import, alphabétiquement entre `mapicons_routes` et `pipelines_routes` :

```diff
 from app.mapicons import routes as mapicons_routes
+from app.notifications import routes as notifications_routes
 from app.pipelines import routes as pipelines_routes
```

Inclusion, **inconditionnelle** (pas de flag de capacité — décision spec §3.2/§Décisions), juste après `reports_routes.router` (l.274 de la zone déjà lue, avant le premier `if is_etl_enabled():`) :

```diff
     app.include_router(reports_routes.router)
+    app.include_router(notifications_routes.router)
     if is_etl_enabled():
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_notifications_routes.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add core/app/notifications/schemas.py core/app/notifications/routes.py core/app/main.py \
  core/tests/test_notifications_routes.py
git commit -m "feat(core): routes self-service /notifications (SP-39)"
```

---

## Task 4: Site d'écriture — Ingestion

**Files:**
- Modify: `core/app/ingestion/tasks.py` (imports + `run_ingestion_task`, l.34-85)
- Test: `core/tests/test_ingestion_tasks.py`

**Interfaces:**
- Consumes: `notifications_repo.create_notification` (Tâche 2).

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_ingestion_tasks.py` (réutilise la fixture `env` existante, l.34-60) :

```python
from sqlalchemy import select

from app.notifications.models import Notification


def test_success_writes_a_notification_for_the_creator(env, monkeypatch):
    app, Session, tenant, user = env
    geojson = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
    )
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k3": geojson})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k3",
            filename="villes.geojson",
            collection_title="Villes notif",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        notification = s.scalar(
            select(Notification).where(Notification.tenant_id == tenant.id)
        )
        assert notification is not None
        assert notification.recipient_user_id == user.id
        assert notification.kind == "ingestion"
        assert notification.status == "success"
        assert notification.item_resource_type == "dataset"
        assert notification.item_title == "Villes notif"
        assert notification.item_id is not None


def test_failure_writes_a_notification_with_no_item(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k4": b"not json"})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k4",
            filename="broken.geojson",
            collection_title="Casse notif",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        notification = s.scalar(
            select(Notification).where(Notification.tenant_id == tenant.id)
        )
        assert notification is not None
        assert notification.status == "failure"
        assert notification.item_id is None
        assert notification.item_title == "Casse notif"
        assert notification.error_message is not None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_tasks.py -k notification -v`
Expected: FAIL — aucune ligne `Notification` trouvée (`notification is None`).

- [ ] **Step 3: Implémenter le site d'écriture**

`core/app/ingestion/tasks.py` — ajouter l'import et écrire la notification juste après chaque `mark_done`/`mark_error`, dans un bloc `try/except` séparé (best-effort — cf. Global Constraints) :

```diff
 from app.db import make_engine, make_session_factory, request_scoped_session
 from app.ingestion import repository as ingestion_repo
 from app.ingestion.importer import run_import
 from app.ingestion.parsers import IngestionParseError
 from app.ingestion.storage import download_object, make_s3_client
 from app.jobs import app
+from app.notifications import repository as notifications_repo
 
 logger = logging.getLogger(__name__)
+
+
+def _notify(session_factory, *, tenant_id, created_by, status, item_id, collection_title, error=None):
+    try:
+        with request_scoped_session(session_factory) as session:
+            notifications_repo.create_notification(
+                session,
+                tenant_id=tenant_id,
+                recipient_user_id=created_by,
+                kind="ingestion",
+                status=status,
+                item_id=item_id,
+                item_resource_type="dataset" if item_id is not None else None,
+                item_title=collection_title,
+                error_message=error,
+            )
+    except Exception:
+        logger.exception("ingestion job : échec de l'écriture de la notification")
```

```diff
         with request_scoped_session(session_factory) as session:
             ingestion_repo.mark_done(
                 session,
                 job_id=job_id,
                 collection_id=result.collection_id,
                 item_id=result.item_id,
             )
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            created_by=created_by,
+            status="success",
+            item_id=result.item_id,
+            collection_title=collection_title,
+        )
     except IngestionParseError as exc:
         with request_scoped_session(session_factory) as session:
             ingestion_repo.mark_error(session, job_id=job_id, error_message=str(exc))
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            created_by=created_by,
+            status="failure",
+            item_id=None,
+            collection_title=collection_title,
+            error=str(exc),
+        )
     except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
         logger.exception("ingestion job %s : erreur inattendue", job_id)
         with request_scoped_session(session_factory) as session:
             ingestion_repo.mark_error(
                 session, job_id=job_id, error_message=f"erreur interne : {exc}"
             )
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            created_by=created_by,
+            status="failure",
+            item_id=None,
+            collection_title=collection_title,
+            error=f"erreur interne : {exc}",
+        )
```

Note : `collection_title`/`created_by`/`tenant_id` sont déjà des variables locales de `run_ingestion_task` (l.46-54 avant modification) — aucune variable supplémentaire à charger.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_tasks.py -v`
Expected: 5 passed (3 existants + 2 nouveaux).

- [ ] **Step 5: Commit**

```bash
git add core/app/ingestion/tasks.py core/tests/test_ingestion_tasks.py
git commit -m "feat(core): notification in-app sur run_ingestion_task (SP-39)"
```

---

## Task 5: Site d'écriture — Pipeline

**Files:**
- Modify: `core/app/pipelines/jobs.py` (imports + `run_pipeline_task`, l.100-147)
- Test: `core/tests/test_pipeline_jobs.py`

**Interfaces:**
- Consumes: `notifications_repo.create_notification` (Tâche 2).
- Destinataire : propriétaire de l'item (`Item.owner_id`), pas l'auteur du run (aucune colonne utilisateur sur `PipelineRun` — décision spec §2.6). Titre/type résolus par la même requête brute que `_acting_user` (l.39-54), étendue pour sélectionner aussi `Item.title`.

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_pipeline_jobs.py` (réutilise la fixture `env`, qui yield `(app, Session, tenant, user, item_id)` avec `user.id` déjà propriétaire de `item_id` — l.28-75) :

```python
from sqlalchemy import select

from app.notifications.models import Notification


def test_success_writes_a_notification_for_the_item_owner(env):
    app, Session, tenant, user, item_id = env
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == user.id
        assert notification.kind == "pipeline"
        assert notification.status == "success"
        assert notification.item_id == item_id
        assert notification.item_resource_type == "pipeline"


def test_failure_writes_a_notification(env, monkeypatch):
    app, Session, tenant, user, item_id = env

    def _boom(session, *, item_id):
        raise ValueError("bad config")

    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.status == "failure"
        assert notification.error_message is not None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -k notification -v`
Expected: FAIL — `notification is None`.

- [ ] **Step 3: Implémenter le site d'écriture**

`core/app/pipelines/jobs.py` :

```diff
 from app.db import make_engine, make_session_factory, request_scoped_session
 from app.jobs import app
+from app.notifications import repository as notifications_repo
 from app.pipelines import repository as pipelines_repo
 from app.pipelines.runtime import NodeStat, PipelineRuntimeError, run_pipeline
 from app.users.models import User
 
 logger = logging.getLogger(__name__)
+
+
+def _owner_and_title(session, *, tenant_id: str, item_id: str) -> tuple[str, str]:
+    from sqlalchemy import select
+
+    from app.items.models import Item
+
+    row = session.execute(
+        select(Item.owner_id, Item.title).where(
+            Item.id == item_id, Item.tenant_id == tenant_id
+        )
+    ).one()
+    return row.owner_id, row.title
+
+
+def _notify(session_factory, *, tenant_id, item_id, status, error=None):
+    try:
+        with request_scoped_session(session_factory) as session:
+            owner_id, title = _owner_and_title(session, tenant_id=tenant_id, item_id=item_id)
+            notifications_repo.create_notification(
+                session,
+                tenant_id=tenant_id,
+                recipient_user_id=owner_id,
+                kind="pipeline",
+                status=status,
+                item_id=item_id,
+                item_resource_type="pipeline",
+                item_title=title,
+                error_message=error,
+            )
+    except Exception:
+        logger.exception("pipeline run : échec de l'écriture de la notification")
```

```diff
         with request_scoped_session(session_factory) as session:
             pipelines_repo.mark_succeeded(
                 session,
                 run_id=run_id,
                 node_stats={s.nodeId: s.to_dict() for s in stats},
             )
+        _notify(session_factory, tenant_id=tenant_id, item_id=item_id, status="success")
     except (PipelineRuntimeError, ValueError) as exc:
         with request_scoped_session(session_factory) as session:
             pipelines_repo.mark_failed(session, run_id=run_id, error=str(exc))
+        _notify(
+            session_factory, tenant_id=tenant_id, item_id=item_id, status="failure", error=str(exc)
+        )
     except Exception as exc:  # toute erreur inattendue finit "failed", jamais zombie
         logger.exception("pipeline run %s : erreur inattendue", run_id)
         with request_scoped_session(session_factory) as session:
             pipelines_repo.mark_failed(session, run_id=run_id, error=f"erreur interne : {exc}")
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            item_id=item_id,
+            status="failure",
+            error=f"erreur interne : {exc}",
+        )
```

Note : `item_id` (= `run.pipeline_item_id`) est déjà chargé en local dès le premier bloc `with` (l.111 avant modification), disponible dans les trois branches `except`.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -v`
Expected: tous les tests existants + 2 nouveaux, PASS (fichier marqué `pytest.mark.postgis` — nécessite `CORE_TEST_DATABASE_URL`, cf. Tâche 12 pour la vérification complète si non disponible en local).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/jobs.py core/tests/test_pipeline_jobs.py
git commit -m "feat(core): notification in-app sur run_pipeline_task (SP-39)"
```

---

## Task 6: Site d'écriture — Export (avec garde anti-double-notification)

**Files:**
- Modify: `core/app/export/jobs.py` (imports + `render_export_task`, l.85-159)
- Test: `core/tests/test_export_jobs.py`

**Interfaces:**
- Consumes: `notifications_repo.create_notification` (Tâche 2).
- **Garde critique** : ne PAS écrire de notification `kind="export"` quand `job.page_id is not None` — ce job est interne au sweep de rapports (`reports/jobs.py:153`), il sera notifié comme `kind="report"` par la Tâche 8. Testé explicitement ci-dessous.

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_export_jobs.py` (réutilise la fixture `db_session`, l.32-67, qui crée un item `resource_type="map"` — donc `item_resource_type` attendu = `"map"`) :

```python
from sqlalchemy import select

from app.notifications.models import Notification


def test_success_writes_a_notification_for_the_requester(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is not None
    assert notification.recipient_user_id == user.id
    assert notification.kind == "export"
    assert notification.status == "success"
    assert notification.item_resource_type == "map"
    assert notification.item_title == "Carte test"


def test_failure_writes_a_notification(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()

    def _boom(url):
        raise RuntimeError("navigation timeout")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is not None
    assert notification.status == "failure"
    assert "navigation timeout" in notification.error_message


def test_report_triggered_export_does_not_write_an_export_notification(db_session, monkeypatch):
    """job.page_id renseigné == rendu interne au sweep de rapports — la
    notification sera écrite comme kind="report" par _notify_pending_reports
    (Tâche 8), jamais ici (sinon double notification pour le même événement,
    cf. spec §3.1)."""
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        user_id=user.id,
        format="pdf",
        page_id="page-1",
    )
    session.commit()
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_export_jobs.py -k notification -v`
Expected: FAIL — `notification is None` sur les deux premiers tests (le 3e passe déjà trivialement, à vérifier qu'il échoue pour la bonne raison une fois l'implémentation écrite en Step 3, pas avant).

- [ ] **Step 3: Implémenter le site d'écriture**

`core/app/export/jobs.py` :

```diff
 from app.export import repository as export_repo
 from app.export.rendering import RenderPage, render_export
 from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
 from app.jobs import app
+from app.items import repository as items_repo
+from app.notifications import repository as notifications_repo
 
 logger = logging.getLogger(__name__)
 
 _CONTENT_TYPE = {"png": "image/png", "pdf": "application/pdf"}
+
+
+def _notify(session_factory, *, tenant_id, item_id, user_id, page_id, resource_type, status, error=None):
+    if page_id is not None:
+        # Rendu interne au sweep de rapports (reports/jobs.py:153) — notifié
+        # comme kind="report" par _notify_pending_reports, jamais ici (spec
+        # §3.1, garde anti-double-notification).
+        return
+    try:
+        with request_scoped_session(session_factory) as session:
+            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
+            title = item.title if item is not None else item_id
+            notifications_repo.create_notification(
+                session,
+                tenant_id=tenant_id,
+                recipient_user_id=user_id,
+                kind="export",
+                status=status,
+                item_id=item_id,
+                item_resource_type=resource_type,
+                item_title=title,
+                error_message=error,
+            )
+    except Exception:
+        logger.exception("export job : échec de l'écriture de la notification")
```

```diff
         with request_scoped_session(session_factory) as session:
             export_repo.mark_done(session, job_id=job_id, result_key=result_key)
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            item_id=item_id,
+            user_id=user_id,
+            page_id=page_id,
+            resource_type="map" if config.kind == "map" else "app",
+            status="success",
+        )
     except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
         logger.exception("export job %s : erreur inattendue", job_id)
         with request_scoped_session(session_factory) as session:
             export_repo.mark_error(session, job_id=job_id, error=str(exc))
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            item_id=item_id,
+            user_id=user_id,
+            page_id=page_id,
+            resource_type=None,
+            status="failure",
+            error=str(exc),
+        )
```

Notes :
- `item_id`, `user_id`, `page_id` sont déjà des variables locales (l.100 avant modification, `item_id, user_id, export_format = job.item_id, job.user_id, job.format` puis `page_id, ctx = job.page_id, job.ctx`).
- `config` (avec `.kind`) n'est disponible que dans le chemin de succès (chargé en Step au début du `try`) — dans le chemin d'échec, `resource_type=None` est passé explicitement : `item_resource_type` est nullable précisément pour ce cas (schéma Tâche 1). Le titre reste résolu via `items_repo.get_item`, indépendant de `config`.
- Le chemin `if not is_export_enabled(): ... return` (l.89-92, tout en haut de la fonction, AVANT le chargement du job) n'écrit délibérément **aucune** notification — cf. spec §4 « Hors périmètre », limite connue et documentée, pas un oubli.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: tous les tests existants + 3 nouveaux, PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/export/jobs.py core/tests/test_export_jobs.py
git commit -m "feat(core): notification in-app sur render_export_task (SP-39)"
```

---

## Task 7: Site d'écriture — Export d'app

**Files:**
- Modify: `core/app/appexport/jobs.py` (imports + `build_app_export_task`, l.68-115)
- Test: `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes: `notifications_repo.create_notification` (Tâche 2).
- `job.user_id` n'est aujourd'hui **pas** capturé en local dans `build_app_export_task` (seuls `item_id`/`mode` le sont, l.83-84 avant modification) — à ajouter.

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_appexport_jobs.py` (réutilise `_setup`, qui retourne `(Session, tenant_id, job_id)` — l.12-79) :

```python
from sqlalchemy import select

from app.notifications.models import Notification


def test_success_writes_a_notification_for_the_requester(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)

    build_app_export_task(job_id=job_id, tenant_id=tenant_id)

    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant_id))
    assert job.status == "done"
    assert notification is not None
    assert notification.recipient_user_id == job.user_id
    assert notification.kind == "appexport"
    assert notification.status == "success"
    assert notification.item_resource_type == "app"
    assert notification.item_title == "App"


def test_disabled_flag_writes_no_notification(monkeypatch, tmp_path):
    """L'export est marqué "error" AVANT le chargement du job (item_id/user_id
    jamais lus) — cf. spec §4, même limite documentée que sur export/jobs.py."""
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)

    build_app_export_task(job_id=job_id, tenant_id=tenant_id)

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant_id))
    assert notification is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -k notification -v`
Expected: FAIL sur le premier test (`notification is None`) ; le second passe déjà (rien à écrire), à confirmer qu'il continue de passer après implémentation.

- [ ] **Step 3: Implémenter le site d'écriture**

`core/app/appexport/jobs.py` :

```diff
 from app.configs import repository as configs_repo
 from app.configs.schemas import BuilderConfig
 from app.db import make_engine, make_session_factory, request_scoped_session
 from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
 from app.jobs import app
+from app.items import repository as items_repo
+from app.notifications import repository as notifications_repo
 
 logger = logging.getLogger(__name__)
+
+
+def _notify(session_factory, *, tenant_id, item_id, user_id, status, error=None):
+    try:
+        with request_scoped_session(session_factory) as session:
+            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
+            title = item.title if item is not None else item_id
+            notifications_repo.create_notification(
+                session,
+                tenant_id=tenant_id,
+                recipient_user_id=user_id,
+                kind="appexport",
+                status=status,
+                item_id=item_id,
+                item_resource_type="app",
+                item_title=title,
+                error_message=error,
+            )
+    except Exception:
+        logger.exception("app export job : échec de l'écriture de la notification")
```

```diff
         job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
         if job is None:
             logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
             return
         appexport_repo.mark_running(session, job_id=job_id)
         item_id = job.item_id
         mode = job.mode
+        user_id = job.user_id
```

```diff
         with request_scoped_session(session_factory) as session:
             appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
+        _notify(session_factory, tenant_id=tenant_id, item_id=item_id, user_id=user_id, status="success")
     except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
         logger.exception("app export job %s : erreur inattendue", job_id)
         with request_scoped_session(session_factory) as session:
             appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
+        _notify(
+            session_factory,
+            tenant_id=tenant_id,
+            item_id=item_id,
+            user_id=user_id,
+            status="failure",
+            error=str(exc),
+        )
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: tous les tests existants + 2 nouveaux, PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/jobs.py core/tests/test_appexport_jobs.py
git commit -m "feat(core): notification in-app sur build_app_export_task (SP-39)"
```

---

## Task 8: Site d'écriture — Rapport

**Files:**
- Modify: `core/app/reports/jobs.py` (imports + `_notify_pending_reports` l.242-362, `_record_trigger_failure` l.73-97)
- Test: `core/tests/test_report_jobs.py`

**Interfaces:**
- Consumes: `notifications_repo.create_notification` (Tâche 2).
- Écrite **indépendamment** de `payload.channels` (email/webhook) — spec §3.1, une notification in-app par run, que des canaux soient configurés ou non.
- Le run à `export_job_id is None` (`_record_trigger_failure`, déclenchement lui-même échoué) écrit aussi une notification d'échec.

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_report_jobs.py` (réutilise `_make_session`, l.32-34 ; mirroring exact de `test_notify_sends_webhook_with_result_url_and_marks_notified`, l.466-530) :

```python
from sqlalchemy import select

from app.notifications.models import Notification


def test_notify_writes_a_notification_independently_of_configured_channels(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard"
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report"
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [],  # aucun canal configuré — la notification in-app doit tout de même s'écrire
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf"
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-2.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()
        owner_id = owner.id

    monkeypatch.setattr(
        report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-2.pdf"
    )
    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == owner_id
        assert notification.kind == "report"
        assert notification.status == "success"
        assert notification.item_resource_type == "report"
        assert notification.item_title == "Weekly report"


def test_trigger_failure_writes_a_failure_notification(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Broken report"
        ).id
        s.commit()
        owner_id = owner.id

    with Session() as s:
        report_jobs._record_trigger_failure(
            s, tenant_id=tenant.id, item_id=report_id, error="bookmark not readable"
        )
        s.commit()

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == owner_id
        assert notification.kind == "report"
        assert notification.status == "failure"
        assert notification.item_title == "Broken report"
        assert notification.error_message == "bookmark not readable"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_report_jobs.py -k notification -v`
Expected: FAIL sur les deux tests (`notification is None`).

- [ ] **Step 3: Implémenter le site d'écriture**

`core/app/reports/jobs.py` — import :

```diff
 from app.items import repository as items_repo
 from app.items.models import Item
 from app.jobs import app
+from app.notifications import repository as notifications_repo
 from app.reports import repository as reports_repo
```

Dans `_record_trigger_failure` (l.73-97) — écrire la notification d'échec juste après `_audit_trigger_failure`, avant le `session.commit()` final (best-effort, donc entourée de son propre `try/except` malgré le commit partagé — une erreur ici ne doit annuler ni le run créé ni l'audit déjà en session) :

```diff
     run = reports_repo.create_run(
         session,
         tenant_id=tenant_id,
         report_item_id=item_id,
         export_job_id=None,
     )
     reports_repo.mark_notified(session, run_id=run.id)
     _audit_trigger_failure(session, tenant_id=tenant_id, item_id=item_id, error=error)
+    try:
+        owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)
+        item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
+        notifications_repo.create_notification(
+            session,
+            tenant_id=tenant_id,
+            recipient_user_id=owner.id,
+            kind="report",
+            status="failure",
+            item_id=item_id,
+            item_resource_type="report",
+            item_title=item.title if item is not None else item_id,
+            error_message=error,
+        )
+    except Exception:
+        # Best-effort (Global Constraints) : couvre à la fois
+        # ReportTriggerError (propriétaire introuvable — item supprimé entre
+        # l'échec initial et ce point, rien à notifier, le run+audit déjà
+        # écrits ci-dessus suffisent) ET toute erreur inattendue. Doit
+        # rester large ici — cette fonction est appelée depuis le `except
+        # Exception` fourre-tout de _trigger_due_reports (l.201-216) ; une
+        # exception non rattrapée ici remonterait et interromprait le
+        # balayage pour TOUS les tenants restants de ce tick (même piège que
+        # celui documenté en commentaire sur ce fourre-tout).
+        logger.exception(
+            "échec de déclenchement du rapport %s : échec de l'écriture de la notification",
+            item_id,
+        )
     session.commit()
```

Dans `_notify_pending_reports` (l.242-362) — écrire la notification **avant** `mark_notified` (`finally`), à l'intérieur du `try` existant, juste après le calcul de `title` (l.284) : indépendante de `payload.channels`, best-effort (propre `try/except`, jamais laissée remonter — le `finally` doit toujours appeler `mark_notified`) :

```diff
                 item = items_repo.get_item(
                     session, tenant_id=run.tenant_id, item_id=run.report_item_id
                 )
                 title = item.title if item is not None else run.report_item_id
                 result_url = _presigned_url_for_job(job)
+                try:
+                    owner = _owner_user(
+                        session, tenant_id=run.tenant_id, item_id=run.report_item_id
+                    )
+                    notifications_repo.create_notification(
+                        session,
+                        tenant_id=run.tenant_id,
+                        recipient_user_id=owner.id,
+                        kind="report",
+                        status="success" if job.status == "done" else "failure",
+                        item_id=run.report_item_id,
+                        item_resource_type="report",
+                        item_title=title,
+                        error_message=job.error,
+                    )
+                except Exception:
+                    logger.exception(
+                        "run de rapport %s : échec de l'écriture de la notification", run.id
+                    )
                 message = (
                     f"Rapport « {title} » : {job.status}."
```

Note : `job.status` ne peut valoir que `"done"` ou `"error"` à ce point (garde `if job is None or job.status not in ("done", "error"): continue` juste au-dessus, l.254) — `"done"` → `status="success"`, tout le reste (`"error"`) → `"failure"`.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_report_jobs.py -v`
Expected: tous les tests existants + 2 nouveaux, PASS. Lancer aussi `uv run pytest tests/test_report_sweep.py -v` (non-régression, aucun changement de comportement du sweep lui-même attendu).

- [ ] **Step 5: Commit**

```bash
git add core/app/reports/jobs.py core/tests/test_report_jobs.py
git commit -m "feat(core): notification in-app sur le sweep de rapports (SP-39)"
```

---

## Task 9: Régénération OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json` (généré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (généré)

**Interfaces:**
- Produces: types TS pour les 6 nouvelles routes, consommés par la Tâche 10.

- [ ] **Step 1: Régénérer la spec OpenAPI**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
```

- [ ] **Step 2: Régénérer les types TS**

```bash
cd ../shell && npm run gen:api-types
```

- [ ] **Step 3: Vérifier le diff**

```bash
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```
Expected: diff non vide, limité aux 6 nouveaux chemins `/notifications*` et à leurs schémas (`NotificationRead`, `NotificationPage`, `UnreadCount`, `NotificationPreferenceRead`, `NotificationPreferencePatch`) — aucune autre route/schéma ne doit changer.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore: régénère OpenAPI + types TS pour /notifications (SP-39)"
```

---

## Task 10: Shell — ItemClient + types + hooks

**Files:**
- Modify: `shell/src/api/types.ts` (nouveaux types)
- Modify: `shell/src/api/itemClient.ts` (nouvelles méthodes + interface `ItemClient`)
- Modify: `shell/src/api/hooks.ts` (nouveaux hooks)

**Interfaces:**
- Produces: `NotificationSummary`, `NotificationPage`, `NotificationPreferenceValue` (types) ; `client.listNotifications`, `client.getUnreadNotificationCount`, `client.markNotificationRead`, `client.markAllNotificationsRead`, `client.getNotificationPreference`, `client.updateNotificationPreference` (méthodes) ; `useNotifications`, `useUnreadNotificationCount`, `useMarkNotificationRead`, `useMarkAllNotificationsRead`, `useNotificationPreference`, `useUpdateNotificationPreference` (hooks) — consommés par la Tâche 11.

Pas de test dédié à cette tâche (même choix que SP-38 §2.2/§3 : ces méthodes/hooks sont couverts indirectement par les tests du composant, Tâche 11 — aucun fichier `hooks.test.ts` n'existe dans ce dépôt).

- [ ] **Step 1: Ajouter les types**

`shell/src/api/types.ts`, à la suite de `UserSummary` (l.66-70) :

```typescript
export type NotificationSummary = {
  id: string;
  kind: "ingestion" | "pipeline" | "export" | "appexport" | "report";
  status: "success" | "failure";
  itemId: string | null;
  itemResourceType: ResourceType | null;
  itemTitle: string;
  errorMessage: string | null;
  createdAt: string;
  readAt: string | null;
};

export type NotificationPreferenceValue = "all" | "failuresOnly" | "none";
```

Note : `NotificationPreferenceValue` utilise le casing camelCase idiomatique TS côté shell ; la conversion vers les valeurs cœur (`"all"`/`"failures_only"`/`"none"`) se fait dans `itemClient.ts` (Step 2), jamais dans les composants — même discipline que le reste du fichier (`roleSlug`, etc. déjà en camelCase alors que le cœur répond en snake_case sur certains champs internes).

- [ ] **Step 2: Ajouter les méthodes à `itemClient.ts`**

À la suite de `updateUserRole` (l.596-598) :

```typescript
    async listNotifications(params: {
      page: number;
      pageSize: number;
    }): Promise<{ notifications: NotificationSummary[]; total: number }> {
      const query = new URLSearchParams({
        page: String(params.page),
        pageSize: String(params.pageSize),
      });
      return request<{ notifications: NotificationSummary[]; total: number }>(
        "GET",
        `/notifications?${query.toString()}`,
      );
    },

    async getUnreadNotificationCount(): Promise<number> {
      const { count } = await request<{ count: number }>("GET", "/notifications/unread-count");
      return count;
    },

    async markNotificationRead(id: string): Promise<NotificationSummary> {
      return request<NotificationSummary>("POST", `/notifications/${id}/read`);
    },

    async markAllNotificationsRead(): Promise<void> {
      await request<void>("POST", "/notifications/read-all");
    },

    async getNotificationPreference(): Promise<NotificationPreferenceValue> {
      const { value } = await request<{ value: string }>("GET", "/notifications/preference");
      return _preferenceFromCore(value);
    },

    async updateNotificationPreference(
      value: NotificationPreferenceValue,
    ): Promise<NotificationPreferenceValue> {
      const { value: updated } = await request<{ value: string }>(
        "PATCH",
        "/notifications/preference",
        { value: _preferenceToCore(value) },
      );
      return _preferenceFromCore(updated);
    },
```

Deux petites fonctions de conversion, définies au niveau module (à côté de `createItemClient`, avant sa déclaration — même zone que les autres helpers de fichier comme `_queryParams`) :

```typescript
function _preferenceToCore(value: NotificationPreferenceValue): string {
  return value === "failuresOnly" ? "failures_only" : value;
}

function _preferenceFromCore(value: string): NotificationPreferenceValue {
  return value === "failures_only" ? "failuresOnly" : (value as NotificationPreferenceValue);
}
```

Et l'import en tête de fichier (bloc de types déjà importés, l.66 zone) :

```diff
   UserSummary,
+  NotificationSummary,
+  NotificationPreferenceValue,
```

Et les 6 signatures dans l'interface `ItemClient` (à la suite d'`updateUserRole`, l.295) :

```typescript
  listNotifications(params: {
    page: number;
    pageSize: number;
  }): Promise<{ notifications: NotificationSummary[]; total: number }>;
  getUnreadNotificationCount(): Promise<number>;
  markNotificationRead(id: string): Promise<NotificationSummary>;
  markAllNotificationsRead(): Promise<void>;
  getNotificationPreference(): Promise<NotificationPreferenceValue>;
  updateNotificationPreference(
    value: NotificationPreferenceValue,
  ): Promise<NotificationPreferenceValue>;
```

- [ ] **Step 3: Ajouter les hooks**

`shell/src/api/hooks.ts`, à la suite de `useUpdateUserRole` (l.108-125) :

```typescript
export function useNotifications(params: { page: number; pageSize: number }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => client.listNotifications(params),
  });
}

export function useUnreadNotificationCount() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => client.getUnreadNotificationCount(),
    refetchInterval: 45_000,
    // Sondage indéfini global (monté une fois dans TopBar, toute la session),
    // pas le patron "boucle manuelle capped" de PipelineRunPanel/ExportPanel/
    // ImportFileButton (poll jusqu'à fin d'UN job précis, plafonné) — forme de
    // problème différente, refetchInterval react-query est le bon outil ici.
  });
}

export function useMarkNotificationRead() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.markNotificationRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => client.markAllNotificationsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useNotificationPreference() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", "preference"],
    queryFn: () => client.getNotificationPreference(),
  });
}

export function useUpdateNotificationPreference() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: NotificationPreferenceValue) =>
      client.updateNotificationPreference(value),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
```

Import du type en tête de fichier :

```diff
+import type { NotificationPreferenceValue } from "./types";
```

- [ ] **Step 4: Vérifier la compilation**

```bash
cd shell && npx tsc --noEmit
```
Expected: 0 erreur.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts
git commit -m "feat(shell): ItemClient + hooks pour /notifications (SP-39)"
```

---

## Task 11: Shell — `NotificationBell`/`NotificationPanel`, i18n, câblage `TopBar`

**Files:**
- Create: `shell/src/shell/chrome/NotificationBell.tsx`
- Create: `shell/src/shell/chrome/NotificationBell.test.tsx`
- Modify: `shell/src/shell/routes.tsx` (exporter `useOpenItem`)
- Modify: `shell/src/shell/chrome/TopBar.tsx`
- Modify: `shell/src/shell/chrome/TopBar.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts` (nouvelles clés)

**Interfaces:**
- Consumes: hooks de la Tâche 10 ; `useOpenItem` (`shell/src/shell/routes.tsx:45`, à exporter) ; `Popover`/`Badge`/`IconButton` du kit (`shell/src/ui/kit/`) ; `Bell` de `lucide-react`.

- [ ] **Step 1: Exporter `useOpenItem`**

`shell/src/shell/routes.tsx:45` :

```diff
-function useOpenItem() {
+export function useOpenItem() {
```

- [ ] **Step 2: Ajouter les clés i18n**

`shell/src/i18n/catalog.fr.ts`, nouvelle section (après le bloc `account.*`, l.82-87) :

```typescript
  // Notifications (SP-39, chantier 4.19)
  "notifications.bell": "Notifications",
  "notifications.empty": "Aucune notification.",
  "notifications.markAllRead": "Tout marquer comme lu",
  "notifications.preferenceAll": "Tous",
  "notifications.preferenceFailuresOnly": "Échecs seulement",
  "notifications.preferenceNone": "Aucune",
  "notifications.statusSuccess": "Succès",
  "notifications.statusFailure": "Échec",
  "notifications.kindIngestion": "Import",
  "notifications.kindPipeline": "Pipeline",
  "notifications.kindExport": "Export",
  "notifications.kindAppexport": "Export d'app",
  "notifications.kindReport": "Rapport",
  "notifications.deletedItem": "Élément supprimé",
```

- [ ] **Step 3: Écrire les tests (RED)**

```typescript
// shell/src/shell/chrome/NotificationBell.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { test, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { NotificationBell } from "./NotificationBell";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <NotificationBell />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("masque le badge quand le compte non-lu est à zéro", async () => {
  server.use(
    http.get("https://core.test/notifications/unread-count", () => HttpResponse.json({ count: 0 })),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Notifications" });
  expect(screen.queryByText("2")).not.toBeInTheDocument();
});

test("affiche le badge avec le compte non-lu", async () => {
  server.use(
    http.get("https://core.test/notifications/unread-count", () => HttpResponse.json({ count: 3 })),
  );
  render(<Harness />);
  expect(await screen.findByText("3")).toBeInTheDocument();
});

test("ouvre le panneau et affiche les notifications", async () => {
  server.use(
    http.get("https://core.test/notifications/unread-count", () => HttpResponse.json({ count: 1 })),
    http.get("https://core.test/notifications", () =>
      HttpResponse.json({
        notifications: [
          {
            id: "n1",
            kind: "pipeline",
            status: "failure",
            itemId: "item-1",
            itemResourceType: "pipeline",
            itemTitle: "Pipeline nocturne",
            errorMessage: "timeout",
            createdAt: "2026-09-04T10:00:00Z",
            readAt: null,
          },
        ],
        total: 1,
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
  expect(await screen.findByText("Pipeline nocturne")).toBeInTheDocument();
  expect(screen.getByText("timeout")).toBeInTheDocument();
});

test("une notification sans item n'est pas cliquable, une notification avec item ouvre son écran", async () => {
  server.use(
    http.get("https://core.test/notifications/unread-count", () => HttpResponse.json({ count: 1 })),
    http.get("https://core.test/notifications", () =>
      HttpResponse.json({
        notifications: [
          {
            id: "n2",
            kind: "ingestion",
            status: "failure",
            itemId: null,
            itemResourceType: null,
            itemTitle: "Import cassé",
            errorMessage: "fichier invalide",
            createdAt: "2026-09-04T10:00:00Z",
            readAt: null,
          },
        ],
        total: 1,
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
  await screen.findByText("Import cassé");
  expect(screen.queryByRole("button", { name: "Import cassé" })).not.toBeInTheDocument();
});

test("« Tout marquer comme lu » appelle POST /notifications/read-all", async () => {
  let called = false;
  server.use(
    http.get("https://core.test/notifications/unread-count", () => HttpResponse.json({ count: 1 })),
    http.get("https://core.test/notifications", () =>
      HttpResponse.json({ notifications: [], total: 0 }),
    ),
    http.post("https://core.test/notifications/read-all", () => {
      called = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
  await userEvent.click(await screen.findByRole("button", { name: "Tout marquer comme lu" }));
  await waitFor(() => expect(called).toBe(true));
});
```

- [ ] **Step 4: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/chrome/NotificationBell.test.tsx`
Expected: FAIL — `Cannot find module './NotificationBell'`.

- [ ] **Step 5: Implémenter `NotificationBell`**

```typescript
// shell/src/shell/chrome/NotificationBell.tsx
// SPDX-License-Identifier: Apache-2.0
import { Bell } from "lucide-react";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotificationPreference,
  useNotifications,
  useUnreadNotificationCount,
  useUpdateNotificationPreference,
} from "../../api/hooks";
import type { NotificationPreferenceValue, NotificationSummary } from "../../api/types";
import { Badge } from "../../ui/kit/Badge";
import { Popover } from "../../ui/kit/Popover";
import { t } from "../../i18n";
import type { MessageKey } from "../../i18n";
import { useOpenItem } from "../routes";

const KIND_LABEL_KEYS: Record<NotificationSummary["kind"], MessageKey> = {
  ingestion: "notifications.kindIngestion",
  pipeline: "notifications.kindPipeline",
  export: "notifications.kindExport",
  appexport: "notifications.kindAppexport",
  report: "notifications.kindReport",
};

const PREFERENCE_LABEL_KEYS: Record<NotificationPreferenceValue, MessageKey> = {
  all: "notifications.preferenceAll",
  failuresOnly: "notifications.preferenceFailuresOnly",
  none: "notifications.preferenceNone",
};

function NotificationRow({ notification }: { notification: NotificationSummary }) {
  const { onOpenItem } = useOpenItem();
  const markRead = useMarkNotificationRead();

  const content = (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2 text-xs text-ink-2">
        <span>{t(KIND_LABEL_KEYS[notification.kind])}</span>
        <Badge variant={notification.status === "failure" ? "danger" : "ok"}>
          {t(notification.status === "failure" ? "notifications.statusFailure" : "notifications.statusSuccess")}
        </Badge>
      </div>
      <span className="text-sm text-ink">{notification.itemTitle || t("notifications.deletedItem")}</span>
      {notification.errorMessage && (
        <span className="text-xs text-danger">{notification.errorMessage}</span>
      )}
      <span className="text-xs text-ink-2">{new Date(notification.createdAt).toLocaleString()}</span>
    </div>
  );

  if (notification.itemId === null || notification.itemResourceType === null) {
    return <div className="rounded p-2">{content}</div>;
  }

  const itemId = notification.itemId;
  const resourceType = notification.itemResourceType;
  return (
    <button
      className="w-full rounded p-2 text-left hover:bg-sunken"
      onClick={() => {
        if (notification.readAt === null) markRead.mutate(notification.id);
        onOpenItem(itemId, resourceType);
      }}
    >
      {content}
    </button>
  );
}

export function NotificationBell() {
  const unreadQuery = useUnreadNotificationCount();
  const notificationsQuery = useNotifications({ page: 1, pageSize: 20 });
  const preferenceQuery = useNotificationPreference();
  const updatePreference = useUpdateNotificationPreference();
  const markAllRead = useMarkAllNotificationsRead();
  const unreadCount = unreadQuery.data ?? 0;

  return (
    <Popover
      aria-label={t("notifications.bell")}
      trigger={
        <button aria-label={t("notifications.bell")} className="relative rounded-full p-2">
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <Badge variant="danger" className="absolute -right-1 -top-1">
              {unreadCount}
            </Badge>
          )}
        </button>
      }
    >
      <div className="flex w-72 flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <select
            aria-label={t("notifications.bell")}
            className="rounded border border-rule bg-surface px-1 py-0.5 text-xs text-ink"
            value={preferenceQuery.data ?? "all"}
            onChange={(e) =>
              updatePreference.mutate(e.target.value as NotificationPreferenceValue)
            }
          >
            {(["all", "failuresOnly", "none"] as const).map((value) => (
              <option key={value} value={value}>
                {t(PREFERENCE_LABEL_KEYS[value])}
              </option>
            ))}
          </select>
          <button
            className="text-xs text-ink-2 hover:text-ink"
            onClick={() => markAllRead.mutate()}
          >
            {t("notifications.markAllRead")}
          </button>
        </div>
        <div className="flex max-h-80 flex-col gap-1 overflow-y-auto">
          {(notificationsQuery.data?.notifications.length ?? 0) === 0 && (
            <span className="text-sm text-ink-2">{t("notifications.empty")}</span>
          )}
          {notificationsQuery.data?.notifications.map((n) => (
            <NotificationRow key={n.id} notification={n} />
          ))}
        </div>
      </div>
    </Popover>
  );
}
```

- [ ] **Step 6: Câbler dans `TopBar`**

`shell/src/shell/chrome/TopBar.tsx` :

```diff
 import { NewItemButton } from "../NewItemButton";
 import { ImportFileButton } from "../ImportFileButton";
 import { Tileset3DUploadButton } from "../Tileset3DUploadButton";
 import { AccountMenu } from "./AccountMenu";
+import { NotificationBell } from "./NotificationBell";
 
 export function TopBar({ tileset3dEnabled }: { tileset3dEnabled: boolean }) {
   return (
     <header className="flex items-center justify-between border-b border-rule px-6 py-3">
       <span className="text-lg font-bold text-ink">GeoStudio</span>
       <div className="flex items-center gap-3 text-sm">
         <NewItemButton />
         <ImportFileButton />
         {tileset3dEnabled && <Tileset3DUploadButton />}
+        <NotificationBell />
         <AccountMenu />
       </div>
     </header>
   );
 }
```

- [ ] **Step 7: Mettre à jour `TopBar.test.tsx`**

Mocker `NotificationBell` comme les autres boutons de chrome (même patron que `NewItemButton`/`ImportFileButton`, l.20-26), et étendre l'assertion existante :

```diff
 vi.mock("../Tileset3DUploadButton", () => ({
   Tileset3DUploadButton: () => <button>Téléverser un tileset</button>,
 }));
+vi.mock("./NotificationBell", () => ({
+  NotificationBell: () => <button>Notifications</button>,
+}));
```

```diff
 test("affiche la marque, Nouveau, Importer, et le compte", () => {
   renderBar();
   expect(screen.getByText("GeoStudio")).toBeInTheDocument();
   expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
   expect(screen.getByRole("button", { name: "Importer un fichier" })).toBeInTheDocument();
+  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
   expect(screen.getByRole("button", { name: "Compte" })).toBeInTheDocument();
 });
```

- [ ] **Step 8: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/shell/chrome/NotificationBell.test.tsx src/shell/chrome/TopBar.test.tsx
```
Expected: tous PASS.

- [ ] **Step 9: Lancer la suite shell complète (piège n°6)**

```bash
npm run test
```
Expected: 0 échec (aucun autre fichier ne devrait être affecté — `NotificationBell` n'est consommé que par `TopBar`).

- [ ] **Step 10: Commit**

```bash
git add shell/src/shell/chrome/NotificationBell.tsx shell/src/shell/chrome/NotificationBell.test.tsx \
  shell/src/shell/routes.tsx shell/src/shell/chrome/TopBar.tsx shell/src/shell/chrome/TopBar.test.tsx \
  shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): cloche de notifications dans TopBar (SP-39)"
```

---

## Task 12: Vérification finale

**Files:** aucun (vérification uniquement), sauf mise à jour de CLAUDE.md.

- [ ] **Step 1: Migration Postgres réelle, dans les deux sens, sur base non vide (piège n°8)**

Si un conteneur `postgis-test` est disponible (`CORE_TEST_DATABASE_URL` défini) :

```bash
cd core
uv run alembic upgrade head    # doit passer par 0031 sans erreur
uv run alembic downgrade -1    # doit défaire proprement notifications + notification_preferences
uv run alembic upgrade head    # doit repasser sans erreur (idempotence du aller-retour)
```
Expected: les trois commandes réussissent sans erreur. Si `CORE_TEST_DATABASE_URL` n'est pas disponible dans cet environnement, documenter explicitement l'absence de ce contrôle dans l'entrée CLAUDE.md (même discipline que SP-32/SP-38 face à un environnement sans stack complète), ne pas l'affirmer sans preuve.

- [ ] **Step 2: Portes de qualité cœur**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
uv run pytest
```
Expected: tout vert ; couverture ≥ 85 (seuil CLAUDE.md). `app/notifications` n'est pas dans le périmètre `mypy --strict` listé (mêmes 6 modules qu'avant ce plan — ne pas l'y ajouter sans que Tanguy l'ait demandé, hors périmètre de ce chantier).

- [ ] **Step 3: Portes de qualité shell**

```bash
cd shell
npm run lint && npm run format:check
npx tsc --noEmit
rm -rf dist dist-export
npm run test -- --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
Expected: tout vert ; couverture ≥ 88.

- [ ] **Step 4: Suite E2E complète (piège n°6)**

```bash
cd shell && npm run e2e
```
Expected: 0 échec. Vérifier via `test-results/.last-run.json` (`status`/`failedTests`), pas seulement la fin tronquée du reporter `list` sur un run long (piège méthodologique documenté, entrée SP-31 de CLAUDE.md). Aucun nouveau spec E2E n'est ajouté par ce plan (décision spec §5.3) — si une régression croisée apparaît, la corriger comme d'habitude avant de clore.

- [ ] **Step 5: `uvx pre-commit run --all-files`**

```bash
uvx pre-commit run --all-files
```
Expected: les 5 hooks passent.

- [ ] **Step 6: Mettre à jour CLAUDE.md**

Ajouter une entrée `### Livré` datée SP-39 résumant : nouveau domaine `app/notifications`, les 5 sites d'écriture best-effort (avec la garde anti-double-notification export↔report), la cloche `TopBar`, le réglage persisté `all`/`failures_only`/`none`, les chiffres de suite mesurés en Step 2-4 ci-dessus, et tout écart constaté par rapport à ce plan pendant l'exécution (piège n°3/n°4 — consigner, ne pas re-demander). Retirer 4.19 de toute liste de suivi informelle si elle y apparaît (le document de référence `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` n'est pas modifié — même règle que SP-38 §2.7/§3.3).

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôture le chantier 4.19 dans CLAUDE.md — notifications in-app (SP-39)"
```

---

## Self-Review (fait par l'auteur du plan avant remise)

**1. Couverture de la spec** — chaque section de
`docs/superpowers/specs/2026-09-04-sp39-notifications-in-app-design.md` a une tâche :
§3.1 modèle/migration/écriture/API → Tâches 1-3 + 4-8 ; §3.2 shell → Tâches 10-11 ;
§3.3 CLAUDE.md → Tâche 12 ; §4 hors périmètre (pas de flag de capacité, garde
anti-double-notification, chemin capacité désactivée non notifié) → explicitement
respecté et documenté dans les Tâches 3/6/7 ; §5 tests → une tâche de test par
site d'écriture + tâche dédiée dépôt/routes/composant ; §6 critères de sortie →
couverts par les tests de bout en bout (Tâches 4-8, notification écrite même
si le panneau n'est jamais rouvert) et la vérification finale (Tâche 12).

**2. Placeholders** — aucun "TBD"/"TODO" ; chaque étape de code contient
l'implémentation complète, pas une description.

**3. Cohérence des types/signatures** — vérifié : `create_notification` (Tâche 2)
a la même signature partout où il est appelé (Tâches 4-8) ; `NotificationSummary`
(Tâche 10, shell) reflète exactement `NotificationRead` (Tâche 3, cœur) champ
par champ ; `useOpenItem` (Tâche 11) est bien exporté avant d'être importé par
`NotificationBell`.
