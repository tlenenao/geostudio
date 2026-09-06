# SP-47 — Audit, gouvernance des privilèges et vue d'usage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ferme GAP-03 (2 des 18 privilèges du catalogue — `automation.secrets.manage`, `tasks.view_all` — ne gardent aucune route) et GAP-71/GAP-28 (`audit_log` en écriture seule, aucune vue d'usage exposée aux administrateurs), par une seule construction : un nouveau domaine `core/app/usage/` qui lit `audit_log` en lecture (jamais en écriture — le writer existant, `app.audit.writer.write_audit`, est intouché) et donne enfin à `tasks.view`/`tasks.view_all` une route réelle, tandis que `automation.secrets.manage` élargit la garde des routes `/secrets` existantes.

**Architecture:** `core/app/roles/guards.py` gagne `require_any_privilege` (OR de privilèges, réutilisée par `/secrets` et par `app.usage`). `core/app/usage/` (nouveau domaine, placé au-dessus d'`app.roles` dans le contrat de couches) expose `GET /usage/tasks` (journal d'actions de job, filtré `tasks.view`=soi / `tasks.view_all`=tenant entier) et `GET /usage/summary` (agrégats activité-par-acteur + popularité-des-ressources sur `audit_log` complet, `tasks.view_all` seul). Côté shell, remplace `TasksComingSoonPage` par une vraie page consommant ces deux endpoints via le patron domaine `createXMethods(base)` déjà en place (`shell/src/api/domains/`).

**Tech Stack:** FastAPI + SQLAlchemy (cœur, aucune nouvelle table ni migration — lit `app.audit.models.AuditLog` existant). React + React Query (shell). Aucune nouvelle dépendance.

**Spec de référence :** `docs/superpowers/specs/2026-09-05-sp47-audit-privileges-design.md` — toute divergence avec ce plan se résout en faveur du texte le plus récemment approuvé par Tanguy, sauf contradiction manifeste, auquel cas s'arrêter et demander.

## Global Constraints

- **Vérifier `kind_registry.py` avant de commencer** (Task 1) : la spec l'a
  confirmé mergé en session au moment de sa rédaction, mais ce plan peut
  s'exécuter plus tard — `cat core/app/roles/kind_registry.py` doit
  toujours montrer `privilege_for_kind(kind: str) -> str`. Ce plan ne
  modifie PAS ce fichier (aucun des deux privilèges visés n'est un `kind`
  de config) — si le fichier a disparu ou changé de forme d'ici
  l'exécution, s'arrêter et vérifier que rien de ce plan n'en dépendait
  implicitement (rien ne devrait, mais vérifier).
- **Ne jamais faire confiance au texte d'un gap sans revérifier dans le
  code réel** (piège CLAUDE.md n°3) — chaque tâche ci-dessous commence par
  une étape de vérification contre le fichier réel, pas contre la spec.
- Toute route/schéma suit exactement les conventions déjà en place dans
  `core/app/notifications/` (`schemas.py`/`routes.py`/`repository.py`) —
  pas de nouveau patron : `page`/`pageSize`, réponses `dict[str, Any]` ou
  Pydantic `BaseModel` camelCase, jointure tolérante (`LEFT OUTER JOIN`)
  pour un acteur système/agent/supprimé.
- Régénération OpenAPI + types TS obligatoire dès qu'une route change
  (piège CLAUDE.md n°1) — faite en Task 5, avant les tâches shell qui en
  dépendent. Un diff **vide** est attendu et légitime pour la partie
  `/secrets` (garde interne changée, forme de requête/réponse inchangée) —
  documenté explicitement dans cette tâche, pas juste un oubli qui
  ressemblerait à un oubli.
- Après CHAQUE tâche touchant `shell/`, lancer `npm run test` complet (pas
  seulement le fichier modifié) — piège n°6 de CLAUDE.md (régression
  croisée invisible à un run scopé). Après chaque tâche touchant `core/`,
  lancer `uv run pytest` scopé au module concerné a minima, la suite
  complète en Task 9.
- `uv run lint-imports` doit rester vert après Task 3/4 (nouveau module
  `app.usage` dans `[[tool.importlinter.contracts]] layers`) — sans
  exemption nommée ajoutée (la position choisie, au-dessus d'`app.roles`,
  doit rendre ça inutile ; si une exemption s'avère nécessaire, c'est un
  signal que le placement dans `layers` est faux, pas que l'exemption est
  la bonne réponse — replacer le module plutôt qu'exempter).
- Docs et identifiants de test en français (CLAUDE.md). Code/identifiants
  techniques en anglais.
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), un sujet par
  commit, un commit par tâche au minimum.
- Chaque tâche pose son test AVANT le code correspondant (TDD strict) :
  écrire le test, le lancer, confirmer qu'il échoue pour la bonne raison,
  puis écrire l'implémentation minimale qui le fait passer.

---

## Task 1 (Étape 0) : `require_any_privilege` — primitive de garde OR

**Files:**
- Modify: `core/app/roles/guards.py`
- Test: `core/tests/test_roles_guards.py`

**Interfaces:**
- Produces: `require_any_privilege(session: Session, user: User, privileges: Sequence[str]) -> None` — consommée par Task 2 (`/secrets`) et Task 4 (`/usage/tasks`).

- [ ] **Step 0 — vérification pré-tâche** : confirmer que `core/app/roles/guards.py` contient toujours exactement `has_privilege`, `privilege_required_error`, `require_privilege` (lu en session de préparation de cette spec — revérifier que rien n'a changé depuis) :

```bash
cat core/app/roles/guards.py
```

- [ ] **Step 1: Écrire le test (RED)**

```python
# core/tests/test_roles_guards.py — ajouter à la suite des tests existants
import pytest
from fastapi import HTTPException

from app.roles.guards import has_privilege, require_any_privilege, require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import create_role, ensure_built_in_roles
# ... imports tenant/user déjà présents dans ce fichier, même patron que
# test_require_privilege_allows_a_holder_and_rejects_the_rest


def test_require_any_privilege_allows_holder_of_at_least_one():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        # rôle sur mesure ne portant QUE automation.secrets.manage
        custom = create_role(
            s, tenant_id=tenant.id, name="Secrets pipeline",
            privileges=[Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )
        holder = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="h", username="h",
            email=None, first_name="", last_name="",
        )
        holder.role_id = custom.id
        reader = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r2", username="r2",
            email=None, first_name="", last_name="",
        )
        s.flush()

        # ne lève pas : porte automation.secrets.manage, un des deux acceptés
        require_any_privilege(
            s, holder,
            [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )

        # lève : rôle par défaut (creator), ne porte ni l'un ni l'autre
        with pytest.raises(HTTPException) as exc_info:
            require_any_privilege(
                s, reader,
                [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value],
            )
        assert exc_info.value.status_code == 403
        # le message cite les DEUX privilèges acceptés, pas un seul —
        # sinon un rôle sur mesure ne sait pas lequel des deux cocher
        assert "admin.secrets.manage" in str(exc_info.value.detail)
        assert "automation.secrets.manage" in str(exc_info.value.detail)


def test_require_any_privilege_rejects_when_privilege_list_is_empty():
    # garde-fou : une liste vide ne doit jamais autoriser par défaut
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a2", username="a2",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.flush()
        with pytest.raises(HTTPException):
            require_any_privilege(s, admin, [])
```

Lancer : `cd core && uv run pytest tests/test_roles_guards.py -q` → doit échouer (ImportError sur `require_any_privilege`, ou `AttributeError`).

- [ ] **Step 2: Implémenter (GREEN)**

```python
# core/app/roles/guards.py
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def has_privilege(session: Session, user: User, privilege: str) -> bool:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    return role is not None and privilege in role.privileges


def privilege_required_error(privilege: str) -> HTTPException:
    return HTTPException(status_code=403, detail=f"privilege '{privilege}' required")


def require_privilege(session: Session, user: User, privilege: str) -> None:
    if not has_privilege(session, user, privilege):
        raise privilege_required_error(privilege)


def require_any_privilege(session: Session, user: User, privileges: Sequence[str]) -> None:
    """Autorise si l'utilisateur porte AU MOINS UN des privilèges donnés.
    Une liste vide ne satisfait jamais (`any([])` est `False` — cohérent,
    mais vérifié explicitement par un test dédié pour ne jamais laisser un
    appelant futur croire qu'une liste vide autorise tout le monde)."""
    if not any(has_privilege(session, user, p) for p in privileges):
        joined = " ou ".join(privileges) if privileges else "(aucun privilège listé)"
        raise HTTPException(status_code=403, detail=f"privilege '{joined}' required")
```

Lancer : `cd core && uv run pytest tests/test_roles_guards.py -q` → vert.

- [ ] **Step 3: Vérifier** `uv run ruff check app/roles/guards.py && uv run ruff format --check app/roles/guards.py`.

- [ ] **Commit** : `feat(core): require_any_privilege pour les gardes OR de privilèges`

---

## Task 2 (Étape 1) : GAP-03a — `automation.secrets.manage` garde `/secrets`

**Files:**
- Modify: `core/app/secrets/routes.py`
- Modify: `core/app/roles/privileges.py` (`BUILT_IN_ROLE_PRIVILEGES["creator"]`)
- Modify: `core/tests/test_secrets_routes.py`
- Modify: `shell/src/auth/capabilities.test.ts` (fixture Créateur)
- Modify: `shell/e2e/mocks.ts` (`CREATOR_ME`)

**Interfaces:**
- Consumes: `require_any_privilege` (Task 1).

- [ ] **Step 0 — vérification pré-tâche** : reconfirmer les 3 routes de `core/app/secrets/routes.py` (`POST /secrets`, `GET /secrets`, `DELETE /secrets/{id}`) sont bien les 3 SEULS appels à `require_privilege(..., ADMIN_SECRETS_MANAGE...)` (`grep -n "ADMIN_SECRETS_MANAGE" core/app/secrets/routes.py`) — si un 4e site est apparu depuis, l'ajouter à cette tâche.

- [ ] **Step 1: Écrire les tests (RED)** — dans `core/tests/test_secrets_routes.py`, ajouter (le fichier a déjà une fixture `env()` avec `admin`/`regular` — `regular` est un utilisateur `creator` par défaut, cf. `get_or_create_user` sans flag bootstrap ; vérifier ce point avant d'écrire le test, ne pas le supposer) :

```python
def test_a_role_with_only_automation_secrets_manage_can_manage_secrets(env):
    app, client, Session, admin, regular = env
    with Session() as s:
        tenant_id = admin.tenant_id
        custom = create_role(
            s, tenant_id=tenant_id, name="Secrets pipeline",
            privileges=[Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )
        target = s.get(User, regular.id)
        target.role_id = custom.id
        s.commit()

    def override_user():
        with Session() as s:
            yield s.get(User, regular.id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user

    resp = client.post("/secrets", json=BEARER_BODY)
    assert resp.status_code == 201, resp.text
    resp = client.get("/secrets")
    assert resp.status_code == 200
    secret_id = resp.json()[0]["id"]
    resp = client.delete(f"/secrets/{secret_id}")
    assert resp.status_code == 204


def test_a_role_with_neither_secrets_privilege_is_rejected(env):
    app, client, Session, admin, regular = env
    with Session() as s:
        tenant_id = admin.tenant_id
        custom = create_role(s, tenant_id=tenant_id, name="Sans secrets", privileges=[])
        target = s.get(User, regular.id)
        target.role_id = custom.id
        s.commit()

    def override_user():
        with Session() as s:
            yield s.get(User, regular.id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user

    resp = client.post("/secrets", json=BEARER_BODY)
    assert resp.status_code == 403
```

Import supplémentaire en tête de fichier : `from app.roles.repository import create_role` et `from app.roles.privileges import Privilege`. Lancer :
`cd core && uv run pytest tests/test_secrets_routes.py -q` → les deux nouveaux tests échouent (403 sur le premier, garde encore fermée à `AUTOMATION_SECRETS_MANAGE` seul).

- [ ] **Step 2: Implémenter (GREEN)** — `core/app/secrets/routes.py`, remplacer les 3 occurrences :

```python
# AVANT (x3, une par route)
require_privilege(session, user, Privilege.ADMIN_SECRETS_MANAGE.value)

# APRÈS (x3)
require_any_privilege(
    session,
    user,
    [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value],
)
```

Import : remplacer `from app.roles.guards import require_privilege` par
`from app.roles.guards import require_any_privilege`.

- [ ] **Step 3: Rôle Créateur** — `core/app/roles/privileges.py`, `BUILT_IN_ROLE_PRIVILEGES["creator"]` :

```python
# AVANT
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

# APRÈS
"creator": [
    Privilege.CATALOG_MANAGE.value,
    Privilege.MAPS_MANAGE.value,
    Privilege.DATA_VIEW.value,
    Privilege.DATA_MANAGE.value,
    Privilege.APPS_MANAGE.value,
    Privilege.AUTOMATION_MANAGE.value,
    Privilege.AUTOMATION_SECRETS_MANAGE.value,
    Privilege.ANALYTICS_VIEW.value,
    Privilege.TASKS_VIEW.value,
],
```

Lancer : `cd core && uv run pytest tests/test_secrets_routes.py tests/test_roles_repository.py tests/test_roles_guards.py -q` → vert (le test caractéristique `test_roles_repository.py::…` qui compare `reconciled["creator"].privileges == BUILT_IN_ROLE_PRIVILEGES["creator"]` reste vert par construction — il compare au dict, pas à une liste figée en dur).

- [ ] **Step 4: Fixtures shell** — resynchroniser les deux miroirs manuels de `BUILT_IN_ROLE_PRIVILEGES` (le commentaire de `shell/e2e/mocks.ts:194-198` prévient explicitement que ces fixtures doivent suivre le fichier cœur) :

```typescript
// shell/e2e/mocks.ts — CREATOR_ME.privileges, ajouter "automation.secrets.manage"
// après "automation.manage"
```

```typescript
// shell/src/auth/capabilities.test.ts — fixture Créateur (grep "automation.manage"
// dans ce fichier pour la localiser), même ajout
```

- [ ] **Step 5: Vérifier**

```bash
cd core && uv run pytest tests/test_secrets_routes.py tests/test_roles_guards.py tests/test_roles_repository.py -q
uv run ruff check app/secrets/routes.py app/roles/privileges.py
uv run ruff format --check app/secrets/routes.py app/roles/privileges.py
cd ../shell && npm run test -- capabilities
```

- [ ] **Commit** : `fix(core): garde de /secrets élargie à automation.secrets.manage, rôle Créateur mis à jour`

---

## Task 3 (Étape 2) : `core/app/usage/` — service de requête (query-only)

**Files:**
- Create: `core/app/usage/__init__.py` (vide)
- Create: `core/app/usage/service.py`
- Modify: `core/pyproject.toml` (`[[tool.importlinter.contracts]] layers`)
- Test: `core/tests/test_usage_service.py`

**Interfaces:**
- Produces: `JOB_AUDIT_ACTIONS: frozenset[str]`, `list_tasks(session, *, tenant_id, actor_id=None, page, page_size) -> tuple[list[AuditLog], int]`, `summarize(session, *, tenant_id, since, until, limit) -> UsageSummaryData` (dataclass ou TypedDict interne) — consommées par Task 4 (routes).

- [ ] **Step 0 — vérification pré-tâche** : reconfirmer la liste des `action=` réellement écrites par `write_audit(...)` dans le dépôt (celle de la spec §3.2 a été établie par grep en session de rédaction — la revérifier n'a jamais fait de mal, cf. piège CLAUDE.md n°3) :

```bash
grep -rn "action=" core/app --include=*.py | grep -v test | grep -oP 'action="\K[^"]+' | sort -u
```

Si une action job manque à la liste ci-dessous (nouvelle famille ajoutée entre la rédaction de la spec et l'exécution de ce plan), l'ajouter à `JOB_AUDIT_ACTIONS`.

- [ ] **Step 1: Ajouter `app.usage` au contrat de couches AVANT le code** (sinon Task 3/4 ne peuvent pas être vérifiées par `lint-imports` sans échouer faute d'entrée) — `core/pyproject.toml`, `layers = [...]`, insérer `"app.usage",` juste après `"app.admin_tools",` :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.copilot",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.reports",
    "app.alerts",
    "app.export",
    "app.appexport",
    "app.tileset3d",
    "app.terrain3d",
    "app.mapicons",
    "app.admin_tools",
    "app.usage",
    "app.secrets",
    # ... reste inchangé
]
```

Lancer `cd core && uv run lint-imports` → doit encore passer (aucun module n'importe encore `app.usage`, l'entrée est inerte pour l'instant).

- [ ] **Step 2: Écrire le test (RED)**

```python
# core/tests/test_usage_service.py
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta

from app.audit.writer import write_audit
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.usage.service import JOB_AUDIT_ACTIONS, list_tasks, summarize
from app.users.repository import get_or_create_user


def _seed(s, *, tenant_id, actor_id, action, object_type="pipeline", object_id="p1"):
    write_audit(
        s, tenant_id=tenant_id, actor_id=actor_id, actor_kind="user",
        action=action, object_type=object_type, object_id=object_id,
    )


def test_list_tasks_filters_to_job_actions_and_tenant():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        other_tenant_id = "autre-tenant"
        # bruit : action non-job du même tenant, et action job d'un AUTRE tenant
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="config.update")
        _seed(s, tenant_id=other_tenant_id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u2", action="export.run")
        s.commit()

        rows, total = list_tasks(s, tenant_id=tenant.id, page=1, page_size=50)
        assert total == 2
        assert {r.action for r in rows} == {"pipeline.run", "export.run"}
        assert all(r.tenant_id == tenant.id for r in rows)


def test_list_tasks_scopes_to_one_actor_when_requested():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u2", action="pipeline.run")
        s.commit()

        rows, total = list_tasks(s, tenant_id=tenant.id, actor_id="u1", page=1, page_size=50)
        assert total == 1
        assert rows[0].actor_id == "u1"


def test_list_tasks_paginates_and_orders_newest_first():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        for i in range(3):
            _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run", object_id=f"p{i}")
        s.commit()

        page1, total = list_tasks(s, tenant_id=tenant.id, page=1, page_size=2)
        assert total == 3
        assert len(page1) == 2
        page2, _ = list_tasks(s, tenant_id=tenant.id, page=2, page_size=2)
        assert len(page2) == 1
        # tri décroissant sur created_at : id auto-incrément croissant sert de
        # témoin d'ordre d'insertion sur sqlite (même seconde possible)
        assert page1[0].id > page1[1].id


def test_summarize_aggregates_by_actor_and_resource_across_all_actions():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="s1", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed(s, tenant_id=tenant.id, actor_id="u-inconnu", action="config.update",
              object_type="collection", object_id="c1")
        _seed(s, tenant_id=tenant.id, actor_id="u-inconnu", action="config.update",
              object_type="collection", object_id="c1")
        _seed(s, tenant_id=tenant.id, actor_id="u-inconnu", action="feature.create",
              object_type="collection", object_id="c2")
        s.commit()

        now = datetime.now(UTC)
        summary = summarize(
            s, tenant_id=tenant.id, since=now - timedelta(days=1), until=now + timedelta(days=1),
            limit=10,
        )
        assert summary.total_actions == 3
        by_actor = {a.actor_id: a.count for a in summary.by_actor}
        assert by_actor["u-inconnu"] == 3
        by_resource = {(r.object_type, r.object_id): r.count for r in summary.by_resource}
        assert by_resource[("collection", "c1")] == 2
        assert by_resource[("collection", "c2")] == 1


def test_job_audit_actions_excludes_lifecycle_and_crud_actions():
    # garde-fou : ces actions ne doivent JAMAIS entrer dans la vue "tâches"
    for excluded in ("tileset3d.purge", "analytics.sql", "config.update", "role.create"):
        assert excluded not in JOB_AUDIT_ACTIONS
    for included in ("pipeline.run", "export.run", "ingestion.job_create"):
        assert included in JOB_AUDIT_ACTIONS
```

Lancer : `cd core && uv run pytest tests/test_usage_service.py -q` → échoue (module inexistant).

- [ ] **Step 3: Implémenter (GREEN)**

```python
# core/app/usage/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/usage/service.py
# SPDX-License-Identifier: Apache-2.0
"""Lecture agrégée d'audit_log — jamais d'écriture ici (app.audit.writer
reste l'unique point d'écriture). Deux usages : (1) journal des actions de
job d'un tenant (allowlist fixe, `list_tasks`) — donne enfin une route
réelle à tasks.view/tasks.view_all (GAP-03) ; (2) agrégats pleine largeur
sur tout audit_log (`summarize`) — vue d'usage GAP-71/GAP-28, activité par
acteur + popularité des ressources."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.users.models import User

# Établi par grep exhaustif sur les sites d'appel de write_audit() (core/app/*/jobs.py,
# */routes.py, */importer.py, */service.py, mcp/tools/pipelines.py) — cf. spec §3.2
# pour la justification de chaque exclusion. Revérifier ce grep avant de modifier
# cette liste (piège CLAUDE.md n°3) :
#   grep -rn "action=" core/app --include=*.py | grep -v test \
#     | grep -oP 'action="\K[^"]+' | sort -u
JOB_AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "ingestion.job_create",
        "pipeline.run",
        "export.create",
        "export.run",
        "appexport.create",
        "report.run",
        "report.notify",
        "alert.evaluate",
        "alert.notify",
        "harvest_source.run",
        "tileset3d.job_create",
        "terrain3d.job_create",
    }
)


def list_tasks(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None = None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    base = select(AuditLog).where(
        AuditLog.tenant_id == tenant_id,
        AuditLog.action.in_(JOB_AUDIT_ACTIONS),
    )
    if actor_id is not None:
        base = base.where(AuditLog.actor_id == actor_id)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.scalars(
            base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total


@dataclass
class ActorStat:
    actor_id: str | None
    actor_username: str | None
    count: int


@dataclass
class ResourceStat:
    object_type: str
    object_id: str
    count: int


@dataclass
class UsageSummaryData:
    by_actor: list[ActorStat] = field(default_factory=list)
    by_resource: list[ResourceStat] = field(default_factory=list)
    total_actions: int = 0


def summarize(
    session: Session,
    *,
    tenant_id: str,
    since: datetime,
    until: datetime,
    limit: int,
) -> UsageSummaryData:
    window = (
        AuditLog.tenant_id == tenant_id,
        AuditLog.created_at >= since,
        AuditLog.created_at <= until,
    )
    total_actions = session.scalar(
        select(func.count()).select_from(AuditLog).where(*window)
    ) or 0

    by_actor_rows = session.execute(
        select(AuditLog.actor_id, User.username, func.count().label("n"))
        .outerjoin(
            User, (User.id == AuditLog.actor_id) & (User.tenant_id == AuditLog.tenant_id)
        )
        .where(*window)
        .group_by(AuditLog.actor_id, User.username)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    by_actor = [ActorStat(actor_id=r[0], actor_username=r[1], count=r[2]) for r in by_actor_rows]

    by_resource_rows = session.execute(
        select(AuditLog.object_type, AuditLog.object_id, func.count().label("n"))
        .where(*window)
        .group_by(AuditLog.object_type, AuditLog.object_id)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    by_resource = [
        ResourceStat(object_type=r[0], object_id=r[1], count=r[2]) for r in by_resource_rows
    ]

    return UsageSummaryData(by_actor=by_actor, by_resource=by_resource, total_actions=total_actions)
```

Lancer : `cd core && uv run pytest tests/test_usage_service.py -q` → vert.

- [ ] **Step 4: Vérifier**

```bash
cd core
uv run pytest tests/test_usage_service.py -q
uv run ruff check app/usage/ && uv run ruff format --check app/usage/
uv run lint-imports
```

- [ ] **Commit** : `feat(core): app.usage — lecture agrégée d'audit_log (service query-only)`

---

## Task 4 (Étape 3) : routes `/usage/tasks` + `/usage/summary`

**Files:**
- Create: `core/app/usage/schemas.py`
- Create: `core/app/usage/routes.py`
- Modify: `core/app/main.py` (import + `include_router`)
- Test: `core/tests/test_usage_routes.py`

**Interfaces:**
- Consumes: `service.list_tasks`/`service.summarize` (Task 3), `require_privilege`/`require_any_privilege` (Task 1 + existant).
- Produces: `GET /usage/tasks`, `GET /usage/summary` — consommées par la Task 6 (shell).

- [ ] **Step 0 — vérification pré-tâche** : relire `core/app/notifications/routes.py` et `schemas.py` juste avant d'écrire cette tâche — patron à suivre à l'identique (pagination, `dict[str, Any]` vs `BaseModel`, dépendances `Depends(get_current_user)`/`Depends(get_session)`).

- [ ] **Step 1: Écrire le test (RED)**

```python
# core/tests/test_usage_routes.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        creator = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="c", username="creator",
            email=None, first_name="", last_name="",
        )  # rôle "creator" par défaut -> porte tasks.view, pas tasks.view_all
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        reader_role = create_role(s, tenant_id=tenant.id, name="Sans tâches", privileges=[])
        reader = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="reader",
            email=None, first_name="", last_name="",
        )
        reader.role_id = reader_role.id
        s.commit()
        write_audit(
            s, tenant_id=tenant.id, actor_id=creator.id, actor_kind="user",
            action="pipeline.run", object_type="pipeline", object_id="p1",
        )
        write_audit(
            s, tenant_id=tenant.id, actor_id=admin.id, actor_kind="user",
            action="export.run", object_type="dataset", object_id="d1",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, creator, admin, reader


def _as(app, Session, user):
    def override_user():
        with Session() as s:
            yield s.get(User, user.id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user


def test_tasks_view_holder_sees_only_own_actions(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["tasks"][0]["action"] == "pipeline.run"
    assert body["tasks"][0]["actorId"] == creator.id


def test_tasks_view_holder_gets_403_on_explicit_other_actor_id(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get(f"/usage/tasks?actorId={admin.id}")
    assert resp.status_code == 403


def test_tasks_view_all_holder_sees_every_actor(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, admin)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_no_tasks_privilege_is_rejected(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, reader)
    resp = client.get("/usage/tasks")
    assert resp.status_code == 403


def test_summary_requires_tasks_view_all_not_just_tasks_view(env):
    app, client, Session, creator, admin, reader = env
    _as(app, Session, creator)
    resp = client.get("/usage/summary")
    assert resp.status_code == 403

    _as(app, Session, admin)
    resp = client.get("/usage/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totalActions"] == 2
    assert len(body["byActor"]) == 2
```

Lancer : `cd core && uv run pytest tests/test_usage_routes.py -q` → échoue (404, routes inexistantes).

- [ ] **Step 2: Implémenter (GREEN)**

```python
# core/app/usage/schemas.py
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class UsageTaskRead(BaseModel):
    id: int
    actorId: str | None
    action: str
    objectType: str
    objectId: str
    createdAt: str


class UsageTaskPage(BaseModel):
    tasks: list[UsageTaskRead]
    total: int
    page: int
    pageSize: int


class UsageActorStatRead(BaseModel):
    actorId: str | None
    actorUsername: str | None
    count: int


class UsageResourceStatRead(BaseModel):
    objectType: str
    objectId: str
    count: int


class UsageSummaryRead(BaseModel):
    byActor: list[UsageActorStatRead]
    byResource: list[UsageResourceStatRead]
    totalActions: int
    windowStart: str
    windowEnd: str
```

```python
# core/app/usage/routes.py
# SPDX-License-Identifier: Apache-2.0
"""Routes de lecture d'audit_log (GAP-03b + GAP-71/28) — jamais d'écriture,
app.audit.writer reste l'unique point d'écriture. tasks.view restreint à
soi-même ; tasks.view_all lève cette restriction."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import has_privilege, require_any_privilege, require_privilege
from app.roles.privileges import Privilege
from app.usage import service
from app.usage.schemas import (
    UsageActorStatRead,
    UsageResourceStatRead,
    UsageSummaryRead,
    UsageTaskPage,
    UsageTaskRead,
)
from app.users.models import User

router = APIRouter()


@router.get("/usage/tasks")
def list_usage_tasks(
    page: int = 1,
    pageSize: int = 50,
    actorId: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UsageTaskPage:
    require_any_privilege(
        session, user, [Privilege.TASKS_VIEW.value, Privilege.TASKS_VIEW_ALL.value]
    )
    sees_all = has_privilege(session, user, Privilege.TASKS_VIEW_ALL.value)
    if not sees_all:
        if actorId is not None and actorId != user.id:
            raise HTTPException(status_code=403, detail="cannot view another actor's tasks")
        actorId = user.id
    rows, total = service.list_tasks(
        session,
        tenant_id=user.tenant_id,
        actor_id=actorId,
        page=page,
        page_size=min(pageSize, 200),
    )
    return UsageTaskPage(
        tasks=[
            UsageTaskRead(
                id=r.id,
                actorId=r.actor_id,
                action=r.action,
                objectType=r.object_type,
                objectId=r.object_id,
                createdAt=r.created_at.isoformat(),
            )
            for r in rows
        ],
        total=total,
        page=page,
        pageSize=pageSize,
    )


@router.get("/usage/summary")
def get_usage_summary(
    since: str | None = None,
    until: str | None = None,
    limit: int = 10,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UsageSummaryRead:
    require_privilege(session, user, Privilege.TASKS_VIEW_ALL.value)
    until_dt = datetime.fromisoformat(until) if until else datetime.now(UTC)
    since_dt = datetime.fromisoformat(since) if since else until_dt - timedelta(days=30)
    summary = service.summarize(
        session, tenant_id=user.tenant_id, since=since_dt, until=until_dt, limit=limit
    )
    return UsageSummaryRead(
        byActor=[
            UsageActorStatRead(actorId=a.actor_id, actorUsername=a.actor_username, count=a.count)
            for a in summary.by_actor
        ],
        byResource=[
            UsageResourceStatRead(objectType=r.object_type, objectId=r.object_id, count=r.count)
            for r in summary.by_resource
        ],
        totalActions=summary.total_actions,
        windowStart=since_dt.isoformat(),
        windowEnd=until_dt.isoformat(),
    )
```

`core/app/main.py` :

```python
# AVANT (ligne 62)
from app.tileset3d import routes as tileset3d_routes

# APRÈS
from app.tileset3d import routes as tileset3d_routes
from app.usage import routes as usage_routes
```

et, dans le bloc `include_router` (à la suite de `notifications_routes.router`, hors des blocs conditionnels `if CORE_*_ENABLED` — cette capacité est inconditionnelle, comme `notifications`, pas un opt-in instance-wide) :

```python
app.include_router(notifications_routes.router)
app.include_router(usage_routes.router)
```

- [ ] **Step 3: Vérifier**

```bash
cd core
uv run pytest tests/test_usage_routes.py tests/test_usage_service.py tests/test_roles_guards.py -q
uv run ruff check app/usage/ app/main.py && uv run ruff format --check app/usage/ app/main.py
uv run lint-imports
```

- [ ] **Commit** : `feat(core): GET /usage/tasks et /usage/summary — vue d'usage tenant-scopée`

---

## Task 5 (Étape 4) : régénération OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

- [ ] **Step 1** :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 2 — vérifier le diff** : `git diff core/openapi.json` doit montrer
  UNIQUEMENT `/usage/tasks` et `/usage/summary` en ajout — **aucune**
  modification sur `/secrets` (schéma de requête/réponse inchangé par la
  Task 2, seule la garde interne a changé) ; si `/secrets` apparaît dans le
  diff, quelque chose d'inattendu a changé sa forme — s'arrêter et
  diagnostiquer avant de continuer.

- [ ] **Commit** : `chore(core,shell): régénère OpenAPI + types TS (GET /usage/tasks, GET /usage/summary)`

---

## Task 6 (Étape 5) : shell — client API (`types.ts`, `domains/usage.ts`, hooks, composition)

**Files:**
- Modify: `shell/src/api/types.ts`
- Create: `shell/src/api/domains/usage.ts`
- Create: `shell/src/api/domains/usage.hooks.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient.listUsageTasks`/`ItemClient.getUsageSummary`, hooks `useUsageTasks`/`useUsageSummary` — consommés par Task 7 (`UsagePage`).

- [ ] **Step 0 — vérification pré-tâche** : relire `shell/src/api/domains/notifications.ts`/`.hooks.ts` intégralement (patron à reproduire à l'identique) et confirmer l'ordre alphabétique des imports dans `itemClient.ts` (`createTiles3dMethods` est actuellement le dernier import de domaine, `createUsageMethods` vient après).

- [ ] **Step 1: Écrire les tests (RED)** — dans `shell/src/api/itemClient.test.ts`, à la suite des tests existants (patron déjà en place : `request` mocké via un `fetch` intercepté, cf. tests `listItems`/`getMe` en tête de fichier) :

```typescript
test("listUsageTasks builds the query string and returns tasks+total", async () => {
  // même patron de mock que les tests listItems/getMe de ce fichier —
  // intercepter fetch, vérifier l'URL appelée et le mapping de la réponse
  // GET /usage/tasks?page=1&pageSize=50 -> { tasks: [...], total, page, pageSize }
});

test("getUsageSummary sends since/until/limit as query params", async () => {
  // GET /usage/summary?since=...&until=...&limit=10
});
```

Lancer : `cd shell && npm run test -- itemClient` → échoue (méthodes inexistantes).

- [ ] **Step 2: Implémenter (GREEN)**

```typescript
// shell/src/api/types.ts — ajouter aux types partagés
export type UsageTask = {
  id: number;
  actorId: string | null;
  action: string;
  objectType: string;
  objectId: string;
  createdAt: string;
};

export type UsageActorStat = { actorId: string | null; actorUsername: string | null; count: number };
export type UsageResourceStat = { objectType: string; objectId: string; count: number };
export type UsageSummary = {
  byActor: UsageActorStat[];
  byResource: UsageResourceStat[];
  totalActions: number;
  windowStart: string;
  windowEnd: string;
};

// sur l'interface ItemClient, à la suite des méthodes notifications :
listUsageTasks(params: {
  page: number;
  pageSize: number;
  actorId?: string;
}): Promise<{ tasks: UsageTask[]; total: number }>;
getUsageSummary(params?: { since?: string; until?: string; limit?: number }): Promise<UsageSummary>;
```

```typescript
// shell/src/api/domains/usage.ts
// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, UsageSummary, UsageTask } from "../types";
import type { ItemClientBase } from "../base";

type UsageMethods = Pick<ItemClient, "listUsageTasks" | "getUsageSummary">;

export function createUsageMethods(base: ItemClientBase): UsageMethods {
  const { request } = base;
  return {
    async listUsageTasks(params): Promise<{ tasks: UsageTask[]; total: number }> {
      const query = new URLSearchParams({
        page: String(params.page),
        pageSize: String(params.pageSize),
      });
      if (params.actorId) query.set("actorId", params.actorId);
      return request<{ tasks: UsageTask[]; total: number }>(
        "GET",
        `/usage/tasks?${query.toString()}`,
      );
    },

    async getUsageSummary(params = {}): Promise<UsageSummary> {
      const query = new URLSearchParams();
      if (params.since) query.set("since", params.since);
      if (params.until) query.set("until", params.until);
      if (params.limit) query.set("limit", String(params.limit));
      const qs = query.toString();
      return request<UsageSummary>("GET", `/usage/summary${qs ? `?${qs}` : ""}`);
    },
  };
}
```

```typescript
// shell/src/api/domains/usage.hooks.ts
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

export function useUsageTasks(params: { page: number; pageSize: number; actorId?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["usage", "tasks", params],
    queryFn: () => client.listUsageTasks(params),
  });
}

export function useUsageSummary(params: { since?: string; until?: string; limit?: number } = {}) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["usage", "summary", params],
    queryFn: () => client.getUsageSummary(params),
  });
}
```

`itemClient.ts` :

```typescript
// import, après createTiles3dMethods
import { createUsageMethods } from "./domains/usage";

// composition, après ...createTiles3dMethods(base),
...createUsageMethods(base),
```

`hooks.ts` (barrel) :

```typescript
export * from "./domains/usage.hooks";
```

- [ ] **Step 3: Vérifier**

```bash
cd shell
npm run test        # suite complète, pas seulement itemClient (piège CLAUDE.md n°6)
npm run build
```

- [ ] **Commit** : `feat(shell): client API du domaine usage (listUsageTasks/getUsageSummary)`

---

## Task 7 (Étape 6) : `UsagePage` — remplace `TasksComingSoonPage`

**Files:**
- Create: `shell/src/pages/UsagePage.tsx`
- Delete: `shell/src/pages/TasksComingSoonPage.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/UsagePage.test.tsx`
- Delete (si existant) : test dédié de `TasksComingSoonPage`

**Interfaces:**
- Consumes: `useUsageTasks`/`useUsageSummary` (Task 6), `useMe` (existant).

- [ ] **Step 0 — vérification pré-tâche** : relire `shell/src/pages/UsersAdminPage.tsx` intégralement (patron `TriptychLayout` + table paginée à reproduire) et confirmer si un fichier `TasksComingSoonPage.test.tsx` existe (`find shell/src -iname "*TasksComingSoon*"`) — si oui, le supprimer dans cette tâche plutôt que de le laisser tester un composant mort.

- [ ] **Step 1: Écrire le test (RED)**

```typescript
// shell/src/pages/UsagePage.test.tsx
// SPDX-License-Identifier: Apache-2.0
// Patron : mocker useMe (profil) + useUsageTasks/useUsageSummary (ou mocker
// fetch directement, selon le patron déjà en place dans
// UsersAdminPage.test.tsx — le relire d'abord et le suivre à l'identique).

test("un profil tasks.view (sans tasks.view_all) voit sa liste mais pas la section usage", async () => {
  // useMe -> privileges: ["tasks.view"]
  // useUsageTasks -> { tasks: [...], total: 1 }
  // assert : la table "Mes tâches récentes" est rendue
  // assert : la section "Usage de la plateforme" est ABSENTE du DOM
  //          (pas juste masquée par CSS — vérifier queryByText/queryByRole)
});

test("un profil tasks.view_all voit les deux sections", async () => {
  // useMe -> privileges: ["tasks.view", "tasks.view_all"]
  // useUsageSummary -> { byActor: [...], byResource: [...], totalActions: 5, ... }
  // assert : les deux sections sont rendues
});

test("état vide : aucune tâche récente affiche un message, pas une table vide", async () => {
  // useUsageTasks -> { tasks: [], total: 0 }
});

test("le libellé français de l'action est affiché, pas la clé technique brute", async () => {
  // task.action === "pipeline.run" -> le texte affiché n'est PAS "pipeline.run"
});
```

Lancer : `cd shell && npm run test -- UsagePage` → échoue (composant inexistant).

- [ ] **Step 2: Implémenter (GREEN)**

```typescript
// shell/src/pages/UsagePage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMe, useUsageSummary, useUsageTasks } from "../api/hooks";
import { EmptyState } from "../ui/kit/EmptyState";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

const PAGE_SIZE = 50;

// Libellé français par action de JOB_AUDIT_ACTIONS (core/app/usage/service.py)
// — tenu synchronisé manuellement, comme BUILT_IN_ROLE_PRIVILEGES/CREATOR_ME
// (même classe de duplication assumée que les fixtures de rôle, cf. Task 2).
const ACTION_LABELS: Record<string, string> = {
  "ingestion.job_create": t("usage.action.ingestionJobCreate"),
  "pipeline.run": t("usage.action.pipelineRun"),
  "export.create": t("usage.action.exportCreate"),
  "export.run": t("usage.action.exportRun"),
  "appexport.create": t("usage.action.appexportCreate"),
  "report.run": t("usage.action.reportRun"),
  "report.notify": t("usage.action.reportNotify"),
  "alert.evaluate": t("usage.action.alertEvaluate"),
  "alert.notify": t("usage.action.alertNotify"),
  "harvest_source.run": t("usage.action.harvestSourceRun"),
  "tileset3d.job_create": t("usage.action.tileset3dJobCreate"),
  "terrain3d.job_create": t("usage.action.terrain3dJobCreate"),
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

export function UsagePage() {
  const [page, setPage] = useState(1);
  const meQuery = useMe();
  const tasksQuery = useUsageTasks({ page, pageSize: PAGE_SIZE });
  const sameTenantAll = meQuery.data?.privileges.includes("tasks.view_all") === true;
  const summaryQuery = useUsageSummary(undefined /* uniquement monté si sameTenantAll, cf. rendu conditionnel ci-dessous */);

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← {t("domain.catalog")}
              </Link>
            </Panel>
          ),
        }}
        main={{
          id: "main",
          label: t("domain.tasks"),
          content: (
            <div className="flex flex-col gap-6 p-4">
              <section>
                <h2 className="text-lg font-semibold">{t("usage.myTasks")}</h2>
                {tasksQuery.data?.total === 0 ? (
                  <EmptyState title={t("usage.noTasks")} description="" />
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>{t("usage.columnAction")}</th>
                        <th>{t("usage.columnResource")}</th>
                        <th>{t("usage.columnDate")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasksQuery.data?.tasks.map((task) => (
                        <tr key={task.id}>
                          <td>{actionLabel(task.action)}</td>
                          <td>{task.objectType}/{task.objectId}</td>
                          <td>{task.createdAt}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {/* pagination : même patron que UsersAdminPage (totalPages dérivé
                    de tasksQuery.data.total / PAGE_SIZE) */}
              </section>
              {sameTenantAll && (
                <section>
                  <h2 className="text-lg font-semibold">{t("usage.platformUsage")}</h2>
                  {summaryQuery.data && (
                    <div className="flex gap-8">
                      <div>
                        <h3>{t("usage.byActor")}</h3>
                        <ol>
                          {summaryQuery.data.byActor.map((a) => (
                            <li key={a.actorId ?? "?"}>
                              {a.actorUsername ?? a.actorId ?? "?"} — {a.count}
                            </li>
                          ))}
                        </ol>
                      </div>
                      <div>
                        <h3>{t("usage.byResource")}</h3>
                        <ol>
                          {summaryQuery.data.byResource.map((r) => (
                            <li key={`${r.objectType}/${r.objectId}`}>
                              {r.objectType}/{r.objectId} — {r.count}
                            </li>
                          ))}
                        </ol>
                      </div>
                    </div>
                  )}
                </section>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
```

Note d'implémentation : `useUsageSummary` ne doit s'exécuter (`enabled: sameTenantAll`) que si le profil porte `tasks.view_all` — sinon React Query émettrait un appel réseau vers un endpoint qui répondra 403 pour un profil qui n'en a pas besoin. Ajuster `useUsageSummary` (Task 6) pour accepter un `enabled?: boolean` optionnel si ce n'est pas déjà le cas, ou passer `enabled` directement dans le hook local ici via une option additionnelle — trancher au moment de l'implémentation selon le patron React Query déjà en place ailleurs dans ce dépôt (`useUnreadNotificationCount` n'a pas ce besoin, chercher un hook conditionnel existant, ex. `usePipelineRun` avec `enabled` sur un id optionnel, pour le patron exact).

`shell/src/shell/routes.tsx` :

```typescript
// AVANT
import { TasksComingSoonPage } from "../pages/TasksComingSoonPage";
// ...
<Route path="/tasks" element={<TasksComingSoonPage />} />

// APRÈS
import { UsagePage } from "../pages/UsagePage";
// ...
<Route
  path="/tasks"
  element={
    <RequirePrivilege privilege="tasks.view" deniedMessage="Accès réservé — privilège tasks.view requis.">
      <UsagePage />
    </RequirePrivilege>
  }
/>
```

`shell/src/i18n/catalog.fr.ts` : retirer `"comingSoon.tasks"`, ajouter les clés `usage.*`/`usage.action.*` utilisées ci-dessus (libellés français des 12 actions de `JOB_AUDIT_ACTIONS`, ex. `"usage.action.pipelineRun": "Exécution de pipeline"`).

- [ ] **Step 3: Vérifier**

```bash
cd shell
npm run test    # suite complète
npm run lint && npm run format:check
npm run build
```

- [ ] **Commit** : `feat(shell): UsagePage remplace TasksComingSoonPage — mes tâches + usage plateforme`

---

## Task 8 (Étape 7) : E2E

**Files:**
- Create: `shell/e2e/tasks.spec.ts`

- [ ] **Step 0 — vérification pré-tâche** : relire un spec E2E existant qui bascule entre personas via `mockMe(page, ...)` (ex. `shell/e2e/*.spec.ts` qui utilise `ADMIN_ME`/`CREATOR_ME`, `grep -rln "mockMe(page, ADMIN_ME)" shell/e2e`) pour le patron exact de mock réseau (`page.route`) à reproduire pour `/usage/tasks` et `/usage/summary`.

- [ ] **Step 1: Écrire le spec (RED)**

```typescript
// shell/e2e/tasks.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { ADMIN_ME, mockMe } from "./mocks";
// ... imports habituels de ce répertoire (helpers de navigation/login mock)

test("persona Créateur : voit ses tâches, pas la section usage plateforme", async ({ page }) => {
  await mockMe(page /* défaut = creator, cf. DEFAULT_ME */);
  await page.route("**/usage/tasks**", (route) =>
    route.fulfill({ json: { tasks: [{ id: 1, actorId: "me", action: "pipeline.run", objectType: "pipeline", objectId: "p1", createdAt: "2026-09-01T00:00:00Z" }], total: 1, page: 1, pageSize: 50 } }),
  );
  await page.goto("/tasks");
  await expect(page.getByText(/Mes tâches récentes/i)).toBeVisible();
  await expect(page.getByText(/Usage de la plateforme/i)).toHaveCount(0);
});

test("persona Administrateur : voit les deux sections", async ({ page }) => {
  await mockMe(page, ADMIN_ME);
  await page.route("**/usage/tasks**", (route) =>
    route.fulfill({ json: { tasks: [], total: 0, page: 1, pageSize: 50 } }),
  );
  await page.route("**/usage/summary**", (route) =>
    route.fulfill({
      json: {
        byActor: [{ actorId: "u1", actorUsername: "alice", count: 3 }],
        byResource: [{ objectType: "collection", objectId: "c1", count: 2 }],
        totalActions: 3,
        windowStart: "2026-08-01T00:00:00Z",
        windowEnd: "2026-09-01T00:00:00Z",
      },
    }),
  );
  await page.goto("/tasks");
  await expect(page.getByText(/Usage de la plateforme/i)).toBeVisible();
});
```

Lancer : `cd shell && npx playwright test tasks.spec.ts` → échoue (page/route inexistante avant Task 7 — si cette tâche est exécutée après Task 7 comme prévu par l'ordre du plan, elle doit au contraire échouer pour de mauvaises assertions temporaires, puis passer une fois le spec correctement calé sur le DOM réel de `UsagePage`. Ajuster les sélecteurs `getByText`/`getByRole` au DOM réellement produit par la Task 7, pas à ce pseudo-code).

- [ ] **Step 2: Faire passer** — ajuster les sélecteurs si nécessaire pour matcher le DOM réel de `UsagePage.tsx` produit en Task 7.

- [ ] **Step 3: Vérifier** `cd shell && VITE_AUTH_MODE=mock npm run e2e -- tasks.spec.ts` (puis suite complète en Task 9).

- [ ] **Commit** : `test(e2e): tasks.spec — vue d'usage par persona`

---

## Task 9 (Étape 8) : vérification finale et clôture

**Files:** aucun fichier de production — vérification uniquement, plus la mise à jour de `CLAUDE.md`.

- [ ] **Step 1 — suite complète cœur**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run pytest
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

Note : `app.usage` n'entre pas dans le périmètre `mypy --strict` (4 modules
listés dans `Global Constraints`/CLAUDE.md ne l'incluent pas) — mypy non
strict standard s'applique quand même via la configuration globale du
projet, vérifier qu'il ne râle pas.

- [ ] **Step 2 — suite complète shell**

```bash
cd shell
rm -rf dist dist-export   # piège coverage documenté 4 fois (CLAUDE.md)
npm run lint && npm run format:check
npm run test
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
VITE_AUTH_MODE=mock npm run e2e
```

- [ ] **Step 3 — pre-commit** : `uvx pre-commit run --all-files`

- [ ] **Step 4 — revue finale de branche** (CLAUDE.md piège n°4 : une revue
  par tâche ne suffit pas) — relire spécifiquement :
  - `automation.secrets.manage` gardé UNIQUEMENT sur `/secrets` (pas
    d'autre site qui l'ignorerait — grep `AUTOMATION_SECRETS_MANAGE` sur
    tout `core/app`) ;
  - `tasks.view`/`tasks.view_all` gardent `/usage/tasks` ET `/usage/summary`
    correctement (pas un endpoit oublié sur la restriction actor_id) ;
  - le contrat de couches (`lint-imports`) n'a nécessité AUCUNE exemption
    nommée pour `app.usage` — si une exemption a dû être ajoutée en cours de
    route, c'est un signal que le placement choisi en Task 3 était faux,
    revenir dessus plutôt que de la garder ;
  - les 3 fixtures de miroir de `BUILT_IN_ROLE_PRIVILEGES["creator"]`
    (`capabilities.test.ts`, `shell/e2e/mocks.ts`, tout autre site qu'un
    grep `AUTOMATION_SECRETS_MANAGE\|automation.secrets.manage` ferait
    apparaître) sont bien synchronisées.

- [ ] **Step 5 — mise à jour `CLAUDE.md`** : une ligne dans `### Livré`
  (`SP-47 — …`), retrait des deux entrées `REV-097`
  (`automation.secrets.manage`/`tasks.view_all` sans route) de la section
  « Suivis et dette non bloquante » si elles y figurent encore telles
  quelles au moment de l'exécution (revérifier le texte actuel de
  `CLAUDE.md` avant d'éditer — il peut avoir changé depuis la rédaction de
  ce plan).

- [ ] **Commit** : `docs: clôture SP-47 — CLAUDE.md`

---

## Self-Review (à faire par l'exécutant avant de remettre la branche)

- Vérifier qu'aucune des 3 routes `/secrets` n'a été oubliée dans la Task 2
  (grep direct sur le fichier final, pas sur ce plan).
- Vérifier que `GET /usage/tasks` sans aucun paramètre, pour un profil
  `tasks.view` seul, ne fuit JAMAIS les tâches d'un autre acteur (test
  explicite en Task 4 — mais revérifier en lisant le code final, pas
  seulement en faisant confiance au test qui pourrait lui-même avoir un
  trou, cf. CLAUDE.md piège n°10 sur la falsification des filets de test).
- Vérifier que `JOB_AUDIT_ACTIONS` (Task 3) a bien été revérifié par grep
  au moment de l'exécution réelle (pas recopié aveuglément de ce plan,
  écrit à une date antérieure — une nouvelle famille de job a pu être
  ajoutée entretemps).
- Vérifier que la suite E2E complète (pas seulement `tasks.spec.ts`) est
  verte avant de clore (piège CLAUDE.md n°6).
