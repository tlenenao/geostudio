### Task 3: Wire item creation/deletion into `configs`; remove GeoNode from the create/delete paths

**Files:**
- Modify: `core/app/configs/routes.py`
- Modify: `core/app/main.py`
- Delete: `core/tests/test_main_wiring.py`
- Modify: `core/tests/test_routes.py`

**Interfaces:**
- Consumes: `app.items.repository.create_item(session, *, tenant_id, owner_id, resource_type, title) -> Item`.
- Produces: `POST /configs` creates `items` + `configs` in one local transaction from the authenticated user; `DELETE /configs/{id}`, `DELETE /configs/by-item/{item_id}`, and a new `DELETE /items/{item_id}` (registered from this router, per this plan's layering — see Architecture) all delete `config_revisions` explicitly then delete the `items` row, letting the DB cascade remove `configs`. `app.geonode.ItemClient`/`StubItemClient`/`GeoNodeItemClient` are no longer referenced anywhere in `configs/routes.py` or `main.py` (the module `app/geonode.py` itself is untouched — still scheduled for deletion in SP-1d, not this plan).

- [ ] **Step 1: Write the failing tests**

Replace the `client` fixture and the create/delete tests in `core/tests/test_routes.py`. Read the current file first (it was last touched in SP-1a's Task 7) — then apply these changes:

Remove the `owner` field from every `client.post("/configs", json={...})` call in this file (search for `"owner": "alice"` and delete that key from each request body — the endpoint no longer accepts it). Replace the fixture:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app import db
from app.audit.models import AuditLog
from app.db import make_engine, make_session_factory, init_db
from app.configs import routes
from app.auth.dependency import get_current_user
from app.items.models import Item
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
            username="alice", email="alice@example.com", first_name="Alice", last_name="Doe",
        )

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _config_body(widget: str = "map") -> dict:
    return {
        "kind": "app",
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    }


def _create(client, widget: str = "map") -> dict:
    response = client.post("/configs", json={"title": "My App", "config": _config_body(widget)})
    assert response.status_code == 201, response.text
    return response.json()
```

Then, in place of `test_create_config_creates_item_and_returns_201` (which asserted `client.stub.created[...]`), write:
```python
def test_create_config_creates_a_real_item_owned_by_the_authenticated_user(client):
    body = _create(client)
    assert body["version"] == 1
    with client.session_factory() as session:
        item = session.get(Item, body["itemId"])
        assert item is not None
        assert item.owner_id == client.user.id
        assert item.title == "My App"
```

In place of `test_delete_config_removes_it_and_deletes_linked_item` and `test_delete_by_item_removes_config_and_item` (which asserted `client.stub.deleted == [...]`), write:
```python
def test_delete_config_removes_config_and_item(client):
    created = _create(client)
    config_id = created["id"]
    item_id = created["itemId"]

    response = client.delete(f"/configs/{config_id}")
    assert response.status_code == 204
    assert client.get(f"/configs/{config_id}").status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_by_item_removes_config_and_item(client):
    created = _create(client)
    item_id = created["itemId"]

    response = client.delete(f"/configs/by-item/{item_id}")
    assert response.status_code == 204
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_item_directly_removes_config_and_item(client):
    created = _create(client)
    config_id, item_id = created["id"], created["itemId"]

    response = client.delete(f"/items/{item_id}")
    assert response.status_code == 204
    assert client.get(f"/configs/{config_id}").status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_item_missing_returns_404(client):
    assert client.delete("/items/nope").status_code == 404
```

Keep `test_create_config_writes_audit_log` (from SP-1a) but add an assertion that an `item.create` audit row also exists:
```python
def test_create_config_writes_audit_log(client):
    created = _create(client)
    with client.session_factory() as session:
        rows = session.scalars(select(AuditLog)).all()
        actions = {r.action for r in rows}
        assert "config.create" in actions
        assert "item.create" in actions
```

Delete `core/tests/test_main_wiring.py` entirely — it tested `main.py`'s conditional wiring of `GeoNodeItemClient` vs. `StubItemClient`, which this task removes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: FAIL — `POST /configs` still requires `owner` in the body (422) or the old GeoNode-based create/delete behavior doesn't match the new assertions.

- [ ] **Step 3: Rewrite `app/configs/routes.py`**

Replace the file's content:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as repo
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.db import get_session
from app.items import repository as items_repo
from app.items.models import Item
from app.users.models import User

router = APIRouter()


class CreateConfigRequest(BaseModel):
    title: str
    config: BuilderConfig


class RollbackRequest(BaseModel):
    version: int


def _delete_config_and_item(session: Session, config_id: str, item_id: str) -> None:
    from sqlalchemy import delete
    from app.configs.models import ConfigRevision, Config

    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.execute(delete(Config).where(Config.id == config_id))
    session.execute(delete(Item).where(Item.id == item_id))
    session.commit()


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    item = items_repo.create_item(
        session, tenant_id=user.tenant_id, owner_id=user.id,
        resource_type=request.config.kind, title=request.title,
    )
    result = repo.create_config(session, request.config, item_id=item.id)
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
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    _delete_config_and_item(session, config_id, result.itemId)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=config_id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=result.itemId, payload={},
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
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    _delete_config_and_item(session, result.id, item_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=item_id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    # Lives here, not in app/items/routes.py: deleting an item must also clear
    # its config_revisions before the DB cascades configs -> items (see plan
    # Architecture). app.items must never import app.configs, so this
    # cross-cutting orchestration belongs to the configs layer.
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    _delete_config_and_item(session, result.id, item_id)
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

(`get_item_client`/`ItemClient`/`StubItemClient` are gone from this file entirely — no import from `app.geonode` remains here.)

- [ ] **Step 4: Update `app/main.py`**

Remove the `geonode_url`/`geonode_token` block and its `GeoNodeItemClient` import/wiring entirely (it referenced `configs_routes.get_item_client`, which no longer exists). The function should now read:

```python
import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import db
from app.auth import routes as auth_routes
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory
from app.items import routes as items_routes


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

    app.include_router(configs_routes.router)
    app.include_router(items_routes.router)
    app.include_router(auth_routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

(Adjust import ordering/grouping to match the file's existing style; the key change is removing all `GeoNodeItemClient`/`geonode_url`/`geonode_token`/`logging` wiring and adding the `items_routes` import + include.)

- [ ] **Step 5: Delete the obsolete test file**

```bash
git rm core/tests/test_main_wiring.py
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite and `lint-imports`**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 8: Confirm `app/geonode.py`'s own tests still pass untouched**

Run: `cd core && uv run pytest tests/test_geonode.py tests/test_geonode_http.py -v`
Expected: PASS (these test the module directly, independent of routes wiring — must be unaffected).

- [ ] **Step 9: Commit**

```bash
git add core/app/configs/routes.py core/app/main.py core/tests/test_routes.py
git rm core/tests/test_main_wiring.py
git commit -m "feat(core): create/delete items+configs in one local transaction; remove GeoNode from these paths"
```

---

