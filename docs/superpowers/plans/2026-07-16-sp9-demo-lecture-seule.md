# SP-9 — Mode démo lecture seule : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un déploiement démarré avec `CORE_READ_ONLY_MODE=true` refuse toute
écriture (REST et MCP, tout utilisateur y compris admin) sans affecter la
lecture ; le shell l'affiche (bannière) et masque en fail-open les actions
d'écriture déjà identifiées (Formulaire, dialogues admin collections, page
admin extensions) — la frontière réelle reste le 403 serveur.

**Architecture:** Un seul point d'interception côté cœur — middleware ASGI
dans `app/main.py` qui refuse toute requête `POST`/`PUT`/`PATCH`/`DELETE`
(hors `/mcp`) avec un `403` avant même le routing FastAPI, plus une garde
identique en tête des 4 outils MCP d'écriture (`ValueError`, transport MCP).
Un nouvel endpoint public `GET /instance` expose l'état à un visiteur anonyme.
Côté shell, un hook `useInstanceInfo()` (react-query, fail-open) consommé
directement — pas de nouveau mécanisme générique — par chaque composant
d'écriture déjà identifié, qui combine sa condition `disabled`/d'affichage
existante avec `!readOnly`, exactement comme SP-4c l'a déjà fait pour
`canWrite`.

**Tech Stack:** FastAPI (middleware ASGI), Pydantic, pytest/TestClient
(cœur) ; React/TanStack Query, Vitest/MSW, Playwright (shell).

## Global Constraints

- Toute nouvelle variable d'environnement documentée dans `.env.example` et
  câblée dans `docker-compose.yml` (service `core` uniquement — le mode
  lecture seule ne concerne ni `worker` ni `shell`).
- `CORE_READ_ONLY_MODE` défaut `false` — comportement inchangé hors ce mode
  (spec §6, critère d'acceptation).
- Message d'erreur exact, partout (403 REST, `ValueError` MCP, bannière
  shell dérivée) : `"Mode démo : lecture seule, écritures désactivées."`
  (espace avant le `:`, typographie française).
- Texte de la bannière shell, exact : `"Mode démo — lecture seule, les
  modifications ne sont pas enregistrées."`
- Le masquage client (boutons désactivés/masqués) n'est jamais la frontière
  de sécurité — toujours doublé d'un 403 serveur réel, testé explicitement
  dans chaque tâche cœur, même principe que SP-4c/SP-8b déjà documenté dans
  ce projet.
- Le Widget Table (`shell/src/builder/widgets/data.tsx`) n'a aujourd'hui
  aucune action d'écriture propre (il émet seulement `itemSelected` pour
  charger un enregistrement dans le Formulaire, cf. SP-4b) — la mention
  « écriture Table » de la spec design est donc déjà entièrement couverte
  par le masquage du Formulaire (Task 4) ; ce plan ne touche pas `data.tsx`
  (YAGNI, rien à masquer qui n'existe pas).
- Le masquage shell se fait au niveau de chaque composant d'écriture
  directement (chacun appelle `useInstanceInfo()` lui-même, mis en cache par
  clé de requête react-query) — pas via `WidgetContext`/`WidgetHost` : ce
  dernier est rendu sans `QueryClientProvider`/`ItemClientProvider` dans
  `WidgetHost.test.tsx` (8 tests), y ajouter un appel react-query
  casserait ces tests pour un bénéfice nul (le Formulaire a déjà son propre
  accès à `useItemClient()`/`useQuery` pour `canWrite`).
- Baseline de non-régression actuelle (cf. `CLAUDE.md`) : **395 tests cœur
  passed/65 skipped** (460 passed/0 skipped contre un PostGIS+pgvector
  réel), **466 tests shell**, **36/36 specs E2E**. Cette sous-partie est
  additive : ces chiffres n'augmentent que du nombre de tests réels ajoutés
  ci-dessous, aucun test existant ne change de comportement.
- Docs et commentaires en français, code/identifiants en anglais (`CLAUDE.md`).

---

## File Structure

- Modify `core/app/auth/dependency.py` — ajoute `is_read_only_mode()`.
- Modify `core/app/main.py` — ajoute le middleware `read_only_guard` et
  monte le nouveau routeur `app.instance`.
- Create `core/app/instance/__init__.py`, `core/app/instance/routes.py` —
  `GET /instance` public.
- Create `core/tests/test_read_only_mode.py` — middleware REST + `GET /instance`.
- Modify `core/app/mcp/tools.py` — `READ_ONLY_TOOLS` + garde sur les 4 outils
  d'écriture.
- Create `core/tests/test_mcp_read_only_mode.py`.
- Modify `.env.example`, `docker-compose.yml` (service `core`).
- Modify `shell/src/api/types.ts` — type `InstanceInfo` + méthode sur `ItemClient`.
- Modify `shell/src/api/itemClient.ts` — implémentation `getInstanceInfo`.
- Modify `shell/src/api/hooks.ts` — `useInstanceInfo()`.
- Modify `shell/src/test/msw/handlers.ts` — défaut `readOnly: false`.
- Modify `shell/src/api/hooks.test.tsx` — tests du hook.
- Modify `shell/src/shell/AppLayout.tsx` — bannière.
- Modify `shell/src/shell/AppLayout.test.tsx` — tests bannière.
- Modify `shell/src/builder/widgets/form.tsx` — masquage Enregistrer/Supprimer.
- Modify `shell/src/builder/widgets/form.test.tsx` — test masquage.
- Modify `shell/src/shell/RegisterCollectionDialog.tsx` (+ test).
- Modify `shell/src/shell/EditCollectionDialog.tsx` (+ test).
- Modify `shell/src/shell/CollectionShareDialog.tsx` (+ test).
- Modify `shell/src/pages/AdminExtensionsPage.tsx` (+ test).
- Modify `shell/e2e/mocks.ts` — défaut `readOnly: false`.
- Create `shell/e2e/read-only-demo.spec.ts`.

---

### Task 1: Cœur — middleware REST + `GET /instance`

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/app/main.py`
- Create: `core/app/instance/__init__.py`
- Create: `core/app/instance/routes.py`
- Test: `core/tests/test_read_only_mode.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: rien (première tâche).
- Produces: `is_read_only_mode() -> bool` dans `app/auth/dependency.py`
  (consommé par Task 2, `app/mcp/tools.py`) ; endpoint public `GET /instance`
  → `{"readOnly": bool}` (contrat consommé par Task 3, shell).

- [ ] **Step 1: Écrire les tests (rouge) du middleware REST + `GET /instance`**

Create `core/tests/test_read_only_mode.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

READ_ONLY_MESSAGE = "Mode démo : lecture seule, écritures désactivées."


@pytest.fixture()
def env():
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
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_defaults_to_read_write(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False}


def test_instance_reports_read_only_without_needing_auth(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": True}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/configs"),
        ("PATCH", "/collections/does-not-exist"),
        ("DELETE", "/configs/does-not-exist"),
        ("PUT", "/collections/does-not-exist/items/1"),
        ("POST", "/extensions"),
    ],
)
def test_read_only_mode_blocks_every_mutation_even_for_admin(env, monkeypatch, method, path):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.request(method, path, json={})
    assert response.status_code == 403
    assert response.json() == {"detail": READ_ONLY_MESSAGE}


def test_read_only_mode_does_not_affect_reads(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    assert env.get("/items").status_code == 200
    assert env.get("/me").status_code == 200


def test_read_only_mode_off_by_default_leaves_mutations_working(env):
    response = env.post(
        "/configs",
        json={"title": "T", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_read_only_mode.py -v
```

Expected: FAIL — `GET /instance` retourne 404 (route inexistante), les
mutations en mode lecture seule ne sont pas bloquées (`is_read_only_mode`
n'existe pas encore).

- [ ] **Step 3: Ajouter `is_read_only_mode()` dans `app/auth/dependency.py`**

Modify `core/app/auth/dependency.py` — juste après `_mock_mode()` (avant
`def admin_subs() -> set[str]:`) :

```python
def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def is_read_only_mode() -> bool:
    """CORE_READ_ONLY_MODE (mode démo, SP-9) — lu à chaque appel, sans cache,
    même convention que _mock_mode() ci-dessus : les tests basculent le mode
    via monkeypatch sans recréer l'app."""
    return os.environ.get("CORE_READ_ONLY_MODE", "false").lower() == "true"


def admin_subs() -> set[str]:
```

- [ ] **Step 4: Créer le module `app/instance`**

Create `core/app/instance/__init__.py`:

```python
# SPDX-License-Identifier: Apache-2.0
```

Create `core/app/instance/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_read_only_mode

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {"readOnly": is_read_only_mode()}
```

- [ ] **Step 5: Ajouter le middleware et monter le routeur dans `app/main.py`**

Modify `core/app/main.py` — imports (ajoute `Request` à l'import `fastapi`,
`JSONResponse`, `is_read_only_mode`, `instance_routes`) :

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import db
from app.auth import routes as auth_routes
from app.auth.dependency import is_read_only_mode
from app.collections import routes as collections_routes
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.extensions import routes as extensions_routes
from app.features import routes as features_routes
from app.ingestion import routes as ingestion_routes
from app.instance import routes as instance_routes
from app.items import routes as items_routes
from app.mcp.server import create_mcp_server
from app.public import routes as public_routes
from app.schemas_routes import router as schemas_router
from app.sharing import routes as sharing_routes
```

Puis, juste après `app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)`
et avant `def get_session() -> Iterator[Session]:` :

```python
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Mode démo : lecture seule, écritures désactivées."},
            )
        return await call_next(request)

    def get_session() -> Iterator[Session]:
```

Puis ajoute `app.include_router(instance_routes.router)` avec les autres
`include_router` (n'importe où dans la liste, l'ordre entre eux ne compte
pas — seul le montage MCP final à `"/"` doit rester en dernier) :

```python
    app.include_router(configs_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(instance_routes.router)
    app.include_router(items_routes.router)
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_read_only_mode.py -v
```

Expected: PASS (9 tests — le test paramétré compte pour 5).

- [ ] **Step 7: Lancer la suite complète du cœur (non-régression)**

```bash
cd core && uv run pytest
```

Expected: PASS, aucune régression sur les 395 tests existants (+9 nouveaux).

- [ ] **Step 8: Documenter et câbler la variable d'environnement**

Modify `.env.example` — ajoute, après le bloc `CORE_EMBEDDING_*` existant :

```
# ─── Cœur : mode démo (lecture seule, SP-9) ──────────────
# "true" pour une démo publique où toute écriture (REST + MCP) est refusée,
# quel que soit l'utilisateur, y compris admin ; "false" (défaut) en usage
# normal.
CORE_READ_ONLY_MODE=false
```

Modify `docker-compose.yml` — dans le service `core`, ajoute une ligne dans
son bloc `environment:`, juste après `CORE_BASE_URL` :

```yaml
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
      CORE_READ_ONLY_MODE: ${CORE_READ_ONLY_MODE:-false}
      S3_ENDPOINT_URL: http://minio:9000
```

- [ ] **Step 9: Commit**

```bash
git add core/app/auth/dependency.py core/app/main.py core/app/instance \
        core/tests/test_read_only_mode.py .env.example docker-compose.yml
git commit -m "feat(core): mode démo lecture seule — middleware REST + GET /instance"
```

---

### Task 2: Cœur — garde MCP sur les 4 outils d'écriture

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_read_only_mode.py`

**Interfaces:**
- Consumes: `is_read_only_mode()` de `core/app/auth/dependency.py` (Task 1).
- Produces: `READ_ONLY_TOOLS: set[str]` dans `app/mcp/tools.py` (documentation,
  vérifiée par un test de complétude — pas consommée par une tâche suivante).

- [ ] **Step 1: Écrire les tests (rouge)**

Create `core/tests/test_mcp_read_only_mode.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.mcp.tools import READ_ONLY_TOOLS
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

READ_ONLY_MESSAGE = "Mode démo : lecture seule, écritures désactivées."


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    # create_app() construit son propre engine depuis DATABASE_URL (app/main.py)
    # et les outils MCP ferment sur *ce* session_factory — pas celui construit
    # ici. Un ":memory:" nu donnerait deux bases déconnectées ; on route donc
    # les deux par le même fichier sur disque (même patron que
    # test_mcp_tools_create.py, SP-7).
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
            username="mockuser", email=None, first_name="Mock", last_name="User",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.mock_user = mock_user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def call_tool(test_client, name: str, arguments: dict) -> dict:
    result = call_tool_raw(test_client, name, arguments)
    if result.get("isError"):
        raise AssertionError(f"tool {name} errored: {result['content'][0]['text']}")
    return json.loads(result["content"][0]["text"])


def call_tool_expecting_error(test_client, name: str, arguments: dict) -> str:
    result = call_tool_raw(test_client, name, arguments)
    assert result.get("isError"), f"expected tool {name} to error, got: {result}"
    return result["content"][0]["text"]


def call_tool_raw(test_client, name: str, arguments: dict) -> dict:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=headers,
    )
    assert init_response.status_code == 200
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}

    notify_response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers,
    )
    assert notify_response.status_code == 202

    call_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(
        line for line in call_response.text.splitlines() if line.startswith("data: ")
    )
    payload = json.loads(body_line.removeprefix("data: "))
    return payload["result"]


def test_read_only_tools_constant_matches_the_four_write_tools():
    assert READ_ONLY_TOOLS == {"save_app_config", "create_item", "create_form_app", "set_sharing"}


def test_save_app_config_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "save_app_config",
            {"itemId": "does-not-exist", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
        )
    assert error_text == READ_ONLY_MESSAGE


def test_create_item_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_item",
            {"kind": "app", "title": "X", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
        )
    assert error_text == READ_ONLY_MESSAGE


def test_create_form_app_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_form_app", {"collectionId": "does-not-exist"},
        )
    assert error_text == READ_ONLY_MESSAGE


def test_set_sharing_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "set_sharing",
            {"itemId": "does-not-exist", "sharing": {"public": False, "groups": []}},
        )
    assert error_text == READ_ONLY_MESSAGE


def test_read_only_mode_does_not_affect_read_tools(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        result = call_tool(app_client, "whoami", {})
    assert result["username"] == "mockuser"
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

```bash
cd core && uv run pytest tests/test_mcp_read_only_mode.py -v
```

Expected: FAIL — `READ_ONLY_TOOLS` n'existe pas encore
(`ImportError`/`AttributeError`), et les 4 outils d'écriture n'errorent pas
en mode lecture seule.

- [ ] **Step 3: Ajouter la garde dans `app/mcp/tools.py`**

Modify `core/app/mcp/tools.py` — import (ligne 8) :

```python
from app.auth.dependency import admin_subs, is_read_only_mode
```

Ajoute la constante juste après les imports, avant `def _resolve_actor(...)` :

```python
READ_ONLY_TOOLS = {"save_app_config", "create_item", "create_form_app", "set_sharing"}


def _resolve_actor(session, access_token) -> User:
```

Ajoute la garde comme toute première instruction du corps de chacun des 4
outils (juste après leur docstring, avant `access_token = get_access_token()`) :

```python
    @server.tool()
    async def save_app_config(ctx: Context, itemId: str, config: BuilderConfig) -> ConfigRead:
        """Save (and version) the app/dashboard config for an item — mirrors
        PUT /configs/by-item/{id}."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
```

```python
    @server.tool()
    async def create_item(
        ctx: Context, kind: Literal["app", "dashboard"], title: str, config: BuilderConfig,
    ) -> ItemRead:
        """Create a new app or dashboard — mirrors POST /configs. The item's
        owner is always the authenticated caller; there is no owner
        parameter to accept from the agent."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
```

```python
    @server.tool()
    async def create_form_app(
        ctx: Context, collectionId: str, title: str | None = None,
    ) -> ItemRead:
        """Compose a Carte+Table(+Formulaire if the caller can write) app on
        an existing collection, from its introspected schema — same shape as
        the builder's "Application de saisie" gallery template (SP-4c),
        generated instead of hand-picked. Formulaire is included only if the
        caller has write access to the collection (mirrors the canWrite
        predicate SP-4c exposes on collections). SP-7 MCP v1."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
```

```python
    @server.tool()
    async def set_sharing(ctx: Context, itemId: str, sharing: Sharing) -> None:
        """Set an item's sharing settings — mirrors PUT /items/{id}/sharing."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_mcp_read_only_mode.py -v
```

Expected: PASS (6 tests).

- [ ] **Step 5: Lancer la suite complète du cœur (non-régression)**

```bash
cd core && uv run pytest
```

Expected: PASS, aucune régression (395 + 9 + 6 = 410 tests).

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_read_only_mode.py
git commit -m "feat(core): mode démo lecture seule — garde sur les 4 outils MCP d'écriture"
```

---

### Task 3: Shell — plomberie `useInstanceInfo()` + bannière `AppLayout`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Modify: `shell/src/api/hooks.test.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/AppLayout.test.tsx`
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: contrat `GET /instance` → `{"readOnly": boolean}` (Task 1).
- Produces: `type InstanceInfo = { readOnly: boolean }` (`src/api/types.ts`) ;
  `getInstanceInfo(): Promise<InstanceInfo>` sur `ItemClient` ;
  `useInstanceInfo()` (`src/api/hooks.ts`, `queryKey: ["instance"]`) —
  consommé par Task 4 (`form.tsx`) et Task 5 (dialogues admin).

- [ ] **Step 1: Ajouter le type et la méthode `ItemClient` (types.ts)**

Modify `shell/src/api/types.ts` — ajoute juste après le type `Me` (ligne 30) :

```typescript
export type Me = {
  username: string;
  firstName: string;
  lastName: string;
  isAdmin: boolean;
};

export type InstanceInfo = { readOnly: boolean };
```

Ajoute la méthode dans l'interface `ItemClient`, juste après `getMe()` :

```typescript
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getMe(): Promise<Me>;
  getInstanceInfo(): Promise<InstanceInfo>;
  createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item>;
```

- [ ] **Step 2: Implémenter `getInstanceInfo` dans `CoreItemClient` (itemClient.ts)**

Modify `shell/src/api/itemClient.ts` — ajoute `InstanceInfo` à l'import de
types (ligne 2, liste alphabétique) :

```typescript
import type { ActionMessage, AdminExtension, AppConfig, CandidateTable, CollectionAdmin, CollectionCreateInput, CollectionPatchInput, CollectionSchema, CreateKind, DataRecord, DataSource, ExtensionManifest, FieldError, GeoJSONFeatureInput, Group, InstanceInfo, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, Page, ResourceType, Sharing, Theme, UpdatePatch, Variable } from "./types";
```

Ajoute la méthode dans l'objet retourné par `createItemClient`, juste après
`getMe` :

```typescript
    async getMe(): Promise<Me> {
      const data = await request<{ username: string; firstName: string; lastName: string; isAdmin: boolean }>(
        "GET", `/me`,
      );
      return { username: data.username, firstName: data.firstName, lastName: data.lastName, isAdmin: data.isAdmin };
    },

    async getInstanceInfo(): Promise<InstanceInfo> {
      return request<InstanceInfo>("GET", "/instance");
    },
```

- [ ] **Step 3: Ajouter le hook `useInstanceInfo` (hooks.ts)**

Modify `shell/src/api/hooks.ts` — ajoute juste après `useMe` :

```typescript
export function useMe() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["me"], queryFn: () => client.getMe() });
}

export function useInstanceInfo() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["instance"],
    // Garde défensive identique à useActiveExtensions ci-dessous : un
    // ItemClient de test qui n'implémente pas encore la méthode (mocks
    // Partial<ItemClient>) résout silencieusement à { readOnly: false }
    // plutôt que de planter la query. Une vraie panne réseau laisse `data`
    // undefined (react-query), et chaque appelant traite ça en fail-open
    // via `?.readOnly === true` — jamais un faux positif "lecture seule".
    queryFn: () => client.getInstanceInfo?.() ?? Promise.resolve({ readOnly: false }),
  });
}
```

- [ ] **Step 4: Ajouter le handler MSW par défaut (fail-safe pour tous les tests existants)**

Modify `shell/src/test/msw/handlers.ts` — ajoute juste après le handler `/me` :

```typescript
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1", username: "alice", firstName: "Alice", lastName: "Martin",
      email: "alice@example.com", tenantId: "t1", isAdmin: false,
    }),
  ),
  http.get(`${CORE}/instance`, () => HttpResponse.json({ readOnly: false })),
```

- [ ] **Step 5: Écrire les tests du hook (rouge avant Step 1-4, mais vérifiés maintenant)**

Modify `shell/src/api/hooks.test.tsx` — ajoute `useInstanceInfo` à l'import
(ligne 10) et deux tests, après le test `useMe` :

```typescript
import { useAppConfig, useCandidateTables, useCollectionSharing, useCollectionsAdmin, useCreateItem, useCreateMap, useDeleteItem, useGroups, useInstanceInfo, useItems, useMapConfig, useMe, useSaveApp, useSaveMap, useSharing, useUpdateItem } from "./hooks";
```

```typescript
test("useMe returns the current user", async () => {
  const { result } = renderHook(() => useMe(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.username).toBe("alice");
});

test("useInstanceInfo returns readOnly from the core", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  const { result } = renderHook(() => useInstanceInfo(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.readOnly).toBe(true);
});

test("useInstanceInfo degrades fail-open (data stays undefined, never a false positive) on network failure", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.error()),
  );
  const { result } = renderHook(() => useInstanceInfo(), { wrapper });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.data?.readOnly).not.toBe(true);
});
```

- [ ] **Step 6: Lancer les tests du hook**

```bash
cd shell && npx vitest run src/api/hooks.test.tsx
```

Expected: PASS (tests existants + 2 nouveaux).

- [ ] **Step 7: Ajouter la bannière dans `AppLayout`**

Modify `shell/src/shell/AppLayout.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useInstanceInfo, useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { NewItemButton } from "./NewItemButton";
import { ImportFileButton } from "./ImportFileButton";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  return (
    <div className="flex min-h-screen flex-col">
      {readOnly && (
        <p className="bg-amber-100 px-6 py-2 text-center text-sm text-amber-900">
          Mode démo — lecture seule, les modifications ne sont pas enregistrées.
        </p>
      )}
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
```

(le reste du fichier, à partir de `<span className="text-lg font-bold">GeoStudio</span>`, est inchangé.)

- [ ] **Step 8: Écrire les tests de la bannière**

Modify `shell/src/shell/AppLayout.test.tsx` — ajoute après le test `hides
the admin links for a non-admin user` :

```typescript
test("shows the read-only demo banner when the instance is in read-only mode", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  renderLayout();
  expect(
    await screen.findByText("Mode démo — lecture seule, les modifications ne sont pas enregistrées."),
  ).toBeInTheDocument();
});

test("hides the read-only demo banner by default", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByText(/Mode démo/)).not.toBeInTheDocument();
});
```

- [ ] **Step 9: Lancer les tests shell (non-régression)**

```bash
cd shell && npm run test
```

Expected: PASS (466 + 4 nouveaux tests).

- [ ] **Step 10: Ajouter le mock E2E par défaut**

Modify `shell/e2e/mocks.ts` — ajoute juste après le `page.route("**/me", ...)`
existant :

```typescript
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: false,
      },
    });
  });

  // Instance info (SP-9 démo lecture seule) — AppLayout appelle
  // GET /instance sans condition sur chaque page via useInstanceInfo().
  // Défaut readOnly: false pour que toute spec pré-existante (qui ne
  // surcharge jamais cette route) se comporte exactement comme avant.
  // La spec dédiée au mode lecture seule surcharge cette route elle-même.
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false } });
  });
```

- [ ] **Step 11: Lancer le typecheck/build (tsc) et une spec E2E existante en fumée**

```bash
cd shell && npm run build
npx playwright test e2e/catalog.spec.ts
```

Expected: build clean, spec verte (le nouveau mock par défaut ne casse rien).

- [ ] **Step 12: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts \
        shell/src/test/msw/handlers.ts shell/src/api/hooks.test.tsx \
        shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx shell/e2e/mocks.ts
git commit -m "feat(shell): mode démo lecture seule — useInstanceInfo() + bannière AppLayout"
```

---

### Task 4: Shell — masquage du Formulaire

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx`
- Modify: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes: `useInstanceInfo()` (Task 3).

- [ ] **Step 1: Écrire le test (rouge)**

Modify `shell/src/builder/widgets/form.test.tsx` — ajoute après le test
`hides the write buttons once the collection permission resolves to
canWrite=false` :

```typescript
test("hides the write buttons when the instance is in read-only demo mode, even if canWrite is true", async () => {
  const getInstanceInfo = vi.fn().mockResolvedValue({ readOnly: true });
  renderConnectedForm({ client: { getInstanceInfo } });
  await waitFor(() => expect(getInstanceInfo).toHaveBeenCalled());
  await waitFor(() => expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument());
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "read-only demo mode"
```

Expected: FAIL — le bouton "Enregistrer" est toujours présent (le composant
n'appelle pas encore `getInstanceInfo`).

- [ ] **Step 3: Câbler `useInstanceInfo` dans `FormComponent`**

Modify `shell/src/builder/widgets/form.tsx` — import (ajoute
`useInstanceInfo` à côté de `useItemClient`) :

```typescript
import { useItemClient } from "../../api/ItemClientProvider";
import { useInstanceInfo } from "../../api/hooks";
```

Remplace le calcul de `canWrite` :

```typescript
  const collectionId = ctx.data?.layer ?? "";
  const permissionQuery = useQuery({
    queryKey: ["collection-permission", collectionId],
    queryFn: () => client.getCollectionPermission(collectionId),
    enabled: collectionId !== "",
  });
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const canWrite = (permissionQuery.data ?? true) && !readOnly;
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx
```

Expected: PASS (tous les tests du fichier, y compris le nouveau).

- [ ] **Step 5: Lancer les tests shell (non-régression)**

```bash
cd shell && npm run test
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.test.tsx
git commit -m "feat(shell): masque les boutons d'écriture du Formulaire en mode démo lecture seule"
```

---

### Task 5: Shell — masquage des dialogues admin collections + page admin extensions

**Files:**
- Modify: `shell/src/shell/RegisterCollectionDialog.tsx` (+ test)
- Modify: `shell/src/shell/EditCollectionDialog.tsx` (+ test)
- Modify: `shell/src/shell/CollectionShareDialog.tsx` (+ test)
- Modify: `shell/src/pages/AdminExtensionsPage.tsx` (+ test)

**Interfaces:**
- Consumes: `useInstanceInfo()` (Task 3).

- [ ] **Step 1: Écrire les 4 tests (rouge)**

Modify `shell/src/shell/RegisterCollectionDialog.test.tsx` — ajoute à la fin :

```typescript
test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
```

Modify `shell/src/shell/EditCollectionDialog.test.tsx` — ajoute à la fin :

```typescript
test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
```

Modify `shell/src/shell/CollectionShareDialog.test.tsx` — ajoute à la fin :

```typescript
test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/groups", () => HttpResponse.json([{ id: "g1", name: "Équipe terrain" }])),
    http.get("https://core.test/collections/incidents/sharing", () => HttpResponse.json({ public: false, groups: [] })),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
```

Modify `shell/src/pages/AdminExtensionsPage.test.tsx` — ajoute à la fin :

```typescript
test("disables the enabled toggle when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
          },
        ],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).toBeDisabled();
});
```

- [ ] **Step 2: Lancer les 4 tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/shell/RegisterCollectionDialog.test.tsx \
  src/shell/EditCollectionDialog.test.tsx src/shell/CollectionShareDialog.test.tsx \
  src/pages/AdminExtensionsPage.test.tsx -t "read-only demo mode"
```

Expected: FAIL — les 4 boutons/toggle restent activés (aucun composant
n'appelle encore `useInstanceInfo`).

- [ ] **Step 3: Câbler le masquage dans les 4 composants**

Modify `shell/src/shell/RegisterCollectionDialog.tsx`:

```typescript
import { useCandidateTables, useCreateCollection, useInstanceInfo } from "../api/hooks";
```

```typescript
  const candidatesQuery = useCandidateTables({ enabled: open });
  const createCollection = useCreateCollection();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
```

```typescript
            <Button type="submit" size="sm" disabled={!tableName || createCollection.isPending || readOnly}>
              Enregistrer
            </Button>
```

Modify `shell/src/shell/EditCollectionDialog.tsx`:

```typescript
import { useInstanceInfo, useUpdateCollection } from "../api/hooks";
```

```typescript
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
```

```typescript
          <Button type="submit" size="sm" disabled={updateCollection.isPending || readOnly}>
            Enregistrer
          </Button>
```

Modify `shell/src/shell/CollectionShareDialog.tsx`:

```typescript
import { useCollectionSharing, useGroups, useInstanceInfo, useSetCollectionSharing } from "../api/hooks";
```

```typescript
  const setSharing = useSetCollectionSharing(collectionId);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
```

```typescript
            <Button type="button" size="sm" disabled={setSharing.isPending || readOnly} onClick={submit}>
              Enregistrer
            </Button>
```

Modify `shell/src/pages/AdminExtensionsPage.tsx`:

```typescript
import { useAllExtensions, useInstanceInfo, useMe, useSetExtensionEnabled } from "../api/hooks";

export function AdminExtensionsPage() {
  const meQuery = useMe();
  const extensionsQuery = useAllExtensions({ enabled: meQuery.data?.isAdmin === true });
  const setEnabled = useSetExtensionEnabled();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
```

```typescript
                  <input
                    type="checkbox"
                    aria-label={`Actif : ${ext.label}`}
                    checked={ext.enabled}
                    disabled={setEnabled.isPending || readOnly}
                    onChange={(e) => setEnabled.mutate({ id: ext.type, enabled: e.target.checked })}
                  />
```

- [ ] **Step 4: Lancer les 4 tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/shell/RegisterCollectionDialog.test.tsx \
  src/shell/EditCollectionDialog.test.tsx src/shell/CollectionShareDialog.test.tsx \
  src/pages/AdminExtensionsPage.test.tsx
```

Expected: PASS (tous les tests des 4 fichiers, y compris les nouveaux).

- [ ] **Step 5: Lancer les tests shell (non-régression) et le build**

```bash
cd shell && npm run test && npm run build
```

Expected: PASS, build clean.

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/RegisterCollectionDialog.tsx shell/src/shell/RegisterCollectionDialog.test.tsx \
        shell/src/shell/EditCollectionDialog.tsx shell/src/shell/EditCollectionDialog.test.tsx \
        shell/src/shell/CollectionShareDialog.tsx shell/src/shell/CollectionShareDialog.test.tsx \
        shell/src/pages/AdminExtensionsPage.tsx shell/src/pages/AdminExtensionsPage.test.tsx
git commit -m "feat(shell): masque les actions d'écriture admin (collections, extensions) en mode démo"
```

---

### Task 6: E2E — `read-only-demo.spec.ts`

**Files:**
- Create: `shell/e2e/read-only-demo.spec.ts`

**Interfaces:**
- Consumes: bannière (Task 3), masquage Formulaire (Task 4), mock par défaut
  `mockCore` (Task 3).

- [ ] **Step 1: Écrire la spec**

Create `shell/e2e/read-only-demo.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("mode démo lecture seule : bannière visible, Formulaire masqué, écriture forcée refusée (403)", async ({ page }) => {
  await mockCore(page);
  // Surcharge posée APRÈS mockCore : Playwright privilégie la route la plus
  // récemment enregistrée qui matche (même patron que incident-form.spec.ts).
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: true } });
  });
  await page.route("**/collections/incidents/items*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 403,
        json: { detail: "Mode démo : lecture seule, écritures désactivées." },
      });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");
  await expect(
    page.getByText("Mode démo — lecture seule, les modifications ne sont pas enregistrées."),
  ).toBeVisible();

  // Créer l'app depuis le gabarit "Application de saisie" (config créée via
  // le mock /configs — la création de config n'est pas ce que ce test
  // exerce, cf. Task 1/2 côté cœur pour le vrai 403 serveur sur les
  // mutations REST/MCP).
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Démo lecture seule");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Déclarer l'incident" })).not.toBeVisible();

  // Écriture forcée (contournement de l'UI, ex. devtools) : le serveur refuse.
  const status = await page.evaluate(async () => {
    const res = await fetch("https://core.test/collections/incidents/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "Feature", properties: { titre: "Forcé", gravite: "haute" }, geometry: null }),
    });
    return res.status;
  });
  expect(status).toBe(403);
});
```

- [ ] **Step 2: Lancer la spec**

```bash
cd shell && npx playwright test e2e/read-only-demo.spec.ts
```

Expected: PASS.

- [ ] **Step 3: Lancer la suite E2E complète (non-régression)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 36 + 1 = 37 specs vertes.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/read-only-demo.spec.ts
git commit -m "test(e2e): mode démo lecture seule — bannière, masquage Formulaire, 403 forcé"
```

---

## Vérification finale (après les 6 tâches)

```bash
cd core && uv run pytest
cd ../shell && npm run test && npm run build && npm run e2e
```

Expected: cœur PASS (395 + 15 nouveaux, cf. Task 1/2 : 9 + 6), shell PASS
(466 + 9 nouveaux, cf. Task 3/4/5 : 4 + 1 + 4), 37/37 specs E2E vertes (36 +
Task 6). Confirme les critères d'acceptation de la spec §6.
