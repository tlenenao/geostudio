# SP-8b — Chargement dynamique de modules ES + registre d'extensions : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un widget Web Component écrit et hébergé hors du repo shell (manifeste + module ES servis par une URL) devient disponible dans le builder après activation par un admin — sans redéploiement du shell — et sa désactivation ne casse pas les apps qui l'utilisaient.

**Architecture:** Nouvelle table `app.extensions` côté cœur (admin-only, même famille que `app.collections`), exposée en lecture par `GET /extensions` (accessible anonyme, tenant résolu). Côté shell, `ItemClient.listActiveExtensions()` récupère la liste au bootstrap de chaque page builder/runtime ; chaque manifeste est enregistré dans le registre de widgets existant (`registerWidget`, inchangé) via un `Component` qui importe paresseusement (`import()`, mémoïsé) le module JS au premier montage, délègue ensuite au `WcHost` de SP-8a (composition, réutilisé tel quel), et affiche un placeholder pendant le chargement ou en cas d'échec.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic (cœur), React 19 + TypeScript (shell existant), Vitest + Testing Library, Playwright.

## Global Constraints

- **Ce plan dépend de SP-8a (PR #27, `sp8a-wc-widget-bridge` → `dev`), pas encore mergée.** Le worktree/branche de ce plan doit être créé à partir de `sp8a-wc-widget-bridge`, PAS de `dev` — `dev` ne contient pas encore `shell/src/builder/wc/`. Si SP-8a a été mergée d'ici l'exécution de ce plan, rebaser/recréer le worktree depuis `dev` à la place et vérifier que tous les fichiers `wc/` référencés ci-dessous existent bien.
- Aucune modification de `shell/src/builder/registry.ts`, `WidgetHost.tsx`, `PropsPanel.tsx`, `ActionsPanel.tsx`, `WidgetPalette.tsx` (même contrainte que SP-8a).
- Aucune modification de `shell/src/builder/wc/WcHost.tsx`, `wc/registerWcWidget.ts` — réutilisés tels quels, par composition. `wc/manifest.ts` et `wc/generatedPropsPanel.tsx` sont étendus (rétrocompatible), pas réécrits.
- Pas de sandbox dure, pas de validation de version semver, pas d'UI d'administration shell, pas de validation du scope de permissions côté cœur — hors périmètre (cf. spec).
- Toutes les commandes shell s'exécutent depuis `shell/` (`cd shell` si le répertoire courant diffère) ; toutes les commandes cœur depuis `core/` (`cd core`, `uv run ...`).
- Les 28 specs E2E existantes (20 + 7 ajoutées depuis SP-7 + `wc-widget-bridge.spec.ts`) doivent rester vertes — la Task 10 ajoute une route mockée par défaut à `e2e/mocks.ts` précisément pour ça (cf. Task 10, Step 1).

---

### Task 1: Cœur — modèle `Extension` + migration

**Files:**
- Create: `core/app/extensions/__init__.py`
- Create: `core/app/extensions/models.py`
- Create: `core/alembic/versions/0013_extensions.py`
- Modify: `core/app/db.py` (`core_table_names()`)
- Test: `core/tests/test_extensions_models.py`

**Interfaces:**
- Produces: `Extension` (ORM model, `core/app/extensions/models.py`) — colonnes `id`, `tenant_id` (clé primaire composite), `owner_id`, `tag`, `label`, `module_url`, `props` (JSON), `events` (JSON, nullable), `actions` (JSON, nullable), `default_size` (JSON), `permissions` (JSON), `enabled` (bool), `created_at`.

- [ ] **Step 1: Écrire le test du modèle (échoue — le module n'existe pas encore)**

`core/tests/test_extensions_models.py` :

```python
from app.db import init_db, make_engine, make_session_factory
from app.extensions.models import Extension
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_extension_round_trips_json_columns():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
        ext = Extension(
            id="acme.gauge", tenant_id=tenant.id, owner_id=admin.id,
            tag="gauge-extension-widget", label="Jauge (extension)",
            module_url="https://example.com/gauge.js",
            props=[{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}],
            events=["changed"], actions=["reset"],
            default_size={"w": 2, "h": 2},
            permissions={"collections": "all"},
        )
        s.add(ext)
        s.commit()

    with Session() as s:
        fetched = s.get(Extension, ("acme.gauge", tenant.id))
        assert fetched is not None
        assert fetched.props == [{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}]
        assert fetched.events == ["changed"]
        assert fetched.default_size == {"w": 2, "h": 2}
        assert fetched.permissions == {"collections": "all"}
        assert fetched.enabled is True
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_extensions_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions'`

- [ ] **Step 3: Créer le module et le modèle**

`core/app/extensions/__init__.py` : fichier vide.

`core/app/extensions/models.py` :

```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Extension(Base):
    __tablename__ = "extensions"

    # Clé primaire composite (id, tenant_id) : id = type du widget côté shell
    # (ex. "acme.gauge"), PAS unique seul — deux tenants peuvent enregistrer
    # le même type. Pas de surrogate séparé (contrairement à
    # Collection.id/table_name) : il n'y a ici aucune ressource physique
    # sous-jacente à découpler du nom d'enregistrement.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    module_url: Mapped[str] = mapped_column(String, nullable=False)
    props: Mapped[list] = mapped_column(JSON, nullable=False)
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    default_size: Mapped[dict] = mapped_column(JSON, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 4: Enregistrer le module auprès de `core_table_names()`**

`core/app/db.py` — dans `core_table_names()`, ajouter l'import (ordre alphabétique, entre `configs` et `ingestion`) :

```python
    from app.configs import models  # noqa: F401
    from app.extensions import models as extensions_models  # noqa: F401
    from app.ingestion import models as ingestion_models  # noqa: F401
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_extensions_models.py -v`
Expected: PASS (1 test) — `init_db` sur SQLite crée la table `extensions` via `Base.metadata.create_all()` maintenant que le modèle est importé par `core_table_names()`.

- [ ] **Step 6: Écrire la migration Alembic (schéma réel Postgres)**

`core/alembic/versions/0013_extensions.py` :

```python
"""app.extensions — registre d'extensions (SP-8b)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extensions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("module_url", sa.String(), nullable=False),
        sa.Column("props", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.Column("actions", sa.JSON(), nullable=True),
        sa.Column("default_size", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("extensions")
```

- [ ] **Step 7: Commit**

```bash
cd core
git add app/extensions/__init__.py app/extensions/models.py app/db.py \
        alembic/versions/0013_extensions.py tests/test_extensions_models.py
git commit -m "feat(core): modèle Extension + migration 0013 (SP-8b)"
```

---

### Task 2: Cœur — repository + schémas Pydantic

**Files:**
- Create: `core/app/extensions/repository.py`
- Create: `core/app/extensions/schemas.py`
- Test: `core/tests/test_extensions_repository.py`

**Interfaces:**
- Consumes: `Extension` (Task 1, `app.extensions.models`).
- Produces: `get_extension(session, *, tenant_id, extension_id) -> Extension | None`,
  `create_extension(session, *, tenant_id, owner_id, id, tag, label, module_url, props, events, actions, default_size, permissions) -> Extension`,
  `update_extension(session, ext, **fields) -> Extension`,
  `list_active_extensions(session, *, tenant_id) -> list[Extension]`
  (toutes dans `app.extensions.repository`, utilisées par Task 3).
  `ExtensionCreate`, `ExtensionPatch` (Pydantic, `app.extensions.schemas`, utilisées par Task 3).

- [ ] **Step 1: Écrire le test du repository (échoue — le module n'existe pas encore)**

`core/tests/test_extensions_repository.py` :

```python
from app.db import init_db, make_engine, make_session_factory
from app.extensions import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    return Session, tenant.id, admin.id


def test_create_get_and_list_active():
    Session, tenant_id, owner_id = _env()
    with Session() as s:
        repo.create_extension(
            s, tenant_id=tenant_id, owner_id=owner_id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge (extension)",
            module_url="https://example.com/gauge.js",
            props=[], events=["changed"], actions=["reset"],
            default_size={"w": 2, "h": 2}, permissions={"collections": "all"},
        )
        s.commit()

    with Session() as s:
        ext = repo.get_extension(s, tenant_id=tenant_id, extension_id="acme.gauge")
        assert ext is not None and ext.label == "Jauge (extension)"
        assert [e.id for e in repo.list_active_extensions(s, tenant_id=tenant_id)] == ["acme.gauge"]


def test_list_active_excludes_disabled():
    Session, tenant_id, owner_id = _env()
    with Session() as s:
        ext = repo.create_extension(
            s, tenant_id=tenant_id, owner_id=owner_id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge", module_url="https://x/gauge.js",
            props=[], events=None, actions=None,
            default_size={"w": 2, "h": 2}, permissions={"collections": "all"},
        )
        repo.update_extension(s, ext, enabled=False)
        s.commit()

    with Session() as s:
        assert repo.list_active_extensions(s, tenant_id=tenant_id) == []
        # toujours récupérable par id, seule la liste "actives" l'exclut
        assert repo.get_extension(s, tenant_id=tenant_id, extension_id="acme.gauge") is not None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_extensions_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.repository'`

- [ ] **Step 3: Implémenter le repository**

`core/app/extensions/repository.py` :

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.models import Extension


def get_extension(session: Session, *, tenant_id: str, extension_id: str) -> Extension | None:
    return session.scalar(select(Extension).where(
        Extension.tenant_id == tenant_id, Extension.id == extension_id))


def create_extension(
    session: Session, *, tenant_id: str, owner_id: str, id: str, tag: str, label: str,
    module_url: str, props: list, events: list[str] | None, actions: list[str] | None,
    default_size: dict, permissions: dict,
) -> Extension:
    ext = Extension(
        id=id, tenant_id=tenant_id, owner_id=owner_id, tag=tag, label=label,
        module_url=module_url, props=props, events=events, actions=actions,
        default_size=default_size, permissions=permissions,
    )
    session.add(ext)
    session.flush()
    return ext


def update_extension(session: Session, ext: Extension, **fields) -> Extension:
    for key, value in fields.items():
        setattr(ext, key, value)
    session.flush()
    return ext


def list_active_extensions(session: Session, *, tenant_id: str) -> list[Extension]:
    stmt = select(Extension).where(Extension.tenant_id == tenant_id, Extension.enabled.is_(True))
    return list(session.scalars(stmt.order_by(Extension.label)).all())
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_extensions_repository.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Écrire les schémas Pydantic (pas de test dédié — validés via Task 3)**

`core/app/extensions/schemas.py` :

```python
from typing import Literal

from pydantic import BaseModel, Field


class ExtensionProp(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "dataSource"]
    label: str
    default: object = None


class ExtensionPermissions(BaseModel):
    collections: list[str] | Literal["all"] = "all"


class ExtensionSize(BaseModel):
    w: int
    h: int


class ExtensionCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    tag: str = Field(min_length=1)
    label: str = Field(min_length=1)
    moduleUrl: str = Field(min_length=1)
    props: list[ExtensionProp] = []
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize
    permissions: ExtensionPermissions = ExtensionPermissions()


class ExtensionPatch(BaseModel):
    tag: str | None = None
    label: str | None = None
    moduleUrl: str | None = None
    props: list[ExtensionProp] | None = None
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize | None = None
    permissions: ExtensionPermissions | None = None
    enabled: bool | None = None
```

- [ ] **Step 6: Commit**

```bash
cd core
git add app/extensions/repository.py app/extensions/schemas.py tests/test_extensions_repository.py
git commit -m "feat(core): repository + schémas Pydantic pour app.extensions (SP-8b)"
```

---

### Task 3: Cœur — routes `POST`/`PATCH`/`GET /extensions` + audit

**Files:**
- Create: `core/app/extensions/routes.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_extensions_routes.py`

**Interfaces:**
- Consumes: `repo.*` (Task 2), `ExtensionCreate`/`ExtensionPatch` (Task 2, `app.extensions.schemas`), `get_current_user`/`get_current_user_optional` (`app.auth.dependency`), `write_audit` (`app.audit.writer`), `get_or_create_default_tenant` (`app.tenants.repository`).
- Produces: `router` (`APIRouter`, `app.extensions.routes`) — `POST /extensions`, `PATCH /extensions/{id}`, `GET /extensions`. Monté dans `create_app()` (Task de wiring ci-dessous).

- [ ] **Step 1: Écrire le test des routes (échoue — le module n'existe pas encore)**

`core/tests/test_extensions_routes.py` :

```python
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

GAUGE_BODY = {
    "id": "acme.gauge", "tag": "gauge-extension-widget", "label": "Jauge (extension)",
    "moduleUrl": "https://example.com/gauge.js",
    "props": [{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}],
    "events": ["changed"], "actions": ["reset"],
    "defaultSize": {"w": 2, "h": 2},
    "permissions": {"collections": "all"},
}


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
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_register_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/extensions", json=GAUGE_BODY).status_code == 403


def test_register_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/extensions", json=GAUGE_BODY)
    assert r.status_code == 201
    assert r.json()["id"] == "acme.gauge"
    listed = client.get("/extensions").json()["extensions"]
    assert [e["id"] for e in listed] == ["acme.gauge"]


def test_register_duplicate_same_tenant_is_409(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    assert client.post("/extensions", json=GAUGE_BODY).status_code == 409


def test_patch_requires_admin_and_toggles_enabled(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    _as(app, regular)
    assert client.patch("/extensions/acme.gauge", json={"enabled": False}).status_code == 403
    _as(app, admin)
    assert client.patch("/extensions/acme.gauge", json={"enabled": False}).status_code == 200
    assert client.get("/extensions").json()["extensions"] == []


def test_get_extensions_is_anonymous_and_scoped_to_default_tenant(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    del app.dependency_overrides[get_current_user_optional]
    listed = client.get("/extensions").json()["extensions"]
    assert [e["id"] for e in listed] == ["acme.gauge"]


def test_get_extensions_never_leaks_across_tenants(env):
    app, client, Session, admin, _regular = env
    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="oa", username="other-admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    _as(app, other_admin)
    assert client.get("/extensions").json()["extensions"] == []


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "extension.create" in actions
    assert "extension.update" in actions
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_extensions_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.routes'`

- [ ] **Step 3: Implémenter les routes**

`core/app/extensions/routes.py` :

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import get_session
from app.extensions import repository as repo
from app.extensions.schemas import ExtensionCreate, ExtensionPatch
from app.tenants.repository import get_or_create_default_tenant

router = APIRouter()


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _extension_json(ext) -> dict:
    return {
        "id": ext.id, "tag": ext.tag, "label": ext.label, "moduleUrl": ext.module_url,
        "props": ext.props, "events": ext.events, "actions": ext.actions,
        "defaultSize": ext.default_size, "permissions": ext.permissions,
        "enabled": ext.enabled,
    }


@router.post("/extensions", status_code=201)
def register_extension(
    body: ExtensionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    if repo.get_extension(session, tenant_id=user.tenant_id, extension_id=body.id):
        raise HTTPException(status_code=409, detail="extension already registered")
    ext = repo.create_extension(
        session, tenant_id=user.tenant_id, owner_id=user.id, id=body.id,
        tag=body.tag, label=body.label, module_url=body.moduleUrl,
        props=[p.model_dump() for p in body.props], events=body.events, actions=body.actions,
        default_size=body.defaultSize.model_dump(), permissions=body.permissions.model_dump(),
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="extension.create", object_type="extension", object_id=ext.id,
                payload={"moduleUrl": ext.module_url})
    return _extension_json(ext)


@router.patch("/extensions/{extension_id}")
def patch_extension(
    extension_id: str, body: ExtensionPatch,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    ext = repo.get_extension(session, tenant_id=user.tenant_id, extension_id=extension_id)
    if not ext:
        raise HTTPException(status_code=404, detail="extension not found")
    fields = body.model_dump(exclude_unset=True)
    if "defaultSize" in fields:
        fields["default_size"] = fields.pop("defaultSize")
    if "moduleUrl" in fields:
        fields["module_url"] = fields.pop("moduleUrl")
    repo.update_extension(session, ext, **fields)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="extension.update", object_type="extension", object_id=ext.id,
                payload={"fields": list(fields)})
    return _extension_json(ext)


@router.get("/extensions")
def list_extensions(
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    exts = repo.list_active_extensions(session, tenant_id=tenant_id)
    return {"extensions": [_extension_json(e) for e in exts]}
```

- [ ] **Step 4: Monter le router dans `create_app()`**

`core/app/main.py` — ajouter l'import (ordre alphabétique, entre `db` et `features`) :

```python
from app.extensions import routes as extensions_routes
```

et l'inclusion (après `configs_routes.router`, n'importe quelle position suffit — cohérent avec l'ordre existant) :

```python
    app.include_router(configs_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(items_routes.router)
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_extensions_routes.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Lancer toute la suite pytest pour vérifier l'absence de régression**

Run: `cd core && uv run pytest`
Expected: PASS — tous les tests existants + les nouveaux passent.

- [ ] **Step 7: Commit**

```bash
cd core
git add app/extensions/routes.py app/main.py tests/test_extensions_routes.py
git commit -m "feat(core): routes POST/PATCH/GET /extensions, admin-gated, auditées (SP-8b)"
```

---

### Task 4: Shell — prop `dataSource` + permissions dans le manifeste WC

**Files:**
- Modify: `shell/src/builder/wc/manifest.ts`
- Modify: `shell/src/builder/wc/generatedPropsPanel.tsx`
- Modify: `shell/src/builder/wc/generatedPropsPanel.test.tsx`

**Interfaces:**
- Consumes: `DataSource` (`shell/src/api/types.ts`), `DataSourceSelect` (`shell/src/builder/DataSourceSelect.tsx`, signature `{ value: string; dataSources: DataSource[]; onChange: (id: string) => void }`).
- Produces: `WcWidgetManifest` gagne `props[].type: "dataSource"` et `permissions?: { collections: string[] | "all" }` (rétrocompatible — tout manifeste SP-8a existant, sans `permissions`, continue de fonctionner à l'identique). `makeGeneratedPropsPanel` accepte désormais `dataSources` et filtre selon `permissions`.

- [ ] **Step 1: Étendre le type `WcWidgetManifest`**

`shell/src/builder/wc/manifest.ts` — remplacer le fichier entier :

```ts
export type WcWidgetManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean" | "dataSource";
    label: string;
    default: unknown;
  }>;
  events?: readonly string[];
  actions?: readonly string[];
  defaultSize: { w: number; h: number };
  permissions?: { collections: string[] | "all" };
};
```

- [ ] **Step 2: Ajouter les tests du prop `dataSource` (échouent — pas encore géré)**

Ajouter à `shell/src/builder/wc/generatedPropsPanel.test.tsx`, après les imports existants :

```tsx
import type { DataSource } from "../../api/types";
```

Ajouter après les tests existants :

```tsx
const DS: DataSource[] = [
  { id: "ds-a", type: "features", service: "core", layer: "incidents", query: {} },
  { id: "ds-b", type: "features", service: "core", layer: "villes", query: {} },
];

const manifestWithDataSource: WcWidgetManifest = {
  type: "test.panel-ds",
  tag: "test-panel-ds-widget",
  label: "Test panneau DS",
  props: [{ name: "source", type: "dataSource", label: "Source de données", default: "" }],
  permissions: { collections: ["incidents"] },
  defaultSize: { w: 2, h: 2 },
};

test("a dataSource prop renders a DataSourceSelect filtered by permissions.collections", () => {
  const Panel = makeGeneratedPropsPanel(manifestWithDataSource);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />);
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  const optionLabels = Array.from(select.options).map((o) => o.textContent);
  expect(optionLabels).toEqual(["Aucune", "incidents"]);
});

test("permissions.collections: \"all\" proposes every data source", () => {
  const manifest: WcWidgetManifest = { ...manifestWithDataSource, permissions: { collections: "all" } };
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />);
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Aucune", "incidents", "villes"]);
});

test("no permissions declared proposes every data source (backward compatible)", () => {
  const manifest: WcWidgetManifest = { ...manifestWithDataSource, permissions: undefined };
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />);
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Aucune", "incidents", "villes"]);
});

test("selecting a data source calls onChange with its id", async () => {
  const Panel = makeGeneratedPropsPanel(manifestWithDataSource);
  const onChange = vi.fn();
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds-a");
  expect(onChange).toHaveBeenCalledWith({ source: "ds-a" });
});
```

- [ ] **Step 3: Lancer les tests pour vérifier qu'ils échouent**

Run: `npm test -- generatedPropsPanel --run`
Expected: FAIL — les 4 nouveaux tests échouent (`getByLabelText("Source de données")` introuvable, le prop `dataSource` tombe actuellement dans la branche texte), les 3 tests existants continuent de passer.

- [ ] **Step 4: Étendre `generatedPropsPanel.tsx`**

`shell/src/builder/wc/generatedPropsPanel.tsx` — remplacer le fichier entier :

```tsx
import type { DataSource } from "../../api/types";
import { DataSourceSelect } from "../DataSourceSelect";
import type { WcWidgetManifest } from "./manifest";

function permittedDataSources(dataSources: DataSource[], manifest: WcWidgetManifest): DataSource[] {
  const perm = manifest.permissions;
  if (!perm || perm.collections === "all") return dataSources;
  const allowed = new Set(perm.collections);
  return dataSources.filter((ds) => allowed.has(ds.layer));
}

export function makeGeneratedPropsPanel(manifest: WcWidgetManifest) {
  return function GeneratedPropsPanel({
    props,
    dataSources = [],
    onChange,
  }: {
    props: Record<string, unknown>;
    dataSources?: DataSource[];
    onChange: (props: Record<string, unknown>) => void;
  }) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        {manifest.props.map((p) =>
          p.type === "dataSource" ? (
            <DataSourceSelect
              key={p.name}
              value={String(props[p.name] ?? "")}
              dataSources={permittedDataSources(dataSources, manifest)}
              onChange={(id) => onChange({ ...props, [p.name]: id })}
            />
          ) : (
            <label key={p.name} className="flex flex-col gap-1">
              {p.label}
              {p.type === "boolean" ? (
                <input
                  type="checkbox"
                  aria-label={p.label}
                  checked={Boolean(props[p.name])}
                  onChange={(e) => onChange({ ...props, [p.name]: e.target.checked })}
                />
              ) : (
                <input
                  type={p.type === "number" ? "number" : "text"}
                  aria-label={p.label}
                  className="h-9 rounded-md border border-slate-300 px-2"
                  value={String(props[p.name] ?? "")}
                  onChange={(e) =>
                    onChange({
                      ...props,
                      [p.name]: p.type === "number" ? Number(e.target.value) : e.target.value,
                    })
                  }
                />
              )}
            </label>
          ),
        )}
      </div>
    );
  };
}
```

Note : `dataSources` gagne une valeur par défaut `[]` — les tests de Task 1 de SP-8a (qui ne le passent pas) continuent de fonctionner sans modification.

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `npm test -- generatedPropsPanel --run`
Expected: PASS (7 tests — 3 de SP-8a + 4 nouveaux)

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/wc/manifest.ts shell/src/builder/wc/generatedPropsPanel.tsx \
        shell/src/builder/wc/generatedPropsPanel.test.tsx
git commit -m "feat(shell): prop dataSource + permissions dans le manifeste WC (SP-8b)"
```

---

### Task 5: Shell — `ExtensionManifest`, `ItemClient.listActiveExtensions`, hook

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `ExtensionManifest` (type, `shell/src/api/types.ts`) — `{ type, tag, label, props, events?, actions?, defaultSize, permissions?, moduleUrl }`. `ItemClient.listActiveExtensions(): Promise<ExtensionManifest[]>`. `useActiveExtensions()` (hook, `shell/src/api/hooks.ts`, react-query, `queryKey: ["extensions"]`) — utilisé par Task 9.

- [ ] **Step 1: Écrire le test de `listActiveExtensions` (échoue — la méthode n'existe pas encore)**

`shell/src/api/itemClient.test.ts` utilise MSW (`http`/`HttpResponse` de `msw`, serveur partagé `../test/msw/server`), pas un mock de `fetch` — suivre exactement le patron du test `listLayerSources aggregates Martin vector sources and core collections` déjà présent dans ce fichier (`makeClient(token)` y est déjà défini en tête de fichier via `createItemClient({ coreUrl: "https://core.test", martinUrl: "https://martin.test", getToken: () => token })`). Ajouter :

```ts
test("listActiveExtensions maps the core's /extensions response to ExtensionManifest[]", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
            events: ["changed"], actions: ["reset"],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
          },
        ],
      });
    }),
  );
  const result = await makeClient("abc").listActiveExtensions();
  expect(auth).toBe("Bearer abc");
  expect(result).toEqual([
    {
      type: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js",
      props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
      events: ["changed"], actions: ["reset"],
      defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
    },
  ]);
});
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- itemClient --run`
Expected: FAIL — `client.listActiveExtensions is not a function`

- [ ] **Step 3: Ajouter `ExtensionManifest` à `types.ts`**

`shell/src/api/types.ts` — ajouter après le type `DataSource` (ne pas dériver de `WcWidgetManifest` : `api/` ne dépend jamais de `builder/`, cf. `registry.ts` qui importe déjà `DataSource` depuis `api/types.ts` et jamais l'inverse — cette duplication de forme est un écho documenté, même arbitrage que `fieldsFromSchema`/mapping Python de SP-7) :

```ts
// Écho documenté de WcWidgetManifest (shell/src/builder/wc/manifest.ts) — même
// forme, dupliquée ici plutôt qu'importée : api/ ne dépend jamais de builder/.
// Si WcWidgetManifest change de forme, répercuter le changement ici aussi.
export type ExtensionManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean" | "dataSource";
    label: string;
    default: unknown;
  }>;
  events?: string[];
  actions?: string[];
  defaultSize: { w: number; h: number };
  permissions?: { collections: string[] | "all" };
  moduleUrl: string;
};
```

et à l'interface `ItemClient`, après `listLayerSources` :

```ts
  listActiveExtensions(): Promise<ExtensionManifest[]>;
```

- [ ] **Step 4: Implémenter dans `itemClient.ts`**

`shell/src/api/itemClient.ts` — toutes les méthodes de l'objet `ItemClient` retourné (`return { ... }`, à partir de la ligne `return {`) sont écrites en méthode inline (`async nomDeMethode() { ... }`), pas comme une référence vers une fonction séparée — `fetchCoreCollections`/`fetchMartinSources` ne font exception que parce que `listLayerSources` doit composer plusieurs sources ; `listActiveExtensions` n'a besoin d'aucune composition, donc pas de fonction séparée.

D'abord, ajouter `ExtensionManifest` à l'import de types en tête du fichier — remplacer la ligne 1 :

```ts
import type { ActionMessage, AppConfig, CollectionSchema, CreateKind, DataRecord, DataSource, ExtensionManifest, FieldError, GeoJSONFeatureInput, Group, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, Page, ResourceType, Sharing, Theme, UpdatePatch, Variable } from "./types";
```

Puis repérer la méthode `async listLayerSources(params?: { q?: string }): Promise<LayerSource[]> { ... }` dans l'objet retourné et ajouter juste après sa fermeture (`},`) :

```ts
    async listActiveExtensions(): Promise<ExtensionManifest[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string; tag: string; label: string; moduleUrl: string;
          props: ExtensionManifest["props"]; events?: string[]; actions?: string[];
          defaultSize: { w: number; h: number }; permissions?: { collections: string[] | "all" };
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id, tag: e.tag, label: e.label, moduleUrl: e.moduleUrl,
        props: e.props, events: e.events, actions: e.actions,
        defaultSize: e.defaultSize, permissions: e.permissions,
      }));
    },
```

`getToken` et `coreUrl` sont déjà dans la portée de la fonction fabrique (utilisés par `fetchCoreCollections` un peu plus haut dans le même fichier) — aucun import supplémentaire nécessaire pour ces deux-là.

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- itemClient --run`
Expected: PASS

- [ ] **Step 6: Ajouter le hook `useActiveExtensions`**

`shell/src/api/hooks.ts` — ajouter, dans le même style que `useItems`/`useMe` :

```ts
export function useActiveExtensions() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["extensions"],
    // Optionnel : un ItemClient de test qui n'implémente pas encore la
    // méthode (mocks existants de AppBuilderPage.test.tsx/AppRuntimePage.test.tsx,
    // Partial<ItemClient>) résout silencieusement à [] plutôt que de faire
    // planter la query — CoreItemClient réel l'implémente toujours.
    queryFn: () => client.listActiveExtensions?.() ?? Promise.resolve([]),
  });
}
```

Pas de test dédié pour ce hook seul (couvert indirectement par Task 9) — cohérent avec `useItems`/`useMe` qui n'ont pas non plus de test unitaire isolé dans ce fichier.

- [ ] **Step 7: Lancer toute la suite vitest pour vérifier l'absence de régression**

Run: `npm test -- --run`
Expected: PASS — tous les tests existants + les nouveaux passent, aucune suppression.

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.ts
git commit -m "feat(shell): ExtensionManifest + ItemClient.listActiveExtensions + useActiveExtensions (SP-8b)"
```

---

### Task 6: Shell — `moduleCache` (import paresseux mémoïsé)

**Files:**
- Create: `shell/src/builder/extensions/moduleCache.ts`
- Test: `shell/src/builder/extensions/moduleCache.test.ts`

**Interfaces:**
- Produces: `ensureModuleLoaded(url: string, importFn?: (url: string) => Promise<unknown>): Promise<unknown>`,
  `_resetModuleCache(): void` (test uniquement, même patron que `_resetRegistry` de `registry.ts`) — utilisées par Task 7.

- [ ] **Step 1: Écrire le test (échoue — le fichier n'existe pas encore)**

`shell/src/builder/extensions/moduleCache.test.ts` :

```ts
import { beforeEach, expect, test, vi } from "vitest";
import { _resetModuleCache, ensureModuleLoaded } from "./moduleCache";

beforeEach(() => _resetModuleCache());

test("calls the importer once and returns the same promise for two calls with the same URL", async () => {
  const importFn = vi.fn().mockResolvedValue({ ok: true });
  const p1 = ensureModuleLoaded("https://example.com/a.js", importFn);
  const p2 = ensureModuleLoaded("https://example.com/a.js", importFn);
  expect(p1).toBe(p2);
  await p1;
  expect(importFn).toHaveBeenCalledTimes(1);
});

test("does not share the cache across different URLs", async () => {
  const importFn = vi.fn().mockResolvedValue({ ok: true });
  await ensureModuleLoaded("https://example.com/a.js", importFn);
  await ensureModuleLoaded("https://example.com/b.js", importFn);
  expect(importFn).toHaveBeenCalledTimes(2);
});

test("caches a rejected import too — a second call does not retry", async () => {
  const importFn = vi.fn().mockRejectedValue(new Error("network down"));
  await expect(ensureModuleLoaded("https://example.com/broken.js", importFn)).rejects.toThrow("network down");
  await expect(ensureModuleLoaded("https://example.com/broken.js", importFn)).rejects.toThrow("network down");
  expect(importFn).toHaveBeenCalledTimes(1);
});

test("defaults to a real dynamic import() when no importer is passed", async () => {
  await expect(ensureModuleLoaded("./__fixtures__/does-not-exist.ts")).rejects.toThrow();
});
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- moduleCache --run`
Expected: FAIL — `Cannot find module './moduleCache'`

- [ ] **Step 3: Implémenter**

`shell/src/builder/extensions/moduleCache.ts` :

```ts
const cache = new Map<string, Promise<unknown>>();

function defaultImport(url: string): Promise<unknown> {
  return import(/* @vite-ignore */ url);
}

export function ensureModuleLoaded(
  url: string,
  importFn: (url: string) => Promise<unknown> = defaultImport,
): Promise<unknown> {
  let p = cache.get(url);
  if (!p) {
    p = importFn(url);
    cache.set(url, p);
  }
  return p;
}

export function _resetModuleCache(): void {
  cache.clear();
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- moduleCache --run`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/extensions/moduleCache.ts shell/src/builder/extensions/moduleCache.test.ts
git commit -m "feat(shell): ensureModuleLoaded — import() paresseux mémoïsé par URL (SP-8b)"
```

---

### Task 7: Shell — `LazyWcHost` (placeholder pendant/après l'import)

**Files:**
- Create: `shell/src/builder/extensions/LazyWcHost.tsx`
- Create: `shell/src/builder/extensions/__fixtures__/dummyLazyWidget.ts`
- Test: `shell/src/builder/extensions/LazyWcHost.test.tsx`

**Interfaces:**
- Consumes: `makeWcHost` (`shell/src/builder/wc/WcHost.tsx`, SP-8a, inchangé), `ensureModuleLoaded` (Task 6), `ExtensionManifest` (Task 5, `shell/src/api/types.ts`), `WidgetContext` (`shell/src/builder/registry.ts`).
- Produces: `makeLazyWcHost(manifest: ExtensionManifest): (p: { props: Record<string, unknown>; ctx: WidgetContext }) => ReactNode` — compatible avec la signature `Component` de `WidgetDefinition`, utilisé par Task 8.

- [ ] **Step 1: Créer la fixture de module (self-registering custom element)**

`shell/src/builder/extensions/__fixtures__/dummyLazyWidget.ts` :

```ts
class DummyLazyWidget extends HTMLElement {}
if (!customElements.get("test-lazy-ready-widget")) {
  customElements.define("test-lazy-ready-widget", DummyLazyWidget);
}
```

- [ ] **Step 2: Écrire le test (échoue — le fichier n'existe pas encore)**

`shell/src/builder/extensions/LazyWcHost.test.tsx` :

```tsx
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";
import { makeLazyWcHost } from "./LazyWcHost";
import { _resetModuleCache } from "./moduleCache";
import type { ExtensionManifest } from "../../api/types";
import type { WidgetContext } from "../registry";

afterEach(cleanup);
beforeEach(() => _resetModuleCache());

const readyManifest: ExtensionManifest = {
  type: "test.lazy-ready", tag: "test-lazy-ready-widget", label: "Test prêt",
  props: [], defaultSize: { w: 2, h: 2 },
  moduleUrl: "./__fixtures__/dummyLazyWidget.ts",
};

const errorManifest: ExtensionManifest = {
  type: "test.lazy-error", tag: "test-lazy-error-widget", label: "Test en échec",
  props: [], defaultSize: { w: 2, h: 2 },
  moduleUrl: "./__fixtures__/does-not-exist.ts",
};

test("shows a loading placeholder, then delegates to WcHost once the module resolves", async () => {
  const LazyWcHost = makeLazyWcHost(readyManifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container } = render(<LazyWcHost props={{}} ctx={ctx} />);
  expect(screen.getByText("Chargement…")).toBeInTheDocument();
  await waitFor(() => expect(container.querySelector("test-lazy-ready-widget")).not.toBeNull());
});

test("shows an error placeholder when the module import rejects", async () => {
  const LazyWcHost = makeLazyWcHost(errorManifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  render(<LazyWcHost props={{}} ctx={ctx} />);
  expect(await screen.findByText("Extension indisponible")).toBeInTheDocument();
});
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- LazyWcHost --run`
Expected: FAIL — `Cannot find module './LazyWcHost'`

- [ ] **Step 4: Implémenter**

`shell/src/builder/extensions/LazyWcHost.tsx` :

```tsx
import { useEffect, useState } from "react";
import type { ExtensionManifest } from "../../api/types";
import { makeWcHost } from "../wc/WcHost";
import type { WidgetContext } from "../registry";
import { ensureModuleLoaded } from "./moduleCache";

function Placeholder({ text, tone }: { text: string; tone: "loading" | "error" }) {
  return (
    <div
      className={
        tone === "error"
          ? "flex h-full items-center justify-center bg-slate-100 text-xs text-red-600"
          : "flex h-full items-center justify-center bg-slate-50 text-xs text-slate-400"
      }
    >
      {text}
    </div>
  );
}

export function makeLazyWcHost(manifest: ExtensionManifest) {
  const WcHost = makeWcHost(manifest);

  return function LazyWcHost(p: { props: Record<string, unknown>; ctx: WidgetContext }) {
    const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

    useEffect(() => {
      let cancelled = false;
      ensureModuleLoaded(manifest.moduleUrl)
        .then(() => { if (!cancelled) setStatus("ready"); })
        .catch(() => { if (!cancelled) setStatus("error"); });
      return () => { cancelled = true; };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    if (status === "loading") return <Placeholder text="Chargement…" tone="loading" />;
    if (status === "error") return <Placeholder text="Extension indisponible" tone="error" />;
    return <WcHost {...p} />;
  };
}
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- LazyWcHost --run`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/extensions/LazyWcHost.tsx \
        shell/src/builder/extensions/__fixtures__/dummyLazyWidget.ts \
        shell/src/builder/extensions/LazyWcHost.test.tsx
git commit -m "feat(shell): LazyWcHost — placeholder pendant/en échec de l'import, délègue à WcHost (SP-8b)"
```

---

### Task 8: Shell — `registerExtensionWidget` (adaptateur registre)

**Files:**
- Create: `shell/src/builder/extensions/registerExtensionWidget.ts`
- Test: `shell/src/builder/extensions/registerExtensionWidget.test.tsx`

**Interfaces:**
- Consumes: `registerWidget`/`getWidget`/`_resetRegistry` (`shell/src/builder/registry.ts`), `makeGeneratedPropsPanel` (`shell/src/builder/wc/generatedPropsPanel.ts`, Task 4), `makeLazyWcHost` (Task 7), `ExtensionManifest` (Task 5).
- Produces: `registerExtensionWidget(manifest: ExtensionManifest): void` — point d'entrée public du module `extensions/`, utilisé par Task 9.

- [ ] **Step 1: Écrire le test (échoue — le fichier n'existe pas encore)**

`shell/src/builder/extensions/registerExtensionWidget.test.tsx` :

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { registerExtensionWidget } from "./registerExtensionWidget";
import { _resetModuleCache } from "./moduleCache";
import type { ExtensionManifest } from "../../api/types";

const manifest: ExtensionManifest = {
  type: "acme.gauge", tag: "test-lazy-ready-widget", label: "Jauge (extension)",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 7 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 3, h: 2 },
  moduleUrl: "./__fixtures__/dummyLazyWidget.ts",
};

beforeEach(() => {
  _resetRegistry();
  _resetModuleCache();
});

test("registers a WidgetDefinition with the manifest's identity and defaults", () => {
  registerExtensionWidget(manifest);
  const def = getWidget("acme.gauge")!;
  expect(def.label).toBe("Jauge (extension)");
  expect(def.defaultProps).toEqual({ initial: 7 });
  expect(def.defaultSize).toEqual({ w: 3, h: 2 });
  expect(def.events).toEqual(["changed"]);
  expect(def.actions).toEqual(["reset"]);
});

test("the generated props panel edits props through onChange", async () => {
  registerExtensionWidget(manifest);
  const Panel = getWidget("acme.gauge")!.PropsPanel;
  const onChange = vi.fn();
  render(<Panel props={{ initial: 7 }} dataSources={[]} onChange={onChange} />);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "9");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 9 });
});

test("the generated Component lazily mounts the custom element", async () => {
  registerExtensionWidget(manifest);
  const Component = getWidget("acme.gauge")!.Component;
  const { container } = render(
    <Component props={{ initial: 9 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  await waitFor(() => expect(container.querySelector("test-lazy-ready-widget")).not.toBeNull());
});
```

Le deuxième test édite un champ `number` — cf. le piège de valeur contrôlée documenté dans SP-8a (`generatedPropsPanel.test.tsx`) : si ce test échoue de façon inattendue avec une valeur concaténée (ex. `79` au lieu de `9`), envelopper le rendu dans un composant avec `useState` qui fait suivre `onChange` vers `props`, comme dans `shell/src/builder/wc/generatedPropsPanel.test.tsx`.

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- registerExtensionWidget --run`
Expected: FAIL — `Cannot find module './registerExtensionWidget'`

- [ ] **Step 3: Implémenter**

`shell/src/builder/extensions/registerExtensionWidget.ts` :

```ts
import { registerWidget } from "../registry";
import { makeGeneratedPropsPanel } from "../wc/generatedPropsPanel";
import { makeLazyWcHost } from "./LazyWcHost";
import type { ExtensionManifest } from "../../api/types";

export function registerExtensionWidget(manifest: ExtensionManifest): void {
  registerWidget({
    type: manifest.type,
    label: manifest.label,
    defaultProps: Object.fromEntries(manifest.props.map((p) => [p.name, p.default])),
    defaultSize: manifest.defaultSize,
    events: manifest.events,
    actions: manifest.actions,
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeLazyWcHost(manifest),
  });
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- registerExtensionWidget --run`
Expected: PASS (3 tests)

- [ ] **Step 5: Lancer tout vitest + le build pour vérifier l'absence de régression**

Run: `npm test -- --run && npm run build`
Expected: PASS / succès sans erreur de type.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/extensions/registerExtensionWidget.ts \
        shell/src/builder/extensions/registerExtensionWidget.test.tsx
git commit -m "feat(shell): registerExtensionWidget — adaptateur registre pour un manifeste d'extension (SP-8b)"
```

---

### Task 9: Shell — bootstrap dans `AppBuilderPage`/`AppRuntimePage`

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`

**Interfaces:**
- Consumes: `useActiveExtensions` (Task 5, `shell/src/api/hooks.ts`), `registerExtensionWidget` (Task 8).

- [ ] **Step 1: Câbler `AppBuilderPage.tsx`**

Ajouter l'import (après celui de `registerCounterWcExampleWidget`) :

```ts
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
```

Dans le corps de `AppBuilderPage`, juste après les `useState` existants, ajouter :

```ts
  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
    // Se déclenche une fois les données arrivées OU en erreur (fail-open :
    // un /extensions en échec ne doit pas rendre le builder inutilisable) —
    // jamais tant que isLoading est vrai.
  }, [extensionsQuery.isLoading, extensionsQuery.data]);
```

Modifier la garde de chargement existante (repérer la ligne `if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;`) pour y ajouter la condition :

```ts
  if (query.isLoading || !extensionsRegistered || (!draft && !query.isError))
    return <p role="status">Chargement…</p>;
```

- [ ] **Step 2: Câbler `AppRuntimePage.tsx`**

Ajouter l'import (après celui de `registerCounterWcExampleWidget`) :

```ts
import { useState, useEffect } from "react";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
```

Dans le corps de `AppRuntimePage`, après `const query = useAppConfig(...)` :

```ts
  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
  }, [extensionsQuery.isLoading, extensionsQuery.data]);
```

Modifier la garde existante :

```ts
  if (itemQuery.isLoading || (itemQuery.isSuccess && query.isLoading) || !extensionsRegistered) {
    return <p role="status">Chargement…</p>;
  }
```

- [ ] **Step 3: Lancer toute la suite vitest**

Run: `npm test -- --run`
Expected: PASS — `AppBuilderPage.test.tsx` et `AppRuntimePage.test.tsx` passent toujours sans modification (leurs `Partial<ItemClient>` de test n'implémentent pas `listActiveExtensions` ; `useActiveExtensions` résout silencieusement à `[]` dans ce cas, cf. Task 5 Step 6 — `extensionsQuery.isLoading` devient `false` dès la résolution, `extensionsRegistered` passe à `true`, la page se rend normalement).

Si un test de ces deux fichiers reste bloqué sur "Chargement…", vérifier que `useActiveExtensions` utilise bien `client.listActiveExtensions?.()` (chaînage optionnel) et non `client.listActiveExtensions()` sans garde.

- [ ] **Step 4: Lancer le build**

Run: `npm run build`
Expected: succès (`tsc --noEmit` + `vite build`), aucune erreur de type.

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): bootstrap des extensions actives dans AppBuilderPage/AppRuntimePage (SP-8b)"
```

---

### Task 10: E2E — widget d'extension chargé dynamiquement, désactivation → placeholder

**Files:**
- Create: `shell/public/fixtures/gauge-extension-widget.js`
- Modify: `shell/e2e/mocks.ts`
- Create: `shell/e2e/extension-widget.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`).

- [ ] **Step 1: Ajouter une route `**/extensions*` par défaut à `mocks.ts`**

**Important** : dès la Task 9, `AppBuilderPage`/`AppRuntimePage` appellent inconditionnellement `GET /extensions` au montage. Sans cette étape, les 28 specs E2E existantes (qui n'interceptent pas cette route) tenteraient une vraie requête réseau vers un hôte non résolvable et resteraient bloquées sur "Chargement…".

Dans `shell/e2e/mocks.ts`, à l'intérieur de `mockCore(page)`, ajouter (n'importe où parmi les autres `page.route`, par exemple juste après la route `**/me`) :

```ts
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [] } });
  });
```

- [ ] **Step 2: Lancer toute la suite E2E pour vérifier l'absence de régression AVANT d'ajouter la nouvelle spec**

Run: `npm run e2e`
Expected: PASS — 28 specs vertes (aucune nouvelle spec encore ajoutée à ce stade), preuve que le défaut `{ extensions: [] }` suffit à ne rien casser.

- [ ] **Step 3: Créer la fixture de widget d'extension (JS pur, non transformé par Vite — servi tel quel depuis `public/`)**

`shell/public/fixtures/gauge-extension-widget.js` :

```js
class GaugeExtensionWidget extends HTMLElement {
  constructor() {
    super();
    this._count = 0;
    this._initialized = false;
  }

  set props(value) {
    this._props = value || {};
    if (!this._initialized) {
      this._count = Number(this._props.initial ?? 0);
      this._initialized = true;
    }
    this._render();
  }

  get props() {
    return this._props;
  }

  connectedCallback() {
    this._render();
  }

  reset() {
    this._count = Number(this._props?.initial ?? 0);
    this._render();
  }

  _increment() {
    this._count += 1;
    this.dispatchEvent(new CustomEvent("changed", { detail: { count: this._count } }));
    this._render();
  }

  _render() {
    this.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.style.cssText =
      "display:flex;height:100%;flex-direction:column;align-items:center;justify-content:center;" +
      "gap:.25rem;font-family:var(--gs-font,system-ui,sans-serif);";
    const span = document.createElement("span");
    span.textContent = String(this._count);
    span.style.cssText = "font-size:1.5rem;font-weight:600;color:var(--gs-color-text,#0f172a);";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "+1";
    button.addEventListener("click", () => this._increment());
    wrapper.appendChild(span);
    wrapper.appendChild(button);
    this.appendChild(wrapper);
  }
}

if (!customElements.get("gauge-extension-widget")) {
  customElements.define("gauge-extension-widget", GaugeExtensionWidget);
}
```

- [ ] **Step 4: Écrire la spec E2E**

`shell/e2e/extension-widget.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const GAUGE_MANIFEST = {
  id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
  moduleUrl: "/fixtures/gauge-extension-widget.js",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("un widget d'extension chargé dynamiquement par URL se pose dans le builder et se comporte comme un widget WC ordinaire", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App extension");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // La palette liste l'extension sans redéploiement du shell.
  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  const gauge = page.locator("gauge-extension-widget");
  await expect(gauge.getByText("0", { exact: true })).toBeVisible();

  // Bouton (déclenchera reset) et Texte (affichera la variable count).
  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, import() du module ré-exécuté depuis le cache navigateur.
  await page.goto("/apps/9");
  const runtimeGauge = page.locator("gauge-extension-widget");
  await expect(runtimeGauge.getByText("0", { exact: true })).toBeVisible();

  await runtimeGauge.getByRole("button", { name: "+1" }).click();
  await runtimeGauge.getByRole("button", { name: "+1" }).click();
  await expect(runtimeGauge.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("Compte : 2")).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeGauge.getByText("0", { exact: true })).toBeVisible();
});

test("désactiver une extension affiche un placeholder au lieu de casser une app qui l'utilisait", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App extension désactivée");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // L'admin désactive l'extension : /extensions ne la renvoie plus.
  await page.unroute("**/extensions*");
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [] } });
  });

  await page.goto("/apps/9");
  await expect(page.getByText("Widget inconnu : acme.gauge")).toBeVisible();
  await expect(page.locator("gauge-extension-widget")).toHaveCount(0);
});
```

- [ ] **Step 5: Lancer la nouvelle spec seule**

Run: `npm run e2e -- extension-widget`
Expected: PASS (2 tests).

Si le premier test échoue sur une étape de sélection (`selectOption`/`getByLabel`), comparer les libellés exacts contre `shell/e2e/wc-widget-bridge.spec.ts` (SP-8a) — même conventions (`getByLabel("Action", { exact: true })` requis dès la 2e action composée, cf. note dans ce fichier).

- [ ] **Step 6: Lancer toute la suite E2E pour vérifier l'absence de régression**

Run: `npm run e2e`
Expected: PASS — 30 specs vertes (28 existantes + `extension-widget.spec.ts` avec ses 2 tests).

- [ ] **Step 7: Commit**

```bash
git add shell/public/fixtures/gauge-extension-widget.js shell/e2e/mocks.ts shell/e2e/extension-widget.spec.ts
git commit -m "test(e2e): widget d'extension chargé dynamiquement par URL, désactivation -> placeholder (SP-8b)"
```

---

## Vérification finale

- [ ] `cd core && uv run pytest` — tous les tests cœur passent (nouveaux + existants).
- [ ] `cd shell && npm run build` — `tsc --noEmit` + `vite build` sans erreur.
- [ ] `cd shell && npm test -- --run` — tous les tests vitest passent.
- [ ] `cd shell && npm run e2e` — 30 specs E2E vertes.
- [ ] Relire `docs/superpowers/specs/2026-07-13-sp8b-chargement-dynamique-extensions-design.md`
  et confirmer que chaque critère d'acceptation a une preuve dans les tests
  ci-dessus (palette → canvas → props/thème/events/actions par URL,
  désactivation → placeholder, aucune régression sur SP-8a ni les 28 specs
  E2E précédentes).
