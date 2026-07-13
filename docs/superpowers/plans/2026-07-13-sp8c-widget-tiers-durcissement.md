# SP-8c — Widget tiers réel, admin, permissions serveur, containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close SP-8 (jalon M5 « SDK ouvrable ») — un widget WC réellement hébergé hors du repo shell (cross-origin) fonctionne dans le builder sans redéploiement, un admin peut l'activer/désactiver depuis le shell, une config qui dépasse le scope de permissions déclaré d'une extension est rejetée par le cœur, et une extension défaillante ne casse plus les actions composées des autres widgets.

**Architecture:** Quatre chantiers indépendants au niveau code, tous construits sur le registre d'extensions de SP-8b (`app.extensions`, `shell/src/builder/extensions/`) : (1) un widget WC minimal hors de `shell/src`, servi par un serveur statique dédié avec CORS pour une E2E réellement cross-origin ; (2) `isAdmin` exposé par `GET /me` + première page admin du shell (liste + toggle enabled) ; (3) une fonction de validation côté cœur qui rejette (400) une config dont un widget d'extension route une collection hors de son scope déclaré ; (4) `ActionBus.emit` isolé par handler (try/catch) pour qu'un handler défaillant n'interrompe pas les messages composés suivants.

**Tech Stack:** FastAPI/SQLAlchemy/Pydantic (cœur), React/TanStack Query/Vitest (shell), Playwright (E2E), Node natif (serveur statique E2E, aucune dépendance npm supplémentaire).

## Global Constraints

- Docs et messages utilisateur en français ; code/identifiants en anglais (CLAUDE.md).
- Commits conventionnels (`feat(shell): …`, `fix(core): …`, `docs: …`), un sujet par commit.
- Baseline avant cette branche : **369 tests cœur passed/62 skipped**, **435 tests shell**, **30 specs E2E vertes** — aucune régression tolérée.
- Toute modification d'une route/schéma cœur exposé (nouveau champ de réponse, nouveau paramètre de requête) doit être suivie d'une régénération de `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` (CI `api-types-drift` les compare à l'identique) :
  ```bash
  cd core && PYTHONPATH=. uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
- Le widget externe de référence (`examples/external-widget/`) est zéro-dépendance et zéro-build : JS natif uniquement, jamais de TypeScript compilé ni de Lit — un auteur tiers doit pouvoir le copier sans notre toolchain.
- `app.extensions` doit être déclaré dans le contrat `layers` d'import-linter (`core/pyproject.toml`) dès qu'un autre module du cœur l'importe — vérifier `uv run lint-imports` après toute nouvelle dépendance inter-modules.
- Toute nouvelle route cœur mutante (`PATCH`, `POST`) reste auditée (`write_audit`) — patron déjà en place, ne pas le casser.

---

### Task 1: Core — `isAdmin` exposé par `GET /me`

**Files:**
- Modify: `core/app/auth/routes.py:14-32` (`MeResponse`, `get_me`)
- Test: `core/tests/test_me.py`

**Interfaces:**
- Produces: `GET /me` retourne désormais `isAdmin: bool` en plus des champs existants (`id`, `tenantId`, `username`, `email`, `firstName`, `lastName`).

- [ ] **Step 1: Écrire les tests qui échouent**

Remplacer le contenu de `core/tests/test_me.py` par :

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client(*, username: str, oidc_sub: str, bootstrap_admin: bool = False) -> TestClient:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub=oidc_sub,
            username=username, email=f"{username}@example.com",
            first_name="Alice", last_name="Doe", bootstrap_admin=bootstrap_admin,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def client():
    return _make_client(username="alice", oidc_sub="sub-1")


@pytest.fixture()
def admin_client():
    return _make_client(username="admin", oidc_sub="sub-admin", bootstrap_admin=True)


def test_get_me_returns_the_resolved_user(client):
    response = client.get("/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert body["firstName"] == "Alice"
    assert body["isAdmin"] is False


def test_get_me_reflects_admin_flag(admin_client):
    response = admin_client.get("/me")
    assert response.json()["isAdmin"] is True
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_me.py -v`
Expected: FAIL — `KeyError: 'isAdmin'` sur les deux tests (le champ n'existe pas encore dans la réponse).

- [ ] **Step 3: Implémenter**

Dans `core/app/auth/routes.py`, remplacer :

```python
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

par :

```python
class MeResponse(BaseModel):
    id: str
    tenantId: str
    username: str
    email: str | None
    firstName: str
    lastName: str
    isAdmin: bool


@router.get("/me", response_model=MeResponse)
def get_me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        isAdmin=user.is_admin,
    )
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_me.py -v`
Expected: PASS (2 passed)

Run la suite complète pour vérifier l'absence de régression : `cd core && uv run pytest -q`
Expected: `369 passed, 62 skipped` → `369 passed, 62 skipped` (compte inchangé, seul le contenu de `test_me.py` a changé sans ajouter de test — 2 tests existaient déjà, toujours 2).

- [ ] **Step 5: Régénérer le schéma OpenAPI et commiter**

```bash
cd core && PYTHONPATH=. uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd ..
git add core/app/auth/routes.py core/tests/test_me.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): GET /me expose isAdmin"
```

---

### Task 2: Core — `GET /extensions?all=true` pour les admins

**Files:**
- Modify: `core/app/extensions/repository.py:34-36` (renomme `list_active_extensions` en `list_extensions` avec un paramètre `include_disabled`)
- Modify: `core/app/extensions/routes.py:69-75` (route `list_extensions`)
- Test: `core/tests/test_extensions_repository.py`
- Test: `core/tests/test_extensions_routes.py`

**Interfaces:**
- Consumes: `Extension` (modèle SQLAlchemy, `core/app/extensions/models.py`, inchangé).
- Produces: `repo.list_extensions(session, *, tenant_id: str, include_disabled: bool = False) -> list[Extension]`. `GET /extensions?all=true` retourne aussi les extensions désactivées **si et seulement si** l'appelant est un admin authentifié ; sinon comportement inchangé (`enabled=True` uniquement).

- [ ] **Step 1: Écrire les tests qui échouent (repository)**

Dans `core/tests/test_extensions_repository.py`, remplacer les deux occurrences de `repo.list_active_extensions` par `repo.list_extensions` (mêmes arguments — `include_disabled` a une valeur par défaut, donc l'appel reste identique), et ajouter à la fin du fichier :

```python
def test_list_extensions_include_disabled_returns_all():
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
        assert repo.list_extensions(s, tenant_id=tenant_id) == []
        assert [e.id for e in repo.list_extensions(s, tenant_id=tenant_id, include_disabled=True)] == ["acme.gauge"]
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_extensions_repository.py -v`
Expected: FAIL — `AttributeError: module 'app.extensions.repository' has no attribute 'list_extensions'`

- [ ] **Step 3: Implémenter le repository**

Dans `core/app/extensions/repository.py`, remplacer :

```python
def list_active_extensions(session: Session, *, tenant_id: str) -> list[Extension]:
    stmt = select(Extension).where(Extension.tenant_id == tenant_id, Extension.enabled.is_(True))
    return list(session.scalars(stmt.order_by(Extension.label)).all())
```

par :

```python
def list_extensions(session: Session, *, tenant_id: str, include_disabled: bool = False) -> list[Extension]:
    stmt = select(Extension).where(Extension.tenant_id == tenant_id)
    if not include_disabled:
        stmt = stmt.where(Extension.enabled.is_(True))
    return list(session.scalars(stmt.order_by(Extension.label)).all())
```

- [ ] **Step 4: Vérifier que les tests repository passent**

Run: `cd core && uv run pytest tests/test_extensions_repository.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Écrire les tests qui échouent (routes)**

Ajouter à la fin de `core/tests/test_extensions_routes.py` :

```python
def test_get_extensions_all_true_shows_disabled_to_admin(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    default_listed = client.get("/extensions").json()["extensions"]
    assert default_listed == []
    all_listed = client.get("/extensions?all=true").json()["extensions"]
    assert [e["id"] for e in all_listed] == ["acme.gauge"]


def test_get_extensions_all_true_ignored_for_non_admin(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    _as(app, regular)
    listed = client.get("/extensions?all=true").json()["extensions"]
    assert listed == []


def test_get_extensions_all_true_ignored_for_anonymous(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    del app.dependency_overrides[get_current_user_optional]
    listed = client.get("/extensions?all=true").json()["extensions"]
    assert listed == []
```

- [ ] **Step 6: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_extensions_routes.py -v`
Expected: FAIL sur les 3 nouveaux tests — la route ne connaît pas encore le paramètre `all` (FastAPI ignore silencieusement un query param non déclaré, donc `?all=true` ne change rien : les 2 premiers tests échouent sur l'assertion `all_listed`/`listed`).

- [ ] **Step 7: Implémenter la route**

Dans `core/app/extensions/routes.py`, remplacer :

```python
@router.get("/extensions")
def list_extensions(
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    exts = repo.list_active_extensions(session, tenant_id=tenant_id)
    return {"extensions": [_extension_json(e) for e in exts]}
```

par :

```python
@router.get("/extensions")
def list_extensions(
    all: bool = False,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    include_disabled = bool(user and user.is_admin and all)
    exts = repo.list_extensions(session, tenant_id=tenant_id, include_disabled=include_disabled)
    return {"extensions": [_extension_json(e) for e in exts]}
```

- [ ] **Step 8: Vérifier que tout passe**

Run: `cd core && uv run pytest tests/test_extensions_routes.py tests/test_extensions_repository.py -v`
Expected: PASS (10 passed + 3 passed = 13 passed)

Run la suite complète : `cd core && uv run pytest -q`
Expected: `373 passed, 62 skipped` (369 + 4 nouveaux tests : 1 repository (Step 1) + 3 routes (Step 5)).

- [ ] **Step 9: Régénérer le schéma OpenAPI et commiter**

```bash
cd core && PYTHONPATH=. uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd ..
git add core/app/extensions/repository.py core/app/extensions/routes.py core/tests/test_extensions_repository.py core/tests/test_extensions_routes.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): GET /extensions?all=true montre les extensions désactivées à un admin"
```

---

### Task 3: Core — validation du scope de permissions à l'enregistrement d'une config

**Files:**
- Create: `core/app/configs/extension_permissions.py`
- Modify: `core/app/configs/routes.py` (import + helper `_validate_extension_scope` + appel dans `create_config`/`update_config`/`update_config_by_item`)
- Modify: `core/pyproject.toml` (déclarer `app.extensions` dans le contrat `layers`)
- Test: `core/tests/test_configs_extension_permissions.py` (nouveau)

**Interfaces:**
- Consumes: `BuilderConfig`, `LayoutItem`, `Layout`, `Page` (`core/app/configs/schemas.py`, inchangés) ; `Extension` (`core/app/extensions/models.py`, inchangé).
- Produces: `validate_extension_permissions(session: Session, config: BuilderConfig, *, tenant_id: str) -> None` — lève `ExtensionPermissionError` si un widget d'extension route une collection hors de son scope déclaré ; ne lève rien sinon (widgets non-extension, extensions à permissions `"all"`, props hors scope non renseignées).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `core/tests/test_configs_extension_permissions.py` :

```python
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.extensions import repository as ext_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1", username="alice",
            email="alice@example.com", first_name="Alice", last_name="Doe",
        )
        ext_repo.create_extension(
            s, tenant_id=tenant.id, owner_id=user.id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge", module_url="https://x/gauge.js",
            props=[{"name": "source", "type": "dataSource", "label": "Source", "default": None}],
            events=None, actions=None,
            default_size={"w": 2, "h": 2},
            permissions={"collections": ["communes"]},
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant_id = tenant.id  # type: ignore[attr-defined]
    return test_client


def _config_body(data_source_layer: str) -> dict:
    return {
        "kind": "app",
        "dataSources": [{"id": "ds1", "type": "features", "service": "core", "layer": data_source_layer, "query": {}}],
        "layout": {"type": "grid", "items": [
            {"widget": "acme.gauge", "x": 0, "y": 0, "w": 2, "h": 2, "props": {"source": "ds1"}},
        ]},
    }


def test_create_config_rejects_extension_prop_outside_scope(client):
    response = client.post("/configs", json={"title": "App", "config": _config_body("incidents")})
    assert response.status_code == 400
    assert "acme.gauge" in response.json()["detail"]


def test_create_config_accepts_extension_prop_inside_scope(client):
    response = client.post("/configs", json={"title": "App", "config": _config_body("communes")})
    assert response.status_code == 201


def test_create_config_ignores_non_extension_widgets(client):
    body = {
        "kind": "app",
        "dataSources": [],
        "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 2, "h": 2}]},
    }
    response = client.post("/configs", json={"title": "App", "config": body})
    assert response.status_code == 201


def test_update_config_rejects_extension_prop_outside_scope(client):
    created = client.post("/configs", json={"title": "App", "config": _config_body("communes")}).json()
    response = client.put(f"/configs/{created['id']}", json=_config_body("incidents"))
    assert response.status_code == 400


def test_rejected_create_does_not_leave_an_orphan_item(client):
    client.post("/configs", json={"title": "App", "config": _config_body("incidents")})
    listed = client.get("/items").json()
    assert listed["total"] == 0


def test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope(client):
    from app.extensions import repository as ext_repo

    # v1 : "communes" est dans le scope déclaré de l'extension au moment de la création.
    created = client.post("/configs", json={"title": "App", "config": _config_body("communes")}).json()

    # Un admin resserre ensuite le scope de l'extension : "communes" n'est
    # plus autorisée. On le fait directement en base (pas via l'API
    # /extensions, hors périmètre de ce test) pour isoler le comportement du
    # rollback de celui de la route PATCH /extensions déjà testée ailleurs.
    with client.session_factory() as s:
        ext = ext_repo.get_extension(s, tenant_id=client.tenant_id, extension_id="acme.gauge")
        ext_repo.update_extension(s, ext, permissions={"collections": ["incidents"]})
        s.commit()

    # create_config/update_config revalident bien contre le scope courant :
    # "communes" est désormais refusée.
    reject = client.put(f"/configs/{created['id']}", json=_config_body("communes"))
    assert reject.status_code == 400

    # Mais rollback restaure v1 tel quel, sans revalidation contre le scope
    # courant — comportement volontaire (cf. spec, §Hors périmètre).
    rollback = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 200
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_configs_extension_permissions.py -v`
Expected: FAIL — `test_create_config_rejects_extension_prop_outside_scope` et `test_update_config_rejects_extension_prop_outside_scope` reçoivent `201`/`200` au lieu de `400` ; `test_rejected_create_does_not_leave_an_orphan_item` échoue (`total == 1`, un item a été créé) ; `test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope` échoue sur l'assertion `reject.status_code == 400` (reçoit `200`, la validation n'existe pas encore).

- [ ] **Step 3: Implémenter la validation**

Créer `core/app/configs/extension_permissions.py` :

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig, LayoutItem
from app.extensions.models import Extension


class ExtensionPermissionError(Exception):
    def __init__(self, widget: str, prop: str, collection: str) -> None:
        self.widget = widget
        self.prop = prop
        self.collection = collection
        super().__init__(
            f"widget '{widget}' prop '{prop}': collection '{collection}' is outside its declared permissions"
        )


def _all_layout_items(config: BuilderConfig) -> list[LayoutItem]:
    items: list[LayoutItem] = []
    if config.layout:
        items.extend(config.layout.items)
    for page in config.pages:
        items.extend(page.layout.items)
    return items


def validate_extension_permissions(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    items = _all_layout_items(config)
    widget_types = {item.widget for item in items}
    if not widget_types:
        return
    extensions = {
        ext.id: ext
        for ext in session.scalars(
            select(Extension).where(Extension.tenant_id == tenant_id, Extension.id.in_(widget_types))
        )
    }
    if not extensions:
        return
    data_sources_by_id = {ds.id: ds for ds in config.dataSources}
    for item in items:
        ext = extensions.get(item.widget)
        if ext is None:
            continue
        allowed = ext.permissions.get("collections", "all")
        if allowed == "all":
            continue
        data_source_props = {p["name"] for p in ext.props if p["type"] == "dataSource"}
        for prop_name in data_source_props:
            value = item.props.get(prop_name)
            if not value:
                continue
            source = data_sources_by_id.get(value)
            if source is None:
                continue
            if source.layer not in allowed:
                raise ExtensionPermissionError(item.widget, prop_name, source.layer)
```

- [ ] **Step 4: Câbler la validation dans les routes**

Dans `core/app/configs/routes.py`, ajouter l'import (après `from app.configs.schemas import BuilderConfig`) :

```python
from app.configs.extension_permissions import ExtensionPermissionError, validate_extension_permissions
```

Ajouter un helper juste avant `create_config` :

```python
def _validate_extension_scope(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    try:
        validate_extension_permissions(session, config, tenant_id=tenant_id)
    except ExtensionPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
```

Modifier `create_config` — insérer l'appel en toute première ligne du corps, avant la création de l'item :

```python
@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    item = items_repo.create_item(
        session, tenant_id=user.tenant_id, owner_id=user.id,
        resource_type=request.config.kind, title=request.title,
    )
    result = repo.create_config(session, request.config, item_id=item.id, tenant_id=user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.create", object_type="config", object_id=result.id,
        payload={"title": request.title, "kind": request.config.kind},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.create", object_type="item", object_id=item.id,
        payload={"title": request.title},
    )
    return result
```

Modifier `update_config` — insérer l'appel juste après `_require_access`, avant `repo.update_config` :

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
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)

    result = repo.update_config(session, config_id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=config_id, payload={},
    )
    return result
```

Modifier `update_config_by_item` — insérer l'appel après la résolution de `existing`, avant `repo.update_config` :

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
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    result = repo.update_config(session, existing.id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=existing.id, payload={},
    )
    return result
```

- [ ] **Step 5: Déclarer `app.extensions` dans le contrat de couches**

`app.configs` importe maintenant `app.extensions` (nouveau) — sans déclaration, `app.extensions` reste hors du contrat `layers` (import-linter ne le vérifierait pas du tout, un trou pré-existant depuis SP-8b). Dans `core/pyproject.toml`, remplacer :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.features",
    "app.collections",
    "app.configs",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

par :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

(`app.extensions` importe `app.tenants`/`app.auth`/`app.audit`, tous plus bas dans la liste — placé juste sous `app.configs`, qui l'importe désormais, et au-dessus de tout ce qu'il importe lui-même.)

- [ ] **Step 6: Vérifier que tout passe**

Run: `cd core && uv run pytest tests/test_configs_extension_permissions.py -v`
Expected: PASS (6 passed)

Run: `cd core && uv run lint-imports`
Expected: pas d'erreur (contrat de couches respecté).

Run la suite complète : `cd core && uv run pytest -q`
Expected: `379 passed, 62 skipped` (373 de Task 2 + 6 nouveaux).

- [ ] **Step 7: Commiter**

```bash
git add core/app/configs/extension_permissions.py core/app/configs/routes.py core/pyproject.toml core/tests/test_configs_extension_permissions.py
git commit -m "feat(core): rejette une config qui route une collection hors du scope d'une extension"
```

---

### Task 4: Shell — containment des erreurs runtime dans `ActionBus.emit`

**Files:**
- Modify: `shell/src/builder/ActionBus.ts:39-46`
- Test: `shell/src/builder/ActionBus.test.ts`

**Interfaces:**
- Produces: `ActionBus.emit()` ne lève plus si un handler cible lève — logue via `console.error` et continue vers les messages suivants du même appel.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `shell/src/builder/ActionBus.test.ts` :

```ts
test("a handler that throws does not prevent the next handler in the same emit from running", () => {
  const bus = new ActionBus();
  const failing = vi.fn(() => {
    throw new Error("boom");
  });
  const succeeding = vi.fn();
  bus.register("ext1", "reset", failing);
  bus.register("list1", "setFilter", succeeding);
  bus.configure([
    { id: "1", from: "btn1", event: "clicked", to: "ext1", action: "reset" },
    { id: "2", from: "btn1", event: "clicked", to: "list1", action: "setFilter" },
  ]);
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => bus.emit("btn1", "clicked", {})).not.toThrow();
  expect(succeeding).toHaveBeenCalled();
  expect(consoleError).toHaveBeenCalled();
  consoleError.mockRestore();
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: FAIL — l'exception se propage hors de `bus.emit(...)`, `expect(() => ...).not.toThrow()` échoue, `succeeding` n'est jamais appelé.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/ActionBus.ts`, remplacer :

```ts
  emit(widgetId: string, event: string, payload?: unknown): void {
    const list = this.wiring.get(`${widgetId} ${event}`) ?? [];
    const record = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : undefined;
    for (const m of list) {
      if (m.when && !evaluateExpression(m.when, { ...this.context, record })) continue;
      this.actions.get(`${m.to} ${m.action}`)?.(payload);
    }
  }
```

par :

```ts
  emit(widgetId: string, event: string, payload?: unknown): void {
    const list = this.wiring.get(`${widgetId} ${event}`) ?? [];
    const record = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : undefined;
    for (const m of list) {
      if (m.when && !evaluateExpression(m.when, { ...this.context, record })) continue;
      try {
        this.actions.get(`${m.to} ${m.action}`)?.(payload);
      } catch (err) {
        console.error(`Action bus: handler for "${m.to} ${m.action}" threw`, err);
      }
    }
  }
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: PASS (11 passed)

Run la suite complète : `cd shell && npm run test -- --run`
Expected: `436 passed` (435 + 1)

- [ ] **Step 5: Commiter**

```bash
git add shell/src/builder/ActionBus.ts shell/src/builder/ActionBus.test.ts
git commit -m "fix(shell): ActionBus.emit isole les handlers qui lèvent, sans casser les messages suivants"
```

---

### Task 5: Shell — `Me.isAdmin`

**Files:**
- Modify: `shell/src/api/types.ts` (`Me`)
- Modify: `shell/src/api/itemClient.ts:248-251` (`getMe`)
- Modify: `shell/src/api/itemClient.test.ts` (test `getMe` existant)
- Modify: `shell/src/test/msw/handlers.ts:25-30` (mock par défaut de `/me`)

**Interfaces:**
- Produces: `Me` (`shell/src/api/types.ts`) gagne `isAdmin: boolean`. `getMe()` le lit depuis la réponse `GET /me` (Task 1).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts`, remplacer :

```ts
test("getMe maps camelCase fields, dropping id/email/tenantId", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
});
```

par :

```ts
test("getMe maps camelCase fields, dropping id/email/tenantId", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false });
});

test("getMe surfaces isAdmin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: true }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me.isAdmin).toBe(true);
});
```

(Le fichier importe déjà `http`/`HttpResponse` depuis `msw` et `server` depuis `../test/msw/server` — aucun nouvel import nécessaire.)

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `getMe` ne retourne pas `isAdmin` (comparaison `toEqual` échoue sur le premier test ; `me.isAdmin` vaut `undefined` sur le second).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, remplacer :

```ts
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
};
```

par :

```ts
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
};
```

Dans `shell/src/api/itemClient.ts`, remplacer :

```ts
    async getMe(): Promise<Me> {
      const data = await request<{ username: string; firstName: string; lastName: string }>("GET", `/me`);
      return { username: data.username, firstName: data.firstName, lastName: data.lastName };
    },
```

par :

```ts
    async getMe(): Promise<Me> {
      const data = await request<{ username: string; firstName: string; lastName: string; isAdmin: boolean }>(
        "GET", `/me`,
      );
      return { username: data.username, firstName: data.firstName, lastName: data.lastName, isAdmin: data.isAdmin };
    },
```

Dans `shell/src/test/msw/handlers.ts`, remplacer :

```ts
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1", username: "alice", firstName: "Alice", lastName: "Martin",
      email: "alice@example.com", tenantId: "t1",
    }),
  ),
```

par :

```ts
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1", username: "alice", firstName: "Alice", lastName: "Martin",
      email: "alice@example.com", tenantId: "t1", isAdmin: false,
    }),
  ),
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

Run la suite complète : `cd shell && npm run test -- --run`
Expected: `437 passed` (436 + 1 nouveau test)

- [ ] **Step 5: Commiter**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/test/msw/handlers.ts
git commit -m "feat(shell): Me.isAdmin lu depuis GET /me"
```

---

### Task 6: Shell — `ItemClient.listAllExtensions`/`setExtensionEnabled`

**Files:**
- Modify: `shell/src/api/types.ts` (`AdminExtension`, `ItemClient`)
- Modify: `shell/src/api/itemClient.ts` (implémentations)
- Modify: `shell/src/api/itemClient.test.ts` (nouveaux tests)
- Modify: `shell/src/api/hooks.ts` (`useAllExtensions`, `useSetExtensionEnabled`)

**Interfaces:**
- Consumes: `ExtensionManifest` (`shell/src/api/types.ts`, inchangé) ; `GET /extensions?all=true` (Task 2).
- Produces: `AdminExtension = ExtensionManifest & { enabled: boolean }`. `ItemClient.listAllExtensions(): Promise<AdminExtension[]>`. `ItemClient.setExtensionEnabled(id: string, enabled: boolean): Promise<void>`. `useAllExtensions(options?: { enabled?: boolean })`, `useSetExtensionEnabled()` (react-query, mêmes conventions que `useActiveExtensions`/`useSetSharing`).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `shell/src/api/itemClient.test.ts` :

```ts
test("listAllExtensions requests all=true and keeps the enabled flag", async () => {
  let url: string | null = null;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
          },
        ],
      });
    }),
  );
  const result = await makeClient().listAllExtensions();
  expect(url).toContain("all=true");
  expect(result).toEqual([
    {
      type: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
      defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
    },
  ]);
});

test("setExtensionEnabled PATCHes the extension with the new enabled value", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "acme.gauge" });
    }),
  );
  await makeClient().setExtensionEnabled("acme.gauge", false);
  expect(body).toEqual({ enabled: false });
});
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `makeClient().listAllExtensions is not a function` / `setExtensionEnabled is not a function`.

- [ ] **Step 3: Implémenter les types**

Dans `shell/src/api/types.ts`, juste après la définition de `ExtensionManifest`, ajouter :

```ts
export type AdminExtension = ExtensionManifest & { enabled: boolean };
```

Dans l'interface `ItemClient`, juste après `listActiveExtensions(): Promise<ExtensionManifest[]>;`, ajouter :

```ts
  listAllExtensions(): Promise<AdminExtension[]>;
  setExtensionEnabled(id: string, enabled: boolean): Promise<void>;
```

- [ ] **Step 4: Implémenter le client**

Dans `shell/src/api/itemClient.ts`, juste après la méthode `listActiveExtensions`, ajouter :

```ts
    async listAllExtensions(): Promise<AdminExtension[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions?all=true`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string; tag: string; label: string; moduleUrl: string;
          props: ExtensionManifest["props"]; events?: string[]; actions?: string[];
          defaultSize: { w: number; h: number }; permissions?: { collections: string[] | "all" };
          enabled: boolean;
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id, tag: e.tag, label: e.label, moduleUrl: e.moduleUrl,
        props: e.props, events: e.events, actions: e.actions,
        defaultSize: e.defaultSize, permissions: e.permissions, enabled: e.enabled,
      }));
    },

    async setExtensionEnabled(id: string, enabled: boolean): Promise<void> {
      await request<void>("PATCH", `/extensions/${id}`, { enabled });
    },
```

(`AdminExtension` doit être importé — vérifier que `import type { ... } from "./types"` en tête du fichier inclut déjà `ExtensionManifest` ; y ajouter `AdminExtension`.)

- [ ] **Step 5: Vérifier que les tests passent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: Ajouter les hooks**

Dans `shell/src/api/hooks.ts`, juste après `useActiveExtensions`, ajouter :

```ts
export function useAllExtensions(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["extensions", "all"],
    queryFn: () => client.listAllExtensions(),
    enabled: options?.enabled ?? true,
  });
}

export function useSetExtensionEnabled() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => client.setExtensionEnabled(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["extensions"] });
    },
  });
}
```

(`invalidateQueries({ queryKey: ["extensions"] })` invalide par préfixe — rafraîchit à la fois `["extensions"]`, utilisée par `useActiveExtensions`, et `["extensions", "all"]`, utilisée par `useAllExtensions`.)

- [ ] **Step 7: Vérifier l'absence de régression et compiler**

Run: `cd shell && npm run test -- --run`
Expected: `439 passed` (437 + 2)

Run: `cd shell && npx tsc --noEmit`
Expected: pas d'erreur.

- [ ] **Step 8: Commiter**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.ts
git commit -m "feat(shell): ItemClient.listAllExtensions/setExtensionEnabled + hooks"
```

---

### Task 7: Shell — page d'admin `/admin/extensions`

**Files:**
- Create: `shell/src/pages/AdminExtensionsPage.tsx`
- Create: `shell/src/pages/AdminExtensionsPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx` (nouvelle route)
- Modify: `shell/src/shell/routes.test.tsx` (nouveau test de routage)
- Modify: `shell/src/shell/AppLayout.tsx` (lien nav conditionnel)
- Modify: `shell/src/shell/AppLayout.test.tsx` (adapte le harnais + nouveaux tests)

**Interfaces:**
- Consumes: `useMe`, `useAllExtensions`, `useSetExtensionEnabled` (Task 5/6).
- Produces: route `/admin/extensions`, composant `AdminExtensionsPage`.

- [ ] **Step 1: Écrire les tests qui échouent (page)**

Créer `shell/src/pages/AdminExtensionsPage.test.tsx` :

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AdminExtensionsPage } from "./AdminExtensionsPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <AdminExtensionsPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an access-denied message and never calls /extensions when the user is not admin", async () => {
  let extensionsCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/extensions", () => {
      extensionsCalled = true;
      return HttpResponse.json({ extensions: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(extensionsCalled).toBe(false);
});

test("lists extensions (including disabled) and toggles enabled via PATCH", async () => {
  let patchedBody: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/extensions", ({ request }) => {
      expect(new URL(request.url).searchParams.get("all")).toBe("true");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
          },
        ],
      });
    }),
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "acme.gauge", enabled: true });
    }),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  await waitFor(() => expect(patchedBody).toEqual({ enabled: true }));
});
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx`
Expected: FAIL — le module `./AdminExtensionsPage` n'existe pas encore.

- [ ] **Step 3: Implémenter la page**

Créer `shell/src/pages/AdminExtensionsPage.tsx` :

```tsx
import { useAllExtensions, useMe, useSetExtensionEnabled } from "../api/hooks";

export function AdminExtensionsPage() {
  const meQuery = useMe();
  const extensionsQuery = useAllExtensions({ enabled: meQuery.data?.isAdmin === true });
  const setEnabled = useSetExtensionEnabled();

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold">Extensions</h1>
      {extensionsQuery.isLoading && <p role="status">Chargement…</p>}
      {extensionsQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des extensions.
        </p>
      )}
      {extensionsQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Étiquette</th>
              <th className="py-2">Balise</th>
              <th className="py-2">Module</th>
              <th className="py-2">Actif</th>
            </tr>
          </thead>
          <tbody>
            {extensionsQuery.data.map((ext) => (
              <tr key={ext.type} className="border-b border-slate-100">
                <td className="py-2">{ext.label}</td>
                <td className="py-2">{ext.tag}</td>
                <td className="py-2 text-xs text-slate-500">{ext.moduleUrl}</td>
                <td className="py-2">
                  <input
                    type="checkbox"
                    aria-label={`Actif : ${ext.label}`}
                    checked={ext.enabled}
                    disabled={setEnabled.isPending}
                    onChange={(e) => setEnabled.mutate({ id: ext.type, enabled: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Vérifier que les tests de la page passent**

Run: `cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Écrire le test de routage qui échoue**

Dans `shell/src/shell/routes.test.tsx`, ajouter après le bloc `vi.mock("../pages/AppRuntimePage", ...)` :

```ts
vi.mock("../pages/AdminExtensionsPage", () => ({
  AdminExtensionsPage: () => <div>admin-extensions</div>,
}));
```

et ajouter un nouveau test :

```ts
test("renders the admin extensions route at /admin/extensions", () => {
  wrap(<AppRoutes />, "/admin/extensions");
  expect(screen.getByText("admin-extensions")).toBeInTheDocument();
});
```

- [ ] **Step 6: Vérifier que le test de routage échoue**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: FAIL — pas de route `/admin/extensions` (page blanche ou route non trouvée).

- [ ] **Step 7: Ajouter la route**

Dans `shell/src/shell/routes.tsx`, ajouter l'import :

```ts
import { AdminExtensionsPage } from "../pages/AdminExtensionsPage";
```

et, dans `AppRoutes`, ajouter la route à l'intérieur du bloc `<Route element={<ProtectedLayout />}>`, après `/apps/:pk/edit` :

```tsx
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
```

- [ ] **Step 8: Vérifier que le test de routage passe**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: PASS

- [ ] **Step 9: Écrire les tests du lien nav qui échouent**

Remplacer entièrement `shell/src/shell/AppLayout.test.tsx` par :

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));
vi.mock("./NewItemButton", () => ({
  NewItemButton: () => <button>Nouveau</button>,
}));
vi.mock("./ImportFileButton", () => ({
  ImportFileButton: () => <button>Importer un fichier</button>,
}));

const { AppLayout } = await import("./AppLayout");

function renderLayout() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <AppLayout><div>content</div></AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("shows brand, username and sign-out", async () => {
  renderLayout();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByText("alice")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /déconnexion/i }));
  expect(authState.signOut).toHaveBeenCalled();
});

test("shows the admin link only when the current user is admin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "Administration" })).toBeInTheDocument();
});

test("hides the admin link for a non-admin user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
});
```

- [ ] **Step 10: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx`
Expected: FAIL — `AppLayout` n'appelle pas encore `useMe()` (le premier test échoue déjà car il manque `QueryClientProvider`/`ItemClientProvider` dans le harnais actuel avant modification du composant ; après le remplacement du fichier ci-dessus, ce sont les tests 2 et 3 qui échouent — pas de lien "Administration" rendu).

- [ ] **Step 11: Implémenter le lien nav**

Dans `shell/src/shell/AppLayout.tsx`, remplacer :

```tsx
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { NewItemButton } from "./NewItemButton";
import { ImportFileButton } from "./ImportFileButton";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <span className="text-lg font-bold">GeoStudio</span>
        <div className="flex items-center gap-3 text-sm">
          <NewItemButton />
          <ImportFileButton />
          <span>{username}</span>
          <Button size="sm" variant="outline" onClick={signOut}>
            Déconnexion
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

par :

```tsx
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { NewItemButton } from "./NewItemButton";
import { ImportFileButton } from "./ImportFileButton";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <span className="text-lg font-bold">GeoStudio</span>
        <div className="flex items-center gap-3 text-sm">
          <NewItemButton />
          <ImportFileButton />
          <span>{username}</span>
          <Button size="sm" variant="outline" onClick={signOut}>
            Déconnexion
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
          {meQuery.data?.isAdmin === true && (
            <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
              Administration
            </Link>
          )}
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 12: Vérifier que tout passe**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx src/shell/routes.test.tsx src/pages/AdminExtensionsPage.test.tsx`
Expected: PASS (3 + 6 + 2 = à recompter, tous verts)

Run la suite complète : `cd shell && npm run test -- --run`
Expected: `444 passed` (439 de Task 6 + 2 AdminExtensionsPage + 1 routes + 2 AppLayout net nouveau — le fichier AppLayout.test.tsx passe de 1 à 3 tests).

Run: `cd shell && npx tsc --noEmit`
Expected: pas d'erreur.

- [ ] **Step 13: Commiter**

```bash
git add shell/src/pages/AdminExtensionsPage.tsx shell/src/pages/AdminExtensionsPage.test.tsx shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx
git commit -m "feat(shell): page d'admin /admin/extensions (liste + activer/désactiver)"
```

---

### Task 8: Widget externe de référence (`examples/external-widget/`)

**Files:**
- Create: `examples/external-widget/widget.js`
- Create: `examples/external-widget/manifest.json`

**Interfaces:**
- Produces: un custom element `external-example-widget` (props `initial: number`, event `changed`, action `reset`), zéro dépendance, réutilisé par Task 9 (serveur E2E), Task 10 (guide) et Task 11 (spec E2E).

- [ ] **Step 1: Créer le widget**

Créer `examples/external-widget/widget.js` :

```js
// widget.js — GeoStudio external Web Component widget example.
//
// Zero build step, zero dependency: this file is exactly what a third-party
// author would write and host themselves. It only relies on browser-native
// APIs (customElements, CustomEvent) — see manifest.json next to this file
// and docs/guides/2026-07-13-ecrire-un-widget-web-component.md.
class ExternalExampleWidget extends HTMLElement {
  constructor() {
    super();
    this._count = 0;
    this._initialized = false;
  }

  // GeoStudio assigns props/data/user/navigate as DOM properties (never as
  // serialized attributes) right after mounting the element.
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

  // Public method invoked when a composed action from the GeoStudio action
  // bus targets this widget's "reset" action (declared in manifest.json).
  reset() {
    this._count = Number(this._props?.initial ?? 0);
    this._render();
  }

  _increment() {
    this._count += 1;
    // Dispatched as a CustomEvent; GeoStudio relays it to the action bus
    // under the manifest's "changed" event.
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
    // GeoStudio's theme is inherited through the --gs-* CSS variables it
    // sets on an ancestor — a widget just needs to consume them.
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

// customElements.define as a side effect of importing this module is the
// entire contract — GeoStudio requires no other export.
if (!customElements.get("external-example-widget")) {
  customElements.define("external-example-widget", ExternalExampleWidget);
}
```

- [ ] **Step 2: Vérifier la validité syntaxique**

Run: `node --check examples/external-widget/widget.js`
Expected: pas de sortie, code de sortie 0.

- [ ] **Step 3: Créer le manifeste**

Créer `examples/external-widget/manifest.json` :

```json
{
  "id": "example.external-counter",
  "tag": "external-example-widget",
  "label": "Compteur externe (exemple)",
  "moduleUrl": "widget.js",
  "props": [
    { "name": "initial", "type": "number", "label": "Valeur initiale", "default": 0 }
  ],
  "events": ["changed"],
  "actions": ["reset"],
  "defaultSize": { "w": 2, "h": 2 },
  "permissions": { "collections": "all" }
}
```

(`moduleUrl` est relatif ici à titre documentaire — un enregistrement réel via `POST /extensions` ou un mock E2E fournit l'URL absolue de l'hébergement effectif, ex. `http://localhost:4174/widget.js`.)

- [ ] **Step 4: Vérifier la validité du JSON**

Run: `node -e "JSON.parse(require('node:fs').readFileSync('examples/external-widget/manifest.json', 'utf8')); console.log('ok')"`
Expected: `ok`

- [ ] **Step 5: Commiter**

```bash
git add examples/external-widget/widget.js examples/external-widget/manifest.json
git commit -m "docs: widget externe de référence (examples/external-widget/)"
```

---

### Task 9: E2E — serveur statique cross-origin dédié

**Files:**
- Create: `shell/e2e/external-widget-server.mjs`
- Modify: `shell/playwright.config.ts`

**Interfaces:**
- Consumes: `examples/external-widget/` (Task 8).
- Produces: un serveur HTTP sur `http://localhost:4174` servant `examples/external-widget/` avec `Access-Control-Allow-Origin: *`, démarré automatiquement par Playwright en E2E, sur une origine distincte du shell (`http://localhost:4173`).

- [ ] **Step 1: Créer le serveur statique**

Créer `shell/e2e/external-widget-server.mjs` :

```js
// shell/e2e/external-widget-server.mjs
//
// Minimal static file server for E2E: serves examples/external-widget/ on a
// port distinct from the shell's own preview server, with CORS enabled, so
// external-widget.spec.ts exercises a genuinely cross-origin dynamic
// import() — not the same-origin fixture path used by extension-widget.spec.ts.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../examples/external-widget/", import.meta.url));
const PORT = 4174;

const CONTENT_TYPES = {
  ".js": "application/javascript",
  ".json": "application/json",
};

createServer(async (req, res) => {
  const path = (req.url ?? "/").split("?")[0];
  const filePath = join(ROOT, path === "/" ? "widget.js" : path);
  try {
    const body = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": CONTENT_TYPES[extname(filePath)] ?? "application/octet-stream",
      "Access-Control-Allow-Origin": "*",
    });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
}).listen(PORT, () => {
  console.log(`external-widget-server listening on http://localhost:${PORT}`);
});
```

- [ ] **Step 2: Vérifier manuellement le serveur**

Run (démarre en arrière-plan, teste, arrête) :

```bash
cd shell
node e2e/external-widget-server.mjs &
SERVER_PID=$!
sleep 1
curl -sI http://localhost:4174/widget.js
kill $SERVER_PID
```

Expected : la sortie `curl` contient `HTTP/1.1 200 OK`, `content-type: application/javascript` et `access-control-allow-origin: *`.

- [ ] **Step 3: Ajouter le serveur au config Playwright**

Dans `shell/playwright.config.ts`, remplacer tout le fichier par :

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  webServer: [
    {
      command: "npm run build && npm run preview -- --port 4173",
      url: "http://localhost:4173",
      reuseExistingServer: false,
      env: {
        VITE_AUTH_MODE: "mock",
        VITE_CORE_URL: "https://core.test",
        VITE_MARTIN_URL: "https://martin.test",
      },
    },
    {
      command: "node e2e/external-widget-server.mjs",
      url: "http://localhost:4174/widget.js",
      reuseExistingServer: false,
    },
  ],
});
```

- [ ] **Step 4: Vérifier que la suite E2E existante démarre toujours**

Run: `cd shell && npm run e2e -- --grep "Filtre widget filters"`
Expected: 1 passed — preuve que Playwright démarre bien les deux `webServer` (le shell sur 4173 continue de fonctionner) sans régression sur une spec existante représentative.

- [ ] **Step 5: Commiter**

```bash
git add shell/e2e/external-widget-server.mjs shell/playwright.config.ts
git commit -m "test(e2e): serveur statique cross-origin dédié pour le widget externe de référence"
```

---

### Task 10: Guide « écrire un widget Web Component »

**Files:**
- Create: `docs/guides/2026-07-13-ecrire-un-widget-web-component.md`

**Interfaces:**
- Consumes: `examples/external-widget/widget.js`, `examples/external-widget/manifest.json` (Task 8).

- [ ] **Step 1: Rédiger le guide**

Créer `docs/guides/2026-07-13-ecrire-un-widget-web-component.md` :

```markdown
# Écrire un widget Web Component pour GeoStudio

Un widget GeoStudio peut être écrit sans toucher au dépôt du shell : un
custom element standard (Web Component) + un manifeste JSON, hébergés où
vous voulez, activés par un administrateur de la plateforme depuis
`/admin/extensions`. Cette page prend pour exemple
[`examples/external-widget/`](../../examples/external-widget/), le widget de
référence utilisé par les tests de bout en bout du projet — copiez-le comme
point de départ.

## Le manifeste

```json
{
  "id": "example.external-counter",
  "tag": "external-example-widget",
  "label": "Compteur externe (exemple)",
  "moduleUrl": "widget.js",
  "props": [
    { "name": "initial", "type": "number", "label": "Valeur initiale", "default": 0 }
  ],
  "events": ["changed"],
  "actions": ["reset"],
  "defaultSize": { "w": 2, "h": 2 },
  "permissions": { "collections": "all" }
}
```

- `id` : identifiant unique de votre widget côté tenant (ex. `acme.gauge`) —
  c'est aussi le `widget` référencé dans les configs qui l'utilisent.
- `tag` : le nom du custom element (`customElements.define(tag, …)`).
- `props` : chaque entrée décrit un champ édité dans le panneau de props du
  builder. Quatre types supportés :
  - `string`, `number`, `boolean` : champ simple.
  - `dataSource` : un sélecteur de source de données du builder — la valeur
    transmise à votre widget est l'id d'une `DataSource`, pas directement un
    nom de collection.
- `events` : les noms de `CustomEvent` que votre widget peut émettre ;
  utilisables comme déclencheurs d'actions composées dans le builder.
- `actions` : les noms de méthodes publiques que votre widget expose ;
  utilisables comme cibles d'actions composées.
- `permissions.collections` : `"all"` ou une liste explicite de collections
  — limite les sources de données proposées dans le panneau de props
  (confort d'autorat) **et** est vérifiée côté serveur à l'enregistrement
  d'une config (une config qui route une prop `dataSource` de votre widget
  vers une collection hors de cette liste est rejetée, HTTP 400).

## Le contrat DOM

GeoStudio monte votre élément puis lui assigne, comme **propriétés DOM**
(jamais comme attributs sérialisés en chaîne) :

- `props` : l'objet de props tel que configuré dans le builder.
- `data` : les données courantes de l'app (variables, contexte).
- `user` : l'utilisateur courant.
- `navigate` : une fonction de navigation.

```js
set props(value) {
  this._props = value;
  // ré-affiche votre widget avec les nouvelles props
}
```

Pour émettre un événement déclaré dans `events` :

```js
this.dispatchEvent(new CustomEvent("changed", { detail: { count: this._count } }));
```

Pour exposer une action déclarée dans `actions`, définissez simplement une
méthode publique du même nom sur votre élément — GeoStudio l'invoque
directement quand un message composé la cible :

```js
reset() {
  this._count = 0;
  this._render();
}
```

## Le thème

GeoStudio pose des variables CSS `--gs-*` (couleurs, police…) sur un
ancêtre de votre widget. Consommez-les directement, rien à initialiser :

```js
span.style.color = "var(--gs-color-text, #0f172a)";
```

## Hébergement et CORS

Votre module JS est chargé par un `import()` dynamique **cross-origin**
(votre domaine, pas celui du shell). Le navigateur applique les règles CORS
à ce chargement : votre serveur doit répondre avec un en-tête
`Access-Control-Allow-Origin` qui autorise l'origine du shell (`*` convient
pour un widget public). Sans cet en-tête, le chargement échoue silencieusement
et GeoStudio affiche un placeholder « Extension indisponible ».

## Le contrat de confiance

Il n'y a **pas de sandbox** en v1 : une extension activée s'exécute avec les
mêmes droits que le reste de la page. C'est un compromis assumé — l'admin
qui active votre widget vous fait confiance, exactement comme il ferait
confiance à un widget interne. `permissions.collections` est un confort
d'autorat et une vraie frontière serveur pour les props `dataSource`
déclarées dans votre manifeste, pas une sandbox : votre code reste libre de
faire ses propres requêtes réseau, dans la limite de ce que le token de
l'utilisateur autorise déjà côté cœur (RLS/`can()`, inchangés par les
extensions).

## Activation

Un administrateur enregistre votre extension via l'API du cœur
(`POST /extensions`, payload = votre manifeste + `moduleUrl` absolue) puis
l'active/désactive depuis `/admin/extensions` dans le shell. Une extension
désactivée disparaît de la palette et affiche un placeholder propre dans les
apps qui l'utilisaient déjà — pas de crash, pas de redéploiement du shell.
```

- [ ] **Step 2: Auto-relecture**

Vérifier que chaque extrait de code du guide correspond exactement au
contenu réel de `examples/external-widget/manifest.json` et
`examples/external-widget/widget.js` (Task 8) — pas de dérive entre le
guide et l'exemple qu'il documente.

- [ ] **Step 3: Commiter**

```bash
git add docs/guides/2026-07-13-ecrire-un-widget-web-component.md
git commit -m "docs: guide écrire un widget Web Component pour GeoStudio"
```

---

### Task 11: E2E — widget cross-origin, admin, containment

**Files:**
- Modify: `shell/e2e/mocks.ts:43-47` (`**/me` gagne `isAdmin: false` par défaut)
- Create: `shell/public/fixtures/throwing-extension-widget.js`
- Create: `shell/e2e/external-widget.spec.ts`
- Create: `shell/e2e/admin-extensions.spec.ts`
- Create: `shell/e2e/action-bus-containment.spec.ts`

**Interfaces:**
- Consumes : Task 3 (validation permissions, non testée en E2E — couverte en pytest), Task 4 (containment `ActionBus`), Task 7 (page admin), Task 9 (serveur cross-origin).

- [ ] **Step 1: Étendre le mock `/me`**

Dans `shell/e2e/mocks.ts`, remplacer :

```ts
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: { id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User", email: null, tenantId: "t-mock" },
    });
  });
```

par :

```ts
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: false,
      },
    });
  });
```

- [ ] **Step 2: Vérifier l'absence de régression sur les specs existantes**

Run: `cd shell && npm run e2e -- --grep "déclarer un incident"`
Expected: passe toujours (spec représentative qui dépend de `mockCore`, aucun changement de comportement attendu).

- [ ] **Step 3: Créer le widget qui plante (fixture E2E)**

Créer `shell/public/fixtures/throwing-extension-widget.js` :

```js
class ThrowingExtensionWidget extends HTMLElement {
  set props(value) {
    this._props = value || {};
  }

  get props() {
    return this._props;
  }

  connectedCallback() {
    this.textContent = "widget qui plante";
  }

  boom() {
    throw new Error("boom");
  }
}

if (!customElements.get("throwing-extension-widget")) {
  customElements.define("throwing-extension-widget", ThrowingExtensionWidget);
}
```

- [ ] **Step 4: Écrire la spec du widget cross-origin**

Créer `shell/e2e/external-widget.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const EXTERNAL_MANIFEST = {
  id: "example.external-counter", tag: "external-example-widget", label: "Compteur externe (exemple)",
  moduleUrl: "http://localhost:4174/widget.js",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("un widget hébergé sur une origine distincte (CORS) se charge, respecte le thème, et fonctionne comme n'importe quel widget d'extension", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [EXTERNAL_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App widget externe");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // La palette liste le widget hébergé cross-origin sans redéploiement du shell.
  await page.getByRole("button", { name: "Compteur externe (exemple)" }).click();
  const widget = page.locator("external-example-widget");
  await expect(widget.getByText("0", { exact: true })).toBeVisible();

  await page.getByLabel("Couleur du texte").fill("#0000ff");

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Compteur externe (exemple)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Compteur externe (exemple)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, import() cross-origin ré-exécuté depuis le
  // cache mémoïsé du module (moduleCache.ts) — preuve qu'il a réussi malgré
  // l'origine distincte (CORS), pas seulement au premier chargement en édition.
  await page.goto("/apps/9");
  const runtimeWidget = page.locator("external-example-widget");
  await expect(runtimeWidget.getByText("0", { exact: true })).toBeVisible();
  const color = await runtimeWidget.locator("span").evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(0, 0, 255)");

  await runtimeWidget.getByRole("button", { name: "+1" }).click();
  await runtimeWidget.getByRole("button", { name: "+1" }).click();
  await expect(runtimeWidget.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("Compte : 2")).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeWidget.getByText("0", { exact: true })).toBeVisible();
});
```

- [ ] **Step 5: Écrire la spec admin**

Créer `shell/e2e/admin-extensions.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un admin voit les extensions (actives et désactivées) et peut les activer/désactiver depuis le shell", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });
  let patchedBody: unknown;
  await page.route("**/extensions*", async (route) => {
    if (route.request().method() === "PATCH") {
      patchedBody = await route.request().postDataJSON();
      await route.fulfill({ json: { id: "acme.gauge", enabled: false } });
      return;
    }
    await route.fulfill({
      json: {
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: true,
          },
        ],
      },
    });
  });

  await page.goto("/admin/extensions");
  await expect(page.getByRole("link", { name: "Administration" })).toBeVisible();
  const toggle = page.getByRole("checkbox", { name: "Actif : Jauge (extension)" });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect.poll(() => patchedBody).toEqual({ enabled: false });
});

test("un utilisateur non-admin voit un message d'accès refusé et n'appelle jamais /extensions", async ({ page }) => {
  await mockCore(page);
  let extensionsCalled = false;
  await page.route("**/extensions*", async (route) => {
    extensionsCalled = true;
    await route.fulfill({ json: { extensions: [] } });
  });

  await page.goto("/admin/extensions");
  await expect(page.getByRole("alert")).toHaveText("Accès réservé aux administrateurs.");
  expect(await page.getByRole("link", { name: "Administration" }).count()).toBe(0);
  expect(extensionsCalled).toBe(false);
});
```

- [ ] **Step 6: Écrire la spec de containment**

Créer `shell/e2e/action-bus-containment.spec.ts` :

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

const THROWING_MANIFEST = {
  id: "test.throwing", tag: "throwing-extension-widget", label: "Widget qui plante",
  moduleUrl: "/fixtures/throwing-extension-widget.js",
  props: [], events: [], actions: ["boom"],
  defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
};

test("une extension dont l'action lève une exception ne bloque pas le message composé suivant vers un autre widget", async ({ page }) => {
  await mockCore(page);
  await page.route("**/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [GAUGE_MANIFEST, THROWING_MANIFEST] } });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App containment");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Jauge (extension)" }).click();
  await page.getByRole("button", { name: "Widget qui plante" }).click();
  await page.getByRole("button", { name: "Bouton" }).click();

  // Le message vers le widget qui plante est câblé en premier — s'il casse
  // la boucle, le second message (vers la Jauge) ne s'exécute jamais.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Widget qui plante" });
  await page.getByLabel("Action", { exact: true }).selectOption("boom");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Jauge (extension)" });
  await page.getByLabel("Action", { exact: true }).selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const gauge = page.locator("gauge-extension-widget");
  await gauge.getByRole("button", { name: "+1" }).click();
  await gauge.getByRole("button", { name: "+1" }).click();
  await expect(gauge.getByText("2", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(gauge.getByText("0", { exact: true })).toBeVisible();
});
```

- [ ] **Step 7: Lancer les trois nouvelles specs**

Run: `cd shell && npm run e2e -- external-widget.spec.ts admin-extensions.spec.ts action-bus-containment.spec.ts`
Expected: 4 passed (1 + 2 + 1).

- [ ] **Step 8: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: toutes les specs vertes — **33 specs E2E** (30 existantes + `external-widget.spec.ts` + `admin-extensions.spec.ts` (2 tests) + `action-bus-containment.spec.ts`).

- [ ] **Step 9: Commiter**

```bash
git add shell/e2e/mocks.ts shell/public/fixtures/throwing-extension-widget.js shell/e2e/external-widget.spec.ts shell/e2e/admin-extensions.spec.ts shell/e2e/action-bus-containment.spec.ts
git commit -m "test(e2e): widget cross-origin, admin extensions, containment ActionBus (SP-8c)"
```

---

## Vérification finale de branche

Après la Task 11, avant revue finale : relancer l'ensemble des suites pour confirmer les compteurs cumulés.

```bash
cd core && uv run pytest -q && uv run lint-imports
cd ../shell && npm run test -- --run && npx tsc --noEmit && npm run e2e
```

Expected : cœur 379 passed/62 skipped, shell 444 passed, E2E 33 specs vertes, `lint-imports` et `tsc --noEmit` propres. (La sortie réelle de chaque `Step` de vérification fait foi en cas d'écart.)
