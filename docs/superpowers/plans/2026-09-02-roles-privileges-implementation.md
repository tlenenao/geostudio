# Rôles à base de privilèges — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer `User.is_admin`/`User.is_analyst` (deux booléens plats) par un modèle de rôles à privilèges nommés — 4 rôles prédéfinis immuables (Administrateur/Créateur/Analyste/Lecteur, un par tenant) + rôles sur mesure créés par tenant, chacun un ensemble de privilèges cochés dans un catalogue fixe — sans toucher aux permissions par objet (`can()`/`decide()`, RLS, partage).

**Architecture:** Nouveau module `core/app/roles/` (modèle `Role`, catalogue `Privilege` (Enum), repository, garde `require_privilege`, routes CRUD + catalogue), inséré dans le contrat de couches entre `app.instance` et `app.auth`. `User.role_id` (FK, NOT NULL) devient la source de vérité ; `User.is_admin` **survit** comme colonne synchronisée par l'unique chemin d'écriture (signal consommé par ~20 sites existants, inchangés) ; `User.is_analyst` disparaît (un seul consommateur, remplacé directement). Côté shell, `capabilities.ts` bascule de `{isAdmin, isAnalyst}` à un ensemble de privilèges ; nouvel écran `RolesAdminPage` pour gérer les rôles sur mesure.

**Tech Stack:** FastAPI, SQLAlchemy (ORM déclaratif, pas de `relationship()` — convention du dépôt), Alembic, pytest ; React, TanStack Query, Radix UI (kit `shell/src/ui/kit/`), Vitest, Playwright.

**Document de référence :** `docs/superpowers/specs/2026-09-01-roles-privileges-design.md` (design validé, ne pas re-débattre les décisions produit qu'il tranche — §8 de ce document en liste le résumé). Ce plan résout plusieurs points techniques que le design laissait implicites (voir chaque tâche pour le raisonnement) :

- **`User.is_admin`/`is_analyst` ne peuvent pas littéralement disparaître** comme le design le suggérait : ~20 sites de lecture (`app/collections/routes.py`, `app/pipelines/*`, `app/mcp/tools.py`, `app/dcat/routes.py`, `app/stac/routes.py`, etc.) lisent `user.is_admin` comme un simple signal passé à `decide()`/`list_visible_collections()`, et 44 fichiers de test appellent `get_or_create_user(bootstrap_admin=..., bootstrap_analyst=...)`. Résolution : `is_admin` reste une colonne `Boolean` réelle, mais son unique écrivain devient la logique de rôle (synchronisée à chaque changement de `role_id`) — plus jamais réglée indépendamment. `is_analyst` a un seul consommateur (`app/features/routes.py:430`, SQL Lab) : supprimé, remplacé directement par `require_privilege(...)`.
- **Aucune `relationship()` SQLAlchemy n'existe dans ce dépôt** (grep vérifié) — convention respectée : `User.role_id` est un FK brut, jamais un objet `Role` chargé automatiquement. Tout code qui a besoin du rôle complet appelle `app.roles.repository.get_role(session, ...)` explicitement.
- **Le contrat de couches (`core/pyproject.toml`, `[tool.importlinter]`) crée une tension réelle** : `app.roles` doit être au-dessus d'`app.auth` (ses propres routes ont besoin de `get_current_user`), mais `/me` et `PATCH /users/{id}` (dans `app.auth.routes`, en dessous) et `get_or_create_user` (dans `app.users.repository`, encore plus bas) ont besoin de lire les rôles. Résolution : 4 exemptions nommées à l'arête exacte dans `ignore_imports`, exactement le même patron que l'exemption déjà existante `app.auth.routes -> app.sharing.repository` (voir Tâche 4).

## Global Constraints

- Docs et messages utilisateur en français ; code/identifiants en anglais (CLAUDE.md).
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), petits, un sujet par commit — un commit par tâche minimum.
- TDD systématique : test en échec avant l'implémentation, à chaque tâche.
- `tenant_id` sur toute nouvelle table, `audit_log` sur toute écriture de rôle (arbitrage non négociable de CLAUDE.md).
- Régénérer la spec OpenAPI + les types TS dès qu'une route ou un modèle du cœur change (piège n°1 de CLAUDE.md — classe d'oubli la plus fréquente du dépôt) : `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types`.
- Revue par tâche **et** revue finale de branche (piège n°4) — ce chantier touche ~15 fichiers cœur dans des modules variés (harvest, collections, extensions, secrets, features) : découpé en une tâche par sous-domaine, pas une tâche monolithique (déjà acté par le design §7).
- Lancer la suite complète (`uv run pytest` côté cœur, `npm run test`/`npm run e2e` côté shell) avant de clore chaque tâche qui touche une page/route partagée (piège n°6).
- `ruff check`/`ruff format --check`/`lint-imports` côté cœur, `npm run lint`/`npm run format:check` côté shell, à chaque tâche.
- Hors périmètre, à ne pas toucher : `app/sharing/authorization.py` (`can`/`decide`), `app/sharing/repository.py` (`roles_for_items`/`roles_for_collections` — seule `has_any_editor_role` est supprimée, cf. Tâche 4, car son unique appelant disparaît dans cette même tâche), RLS PostGIS, tout ce qui concerne les tâches planifiées (A14, SP-31).

---

## Task 1 : module `app.roles` — modèle, catalogue de privilèges, repository, garde

**Files:**
- Create: `core/app/roles/__init__.py` (vide)
- Create: `core/app/roles/models.py`
- Create: `core/app/roles/privileges.py`
- Create: `core/app/roles/repository.py`
- Create: `core/app/roles/guards.py`
- Modify: `core/app/db.py` (`core_table_names()`)
- Test: `core/tests/test_roles_repository.py`
- Test: `core/tests/test_roles_guards.py`

**Interfaces:**
- Produces: `Role` (ORM, `app.roles.models`) — colonnes `id: str`, `tenant_id: str`, `name: str`, `slug: str`, `is_built_in: bool`, `privileges: list[str]`, `created_at`/`updated_at: datetime`.
- Produces: `Privilege` (Enum `str`, `app.roles.privileges`) — 17 membres, valeurs `"domaine.action"`. `PRIVILEGE_METADATA: dict[Privilege, tuple[str, str]]` (domaine, labelKey). `ALL_PRIVILEGE_VALUES: list[str]`. `BUILT_IN_ROLE_PRIVILEGES: dict[str, list[str]]` (clé = slug). `BUILT_IN_ROLE_NAMES: dict[str, str]`.
- Produces (`app.roles.repository`) : `ensure_built_in_roles(session, *, tenant_id) -> dict[str, Role]`, `get_role(session, *, tenant_id, role_id) -> Role | None`, `list_roles(session, *, tenant_id) -> list[Role]`, `create_role(session, *, tenant_id, name, privileges) -> Role`, `update_role(session, *, tenant_id, role_id, name, privileges) -> Role | None`, `delete_role(session, *, tenant_id, role_id) -> None`, `count_role_holders(session, *, tenant_id, role_id) -> int`, `count_users_with_privileges(session, *, tenant_id, privileges) -> int`, `would_orphan_privilege_holders(session, *, tenant_id, privileges, role_id, new_privileges) -> bool`, `get_privilege_catalog() -> list[dict[str, str]]`.
- Produces (`app.roles.guards`) : `require_privilege(session, user, privilege: str) -> None` (raises `HTTPException(403)`).
- Consumes: `app.users.models.User` (déjà existant, lu seulement — pas de changement dans cette tâche).

- [ ] **Step 1: Écrire `app/roles/models.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    is_built_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    privileges: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 2: Écrire `app/roles/privileges.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from enum import Enum


class Privilege(str, Enum):
    CATALOG_MANAGE = "catalog.manage"
    MAPS_MANAGE = "maps.manage"
    DATA_VIEW = "data.view"
    DATA_MANAGE = "data.manage"
    APPS_MANAGE = "apps.manage"
    AUTOMATION_MANAGE = "automation.manage"
    AUTOMATION_SECRETS_MANAGE = "automation.secrets.manage"
    ANALYTICS_VIEW = "analytics.view"
    ANALYTICS_SQL_LAB_ACCESS = "analytics.sql_lab.access"
    TASKS_VIEW = "tasks.view"
    TASKS_VIEW_ALL = "tasks.view_all"
    ADMIN_USERS_MANAGE = "admin.users.manage"
    ADMIN_ROLES_MANAGE = "admin.roles.manage"
    ADMIN_HARVEST_MANAGE = "admin.harvest.manage"
    ADMIN_COLLECTIONS_MANAGE = "admin.collections.manage"
    ADMIN_EXTENSIONS_MANAGE = "admin.extensions.manage"
    ADMIN_SECRETS_MANAGE = "admin.secrets.manage"
    SETTINGS_INSTANCE_MANAGE = "settings.instance.manage"


# (domaine shell/src/auth/capabilities.ts::DomainId, clé i18n shell/src/i18n/catalog.fr.ts)
# — le cœur ne porte aucun libellé français (A12), seulement l'identifiant du
# domaine et une clé que le shell résout via t().
PRIVILEGE_METADATA: dict[Privilege, tuple[str, str]] = {
    Privilege.CATALOG_MANAGE: ("catalog", "roles.privilege.catalogManage"),
    Privilege.MAPS_MANAGE: ("maps", "roles.privilege.mapsManage"),
    Privilege.DATA_VIEW: ("data", "roles.privilege.dataView"),
    Privilege.DATA_MANAGE: ("data", "roles.privilege.dataManage"),
    Privilege.APPS_MANAGE: ("apps", "roles.privilege.appsManage"),
    Privilege.AUTOMATION_MANAGE: ("automation", "roles.privilege.automationManage"),
    Privilege.AUTOMATION_SECRETS_MANAGE: (
        "automation",
        "roles.privilege.automationSecretsManage",
    ),
    Privilege.ANALYTICS_VIEW: ("analytics", "roles.privilege.analyticsView"),
    Privilege.ANALYTICS_SQL_LAB_ACCESS: ("analytics", "roles.privilege.analyticsSqlLabAccess"),
    Privilege.TASKS_VIEW: ("tasks", "roles.privilege.tasksView"),
    Privilege.TASKS_VIEW_ALL: ("tasks", "roles.privilege.tasksViewAll"),
    Privilege.ADMIN_USERS_MANAGE: ("admin", "roles.privilege.adminUsersManage"),
    Privilege.ADMIN_ROLES_MANAGE: ("admin", "roles.privilege.adminRolesManage"),
    Privilege.ADMIN_HARVEST_MANAGE: ("admin", "roles.privilege.adminHarvestManage"),
    Privilege.ADMIN_COLLECTIONS_MANAGE: ("admin", "roles.privilege.adminCollectionsManage"),
    Privilege.ADMIN_EXTENSIONS_MANAGE: ("admin", "roles.privilege.adminExtensionsManage"),
    Privilege.ADMIN_SECRETS_MANAGE: ("admin", "roles.privilege.adminSecretsManage"),
    Privilege.SETTINGS_INSTANCE_MANAGE: ("settings", "roles.privilege.settingsInstanceManage"),
}

ALL_PRIVILEGE_VALUES: list[str] = [p.value for p in Privilege]

BUILT_IN_ROLE_NAMES: dict[str, str] = {
    "admin": "Administrateur",
    "creator": "Créateur",
    "analyst": "Analyste",
    "reader": "Lecteur",
}

# Reprend la matrice §6.7 de docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md,
# traduite en privilèges concrets (design §3.3).
BUILT_IN_ROLE_PRIVILEGES: dict[str, list[str]] = {
    "admin": list(ALL_PRIVILEGE_VALUES),
    "creator": [
        Privilege.CATALOG_MANAGE.value,
        Privilege.MAPS_MANAGE.value,
        Privilege.DATA_VIEW.value,
        Privilege.DATA_MANAGE.value,
        Privilege.APPS_MANAGE.value,
        Privilege.AUTOMATION_MANAGE.value,
        Privilege.ANALYTICS_VIEW.value,
        Privilege.TASKS_VIEW.value,
    ],
    "analyst": [
        Privilege.DATA_VIEW.value,
        Privilege.ANALYTICS_VIEW.value,
        Privilege.ANALYTICS_SQL_LAB_ACCESS.value,
        Privilege.TASKS_VIEW.value,
    ],
    "reader": [],
}
```

- [ ] **Step 3: Ajouter `app.roles.models` à `core/app/db.py::core_table_names()`**

Dans `core/app/db.py`, insérer (ordre alphabétique existant, entre `app.reports` et `app.secrets`) :

```python
    from app.reports import models as reports_models  # noqa: F401
    from app.roles import models as roles_models  # noqa: F401
    from app.secrets import models as secrets_models  # noqa: F401
```

- [ ] **Step 4: Écrire le test en échec `core/tests/test_roles_repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.roles.privileges import Privilege
from app.roles.repository import (
    count_role_holders,
    count_users_with_privileges,
    create_role,
    delete_role,
    ensure_built_in_roles,
    get_privilege_catalog,
    get_role,
    list_roles,
    update_role,
    would_orphan_privilege_holders,
)
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_ensure_built_in_roles_is_idempotent_and_covers_the_four_profiles():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert set(roles) == {"admin", "creator", "analyst", "reader"}
        assert roles["admin"].privileges == [p.value for p in Privilege]
        assert roles["reader"].privileges == []
        assert all(r.is_built_in for r in roles.values())
        again = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert {r.id for r in again.values()} == {r.id for r in roles.values()}


def test_create_update_delete_a_custom_role():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        role = create_role(
            s, tenant_id=tenant.id, name="Contributeur moissonnage",
            privileges=[Privilege.ADMIN_HARVEST_MANAGE.value],
        )
        assert role.is_built_in is False
        fetched = get_role(s, tenant_id=tenant.id, role_id=role.id)
        assert fetched is not None and fetched.name == "Contributeur moissonnage"
        updated = update_role(
            s, tenant_id=tenant.id, role_id=role.id, name="Moissonnage+",
            privileges=[Privilege.ADMIN_HARVEST_MANAGE.value, Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        assert updated is not None and len(updated.privileges) == 2
        assert {r.id for r in list_roles(s, tenant_id=tenant.id)} >= {role.id}
        delete_role(s, tenant_id=tenant.id, role_id=role.id)
        assert get_role(s, tenant_id=tenant.id, role_id=role.id) is None


def test_count_role_holders():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        u = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="x", username="x", email=None,
            first_name="", last_name="",
        )
        s.flush()
        assert count_role_holders(s, tenant_id=tenant.id, role_id=roles["creator"].id) >= 1
        assert count_role_holders(s, tenant_id=tenant.id, role_id=roles["admin"].id) == 0
        assert u.role_id == roles["creator"].id


def test_count_users_with_privileges_and_orphan_detection():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="admin", username="admin", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        needed = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]
        assert count_users_with_privileges(s, tenant_id=tenant.id, privileges=needed) == 1
        # Retirer ces deux privilèges du rôle admin lui-même (hypothèse) laisserait
        # le tenant sans personne capable de gérer utilisateurs/rôles.
        assert would_orphan_privilege_holders(
            s, tenant_id=tenant.id, privileges=needed, role_id=roles["admin"].id,
            new_privileges=[],
        )
        # Ne rien changer d'autre ne l'orpheline pas.
        assert not would_orphan_privilege_holders(
            s, tenant_id=tenant.id, privileges=needed, role_id=roles["reader"].id,
            new_privileges=[],
        )


def test_privilege_catalog_covers_every_privilege_with_domain_and_label_key():
    catalog = get_privilege_catalog()
    assert len(catalog) == len(list(Privilege))
    for entry in catalog:
        assert set(entry) == {"privilege", "domain", "labelKey"}
```

- [ ] **Step 5: Confirmer l'échec**

Run: `cd core && uv run pytest tests/test_roles_repository.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.roles.repository'`)

- [ ] **Step 6: Écrire `app/roles/repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.roles.models import Role
from app.roles.privileges import BUILT_IN_ROLE_NAMES, BUILT_IN_ROLE_PRIVILEGES, PRIVILEGE_METADATA
from app.users.models import User


def ensure_built_in_roles(session: Session, *, tenant_id: str) -> dict[str, Role]:
    """Crée les 4 rôles prédéfinis pour ce tenant s'ils n'existent pas déjà —
    idempotent, appelée à chaque requête authentifiée (app.auth.dependency).
    Chaque tenant reçoit sa PROPRE copie, jamais un tenant_id nul (arbitrage
    non négociable) ; l'immuabilité vient de is_built_in (app.roles.routes),
    pas du partage d'une ligne (design §2)."""
    existing = {
        role.slug: role
        for role in session.scalars(
            select(Role).where(Role.tenant_id == tenant_id, Role.is_built_in.is_(True))
        ).all()
    }
    for slug, privileges in BUILT_IN_ROLE_PRIVILEGES.items():
        if slug in existing:
            continue
        role = Role(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            name=BUILT_IN_ROLE_NAMES[slug],
            slug=slug,
            is_built_in=True,
            privileges=list(privileges),
        )
        session.add(role)
        existing[slug] = role
    session.flush()
    return existing


def get_role(session: Session, *, tenant_id: str, role_id: str) -> Role | None:
    return session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == role_id))


def list_roles(session: Session, *, tenant_id: str) -> list[Role]:
    return list(
        session.scalars(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)).all()
    )


def create_role(
    session: Session, *, tenant_id: str, name: str, privileges: Sequence[str]
) -> Role:
    role = Role(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        name=name,
        slug=uuid.uuid4().hex,
        is_built_in=False,
        privileges=list(privileges),
    )
    session.add(role)
    session.flush()
    session.refresh(role)
    return role


def update_role(
    session: Session,
    *,
    tenant_id: str,
    role_id: str,
    name: str | None,
    privileges: list[str] | None,
) -> Role | None:
    role = get_role(session, tenant_id=tenant_id, role_id=role_id)
    if role is None:
        return None
    if name is not None:
        role.name = name
    if privileges is not None:
        role.privileges = privileges
    session.flush()
    return role


def delete_role(session: Session, *, tenant_id: str, role_id: str) -> None:
    role = get_role(session, tenant_id=tenant_id, role_id=role_id)
    if role is not None:
        session.delete(role)
        session.flush()


def count_role_holders(session: Session, *, tenant_id: str, role_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.role_id == role_id)
    )


def count_users_with_privileges(
    session: Session, *, tenant_id: str, privileges: Sequence[str]
) -> int:
    needed = set(privileges)
    rows = session.execute(
        select(User.id, Role.privileges)
        .join(Role, Role.id == User.role_id)
        .where(User.tenant_id == tenant_id)
    ).all()
    return sum(1 for _, role_privileges in rows if needed.issubset(set(role_privileges)))


def would_orphan_privilege_holders(
    session: Session,
    *,
    tenant_id: str,
    privileges: Sequence[str],
    role_id: str,
    new_privileges: list[str],
) -> bool:
    """True si remplacer les privilèges du rôle `role_id` par `new_privileges`
    laisserait le tenant sans aucun utilisateur possédant tous les
    `privileges` demandés, par quelque rôle que ce soit."""
    needed = set(privileges)
    rows = session.execute(
        select(User.id, User.role_id, Role.privileges)
        .join(Role, Role.id == User.role_id)
        .where(User.tenant_id == tenant_id)
    ).all()
    for _, holder_role_id, role_privileges in rows:
        effective = set(new_privileges) if holder_role_id == role_id else set(role_privileges)
        if needed.issubset(effective):
            return False
    return True


def get_privilege_catalog() -> list[dict[str, str]]:
    return [
        {"privilege": privilege.value, "domain": domain, "labelKey": label_key}
        for privilege, (domain, label_key) in PRIVILEGE_METADATA.items()
    ]
```

**Note d'implémentation** : `count_role_holders`/`count_users_with_privileges` chargent les lignes en Python plutôt qu'un opérateur JSON SQL (`@>` Postgres) — portable SQLite/Postgres (les tests tournent en SQLite mémoire), et le volume (utilisateurs d'un tenant) ne justifie aucune optimisation (YAGNI).

- [ ] **Step 7: Confirmer le succès partiel**

Run: `cd core && uv run pytest tests/test_roles_repository.py -v`
Expected: PASS (5 tests) — `User.role_id` n'existe pas encore comme colonne, mais `get_or_create_user` (Tâche 2) n'a pas encore changé non plus : à ce stade, `ensure_built_in_roles` et les fonctions de lecture de `Role` ne dépendent PAS de `User.role_id`, seules `count_role_holders`/`count_users_with_privileges` en dépendent — si le test échoue ici avec `AttributeError: role_id`, c'est attendu tant que la Tâche 2 n'est pas faite : dans ce cas, commenter temporairement les deux derniers tests n'est PAS la solution — exécuter les Tâches 1 et 2 dans l'ordre (Tâche 2 dépend de `ensure_built_in_roles`, donc ne peut pas être testée avant que cette tâche existe, mais rien n'empêche `test_roles_repository.py` de rester rouge jusqu'à la fin de la Tâche 2). Si des tests de cette tâche échouent pour cette raison précise, laisser la note dans le commit et les faire passer à la fin de la Tâche 2, pas ici.

- [ ] **Step 8: Écrire le test en échec `core/tests/test_roles_guards.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.db import init_db, make_engine, make_session_factory
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_require_privilege_allows_a_holder_and_rejects_the_rest():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        reader = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="r", email=None,
            first_name="", last_name="",
        )
        s.flush()

        require_privilege(s, admin, Privilege.ADMIN_ROLES_MANAGE.value)  # ne lève pas

        with pytest.raises(HTTPException) as exc_info:
            require_privilege(s, reader, Privilege.ADMIN_ROLES_MANAGE.value)
        assert exc_info.value.status_code == 403
```

- [ ] **Step 9: Confirmer l'échec puis écrire `app/roles/guards.py`**

Run: `cd core && uv run pytest tests/test_roles_guards.py -v` → FAIL (`ModuleNotFoundError`)

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def require_privilege(session: Session, user: User, privilege: str) -> None:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    if role is None or privilege not in role.privileges:
        raise HTTPException(status_code=403, detail=f"privilege '{privilege}' required")
```

- [ ] **Step 10: Run et commit**

Run: `cd core && uv run pytest tests/test_roles_repository.py tests/test_roles_guards.py -v`
Expected: `test_roles_guards.py` PASS. `test_roles_repository.py` peut encore échouer sur les deux tests dépendant de `User.role_id` (attendu, cf. Step 7) — laisser en l'état, résolu Tâche 2.

```bash
cd core && uv run ruff check app/roles tests/test_roles_repository.py tests/test_roles_guards.py
uv run ruff format app/roles tests/test_roles_repository.py tests/test_roles_guards.py
git add app/roles tests/test_roles_repository.py tests/test_roles_guards.py app/db.py
git commit -m "feat(core): module app.roles — modèle Role, catalogue de 17 privilèges, repository, garde require_privilege"
```

---

## Task 2 : `User.role_id`, `is_admin` synchronisé, `is_analyst` retiré

**Files:**
- Modify: `core/app/users/models.py`
- Modify: `core/app/users/repository.py`
- Modify: `core/tests/test_admin_bootstrap.py`
- Delete: `core/tests/test_users_analyst.py` (couverture remplacée par les tests ci-dessous — `is_analyst` disparaît, `set_analyst`/tests dédiés n'ont plus de sujet)
- Test: `core/tests/test_users_repository_roles.py`

**Interfaces:**
- Consumes: `app.roles.repository.ensure_built_in_roles` (Tâche 1).
- Produces: `User.role_id: str` (FK `roles.id`, NOT NULL), `User.is_admin: bool` (colonne, **sémantique inchangée pour les lecteurs** — reste vrai seulement pour le rôle `admin`, jamais réglée que par cette tâche). `get_or_create_user(...)` **signature inchangée** (toujours `bootstrap_admin`/`bootstrap_analyst`). `set_user_role(session, *, tenant_id, user_id, role_id, role_slug) -> User | None` remplace `set_admin`/`set_analyst`/`count_admins` (supprimées).

**Raisonnement (à ne pas re-découvrir en cours de route)** : `app.users` est SOUS `app.roles` dans le contrat de couches (Tâche 4 l'y insère). `get_or_create_user` doit résoudre le rôle initial d'un nouvel utilisateur — cela nécessite `ensure_built_in_roles` (dans `app.roles`), une importation dans le sens interdit. Exactement comme l'exemption existante `app.auth.routes -> app.sharing.repository` (même classe de problème), ce plan ajoute `app.users.repository -> app.roles.repository` aux `ignore_imports` (fait dans cette tâche, avant que Tâche 4 n'ajoute `app.roles` au contrat — sans quoi `lint-imports` n'a rien à exempter encore, l'entrée reste inerte jusqu'à la Tâche 4, ce qui est sans risque).

- [ ] **Step 1: Modifier `core/app/users/models.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


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
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    # Colonne synchronisée, PAS une source de vérité indépendante : réglée
    # uniquement par get_or_create_user()/set_user_role() (app.users.repository),
    # toujours en même temps que role_id. ~20 lecteurs existants (decide(),
    # list_visible_collections(), app.mcp.tools, app.pipelines, app.dcat,
    # app.stac…) la consomment comme signal — préservée à l'identique pour ne
    # pas les toucher (design, résolution documentée en tête de ce plan).
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 2: Écrire le test en échec `core/tests/test_users_repository_roles.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.roles.repository import ensure_built_in_roles, get_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_new_user_without_bootstrap_gets_the_creator_role():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="x", username="x", email=None,
            first_name="", last_name="",
        )
        role = get_role(s, tenant_id=tenant.id, role_id=user.role_id)
        assert role is not None and role.slug == "creator"
        assert user.is_admin is False


def test_bootstrap_admin_assigns_the_admin_role_and_never_demotes():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=user.role_id)
        assert role is not None and role.slug == "admin"
        assert user.is_admin is True
        # Un appel ultérieur sans bootstrap ne rétrograde pas (retirer un sub
        # de CORE_ADMIN_SUBS ne doit pas destituer silencieusement).
        again = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="", bootstrap_admin=False,
        )
        assert again.id == user.id and again.is_admin is True


def test_bootstrap_analyst_assigns_the_analyst_role_but_never_demotes_an_admin():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        still_admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="", bootstrap_analyst=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=still_admin.role_id)
        assert still_admin.id == admin.id and role is not None and role.slug == "admin"

        analyst = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="b", email=None,
            first_name="", last_name="", bootstrap_analyst=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=analyst.role_id)
        assert role is not None and role.slug == "analyst"


def test_set_user_role_updates_role_id_and_synced_is_admin():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="x", username="x", email=None,
            first_name="", last_name="",
        )
        updated = set_user_role(
            s, tenant_id=tenant.id, user_id=user.id, role_id=roles["admin"].id, role_slug="admin",
        )
        assert updated is not None and updated.role_id == roles["admin"].id
        assert updated.is_admin is True
        set_user_role(
            s, tenant_id=tenant.id, user_id=user.id, role_id=roles["reader"].id, role_slug="reader",
        )
        assert user.is_admin is False
        assert set_user_role(
            s, tenant_id=tenant.id, user_id="nope", role_id=roles["admin"].id, role_slug="admin",
        ) is None
```

- [ ] **Step 3: Confirmer l'échec**

Run: `cd core && uv run pytest tests/test_users_repository_roles.py -v`
Expected: FAIL (`role_id` inconnu de `get_or_create_user`, `set_user_role` inexistante)

- [ ] **Step 4: Réécrire `core/app/users/repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.roles.repository import ensure_built_in_roles
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
    bootstrap_admin: bool = False,
    bootstrap_analyst: bool = False,
) -> User:
    roles = ensure_built_in_roles(session, tenant_id=tenant_id)
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.oidc_sub == oidc_sub)
    )
    if user is None:
        if bootstrap_admin:
            initial_role = roles["admin"]
        elif bootstrap_analyst:
            initial_role = roles["analyst"]
        else:
            initial_role = roles["creator"]
        user = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            oidc_sub=oidc_sub,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role_id=initial_role.id,
            is_admin=(initial_role.slug == "admin"),
        )
        session.add(user)
    else:
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        if bootstrap_admin and user.role_id != roles["admin"].id:
            # Promotion par env uniquement — la rétrogradation passe par
            # set_user_role() (retirer un sub de CORE_ADMIN_SUBS ne doit pas
            # destituer silencieusement).
            user.role_id = roles["admin"].id
            user.is_admin = True
        elif bootstrap_analyst and user.role_id not in (roles["admin"].id, roles["analyst"].id):
            # Miroir de bootstrap_admin — ne rétrograde jamais un admin
            # existant vers analyste.
            user.role_id = roles["analyst"].id
    session.flush()
    session.refresh(user)
    return user


def set_user_role(
    session: Session, *, tenant_id: str, user_id: str, role_id: str, role_slug: str
) -> User | None:
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
    if user is None:
        return None
    user.role_id = role_id
    user.is_admin = role_slug == "admin"
    session.flush()
    return user


def list_users(
    session: Session, *, tenant_id: str, page: int, page_size: int
) -> tuple[list[User], int]:
    base = select(User).where(User.tenant_id == tenant_id)
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    users = list(
        session.scalars(
            base.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
        ).all()
    )
    return users, total
```

(`set_admin`, `set_analyst`, `count_admins` supprimées — remplacées par `set_user_role` et, côté anti-lockout, `app.roles.repository.count_users_with_privileges` déjà écrite Tâche 1.)

- [ ] **Step 5: Mettre à jour `core/tests/test_admin_bootstrap.py`**

Remplacer `test_set_admin_and_count` (utilise `set_admin`/`count_admins`, supprimées) — les deux autres tests (`test_bootstrap_promotes`, `test_bootstrap_never_demotes`) restent valides tels quels puisque `user.is_admin` garde exactement sa sémantique.

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


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
        session,
        tenant_id=tenant.id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=bootstrap_admin,
    )


def test_bootstrap_promotes(session):
    user = _user(session, bootstrap_admin=True)
    assert user.is_admin is True


def test_bootstrap_never_demotes(session):
    user = _user(session, bootstrap_admin=True)
    again = _user(session, bootstrap_admin=False)  # sub retiré de l'env ensuite
    assert again.id == user.id and again.is_admin is True
```

- [ ] **Step 6: Supprimer `core/tests/test_users_analyst.py`**

```bash
git rm core/tests/test_users_analyst.py
```

(Couverture remplacée par `test_users_repository_roles.py`, Step 2 ci-dessus — `is_analyst`/`set_analyst` n'existent plus.)

- [ ] **Step 7: Ajouter l'exemption de couches (préparatoire à la Tâche 4)**

Dans `core/pyproject.toml`, section `[tool.importlinter]`, ajouter à `ignore_imports` (juste après `"app.auth.routes -> app.sharing.repository",` ligne 260) :

```toml
    # app.roles doit être AU-DESSUS d'app.auth dans ce contrat (ses propres
    # routes, app.roles.routes, ont besoin de get_current_user) — mais
    # get_or_create_user (app.users.repository, sous app.auth) doit résoudre
    # le rôle initial d'un nouvel utilisateur via app.roles.repository.
    # ensure_built_in_roles(). Même classe de tension que l'exemption
    # ci-dessus : aucune place linéaire ne satisfait les deux sens à la fois.
    "app.users.repository -> app.roles.repository",
```

Cette ligne reste inerte (aucune entrée `app.roles` dans `layers` encore) jusqu'à la Tâche 4 — sans risque, `lint-imports` ignore une exemption qui ne correspond à aucune arête réelle du graphe actuel.

- [ ] **Step 8: Run et confirmer le succès, y compris les tests de la Tâche 1**

```bash
cd core
uv run pytest tests/test_users_repository_roles.py tests/test_admin_bootstrap.py tests/test_roles_repository.py tests/test_roles_guards.py -v
```
Expected: tous PASS, y compris les deux tests de `test_roles_repository.py` laissés en suspens Tâche 1 Step 7 (`test_count_role_holders`, `test_count_users_with_privileges_and_orphan_detection`).

- [ ] **Step 9: Lint et commit**

```bash
cd core
uv run ruff check app/users app/db.py tests/test_users_repository_roles.py tests/test_admin_bootstrap.py
uv run ruff format app/users tests/test_users_repository_roles.py tests/test_admin_bootstrap.py
git add app/users pyproject.toml tests/test_users_repository_roles.py tests/test_admin_bootstrap.py
git rm core/tests/test_users_analyst.py  # si pas déjà indexé par Step 6
git commit -m "feat(core): User.role_id remplace is_analyst — is_admin reste une colonne synchronisée"
```

---

## Task 3 : seed des rôles prédéfinis au moment de l'authentification

**Files:**
- Modify: `core/app/auth/dependency.py:132-153` (fonction `get_current_user`)
- Test: `core/tests/test_auth_dependency_roles.py`

**Interfaces:**
- Consumes: `app.roles.repository.ensure_built_in_roles` (Tâche 1).
- Produces: aucun changement de signature — `get_current_user` continue de garantir, pour tout appelant, que les 4 rôles prédéfinis du tenant courant existent avant de résoudre l'utilisateur.

**Pourquoi ici et pas seulement dans `get_or_create_user`** : `get_or_create_user` appelle déjà `ensure_built_in_roles` (Tâche 2) — cette tâche est donc surtout une garantie explicite et testée au bon niveau (le point d'entrée HTTP), pas une nouvelle dépendance technique. Elle documente l'invariant : par construction, aucun code après `get_current_user` ne peut observer un tenant sans ses 4 rôles.

- [ ] **Step 1: Écrire le test en échec**

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import list_roles
from app.tenants.repository import get_or_create_default_tenant


def test_a_fresh_tenant_gets_its_four_built_in_roles_on_first_authenticated_call(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        assert list_roles(s, tenant_id=tenant.id) == []

    assert client.get("/me").status_code == 200

    with Session() as s:
        slugs = {r.slug for r in list_roles(s, tenant_id=tenant.id)}
    assert slugs == {"admin", "creator", "analyst", "reader"}
```

- [ ] **Step 2: Confirmer l'échec ou le succès inattendu**

Run: `cd core && uv run pytest tests/test_auth_dependency_roles.py -v`
Expected: déjà PASS si Tâche 2 est complète (`get_or_create_user` appelle `ensure_built_in_roles`) — dans ce cas, ce test documente l'invariant sans changement de code, ce qui est acceptable : passer directement au Step 4 sans modifier `dependency.py`. Si un chemin d'authentification existe qui n'appelle PAS `get_or_create_user` avant de toucher aux rôles (aucun connu à l'écriture de ce plan), ajouter `ensure_built_in_roles(session, tenant_id=tenant.id)` juste après la ligne `tenant = get_or_create_default_tenant(session)` dans `get_current_user` (`core/app/auth/dependency.py:136`), avec l'import `from app.roles.repository import ensure_built_in_roles` en tête de fichier.

- [ ] **Step 3: Commit**

```bash
cd core
uv run ruff check tests/test_auth_dependency_roles.py app/auth/dependency.py
git add tests/test_auth_dependency_roles.py app/auth/dependency.py
git commit -m "test(core): documente l'invariant — un tenant authentifié a toujours ses 4 rôles prédéfinis"
```

---

## Task 4 : `app/auth/routes.py` — `/me`, `/users`, `PATCH /users/{id}` sur les rôles

**Files:**
- Modify: `core/app/auth/routes.py` (fichier entier, 179 lignes actuelles)
- Modify: `core/pyproject.toml` (`ignore_imports`)
- Modify: `core/tests/test_users_admin_routes.py`
- Modify: `core/tests/test_auth_me_capabilities.py`

**Interfaces:**
- Consumes: `app.roles.repository.get_role`, `count_users_with_privileges` (Tâche 1) ; `app.roles.guards.require_privilege` (Tâche 1) ; `app.roles.privileges.Privilege` (Tâche 1) ; `app.users.repository.set_user_role` (Tâche 2).
- Produces: `MeResponse.role: {id, name, slug}`, `MeResponse.privileges: list[str]` (remplacent `isAdmin`/`isAnalyst`/`hasAnyEditorRole`). `PATCH /users/{id}` prend désormais `{"roleId": str}` (remplace `{"isAdmin": bool, "isAnalyst": bool}`).

**Deux exemptions de couches supplémentaires nécessaires** (même raisonnement que Tâche 2 Step 7 — `app.auth.routes` est SOUS `app.roles`, mais `/me`/`/users` doivent lire les rôles) :

```toml
    "app.auth.routes -> app.roles.repository",
    "app.auth.routes -> app.roles.privileges",
    "app.auth.routes -> app.roles.guards",
```

- [ ] **Step 1: Mettre à jour `test_users_admin_routes.py` pour le nouveau contrat (`roleId`)**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="regular", email=None,
            first_name="", last_name="",
        )
        s.commit()
        role_ids = {slug: role.id for slug, role in roles.items()}
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_users_requires_admin_users_manage(env):
    app, client, _, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/users").status_code == 403
    _as(app, admin)
    body = client.get("/users").json()
    assert body["total"] == 2
    assert {u["username"] for u in body["users"]} == {"admin", "regular"}


def test_promote_then_demote_via_role_id(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    r = client.patch(f"/users/{regular.id}", json={"roleId": roles["admin"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "admin"
    r = client.patch(f"/users/{regular.id}", json={"roleId": roles["reader"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "reader"


def test_last_admin_cannot_be_demoted(env):
    app, client, _, admin, _regular, roles = env
    _as(app, admin)
    assert client.patch(f"/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 409


def test_patch_unknown_user_404_and_non_admin_403(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    assert client.patch("/users/nope", json={"roleId": roles["admin"]}).status_code == 404
    _as(app, regular)
    assert client.patch(f"/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 403


def test_patch_user_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular, roles = env
    with Session() as s:
        other_tenant = Tenant(
            id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other"
        )
        s.add(other_tenant)
        s.flush()
        outsider = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="sub-outsider", username="outsider",
            email=None, first_name="", last_name="",
        )
        s.commit()
        s.refresh(outsider)

    _as(app, admin)
    assert client.patch(f"/users/{outsider.id}", json={"roleId": roles["admin"]}).status_code == 404


def test_role_change_is_audited(env):
    app, client, Session, admin, regular, roles = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"roleId": roles["admin"]})
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "user.role_change" in actions


def test_patch_user_rejects_an_unknown_role_id(env):
    app, client, _, admin, regular, _roles = env
    _as(app, admin)
    assert client.patch(f"/users/{regular.id}", json={"roleId": "nope"}).status_code == 400
```

- [ ] **Step 2: Confirmer l'échec**

Run: `cd core && uv run pytest tests/test_users_admin_routes.py -v` → FAIL (route actuelle attend `isAdmin`/`isAnalyst`, répond avec ces champs, pas `roleSlug`)

- [ ] **Step 3: Mettre à jour `test_auth_me_capabilities.py`**

Remplacer (lignes 80-94 et 103-107 du fichier actuel) :

```python
def test_me_keeps_its_existing_fields(client):
    body = client.get("/me").json()
    for key in (
        "id", "tenantId", "username", "email", "firstName", "lastName", "role", "privileges",
    ):
        assert key in body, f"champ disparu de MeResponse : {key}"
    assert set(body["role"]) == {"id", "name", "slug"}


def test_me_exposes_tenant_slug_and_version(client):
    body = client.get("/me").json()
    assert isinstance(body["tenantSlug"], str) and body["tenantSlug"] != ""
    assert isinstance(body["version"], str) and body["version"] != ""
```

(Le docstring de `test_me_keeps_its_existing_fields` mentionnant « quinze endroits » est retiré avec le test lui-même — c'était une note de suivi shell, plus pertinente une fois la Tâche 15 faite.)

- [ ] **Step 4: Réécrire `core/app/auth/routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import (
    get_current_user,
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import count_users_with_privileges, get_role
from app.tenants.models import Tenant
from app.users.models import User
from app.users.repository import list_users, set_user_role

router = APIRouter()


class MeCapabilities(BaseModel):
    """Les capacités du déploiement, servies avec le profil.

    Même contenu que `GET /instance`, qui reste servi sans authentification
    (page de connexion, mode démo). Le doublon est délibéré : le shell dérive
    l'état de ses domaines d'un profil unique (spec §6.6) au lieu de croiser
    deux requêtes dans chaque écran. `tests/test_auth_me_capabilities.py`
    interdit aux deux routes de diverger.
    """

    readOnly: bool
    etlEnabled: bool
    exportEnabled: bool
    appExportEnabled: bool
    tileset3dEnabled: bool
    terrain3dEnabled: bool
    copilotEnabled: bool
    adminToolsEnabled: bool


class RoleSummary(BaseModel):
    id: str
    name: str
    slug: str


class MeResponse(BaseModel):
    id: str
    tenantId: str
    tenantSlug: str
    username: str
    email: str | None
    firstName: str
    lastName: str
    role: RoleSummary
    privileges: list[str]
    version: str
    capabilities: MeCapabilities


@router.get("/me", response_model=MeResponse)
def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    tenant = session.get(Tenant, user.tenant_id)
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    assert role is not None  # role_id est NOT NULL, jamais orphelin (suppression bloquée si en usage)
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        tenantSlug=tenant.slug if tenant is not None else user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        role=RoleSummary(id=role.id, name=role.name, slug=role.slug),
        privileges=role.privileges,
        version=request.app.version,
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
            adminToolsEnabled=is_admin_tools_enabled(),
        ),
    )


class UserRolePatch(BaseModel):
    roleId: str


def _user_json(user: User, role_slug: str) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "roleSlug": role_slug}


@router.get("/users")
def get_users(
    page: int = 1,
    pageSize: int = 50,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    users, total = list_users(session, tenant_id=user.tenant_id, page=page, page_size=pageSize)
    result = []
    for u in users:
        role = get_role(session, tenant_id=user.tenant_id, role_id=u.role_id)
        result.append(_user_json(u, role.slug if role is not None else ""))
    return {"users": result, "total": total}


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserRolePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    new_role = get_role(session, tenant_id=user.tenant_id, role_id=body.roleId)
    if new_role is None:
        raise HTTPException(status_code=400, detail="role not found")
    needed = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]
    current_role = get_role(session, tenant_id=user.tenant_id, role_id=target.role_id)
    if (
        current_role is not None
        and set(needed).issubset(set(current_role.privileges))
        and not set(needed).issubset(set(new_role.privileges))
        and count_users_with_privileges(session, tenant_id=user.tenant_id, privileges=needed) == 1
    ):
        raise HTTPException(status_code=409, detail="cannot leave the tenant without an admin")
    set_user_role(
        session, tenant_id=user.tenant_id, user_id=user_id, role_id=body.roleId,
        role_slug=new_role.slug,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="user.role_change",
        object_type="user",
        object_id=user_id,
        payload={"roleId": body.roleId},
    )
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:  # pragma: no cover - existence already proven above
        raise HTTPException(status_code=404, detail="user not found")
    return _user_json(target, new_role.slug)
```

- [ ] **Step 5: Ajouter les 3 exemptions de couches**

Dans `core/pyproject.toml`, `ignore_imports`, juste après `"app.auth.routes -> app.sharing.repository",` :

```toml
    # app.roles doit être AU-DESSUS d'app.auth (ses propres routes ont
    # besoin de get_current_user), mais /me et PATCH /users/{id}
    # (app.auth.routes, EN DESSOUS) doivent lire le rôle et les privilèges de
    # l'appelant/de la cible. Même classe de tension que l'exemption
    # ci-dessus (app.sharing) : aucune place linéaire ne satisfait les deux
    # sens à la fois. Seules ces trois arêtes sont autorisées.
    "app.auth.routes -> app.roles.repository",
    "app.auth.routes -> app.roles.privileges",
    "app.auth.routes -> app.roles.guards",
```

- [ ] **Step 6: Run la suite complète auth + roles**

```bash
cd core
uv run pytest tests/test_users_admin_routes.py tests/test_auth_me_capabilities.py tests/test_roles_repository.py tests/test_roles_guards.py tests/test_users_repository_roles.py tests/test_admin_bootstrap.py -v
uv run lint-imports
```
Expected: tous PASS, `lint-imports` vert.

- [ ] **Step 7: Lint et commit**

```bash
cd core
uv run ruff check app/auth tests/test_users_admin_routes.py tests/test_auth_me_capabilities.py
uv run ruff format app/auth tests/test_users_admin_routes.py tests/test_auth_me_capabilities.py
git add app/auth pyproject.toml tests/test_users_admin_routes.py tests/test_auth_me_capabilities.py
git commit -m "feat(core): /me et /users exposent role+privileges — PATCH /users/{id} prend roleId"
```

---

## Task 5 : `app/roles/routes.py` — CRUD des rôles + catalogue de privilèges

**Files:**
- Create: `core/app/roles/schemas.py`
- Create: `core/app/roles/routes.py`
- Modify: `core/app/main.py` (import + `include_router`)
- Modify: `core/pyproject.toml` (`layers` + `ignore_imports` pour `app.db`)
- Test: `core/tests/test_roles_routes.py`

**Interfaces:**
- Consumes: tout `app.roles.repository`/`guards`/`privileges` (Tâche 1).
- Produces: `GET /roles/catalog`, `GET /roles`, `POST /roles`, `PATCH /roles/{role_id}`, `DELETE /roles/{role_id}` — tous gardés par `admin.roles.manage`.

- [ ] **Step 1: Insérer `app.roles` dans `layers` et ajouter l'exemption `app.db`**

Dans `core/pyproject.toml`, `layers` (ligne 225, entre `"app.instance",` et `"app.auth",`) :

```toml
    "app.instance",
    "app.roles",
    "app.auth",
```

Et dans `ignore_imports`, à la fin de la liste (après `"app.db -> app.mapicons.models",`) :

```toml
    "app.db -> app.roles.models",
```

- [ ] **Step 2: Écrire `app/roles/schemas.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class RoleRead(BaseModel):
    id: str
    name: str
    slug: str
    isBuiltIn: bool
    privileges: list[str]


class RoleCreate(BaseModel):
    name: str
    privileges: list[str]


class RolePatch(BaseModel):
    name: str | None = None
    privileges: list[str] | None = None


class PrivilegeCatalogEntry(BaseModel):
    privilege: str
    domain: str
    labelKey: str
```

- [ ] **Step 3: Écrire le test en échec `core/tests/test_roles_routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="regular", email=None,
            first_name="", last_name="",
        )
        s.commit()
        role_ids = {slug: role.id for slug, role in roles.items()}
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_catalog_lists_every_privilege_and_requires_admin_roles_manage(env):
    app, client, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/roles/catalog").status_code == 403
    _as(app, admin)
    body = client.get("/roles/catalog").json()
    assert len(body) == len(list(Privilege))
    assert {"privilege", "domain", "labelKey"} <= set(body[0])


def test_list_roles_includes_the_four_built_in(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    body = client.get("/roles").json()
    assert {r["slug"] for r in body} == {"admin", "creator", "analyst", "reader"}
    assert all(r["isBuiltIn"] for r in body)


def test_create_edit_delete_a_custom_role(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    created = client.post(
        "/roles", json={"name": "Support moissonnage", "privileges": ["admin.harvest.manage"]}
    ).json()
    assert created["isBuiltIn"] is False

    patched = client.patch(
        f"/roles/{created['id']}",
        json={"privileges": ["admin.harvest.manage", "admin.collections.manage"]},
    ).json()
    assert len(patched["privileges"]) == 2

    assert client.delete(f"/roles/{created['id']}").status_code == 204
    assert created["id"] not in {r["id"] for r in client.get("/roles").json()}


def test_a_built_in_role_cannot_be_edited_or_deleted(env):
    app, client, admin, _regular, roles = env
    _as(app, admin)
    assert client.patch(f"/roles/{roles['reader']}", json={"name": "x"}).status_code == 400
    assert client.delete(f"/roles/{roles['admin']}").status_code == 400


def test_deleting_a_role_still_in_use_is_blocked(env):
    app, client, admin, regular, roles = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"roleId": roles["reader"]})
    assert client.delete(f"/roles/{roles['reader']}").status_code in (400, 409)


def test_removing_admin_roles_manage_from_the_only_holder_is_blocked(env):
    app, client, admin, _regular, roles = env
    _as(app, admin)
    resp = client.patch(f"/roles/{roles['admin']}", json={"privileges": ["catalog.manage"]})
    assert resp.status_code == 409
```

- [ ] **Step 4: Confirmer l'échec**

Run: `cd core && uv run pytest tests/test_roles_routes.py -v` → FAIL (`ModuleNotFoundError: app.roles.routes`)

- [ ] **Step 5: Écrire `app/roles/routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import ALL_PRIVILEGE_VALUES, Privilege
from app.roles.repository import (
    count_role_holders,
    create_role,
    delete_role,
    get_privilege_catalog,
    get_role,
    list_roles,
    update_role,
    would_orphan_privilege_holders,
)
from app.roles.schemas import PrivilegeCatalogEntry, RoleCreate, RolePatch, RoleRead
from app.users.models import User

router = APIRouter()

_ANTI_LOCKOUT_PRIVILEGES = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]


def _role_json(role) -> RoleRead:
    return RoleRead(
        id=role.id, name=role.name, slug=role.slug, isBuiltIn=role.is_built_in,
        privileges=role.privileges,
    )


@router.get("/roles/catalog", response_model=list[PrivilegeCatalogEntry])
def get_roles_catalog(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[PrivilegeCatalogEntry]:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    return [PrivilegeCatalogEntry(**entry) for entry in get_privilege_catalog()]


@router.get("/roles", response_model=list[RoleRead])
def get_roles(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[RoleRead]:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    return [_role_json(r) for r in list_roles(session, tenant_id=user.tenant_id)]


@router.post("/roles", response_model=RoleRead, status_code=201)
def post_role(
    body: RoleCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoleRead:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    unknown = set(body.privileges) - set(ALL_PRIVILEGE_VALUES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown privileges: {sorted(unknown)}")
    role = create_role(session, tenant_id=user.tenant_id, name=body.name, privileges=body.privileges)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="role.create", object_type="role", object_id=role.id,
        payload={"name": role.name, "privileges": role.privileges},
    )
    return _role_json(role)


@router.patch("/roles/{role_id}", response_model=RoleRead)
def patch_role(
    role_id: str,
    body: RolePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoleRead:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    role = get_role(session, tenant_id=user.tenant_id, role_id=role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    if role.is_built_in:
        raise HTTPException(status_code=400, detail="a built-in role cannot be edited")
    if body.privileges is not None:
        unknown = set(body.privileges) - set(ALL_PRIVILEGE_VALUES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown privileges: {sorted(unknown)}")
        if set(_ANTI_LOCKOUT_PRIVILEGES).issubset(set(role.privileges)) and would_orphan_privilege_holders(
            session, tenant_id=user.tenant_id, privileges=_ANTI_LOCKOUT_PRIVILEGES,
            role_id=role.id, new_privileges=body.privileges,
        ):
            raise HTTPException(
                status_code=409,
                detail="this change would leave the tenant without anyone able to manage users/roles",
            )
    updated = update_role(
        session, tenant_id=user.tenant_id, role_id=role_id, name=body.name,
        privileges=body.privileges,
    )
    if updated is None:  # pragma: no cover - existence already proven above
        raise HTTPException(status_code=404, detail="role not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="role.update", object_type="role", object_id=role_id,
        payload={"name": body.name, "privileges": body.privileges},
    )
    return _role_json(updated)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role_route(
    role_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    role = get_role(session, tenant_id=user.tenant_id, role_id=role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    if role.is_built_in:
        raise HTTPException(status_code=400, detail="a built-in role cannot be deleted")
    holders = count_role_holders(session, tenant_id=user.tenant_id, role_id=role_id)
    if holders > 0:
        raise HTTPException(status_code=409, detail=f"{holders} user(s) still have this role")
    delete_role(session, tenant_id=user.tenant_id, role_id=role_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="role.delete", object_type="role", object_id=role_id, payload={},
    )
```

- [ ] **Step 6: Monter le routeur dans `app/main.py`**

Ajouter l'import (ordre alphabétique, entre `app.reports` et `app.schemas_routes`) :

```python
from app.roles import routes as roles_routes
```

Et le montage (à côté de `app.include_router(secrets_routes.router)` ou de tout autre routeur simple, sans configuration spéciale) :

```python
    app.include_router(roles_routes.router)
```

- [ ] **Step 7: Run et vérifier**

```bash
cd core
uv run pytest tests/test_roles_routes.py -v
uv run lint-imports
```
Expected: 6 tests PASS, `lint-imports` vert (le graphe réel correspond maintenant aux 4 nouvelles exemptions + l'insertion `app.roles`).

- [ ] **Step 8: Lint et commit**

```bash
cd core
uv run ruff check app/roles app/main.py tests/test_roles_routes.py
uv run ruff format app/roles app/main.py tests/test_roles_routes.py
git add app/roles app/main.py pyproject.toml tests/test_roles_routes.py
git commit -m "feat(core): routes CRUD /roles + catalogue /roles/catalog, gardées par admin.roles.manage"
```

---

## Task 6 : migration Alembic 0030

**Files:**
- Create: `core/alembic/versions/0030_roles.py`
- Test: `core/tests/test_roles_migration.py`

**Interfaces:**
- Produces (fonctions nommées, appelables hors contexte Alembic — patron `0028_collection_spatial_index.py`) : `seed_built_in_roles(conn) -> None`, `migrate_users_to_roles(conn) -> None`, `migrate_roles_to_booleans(conn) -> None`.

**Note technique importante** : `upgrade()`/`downgrade()` utilisent `op.create_table`/`op.add_column`/`op.drop_column` (API Alembic, nécessite un contexte de migration réel — pas testable en appelant directement `mod.upgrade()` depuis un test, exactement comme `0028`). Les trois fonctions ci-dessus, elles, ne prennent qu'une connexion brute (`conn.execute(text(...))`) et sont testables directement — c'est sur elles que porte le test, pas sur `upgrade()`/`downgrade()` eux-mêmes (dont la responsabilité — créer/retirer une table/colonne — est déléguée à Alembic, déjà éprouvé).

- [ ] **Step 1: Écrire `alembic/versions/0030_roles.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Table roles + users.role_id — remplace is_analyst comme source de vérité
du rôle (docs/superpowers/specs/2026-09-01-roles-privileges-design.md).

Chaque tenant existant reçoit sa propre copie des 4 rôles prédéfinis
(is_built_in=true, immuables en application — app/roles/routes.py).
users.is_admin RESTE une colonne synchronisée (pas supprimée) : ~20 lectures
existantes dans core/ la consomment comme signal, préservées à l'identique.
users.is_analyst, lui, disparaît (un seul consommateur, SQL Lab, remplacé
par require_privilege() — voir la tâche 11 du plan d'implémentation).

Testée dans les deux sens sur base non vide (piège n°8 de CLAUDE.md) —
tests/test_roles_migration.py appelle seed_built_in_roles/
migrate_users_to_roles/migrate_roles_to_booleans directement, hors
upgrade()/downgrade() (qui utilisent l'API `op`, non testable hors contexte
Alembic réel — même limite que 0028_collection_spatial_index.py).

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-02
"""

import json
import sys
import uuid
from pathlib import Path

# Cf. commentaire identique dans 0028_collection_spatial_index.py : nécessaire
# pour que `alembic heads`/`history` (qui chargent les fichiers de versions/
# directement, sans exécuter env.py) trouvent `app.roles.privileges`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op
from app.roles.privileges import BUILT_IN_ROLE_NAMES, BUILT_IN_ROLE_PRIVILEGES

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def seed_built_in_roles(conn) -> None:
    tenant_ids = [row[0] for row in conn.execute(text("SELECT id FROM tenants")).all()]
    for tenant_id in tenant_ids:
        existing_slugs = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT slug FROM roles WHERE tenant_id = :tenant_id AND is_built_in = true"
                ),
                {"tenant_id": tenant_id},
            ).all()
        }
        for slug, privileges in BUILT_IN_ROLE_PRIVILEGES.items():
            if slug in existing_slugs:
                continue
            conn.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) VALUES "
                    "(:id, :tenant_id, :name, :slug, :is_built_in, :privileges, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid.uuid4().hex,
                    "tenant_id": tenant_id,
                    "name": BUILT_IN_ROLE_NAMES[slug],
                    "slug": slug,
                    "is_built_in": True,
                    "privileges": json.dumps(privileges),
                },
            )


def migrate_users_to_roles(conn) -> None:
    role_id_by_tenant_and_slug: dict[tuple[str, str], str] = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            text("SELECT tenant_id, slug, id FROM roles WHERE is_built_in = true")
        ).all()
    }
    users = conn.execute(text("SELECT id, tenant_id, is_admin, is_analyst FROM users")).all()
    for user_id, tenant_id, is_admin, is_analyst in users:
        if is_admin:
            slug = "admin"
        elif is_analyst:
            slug = "analyst"
        else:
            slug = "creator"
        role_id = role_id_by_tenant_and_slug[(tenant_id, slug)]
        conn.execute(
            text("UPDATE users SET role_id = :role_id WHERE id = :user_id"),
            {"role_id": role_id, "user_id": user_id},
        )


def migrate_roles_to_booleans(conn) -> None:
    """Inverse de migrate_users_to_roles, pour downgrade() — limite acceptée
    (design §2) : un rôle sur mesure créé après l'upgrade n'a pas d'équivalent
    booléen, ses porteurs redeviennent is_admin=False/is_analyst=False."""
    role_slug_by_id: dict[str, str] = {
        row[0]: row[1] for row in conn.execute(text("SELECT id, slug FROM roles")).all()
    }
    users = conn.execute(text("SELECT id, role_id FROM users")).all()
    for user_id, role_id in users:
        slug = role_slug_by_id.get(role_id, "")
        conn.execute(
            text(
                "UPDATE users SET is_admin = :is_admin, is_analyst = :is_analyst "
                "WHERE id = :user_id"
            ),
            {"is_admin": slug == "admin", "is_analyst": slug == "analyst", "user_id": user_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    op.create_table(
        "roles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("privileges", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_slug"),
    )
    seed_built_in_roles(conn)
    op.add_column(
        "users", sa.Column("role_id", sa.String(), sa.ForeignKey("roles.id"), nullable=True)
    )
    migrate_users_to_roles(conn)
    op.alter_column("users", "role_id", nullable=False)
    op.drop_column("users", "is_analyst")


def downgrade() -> None:
    conn = op.get_bind()
    op.add_column(
        "users", sa.Column("is_analyst", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    migrate_roles_to_booleans(conn)
    op.drop_column("users", "role_id")
    op.drop_table("roles")
```

- [ ] **Step 2: Écrire le test en échec `core/tests/test_roles_migration.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import pathlib

from sqlalchemy import text

from app.db import Base, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _import_0030():
    """alembic/versions n'est pas un paquet importable par son nom :
    chargement direct par chemin de fichier (patron identique à
    tests/test_collections_spatial_index.py::_import_0028)."""
    path = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "0030_roles.py"
    spec = importlib.util.spec_from_file_location("mig_0030", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_migrate_and_revert_on_a_non_empty_database(pg_engine):
    Base.metadata.create_all(pg_engine)  # forme actuelle (post-migration) : roles + users.role_id
    Session_ = make_session_factory(pg_engine)
    mod = _import_0030()

    with Session_() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="mig-a", username="mig-a", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        analyst = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="mig-b", username="mig-b", email=None,
            first_name="", last_name="", bootstrap_analyst=True,
        )
        plain = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="mig-c", username="mig-c", email=None,
            first_name="", last_name="",
        )
        s.commit()
        admin_id, analyst_id, plain_id, tenant_id = admin.id, analyst.id, plain.id, tenant.id

    try:
        with pg_engine.begin() as conn:
            # Repart d'un état "à l'ancienne" : rôles absents, role_id nul,
            # is_admin/is_analyst posés directement (comme juste après
            # op.add_column("users", "role_id", nullable=True), avant tout
            # backfill).
            conn.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": tenant_id})
            conn.execute(
                text("UPDATE users SET role_id = NULL WHERE tenant_id = :t"), {"t": tenant_id}
            )
            conn.execute(
                text(
                    "UPDATE users SET is_admin = true, is_analyst = false "
                    "WHERE id = :id"
                ),
                {"id": admin_id},
            )
            conn.execute(
                text(
                    "UPDATE users SET is_admin = false, is_analyst = true WHERE id = :id"
                ),
                {"id": analyst_id},
            )
            conn.execute(
                text(
                    "UPDATE users SET is_admin = false, is_analyst = false WHERE id = :id"
                ),
                {"id": plain_id},
            )

            mod.seed_built_in_roles(conn)
            role_ids = {
                row[0]: row[1]
                for row in conn.execute(
                    text("SELECT slug, id FROM roles WHERE tenant_id = :t"), {"t": tenant_id}
                ).all()
            }
            assert set(role_ids) == {"admin", "creator", "analyst", "reader"}

            mod.migrate_users_to_roles(conn)
            assigned = dict(
                conn.execute(
                    text("SELECT id, role_id FROM users WHERE tenant_id = :t"), {"t": tenant_id}
                ).all()
            )
            assert assigned[admin_id] == role_ids["admin"]
            assert assigned[analyst_id] == role_ids["analyst"]
            assert assigned[plain_id] == role_ids["creator"]

            # Downgrade : efface is_admin/is_analyst, les redérive de role_id.
            conn.execute(
                text("UPDATE users SET is_admin = false, is_analyst = false WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            mod.migrate_roles_to_booleans(conn)
            reverted = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    text(
                        "SELECT id, is_admin, is_analyst FROM users WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                ).all()
            }
            assert reverted[admin_id] == (True, False)
            assert reverted[analyst_id] == (False, True)
            assert reverted[plain_id] == (False, False)
    finally:
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM users WHERE id IN (:a, :b, :c)"),
                {"a": admin_id, "b": analyst_id, "c": plain_id},
            )
            conn.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": tenant_id})
```

- [ ] **Step 3: Confirmer l'échec puis le succès**

Run: `cd core && CORE_TEST_DATABASE_URL=<url du postgis de test> uv run pytest tests/test_roles_migration.py -v`
Expected: FAIL d'abord (`alembic/versions/0030_roles.py` n'existe pas encore si l'ordre des steps est inversé — sinon PASS directement puisque Step 1 précède). Si le fixture `pg_engine` skip (`CORE_TEST_DATABASE_URL` non défini), documenter le skip dans le commit plutôt que forcer — cohérent avec le reste de la suite (piège déjà connu, cf. `conftest.py:29`).

**Si un test échoue sur une colonne/contrainte inattendue** (ex. `Base.metadata.create_all()` a évolué depuis l'écriture de ce plan) : vérifier contre `core/app/users/models.py`/`core/app/roles/models.py` réels (Tâches 1-2) avant d'ajuster le SQL brut du test — piège n°3 de CLAUDE.md, le texte littéral d'un plan est régulièrement faux sur ce genre de détail, corriger sans re-demander.

- [ ] **Step 4: Lint et commit**

```bash
cd core
uv run ruff check alembic/versions/0030_roles.py tests/test_roles_migration.py
uv run ruff format alembic/versions/0030_roles.py tests/test_roles_migration.py
git add alembic/versions/0030_roles.py tests/test_roles_migration.py
git commit -m "feat(core): migration 0030 — table roles + users.role_id, testée dans les deux sens"
```

---

## Task 7 : `app/extensions/routes.py` sur `require_privilege`

**Files:**
- Modify: `core/app/extensions/routes.py:15,41,78`
- Test: `core/tests/test_extensions_routes.py` (déjà lu pendant la préparation de ce plan — lignes 74 et 99 attendent `403` avec un utilisateur non-admin (`bootstrap_admin` non passé) ; ces assertions ne changent pas, `require_privilege` lève la même `HTTPException(403)`)

**Interfaces:**
- Consumes: `app.roles.guards.require_privilege`, `app.roles.privileges.Privilege.ADMIN_EXTENSIONS_MANAGE`.

**Aucune modification de test attendue dans cette tâche** : `test_extensions_routes.py` fabrique déjà ses utilisateurs via `get_or_create_user(bootstrap_admin=True)` (signature inchangée depuis la Tâche 2) et n'affirme que le code HTTP — le mécanisme interne change, l'observable non. Le Step 1 ci-dessous ne fait donc que confirmer l'état AVANT le refactor, pour détecter immédiatement si cette hypothèse était fausse.

- [ ] **Step 1: Confirmer que la suite est verte avant toute modification**

```bash
cd core && uv run pytest tests/test_extensions_routes.py -v
```
Expected: PASS (état actuel, avant refactor).

- [ ] **Step 2: Remplacer `_require_admin` dans `app/extensions/routes.py`**

Supprimer (ligne 15) :
```python
def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
```

Ajouter l'import :
```python
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
```

Remplacer les deux appels (lignes 41, 78) :
```python
    require_privilege(session, user, Privilege.ADMIN_EXTENSIONS_MANAGE.value)
```

(Vérifier que `session: Session` est bien un paramètre disponible à ces deux emplacements — déjà confirmé par lecture directe du fichier avant l'écriture de ce plan.)

- [ ] **Step 3: Run et confirmer**

```bash
cd core && uv run pytest tests/test_extensions*.py -v
```
Expected: tous PASS, sans changement d'assertion.

- [ ] **Step 4: Lint et commit**

```bash
cd core
uv run ruff check app/extensions
uv run ruff format app/extensions
git add app/extensions
git commit -m "refactor(core): app.extensions — _require_admin remplacé par require_privilege(admin.extensions.manage)"
```

---

## Task 8 : `app/harvest/routes.py` sur `require_privilege` (6 sites)

**Files:**
- Modify: `core/app/harvest/routes.py:44,131,158,201,215,244,268`
- Test: `core/tests/test_harvest_routes.py` (fixtures `bootstrap_admin=True`/non-admin déjà en place, signature inchangée depuis la Tâche 2 — aucune modification de test attendue, mêmes codes HTTP)

**Interfaces:**
- Consumes: `app.roles.guards.require_privilege`, `app.roles.privileges.Privilege.ADMIN_HARVEST_MANAGE`.

- [ ] **Step 1: Confirmer que la suite est verte avant toute modification**

```bash
cd core && uv run pytest tests/test_harvest_routes.py -v
```
Expected: PASS (état actuel, avant refactor).

- [ ] **Step 2: Remplacer `_require_admin` dans `app/harvest/routes.py`**

Supprimer la définition (ligne 44) :
```python
def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
```

Ajouter l'import (avec les imports existants `from app.auth.dependency import get_current_user`) :
```python
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
```

Remplacer les 6 appels (lignes 131, 158, 201, 215, 244, 268) — chacun devient :
```python
    require_privilege(session, user, Privilege.ADMIN_HARVEST_MANAGE.value)
```

- [ ] **Step 3: Run et confirmer**

```bash
cd core && uv run pytest tests/test_harvest*.py -v
```
Expected: tous PASS.

- [ ] **Step 4: Lint et commit**

```bash
cd core
uv run ruff check app/harvest
uv run ruff format app/harvest
git add app/harvest
git commit -m "refactor(core): app.harvest — _require_admin remplacé par require_privilege(admin.harvest.manage), 6 routes"
```

---

## Task 9 : `app/secrets/routes.py` sur `require_privilege`

**Files:**
- Modify: `core/app/secrets/routes.py:22,51,97,107`
- Test: `core/tests/test_secrets_routes.py` (déjà lu intégralement pendant la préparation de ce plan — fixture `env()`/`_as()` réutilisable sans changement)

**Interfaces:**
- Consumes: `app.roles.guards.require_privilege`, `app.roles.privileges.Privilege.ADMIN_SECRETS_MANAGE`.

- [ ] **Step 1: Remplacer `_require_admin` dans `app/secrets/routes.py`**

Supprimer (ligne 22) :
```python
def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
```

Ajouter l'import :
```python
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
```

Remplacer les 3 appels (lignes 51, 97, 107) :
```python
    require_privilege(session, user, Privilege.ADMIN_SECRETS_MANAGE.value)
```

- [ ] **Step 2: Run et confirmer**

```bash
cd core && uv run pytest tests/test_secrets_routes.py -v
```
Expected: `test_create_requires_admin` et le reste de la suite PASS sans changement.

- [ ] **Step 3: Lint et commit**

```bash
cd core
uv run ruff check app/secrets
uv run ruff format app/secrets
git add app/secrets
git commit -m "refactor(core): app.secrets — _require_admin remplacé par require_privilege(admin.secrets.manage)"
```

---

## Task 10 : `app/collections/routes.py` sur `require_privilege` + docstring `CollectionPermissions`

**Files:**
- Modify: `core/app/collections/routes.py:136,175,294,439`
- Modify: `core/app/collections/schemas.py:17-27` (docstring `CollectionPermissions`)
- Test: `core/tests/test_collections_routes.py` (lignes 82, 257, 380 attendent `403` avec un utilisateur non-admin ; fixtures `bootstrap_admin=True` déjà en place, signature inchangée — aucune modification de test attendue)

**Interfaces:**
- Consumes: `app.roles.guards.require_privilege`, `app.roles.privileges.Privilege.ADMIN_COLLECTIONS_MANAGE`.

**Rappel du piège déjà payé deux fois sur ce dépôt (SP-30g, SP-30i)** : un commentaire qui attribue une garde de sécurité au mauvais mécanisme après un déplacement. La docstring de `CollectionPermissions` nomme `_require_admin` explicitement — elle DOIT changer dans ce même commit, pas après.

- [ ] **Step 1: Confirmer que la suite est verte avant toute modification**

```bash
cd core && uv run pytest tests/test_collections_routes.py -v
```
Expected: PASS (état actuel, avant refactor).

- [ ] **Step 2: Remplacer `_require_admin` dans `app/collections/routes.py`**

Supprimer (ligne 136) :
```python
def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
```

Ajouter l'import :
```python
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
```

Remplacer les 3 appels (lignes 175, 294, 439 — le commentaire existant sur la ligne 439, `# après le 404 : un non-admin qui la voit reçoit 403`, reste pertinent, à conserver) :
```python
    require_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
```

- [ ] **Step 3: Corriger la docstring de `CollectionPermissions`**

Dans `core/app/collections/schemas.py:17-27`, remplacer :

```python
class CollectionPermissions(BaseModel):
    """Miroir d'`ItemPermissions` (`app/items/schemas.py`) pour les
    collections. Calculé depuis `decide()`, jamais recalculé côté client.

    `delete` n'est PAS le verdict générique de `decide()` : `unregister_collection`
    (DELETE /collections/{id}) est gardé par `require_privilege(...,
    "admin.collections.manage")` seul, pas par `can()`/`decide()` — refléter
    autre chose que ce privilège ici afficherait un bouton Supprimer qui
    produit un 403 après clic pour un propriétaire ou un éditeur sans ce
    privilège.
    """

    read: bool
    write: bool
    delete: bool
    share: bool
```

- [ ] **Step 4: Run et confirmer**

```bash
cd core && uv run pytest tests/test_collections*.py -v
```
Expected: tous PASS.

- [ ] **Step 5: Lint et commit**

```bash
cd core
uv run ruff check app/collections
uv run ruff format app/collections
git add app/collections
git commit -m "refactor(core): app.collections — _require_admin remplacé par require_privilege(admin.collections.manage), docstring corrigée"
```

---

## Task 11 : `app/features/routes.py` — SQL Lab sur `require_privilege`

**Files:**
- Modify: `core/app/features/routes.py:430-436`
- Test: fichier de test SQL Lab existant (`grep -rl "analytics/sql\|analyst role required" core/tests/test_features*.py`)

**Interfaces:**
- Consumes: `app.roles.guards.require_privilege`, `app.roles.privileges.Privilege.ANALYTICS_SQL_LAB_ACCESS`.

**Dernier consommateur de `user.is_analyst`** — après cette tâche, `is_analyst` n'existe plus nulle part dans `core/` (déjà retiré du modèle Tâche 2 ; ce site était le seul à encore le lire jusqu'ici via le paramètre implicite, la colonne étant déjà supprimée depuis la Tâche 2 — **cette tâche doit donc suivre, pas précéder, la Tâche 2**, sans quoi le code actuel casserait à l'import).

- [ ] **Step 1: Remplacer le garde dans `app/features/routes.py`**

Remplacer (ligne 430-431) :
```python
    if not user.is_analyst:
        raise HTTPException(status_code=403, detail="analyst role required")
```

par :
```python
    require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)
```

Ajouter l'import en tête de fichier :
```python
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
```

(La ligne 436, `is_admin=user.is_admin`, reste inchangée — `is_admin` est un signal préservé, pas une garde, hors périmètre de cette tâche.)

- [ ] **Step 2: Run et confirmer**

```bash
cd core && uv run pytest tests/test_features*.py -v
```
Expected: tous PASS (le test qui postait avec un utilisateur non-analyste et attendait 403 reste vert — même code de retour, mécanisme interne changé).

- [ ] **Step 3: Lint, suite complète et commit**

```bash
cd core
uv run ruff check app/features
uv run ruff format app/features
uv run pytest  # suite complète — dernière tâche cœur avant l'API shell, piège n°6
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
git add app/features
git commit -m "refactor(core): SQL Lab — is_analyst remplacé par require_privilege(analytics.sql_lab.access), dernier consommateur"
```

---

## Task 12 : régénération OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json` (généré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (généré)

**Interfaces:**
- Consumes: toutes les routes modifiées/ajoutées par les Tâches 4, 5.
- Produces: les types TS pour `RoleRead`, `RoleCreate`, `RolePatch`, `PrivilegeCatalogEntry`, `MeResponse` mis à jour — consommés par la Tâche 13.

- [ ] **Step 1: Régénérer**

```bash
cd core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell
npm run gen:api-types
```

- [ ] **Step 2: Vérifier le diff**

```bash
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```
Expected: diff non vide, contenant `/roles`, `/roles/catalog`, et les nouveaux champs de `MeResponse` (`role`, `privileges`) — plus la disparition d'`isAdmin`/`isAnalyst`/`hasAnyEditorRole` du schéma `/me`.

- [ ] **Step 3: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore: régénère la spec OpenAPI et les types TS — routes /roles, MeResponse.role/privileges"
```

---

## Task 13 : shell — types, `ItemClient`, hooks, handlers MSW par défaut

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Test: `shell/src/api/itemClient.test.ts` (fichier existant — ajouter les cas `getMe`/roles au patron déjà en place)

**Interfaces:**
- Produces: `Me` (sans `isAdmin`/`isAnalyst`/`hasAnyEditorRole`, avec `role: {id,name,slug}` + `privileges: string[]`), `Role`, `PrivilegeCatalogEntry`, `RoleCreateInput`, `RolePatchInput` (types) ; `ItemClient.getMe/getPrivilegeCatalog/listRoles/createRole/updateRole/deleteRole` ; `useRolesCatalog()`, `useRoles(options?)`, `useCreateRole()`, `useUpdateRole(id)`, `useDeleteRole()` (hooks).
- Consumes: types générés (Tâche 12) — sert de référence, pas d'import direct obligatoire (le dépôt maintient `types.ts` à la main, cohérent avec le patron `HarvestSource` déjà en place).

**Décision de périmètre pour cette tâche** : `GET /users`/`PATCH /users/{id}` (réassignation de rôle à un utilisateur) **ne sont pas câblés côté shell** — aucune page ne les consomme aujourd'hui (vérifié par grep avant l'écriture de ce plan), et construire un écran de gestion des utilisateurs est hors périmètre du design (§1, « privilèges de rôle/fonctionnalité uniquement… l'écran de changement de rôle… à situer précisément au moment du plan » — tranché ici : follow-up, pas ce plan). `RolesAdminPage` (Tâche 16) gère uniquement la liste des rôles et leurs privilèges, pas leur attribution à une personne.

- [ ] **Step 1: Mettre à jour `shell/src/api/types.ts`**

Remplacer (lignes 42-51) :
```typescript
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
  isAnalyst: boolean;
  hasAnyEditorRole: boolean;
  version: string;
  tenantSlug: string;
};
```
par :
```typescript
export type RoleSummary = {
  id: string;
  name: string;
  slug: string;
};

export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  role: RoleSummary;
  privileges: string[];
  version: string;
  tenantSlug: string;
};

export type Role = {
  id: string;
  name: string;
  slug: string;
  isBuiltIn: boolean;
  privileges: string[];
};

export type PrivilegeCatalogEntry = {
  privilege: string;
  domain: string;
  labelKey: string;
};

export type RoleCreateInput = {
  name: string;
  privileges: string[];
};

export type RolePatchInput = {
  name?: string;
  privileges?: string[];
};
```

Ajouter à l'interface `ItemClient` (après `getMe(): Promise<Me>;`, ligne 246) :
```typescript
  getPrivilegeCatalog(): Promise<PrivilegeCatalogEntry[]>;
  listRoles(): Promise<Role[]>;
  createRole(input: RoleCreateInput): Promise<Role>;
  updateRole(id: string, patch: RolePatchInput): Promise<Role>;
  deleteRole(id: string): Promise<void>;
```

- [ ] **Step 2: Mettre à jour `shell/src/api/itemClient.ts`**

Remplacer `getMe()` (lignes 535-556) :
```typescript
    async getMe(): Promise<Me> {
      const data = await request<{
        username: string;
        firstName: string;
        lastName: string;
        role: RoleSummary;
        privileges: string[];
        version: string;
        tenantSlug: string;
      }>("GET", `/me`);
      return {
        username: data.username,
        firstName: data.firstName,
        lastName: data.lastName,
        role: data.role,
        privileges: data.privileges,
        version: data.version,
        tenantSlug: data.tenantSlug,
      };
    },
```

Ajouter juste après (avant `getInstanceInfo`) :
```typescript
    async getPrivilegeCatalog(): Promise<PrivilegeCatalogEntry[]> {
      return request<PrivilegeCatalogEntry[]>("GET", "/roles/catalog");
    },

    async listRoles(): Promise<Role[]> {
      return request<Role[]>("GET", "/roles");
    },

    async createRole(input: RoleCreateInput): Promise<Role> {
      return request<Role>("POST", "/roles", input);
    },

    async updateRole(id: string, patch: RolePatchInput): Promise<Role> {
      return request<Role>("PATCH", `/roles/${id}`, patch);
    },

    async deleteRole(id: string): Promise<void> {
      await request<void>("DELETE", `/roles/${id}`);
    },
```

(Vérifier la signature exacte de `request<T>(method, path, body?)` déjà utilisée par les autres mutations du fichier — ex. `createHarvestSource` — avant d'écrire ces cinq méthodes, pour rester au même patron.) Ajouter `RoleSummary`, `Role`, `PrivilegeCatalogEntry`, `RoleCreateInput`, `RolePatchInput` à l'import de types en tête de fichier.

- [ ] **Step 3: Ajouter les hooks dans `shell/src/api/hooks.ts`**

Après `useMe()` (ligne 45-48), sans le modifier (sa forme reste `useQuery({ queryKey: ["me"], queryFn: () => client.getMe() })` — seul le type `Me` retourné change, pas le hook) :

```typescript
export function useRolesCatalog() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["roles", "catalog"], queryFn: () => client.getPrivilegeCatalog() });
}

export function useRoles(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["roles"],
    queryFn: () => client.listRoles(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RoleCreateInput) => client.createRole(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useUpdateRole(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: RolePatchInput) => client.updateRole(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useDeleteRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteRole(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}
```

(Patron identique à `useHarvestSources`/`useCreateHarvestSource`/etc., déjà en place dans ce fichier — ajouter `RoleCreateInput`, `RolePatchInput` à l'import de types.)

- [ ] **Step 4: Mettre à jour le handler MSW par défaut**

Dans `shell/src/test/msw/handlers.ts`, remplacer le handler `GET /me` (lignes 29-43) :
```typescript
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1",
      username: "alice",
      firstName: "Alice",
      lastName: "Martin",
      email: "alice@example.com",
      tenantId: "t1",
      role: { id: "role-creator", name: "Créateur", slug: "creator" },
      privileges: ["catalog.manage", "maps.manage", "data.view", "data.manage"],
      version: "0.1.0",
      tenantSlug: "demo",
    }),
  ),
```

- [ ] **Step 5: Mettre à jour les deux tests `getMe` existants et ajouter la couverture des rôles dans `itemClient.test.ts`**

Les deux tests `getMe` déjà présents (lignes 49-70 et 72-87 du fichier actuel, lus intégralement pendant la préparation de ce plan) fixent encore `isAdmin`/`isAnalyst` en dur — ils cassent dès que le Step 2 change l'implémentation de `getMe()`. Les remplacer :

```typescript
test("getMe maps camelCase fields, dropping id/email/tenantId", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges: ["catalog.manage", "maps.manage"],
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me).toEqual({
    username: "alice",
    firstName: "Alice",
    lastName: "Martin",
    role: { id: "role-1", name: "Créateur", slug: "creator" },
    privileges: ["catalog.manage", "maps.manage"],
  });
});

test("getMe surfaces the caller's privileges", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-2", name: "Administrateur", slug: "admin" },
        privileges: ["admin.roles.manage", "admin.users.manage"],
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me.role.slug).toBe("admin");
  expect(me.privileges).toContain("admin.roles.manage");
});
```

Ajouter, à la fin du fichier, la couverture des cinq nouvelles méthodes — même patron que `listItems`/`getItem` en tête de ce même fichier (Step ci-dessus) :

```typescript
test("getPrivilegeCatalog returns the catalog as-is", async () => {
  server.use(
    http.get("https://core.test/roles/catalog", () =>
      HttpResponse.json([
        { privilege: "admin.harvest.manage", domain: "admin", labelKey: "roles.privilege.adminHarvestManage" },
      ]),
    ),
  );
  const catalog = await makeClient().getPrivilegeCatalog();
  expect(catalog).toHaveLength(1);
  expect(catalog[0].privilege).toBe("admin.harvest.manage");
});

test("listRoles/createRole/updateRole/deleteRole round-trip", async () => {
  let roles = [{ id: "r1", name: "Support", slug: "abc", isBuiltIn: false, privileges: ["admin.harvest.manage"] }];
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(roles)),
    http.post("https://core.test/roles", async ({ request }) => {
      const body = (await request.json()) as { name: string; privileges: string[] };
      const created = { id: "r2", slug: "def", isBuiltIn: false, ...body };
      roles = [...roles, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch("https://core.test/roles/r1", async ({ request }) => {
      const patch = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...roles[0], ...patch });
    }),
    http.delete("https://core.test/roles/r1", () => new HttpResponse(null, { status: 204 })),
  );
  const client = makeClient();
  expect(await client.listRoles()).toEqual(roles);
  const created = await client.createRole({ name: "Analyste+", privileges: ["analytics.view"] });
  expect(created.id).toBe("r2");
  const updated = await client.updateRole("r1", { name: "Support+" });
  expect(updated.name).toBe("Support+");
  await expect(client.deleteRole("r1")).resolves.toBeUndefined();
});
```

Run: `cd shell && npm run test -- itemClient.test.ts` → FAIL d'abord (implémentation du Step 1-2 pas encore écrite si les steps sont pris dans l'ordre inverse — sinon PASS directement puisque Steps 1-2 précèdent celui-ci dans l'ordre du plan).

- [ ] **Step 6: Run la suite complète shell et corriger les usages cassés**

```bash
cd shell && npm run test
```
Expected: des échecs dans TOUT fichier qui référence encore `me.isAdmin`/`me.isAnalyst`/`me.hasAnyEditorRole` (`AccountMenu.tsx`, `AppLayout.tsx`, `KitGalleryPage.tsx`, `RequireRole.tsx`, `capabilities.ts` et leurs tests) — **attendu à ce stade**, résolu par les Tâches 14-15. Ne pas tenter de les corriger dans cette tâche (respecte la découpe par sous-domaine).

- [ ] **Step 7: Lint et commit**

```bash
cd shell
npm run lint -- src/api
npx prettier --check src/api/types.ts src/api/itemClient.ts src/api/hooks.ts src/test/msw/handlers.ts
git add src/api/types.ts src/api/itemClient.ts src/api/hooks.ts src/test/msw/handlers.ts src/api/itemClient.test.ts
git commit -m "feat(shell): Me.role/privileges, CRUD des rôles dans ItemClient + hooks"
```

---

## Task 14 : shell — `capabilities.ts` sur les privilèges, `RequireRole` → `RequirePrivilege`

**Files:**
- Modify: `shell/src/auth/capabilities.ts`
- Delete: `shell/src/auth/RequireRole.tsx`
- Create: `shell/src/auth/RequirePrivilege.tsx`
- Delete: `shell/src/auth/RequireRole.test.tsx` (si présent — remplacé)
- Create: `shell/src/auth/RequirePrivilege.test.tsx`
- Modify: `shell/src/shell/routes.tsx:267-299`
- Test: `shell/src/auth/capabilities.test.ts` (existant — à mettre à jour)

**Interfaces:**
- Produces: `Profile = { privileges: Set<string>; capabilities: InstanceCapabilities }` (remplace `{isAdmin, isAnalyst, capabilities}`) ; `DomainDef.requiresPrivilege?: string | string[]` (remplace `requiresRole`, sémantique **« au moins un » quand c'est un tableau**) ; `RequirePrivilege({ privilege, deniedMessage, children })`.
- Consumes: `Me.privileges` (Tâche 13).

**Nouveau comportement introduit par cette tâche** (absent du code actuel, cf. lecture de `capabilities.ts` avant l'écriture de ce plan : seuls `admin`/`analytics` avaient `requiresRole` — `data`/`apps`/`automation`/`tasks` étaient visibles à tout utilisateur authentifié, quel que soit son rôle) : `data`, `apps`, `automation`, `analytics`, `tasks` gagnent chacun un `requiresPrivilege`, ce qui masque enfin ces domaines pour le rôle Lecteur — résout la dette notée dans CLAUDE.md (« le profil Lecteur n'est pas dérivable du modèle actuel »).

- [ ] **Step 1: Réécrire entièrement `capabilities.test.ts`**

Le fichier actuel (lu intégralement pendant la préparation de ce plan) fixe ses assertions sur l'ANCIEN comportement — notamment `"masque le domaine analytique à un non-analyste"` : avec le nouveau modèle, Créateur a le privilège `analytics.view` (matrice §6.7 : « ◐ sans SQL Lab », donc domaine VISIBLE, pas masqué) — cette assertion doit changer de sens, pas seulement de fixture. Remplacement complet :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  DOMAINS,
  domainState,
  navigableDomains,
  type InstanceCapabilities,
  type Profile,
} from "./capabilities";

const ALL_ON: InstanceCapabilities = {
  readOnly: false,
  etlEnabled: true,
  exportEnabled: true,
  appExportEnabled: true,
  tileset3dEnabled: true,
  terrain3dEnabled: true,
  copilotEnabled: true,
};

// Miroir de BUILT_IN_ROLE_PRIVILEGES (core/app/roles/privileges.py) — mêmes
// valeurs, dupliquées ici faute de source unique inter-langages (le shell ne
// consomme ce catalogue que via GET /roles/catalog à l'exécution, jamais à la
// compilation des tests).
const admin: Profile = {
  privileges: new Set([
    "catalog.manage", "maps.manage", "data.view", "data.manage", "apps.manage",
    "automation.manage", "automation.secrets.manage", "analytics.view",
    "analytics.sql_lab.access", "tasks.view", "tasks.view_all", "admin.users.manage",
    "admin.roles.manage", "admin.harvest.manage", "admin.collections.manage",
    "admin.extensions.manage", "admin.secrets.manage", "settings.instance.manage",
  ]),
  capabilities: ALL_ON,
};
const creator: Profile = {
  privileges: new Set([
    "catalog.manage", "maps.manage", "data.view", "data.manage", "apps.manage",
    "automation.manage", "analytics.view", "tasks.view",
  ]),
  capabilities: ALL_ON,
};
const analyst: Profile = {
  privileges: new Set(["data.view", "analytics.view", "analytics.sql_lab.access", "tasks.view"]),
  capabilities: ALL_ON,
};
const reader: Profile = { privileges: new Set(), capabilities: ALL_ON };

function stateOf(id: string, profile: Profile) {
  const domain = DOMAINS.find((d) => d.id === id);
  if (!domain) throw new Error(`domaine inconnu dans le test : ${id}`);
  return domainState(domain, profile);
}

describe("domainState", () => {
  it("déclare les neuf domaines de la spec", () => {
    expect(DOMAINS.map((d) => d.id)).toEqual([
      "catalog", "maps", "data", "apps", "automation", "analytics", "tasks", "admin", "settings",
    ]);
  });

  it("masque le domaine admin sans aucun privilège admin.*, le montre à l'admin", () => {
    expect(stateOf("admin", reader)).toBe("hidden");
    expect(stateOf("admin", creator)).toBe("hidden");
    expect(stateOf("admin", admin)).toBe("visible");
  });

  it("verrouille — sans masquer — un domaine dont la capacité est coupée", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    expect(stateOf("automation", etlOff)).toBe("locked");
    expect(stateOf("automation", creator)).toBe("visible");
  });

  it("le privilège l'emporte sur la capacité : un domaine masqué le reste", () => {
    // Sinon un lecteur apprendrait l'existence d'automation par son verrou.
    const readerEtlOff: Profile = { ...reader, capabilities: { ...ALL_ON, etlEnabled: false } };
    expect(stateOf("automation", readerEtlOff)).toBe("hidden");
  });

  it("masque le domaine Données au lecteur, le montre au créateur et à l'analyste", () => {
    expect(stateOf("data", reader)).toBe("hidden");
    expect(stateOf("data", creator)).toBe("visible");
    expect(stateOf("data", analyst)).toBe("visible");
  });

  it("montre le domaine analytique au créateur (sans SQL Lab, matrice §6.7) et à l'analyste, le masque au lecteur", () => {
    // Changement de comportement assumé par cette tâche : l'ancien modèle
    // masquait tout le domaine à qui n'était pas isAnalyst=true, y compris un
    // créateur — la matrice §6.7 dit « ◐ sans SQL Lab », pas absent.
    // L'accès à SQL Lab lui-même reste gardé séparément par RequirePrivilege
    // sur la route /analytics/sql (analytics.sql_lab.access), pas ici.
    expect(stateOf("analytics", reader)).toBe("hidden");
    expect(stateOf("analytics", creator)).toBe("visible");
    expect(stateOf("analytics", analyst)).toBe("visible");
  });

  it("le mode démo ne masque ni ne verrouille aucun domaine", () => {
    // Il retire l'écriture, pas la navigation (spec §6.7).
    const demo: Profile = { ...creator, capabilities: { ...ALL_ON, readOnly: true } };
    for (const domain of DOMAINS) {
      expect(domainState(domain, demo)).toBe(domainState(domain, creator));
    }
  });
});

describe("navigableDomains", () => {
  it("ne rend que le visible et le verrouillé, dans l'ordre déclaré", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    const rendered = navigableDomains(etlOff);
    expect(rendered.map((r) => r.domain.id)).not.toContain("admin");
    expect(rendered.find((r) => r.domain.id === "automation")?.state).toBe("locked");
    expect(rendered.map((r) => r.domain.id)).toEqual([
      "catalog", "maps", "data", "apps", "automation", "analytics", "tasks", "settings",
    ]);
  });
});
```

- [ ] **Step 2: Confirmer l'échec**

Run: `cd shell && npm run test -- capabilities.test.ts` → FAIL (`Profile.privileges` n'existe pas encore)

- [ ] **Step 3: Réécrire `shell/src/auth/capabilities.ts`**

```typescript
// SPDX-License-Identifier: Apache-2.0
//
// L'état des neuf domaines du produit, dérivé d'une source unique : le profil
// servi par `GET /me` (privilèges du rôle + capacités du déploiement).
//
// Doctrine (spec §6.2) : un privilège manquant MASQUE, une capacité coupée
// VERROUILLE. Un privilège est une propriété de la personne (via son rôle) ;
// une capacité est une propriété du déploiement, qu'un administrateur doit
// pouvoir comprendre.
//
// La barre de domaines, la palette ⌘K et les onglets du volet gauche se
// calculent tous d'ici : retirer un privilège d'un rôle fait disparaître le
// domaine ET ses commandes, sans code supplémentaire.

import type { MessageKey } from "../i18n";

export type InstanceCapabilities = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
};

export type Profile = {
  privileges: Set<string>;
  capabilities: InstanceCapabilities;
};

export type DomainId =
  | "catalog"
  | "maps"
  | "data"
  | "apps"
  | "automation"
  | "analytics"
  | "tasks"
  | "admin"
  | "settings";

export type DomainState = "visible" | "locked" | "hidden";

export type DomainDef = {
  id: DomainId;
  labelKey: MessageKey;
  /** Absent = ouvert à tous. Un tableau = « au moins un » suffit. Présent et
   * non satisfait = domaine MASQUÉ. */
  requiresPrivilege?: string | string[];
  /** Absent = pas de dépendance. Présent et coupé = domaine VERROUILLÉ. */
  requiresCapability?: keyof InstanceCapabilities;
};

// L'ordre de ce tableau est l'ordre d'affichage de la barre de domaines.
export const DOMAINS: readonly DomainDef[] = [
  { id: "catalog", labelKey: "domain.catalog" },
  { id: "maps", labelKey: "domain.maps" },
  { id: "data", labelKey: "domain.data", requiresPrivilege: "data.view" },
  { id: "apps", labelKey: "domain.apps", requiresPrivilege: "apps.manage" },
  {
    id: "automation",
    labelKey: "domain.automation",
    requiresPrivilege: "automation.manage",
    requiresCapability: "etlEnabled",
  },
  { id: "analytics", labelKey: "domain.analytics", requiresPrivilege: "analytics.view" },
  { id: "tasks", labelKey: "domain.tasks", requiresPrivilege: "tasks.view" },
  {
    id: "admin",
    labelKey: "domain.admin",
    requiresPrivilege: [
      "admin.users.manage",
      "admin.roles.manage",
      "admin.harvest.manage",
      "admin.collections.manage",
      "admin.extensions.manage",
      "admin.secrets.manage",
    ],
  },
  { id: "settings", labelKey: "domain.settings" },
] as const;

function hasRequiredPrivilege(domain: DomainDef, profile: Profile): boolean {
  if (domain.requiresPrivilege === undefined) return true;
  const required = Array.isArray(domain.requiresPrivilege)
    ? domain.requiresPrivilege
    : [domain.requiresPrivilege];
  return required.some((p) => profile.privileges.has(p));
}

export function domainState(domain: DomainDef, profile: Profile): DomainState {
  // Le privilège est évalué EN PREMIER : sinon quelqu'un qui ne l'a pas
  // apprendrait l'existence d'un domaine par le verrou qu'on lui montrerait.
  if (!hasRequiredPrivilege(domain, profile)) return "hidden";
  if (domain.requiresCapability && !profile.capabilities[domain.requiresCapability]) {
    return "locked";
  }
  return "visible";
}

export function navigableDomains(
  profile: Profile,
): { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] {
  const out: { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] = [];
  for (const domain of DOMAINS) {
    const state = domainState(domain, profile);
    if (state !== "hidden") out.push({ domain, state });
  }
  return out;
}
```

- [ ] **Step 4: Confirmer le succès de `capabilities.test.ts`**

Run: `cd shell && npm run test -- capabilities.test.ts` → PASS (le fichier a été intégralement remplacé au Step 1, aucun résidu `isAdmin`/`isAnalyst` à traiter ici).

- [ ] **Step 5: Remplacer `RequireRole.tsx` par `RequirePrivilege.tsx`**

```bash
git rm shell/src/auth/RequireRole.tsx
[ -f shell/src/auth/RequireRole.test.tsx ] && git rm shell/src/auth/RequireRole.test.tsx
```

```typescript
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { useMe } from "../api/hooks";

/**
 * Porte de privilège au niveau route — pendant côté privilèges de rôle de
 * `Gate`/`hasPermission` côté permissions d'objet. Remplace `RequireRole`
 * (SP-30, design §6.5) : la comparaison de droits vit ici, testée une seule
 * fois.
 */
export function RequirePrivilege({
  privilege,
  deniedMessage,
  children,
}: {
  privilege: string;
  deniedMessage: string;
  children: ReactNode;
}): ReactNode {
  const meQuery = useMe();
  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  const allowed = meQuery.data?.privileges.includes(privilege) === true;
  if (!allowed) {
    return (
      <p role="alert" className="text-sm text-danger">
        {deniedMessage}
      </p>
    );
  }
  return children;
}
```

Écrire `shell/src/auth/RequirePrivilege.test.tsx`, patron exact de l'ancien `RequireRole.test.tsx` (lu intégralement pendant la préparation de ce plan avant sa suppression au Step 5) :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RequirePrivilege } from "./RequirePrivilege";

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges,
      }),
    ),
  );
}

function renderGate(privilege: string, deniedMessage: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RequirePrivilege privilege={privilege} deniedMessage={deniedMessage}>
          <p>Contenu protégé</p>
        </RequirePrivilege>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche le contenu quand le privilège requis est présent", async () => {
  mockMe(["analytics.sql_lab.access"]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche le message de refus quand le privilège requis est absent", async () => {
  mockMe([]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
  expect(screen.queryByText("Contenu protégé")).not.toBeInTheDocument();
});

test("un privilège se vérifie indépendamment des autres privilèges détenus", async () => {
  mockMe(["admin.roles.manage"]);
  renderGate("admin.roles.manage", "Accès réservé à la gestion des rôles.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche un statut de chargement avant la résolution de /me", () => {
  mockMe(["analytics.sql_lab.access"]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");
});
```

- [ ] **Step 6: Mettre à jour `shell/src/shell/routes.tsx`**

Remplacer (lignes 267-298) :
```tsx
        <Route
          path="/analytics/sql"
          element={
            <RequirePrivilege
              privilege="analytics.sql_lab.access"
              deniedMessage="Accès réservé aux analystes."
            >
              <SqlLabPage />
            </RequirePrivilege>
          }
        />
        <Route
          path="/admin/extensions"
          element={
            <RequirePrivilege
              privilege="admin.extensions.manage"
              deniedMessage="Accès réservé aux administrateurs."
            >
              <AdminExtensionsPage />
            </RequirePrivilege>
          }
        />
        <Route
          path="/admin/collections"
          element={
            <RequirePrivilege
              privilege="admin.collections.manage"
              deniedMessage="Accès réservé aux administrateurs."
            >
              <CollectionsAdminPage />
            </RequirePrivilege>
          }
        />
        <Route
          path="/admin/harvest"
          element={
            <RequirePrivilege
              privilege="admin.harvest.manage"
              deniedMessage="Accès réservé aux administrateurs."
            >
              <HarvestSourcesAdminPage />
            </RequirePrivilege>
          }
        />
```

Et l'import en tête de fichier : remplacer `RequireRole` par `RequirePrivilege`.

(La route `/internal/kit-gallery`, ligne 299, n'est pas modifiée ici — traitée Tâche 15.)

- [ ] **Step 7: Mettre à jour le test `/admin/extensions` dans `shell/src/shell/routes.test.tsx`**

Ce test (lignes 141-164 du fichier actuel, lu intégralement pendant la préparation de ce plan) surcharge `/me` avec `isAdmin: true` — remplacer :

```typescript
test("renders the admin extensions route at /admin/extensions", async () => {
  // /admin/extensions passe par RequirePrivilege depuis ce commit — le
  // handler MSW par défaut de /me ne porte pas admin.extensions.manage, il
  // faut le surcharger et attendre la résolution avant d'affirmer sur le contenu.
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        email: "alice@example.com",
        tenantId: "t1",
        role: { id: "role-admin", name: "Administrateur", slug: "admin" },
        privileges: ["admin.extensions.manage"],
        version: "0.1.0",
        tenantSlug: "demo",
      }),
    ),
  );
  wrap(<AppRoutes />, "/admin/extensions");
  expect(await screen.findByText("admin-extensions")).toBeInTheDocument();
});
```

- [ ] **Step 8: Run et confirmer**

```bash
cd shell && npm run test -- capabilities.test.ts RequirePrivilege.test.tsx routes.test.tsx
```
Expected: tous PASS.

- [ ] **Step 9: Lint et commit**

```bash
cd shell
npm run lint -- src/auth src/shell/routes.tsx
npx prettier --check src/auth/capabilities.ts src/auth/RequirePrivilege.tsx src/shell/routes.tsx
git add src/auth src/shell/routes.tsx
git commit -m "feat(shell): capabilities.ts sur les privilèges — RequireRole devient RequirePrivilege"
```

---

## Task 15 : shell — `AccountMenu`, `AppLayout`, `KitGalleryPage`, i18n

**Files:**
- Modify: `shell/src/shell/chrome/AccountMenu.tsx`
- Modify: `shell/src/shell/AppLayout.tsx:28-40`
- Modify: `shell/src/pages/KitGalleryPage.tsx:196-209`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: fichiers de test correspondants (`AccountMenu.test.tsx`, `AppLayout.test.tsx`, `KitGalleryPage.test.tsx` si présents — sinon les créer au patron des tests de composants voisins du même dossier)

**Interfaces:**
- Consumes: `Me.role`/`Me.privileges` (Tâche 13), `Profile` (Tâche 14).

- [ ] **Step 1: Ajouter les clés i18n dans `shell/src/i18n/catalog.fr.ts`**

Ajouter (les 4 clés `account.role*` existent déjà — ne pas les dupliquer, vérifié avant l'écriture de ce plan) :

```typescript
  "roles.title": "Rôles",
  "roles.addRole": "Ajouter un rôle",
  "roles.nameLabel": "Nom",
  "roles.privilegesLabel": "Privilèges",
  "roles.builtInBadge": "Prédéfini",
  "roles.deleteConfirmTitle": "Supprimer le rôle",
  "roles.deleteConfirmMessage": "Supprimer le rôle « {name} » ? Cette action est irréversible.",
  "roles.deleteBlockedByUsage": "Encore attribué à {count} utilisateur(s).",
  "roles.privilege.catalogManage": "Créer et modifier les éléments du catalogue",
  "roles.privilege.mapsManage": "Créer et modifier des cartes",
  "roles.privilege.dataView": "Voir le domaine Données",
  "roles.privilege.dataManage": "Créer et modifier des jeux de données",
  "roles.privilege.appsManage": "Créer et modifier des apps et sites",
  "roles.privilege.automationManage": "Créer et modifier des pipelines",
  "roles.privilege.automationSecretsManage": "Voir et gérer les noms de secrets",
  "roles.privilege.analyticsView": "Voir le domaine Analytique",
  "roles.privilege.analyticsSqlLabAccess": "Utiliser SQL Lab",
  "roles.privilege.tasksView": "Voir ses tâches",
  "roles.privilege.tasksViewAll": "Voir les tâches de tout le tenant",
  "roles.privilege.adminUsersManage": "Gérer les utilisateurs",
  "roles.privilege.adminRolesManage": "Gérer les rôles",
  "roles.privilege.adminHarvestManage": "Gérer le moissonnage",
  "roles.privilege.adminCollectionsManage": "Gérer les collections",
  "roles.privilege.adminExtensionsManage": "Gérer les extensions",
  "roles.privilege.adminSecretsManage": "Voir les noms de secrets (administration)",
  "roles.privilege.settingsInstanceManage": "Gérer les paramètres d'instance et de tenant",
```

(Insérer dans le bloc existant, en respectant l'ordre déjà en place dans le fichier — pas de section séparée requise, la convention est un objet plat.)

- [ ] **Step 2: `AccountMenu.tsx`**

Remplacer `roleLabel` (lignes 10-16) :
```tsx
const BUILT_IN_ROLE_LABEL_KEYS: Record<string, MessageKey> = {
  admin: "account.roleAdmin",
  analyst: "account.roleAnalyst",
  creator: "account.roleCreator",
  reader: "account.roleReader",
};

function roleLabel(me: Me | undefined): string {
  if (!me) return "";
  const key = BUILT_IN_ROLE_LABEL_KEYS[me.role.slug];
  return key ? t(key) : me.role.name;
}
```

Ajouter `import type { MessageKey } from "../../i18n";` (ou fusionner avec l'import `t` existant si le fichier le permet).

- [ ] **Step 3: `AppLayout.tsx`**

Remplacer (lignes 28-40) :
```tsx
  const profile: Profile = {
    privileges: new Set(meQuery.data?.privileges ?? []),
    capabilities: {
      readOnly,
      etlEnabled: instanceQuery.data?.etlEnabled === true,
      exportEnabled: instanceQuery.data?.exportEnabled === true,
      appExportEnabled: instanceQuery.data?.appExportEnabled === true,
      tileset3dEnabled,
      terrain3dEnabled: instanceQuery.data?.terrain3dEnabled === true,
      copilotEnabled: instanceQuery.data?.copilotEnabled === true,
    },
  };
```

- [ ] **Step 4: `KitGalleryPage.tsx`**

Remplacer (lignes 203-209) :
```tsx
  if (meQuery.data?.role.slug !== "admin") {
    return (
      <p role="alert" className="text-sm text-danger">
        Accès réservé aux administrateurs.
      </p>
    );
  }
```

(Choix délibéré : `role.slug === "admin"` plutôt qu'un privilège précis — cette page est une galerie de composants interne, pas une surface produit, sans privilège naturel du catalogue §3.2 ; comportement identique à l'existant, aucune régression.)

- [ ] **Step 5: Run la suite complète shell**

```bash
cd shell && npm run test
```
Expected: PASS pour tous les fichiers touchés par les Tâches 13-15. S'il reste des échecs dans des fichiers non listés par ce plan (piège n°6 déjà documenté plusieurs fois dans ce dépôt — SP-30c/d/e), les corriger ici plutôt que les ignorer.

- [ ] **Step 6: Lint et commit**

```bash
cd shell
npm run lint -- src/shell src/pages/KitGalleryPage.tsx src/i18n
npx prettier --check src/shell/chrome/AccountMenu.tsx src/shell/AppLayout.tsx src/pages/KitGalleryPage.tsx src/i18n/catalog.fr.ts
git add src/shell/chrome/AccountMenu.tsx src/shell/AppLayout.tsx src/pages/KitGalleryPage.tsx src/i18n/catalog.fr.ts
git commit -m "refactor(shell): AccountMenu/AppLayout/KitGalleryPage — dernières comparaisons isAdmin/isAnalyst en dur migrées vers role/privileges"
```

---

## Task 16 : shell — `RolesAdminPage`

**Files:**
- Create: `shell/src/pages/RolesAdminPage.tsx`
- Create: `shell/src/shell/CreateRolePanel.tsx`
- Create: `shell/src/shell/EditRolePanel.tsx`
- Modify: `shell/src/shell/routes.tsx` (route `/admin/roles`)
- Test: `shell/src/pages/RolesAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useRoles`, `useRolesCatalog`, `useCreateRole`, `useUpdateRole`, `useDeleteRole` (Tâche 13) ; `RequirePrivilege` (Tâche 14) ; `Checkbox`, `Button`, `Panel`, `ConfirmDialog` (kit, déjà livrés SP-29b).

**Patron répliqué** (lu intégralement avant l'écriture de ce plan) : `shell/src/pages/HarvestSourcesAdminPage.tsx` + `shell/src/shell/CreateHarvestSourcePanel.tsx` — même structure `TriptychLayout`, même exclusivité mutuelle `creating`/`editing`/`deleting` posée à la main dans chaque gestionnaire de clic, même `ConfirmDialog` pour la suppression.

- [ ] **Step 1: Écrire le test en échec `RolesAdminPage.test.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RolesAdminPage } from "./RolesAdminPage";

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <RolesAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const CATALOG = [
  { privilege: "admin.harvest.manage", domain: "admin", labelKey: "roles.privilege.adminHarvestManage" },
  { privilege: "admin.collections.manage", domain: "admin", labelKey: "roles.privilege.adminCollectionsManage" },
];

test("admin crée un rôle sur mesure en cochant des privilèges", async () => {
  let created: Record<string, unknown> | null = null;
  server.use(
    http.get("https://core.test/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/roles", () =>
      HttpResponse.json(
        created
          ? [{ id: "role-1", name: "Support", slug: "abc", isBuiltIn: false, privileges: created.privileges }]
          : [],
      ),
    ),
    http.post("https://core.test/roles", async ({ request }) => {
      created = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { id: "role-1", slug: "abc", isBuiltIn: false, ...created },
        { status: 201 },
      );
    }),
  );

  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: /ajouter un rôle/i }));
  await userEvent.type(screen.getByLabelText(/nom/i), "Support");
  await userEvent.click(screen.getByLabelText(/gérer le moissonnage/i));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));

  await waitFor(() => expect(screen.getByText("Support")).toBeInTheDocument());
  expect(created).not.toBeNull();
  expect((created as { privileges: string[] }).privileges).toEqual(["admin.harvest.manage"]);
});

test("un rôle prédéfini ne propose ni éditer ni supprimer", async () => {
  server.use(
    http.get("https://core.test/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/roles", () =>
      HttpResponse.json([
        { id: "role-admin", name: "Administrateur", slug: "admin", isBuiltIn: true, privileges: [] },
      ]),
    ),
  );

  render(<Harness />);
  const row = await screen.findByText("Administrateur");
  const cell = row.closest("tr") as HTMLElement;
  expect(within(cell).queryByRole("button", { name: /éditer/i })).not.toBeInTheDocument();
  expect(within(cell).queryByRole("button", { name: /supprimer/i })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Confirmer l'échec**

Run: `cd shell && npm run test -- RolesAdminPage.test.tsx` → FAIL (`RolesAdminPage` inexistant)

- [ ] **Step 3: Écrire `shell/src/shell/CreateRolePanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateRole, useRolesCatalog } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Checkbox } from "../ui/kit/Checkbox";
import { t } from "../i18n";
import type { MessageKey } from "../i18n";

export function CreateRolePanel({ onClose }: { onClose: () => void }) {
  const createRole = useCreateRole();
  const catalogQuery = useRolesCatalog();
  const [name, setName] = useState("");
  const [privileges, setPrivileges] = useState<Set<string>>(new Set());

  function toggle(privilege: string) {
    setPrivileges((prev) => {
      const next = new Set(prev);
      if (next.has(privilege)) next.delete(privilege);
      else next.add(privilege);
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name) return;
    try {
      await createRole.mutateAsync({ name, privileges: [...privileges] });
      onClose();
    } catch {
      // surfaced via createRole.isError
    }
  }

  const byDomain = new Map<string, { privilege: string; labelKey: MessageKey }[]>();
  for (const entry of catalogQuery.data ?? []) {
    const list = byDomain.get(entry.domain) ?? [];
    list.push({ privilege: entry.privilege, labelKey: entry.labelKey as MessageKey });
    byDomain.set(entry.domain, list);
  }

  return (
    <section aria-label={t("roles.addRole")} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">{t("roles.addRole")}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("roles.nameLabel")}
          <Input aria-label={t("roles.nameLabel")} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm text-ink">{t("roles.privilegesLabel")}</legend>
          {[...byDomain.entries()].map(([domain, entries]) => (
            <div key={domain} className="flex flex-col gap-1">
              {entries.map(({ privilege, labelKey }) => (
                <label key={privilege} className="flex items-center gap-2 text-sm text-ink-2">
                  <Checkbox
                    checked={privileges.has(privilege)}
                    onCheckedChange={() => toggle(privilege)}
                    aria-label={t(labelKey)}
                  />
                  {t(labelKey)}
                </label>
              ))}
            </div>
          ))}
        </fieldset>
        {createRole.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!name || createRole.isPending}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 4: Écrire `shell/src/shell/EditRolePanel.tsx`**

Patron exact de `shell/src/shell/EditHarvestSourcePanel.tsx` (lu intégralement pendant la préparation de ce plan), avec `useUpdateRole(role.id)` au lieu de `useUpdateHarvestSource(source.id)` et les mêmes cases à cocher par domaine que `CreateRolePanel` (Step 3) :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useRolesCatalog, useUpdateRole } from "../api/hooks";
import type { Role } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Checkbox } from "../ui/kit/Checkbox";
import { t } from "../i18n";
import type { MessageKey } from "../i18n";

export function EditRolePanel({ role, onClose }: { role: Role; onClose: () => void }) {
  const updateRole = useUpdateRole(role.id);
  const catalogQuery = useRolesCatalog();
  const [name, setName] = useState(role.name);
  const [privileges, setPrivileges] = useState<Set<string>>(new Set(role.privileges));

  function toggle(privilege: string) {
    setPrivileges((prev) => {
      const next = new Set(prev);
      if (next.has(privilege)) next.delete(privilege);
      else next.add(privilege);
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateRole.mutateAsync({ name, privileges: [...privileges] });
      onClose();
    } catch {
      // surfaced via updateRole.isError
    }
  }

  const byDomain = new Map<string, { privilege: string; labelKey: MessageKey }[]>();
  for (const entry of catalogQuery.data ?? []) {
    const list = byDomain.get(entry.domain) ?? [];
    list.push({ privilege: entry.privilege, labelKey: entry.labelKey as MessageKey });
    byDomain.set(entry.domain, list);
  }

  return (
    <section aria-label={`Éditer ${role.name}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {role.name}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("roles.nameLabel")}
          <Input aria-label={t("roles.nameLabel")} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm text-ink">{t("roles.privilegesLabel")}</legend>
          {[...byDomain.entries()].map(([domain, entries]) => (
            <div key={domain} className="flex flex-col gap-1">
              {entries.map(({ privilege, labelKey }) => (
                <label key={privilege} className="flex items-center gap-2 text-sm text-ink-2">
                  <Checkbox
                    checked={privileges.has(privilege)}
                    onCheckedChange={() => toggle(privilege)}
                    aria-label={t(labelKey)}
                  />
                  {t(labelKey)}
                </label>
              ))}
            </div>
          ))}
        </fieldset>
        {updateRole.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!name || updateRole.isPending}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 5: Écrire `shell/src/pages/RolesAdminPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useDeleteRole, useRoles } from "../api/hooks";
import type { Role } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { CreateRolePanel } from "../shell/CreateRolePanel";
import { EditRolePanel } from "../shell/EditRolePanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

export function RolesAdminPage() {
  const rolesQuery = useRoles();
  const deleteRole = useDeleteRole();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState<Role | null>(null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteRole.mutateAsync(deleting.id);
      if (editing?.id === deleting.id) setEditing(null);
      setDeleting(null);
    } catch {
      // surfaced via deleteRole.isError
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "roles",
          label: t("roles.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">{t("roles.title")}</h1>
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setCreating(true);
                  }}
                >
                  {t("roles.addRole")}
                </Button>
              </div>
              {rolesQuery.isLoading && <p role="status">Chargement…</p>}
              {rolesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des rôles.
                </p>
              )}
              {deleteRole.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la suppression.
                </p>
              )}
              {rolesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Nom</th>
                      <th className="py-2 text-ink">Privilèges</th>
                      <th className="py-2 text-ink">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rolesQuery.data.map((role) => (
                      <tr key={role.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">
                          {role.name}
                          {role.isBuiltIn && (
                            <span className="ml-2 text-xs text-ink-2">
                              ({t("roles.builtInBadge")})
                            </span>
                          )}
                        </td>
                        <td className="py-2 text-xs text-ink-2">{role.privileges.length}</td>
                        <td className="py-2 flex gap-2">
                          {!role.isBuiltIn && (
                            <>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setCreating(false);
                                  setEditing(role);
                                }}
                              >
                                Éditer
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(role)}
                              >
                                Supprimer
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-3 p-3">
              {creating && <CreateRolePanel onClose={() => setCreating(false)} />}
              {editing && (
                <EditRolePanel key={editing.id} role={editing} onClose={() => setEditing(null)} />
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title={t("roles.deleteConfirmTitle")}
        message={deleting ? t("roles.deleteConfirmMessage", { name: deleting.name }) : ""}
        confirmLabel="Supprimer"
        pending={deleteRole.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
```

- [ ] **Step 6: Câbler la route**

Dans `shell/src/shell/routes.tsx`, ajouter (à côté des trois autres routes `/admin/*`) :
```tsx
        <Route
          path="/admin/roles"
          element={
            <RequirePrivilege
              privilege="admin.roles.manage"
              deniedMessage="Accès réservé à la gestion des rôles."
            >
              <RolesAdminPage />
            </RequirePrivilege>
          }
        />
```
Et l'import `import { RolesAdminPage } from "../pages/RolesAdminPage";`.

- [ ] **Step 7: Run et confirmer**

```bash
cd shell && npm run test -- RolesAdminPage.test.tsx routes.test.tsx
```
Expected: tous PASS.

- [ ] **Step 8: Suite complète + lint + commit**

```bash
cd shell
npm run test
npm run lint -- src/pages/RolesAdminPage.tsx src/shell/CreateRolePanel.tsx src/shell/EditRolePanel.tsx src/shell/routes.tsx
npx prettier --check src/pages/RolesAdminPage.tsx src/shell/CreateRolePanel.tsx src/shell/EditRolePanel.tsx
git add src/pages/RolesAdminPage.tsx src/shell/CreateRolePanel.tsx src/shell/EditRolePanel.tsx src/shell/routes.tsx src/pages/RolesAdminPage.test.tsx
git commit -m "feat(shell): RolesAdminPage — créer/éditer/supprimer des rôles sur mesure, catalogue de privilèges par domaine"
```

---

## Task 17 : vérification finale de branche

**Files:** aucun (tâche de vérification uniquement)

- [ ] **Step 1: Suite complète cœur**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
uv run pytest
```
Expected: tout vert. Comparer le compte de tests à la référence CLAUDE.md (1896 passed + 5 skipped + 1 failed intermittent, mesuré 2026-08-27) — un delta positif attendu (nouveaux tests Tâches 1-11), aucune régression.

- [ ] **Step 2: Suite complète shell**

```bash
cd shell
rm -rf dist dist-export  # avant mesure de couverture — piège documenté 4 fois
npm run lint && npm run format:check
npm run build
npm run test -- --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run e2e
```
Expected: tout vert, couverture ≥ 88 %, E2E 118/4/0 inchangé (aucun nouveau spec E2E dans ce plan — vérifier explicitement qu'aucune régression croisée n'apparaît, piège n°6).

- [ ] **Step 3: `pre-commit` complet**

```bash
uvx pre-commit run --all-files
```

- [ ] **Step 4: Vérifier qu'aucune comparaison de droits en dur ne subsiste**

```bash
grep -rn "isAdmin\|isAnalyst" shell/src --include=*.ts --include=*.tsx | grep -v ".test."
grep -rn "\.is_analyst\b" core/app --include=*.py
```
Expected: le premier grep ne renvoie plus rien lié à `Me`/`Profile` (seuls des faux positifs sans rapport, à examiner un par un s'il en reste) ; le second grep ne renvoie rien du tout (`is_analyst` totalement retiré du cœur).

- [ ] **Step 5: Revue finale de branche**

Invoquer `superpowers:requesting-code-review` (modèle le plus capable disponible) sur l'ensemble de la branche — pas seulement la dernière tâche. Porter une attention particulière (classes de défauts déjà payées sur ce dépôt) :
- un commentaire qui attribue encore une garde à `_require_admin` après son retrait (piège trouvé Important à deux reprises, SP-30g/SP-30i) ;
- une incohérence entre les 4 exemptions de couches ajoutées et le graphe réel (`lint-imports` doit être vert, mais vérifier aussi qu'aucune exemption n'est restée inutilisée) ;
- la garde anti-lockout de `PATCH /roles/{role_id}` (would_orphan_privilege_holders) et celle de `PATCH /users/{id}` (count_users_with_privileges) : vérifier qu'elles ne divergent pas sur un cas limite (ex. un rôle sur mesure qui porte les deux privilèges anti-lockout, jamais testé conjointement dans ce plan).

- [ ] **Step 6: Mettre à jour `CLAUDE.md`**

Ajouter une entrée `### Livré` (numérotation SP à convenir avec Tanguy — ce plan n'en présume aucune) résumant : table `roles` par tenant, 17 privilèges, 4 rôles prédéfinis immuables + rôles sur mesure, `RolesAdminPage`, anti-lockout, migration 0030. Lister les suivis non bloquants trouvés en Step 5. Retirer `is_analyst`/`isAdmin`/`isAnalyst` de toute mention encore active dans les sections "Pièges récurrents"/"Suivis non bloquants" qui les citaient comme dette (aucune identifiée à l'écriture de ce plan, à vérifier).
