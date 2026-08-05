## Task 2: Core — direct validation + REST wiring (`POST /configs`, `PUT /configs/by-item/{id}`)

**Files:**
- Create: `core/app/configs/bookmark_validation.py`
- Modify: `core/app/configs/routes.py:1-20` (import), `:68-92` (create_config), `:211-229` (update_config_by_item)
- Test: `core/tests/test_create_bookmark.py` (new)

**Interfaces:**
- Consumes: `BuilderConfig`/`BookmarkPayload` (Task 1), `items_repo.get_access_facts`/`items_repo.get_item` (`core/app/items/repository.py:129,141`), `can()` (`core/app/sharing/authorization.py:29`).
- Produces: `validate_bookmark_payload(session: Session, config: BuilderConfig, *, user: User) -> None` — raises `HTTPException(422, "app not found")` for both a non-existent `appId` and one the caller can't read (same message, to not leak existence — same convention as `app.collections.dataset_validation`), and for an `appId` that resolves to an item whose `resourceType` isn't `"app"`/`"dashboard"`. This is the exact name Task 3 wraps for the MCP tool.

- [ ] **Step 1: Write the failing REST tests**

Create `core/tests/test_create_bookmark.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
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
        bob = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-2",
            username="bob", email="bob@example.com", first_name="Bob", last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.user = user  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.bob = bob  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _app_body(title: str = "Cible") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1, "kind": "app",
            "layout": {"type": "grid", "breakpoints": {}, "items": []},
        },
    }


def _bookmark_body(app_id: str, title: str = "Ma vue") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1, "kind": "bookmark",
            "bookmark": {
                "appId": app_id, "pageId": "page-1",
                "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
                "extent": None, "crossFilter": {},
            },
        },
    }


def test_create_bookmark_avec_app_existante_et_lisible(client):
    app_item_id = client.post("/configs", json=_app_body()).json()["itemId"]
    res = client.post("/configs", json=_bookmark_body(app_item_id))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/items/{item_id}").json()
    assert item["resourceType"] == "bookmark"


def test_create_bookmark_app_inexistante_rejetee(client):
    res = client.post("/configs", json=_bookmark_body("inexistante"))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_app_non_lisible_rejetee_avec_meme_message(client):
    # Bob's app is private by default (Item.is_public defaults to False) —
    # alice (the caller) is neither its owner nor a group member.
    with client.session_factory() as session:
        from app.configs import repository as configs_repo
        from app.configs.schemas import BuilderConfig
        from app.items import repository as items_repo

        bob_app = items_repo.create_item(
            session, tenant_id=client.user.tenant_id, owner_id=client.bob.id,
            resource_type="app", title="App de Bob",
        )
        configs_repo.create_config(
            session,
            BuilderConfig(version=1, kind="app", layout={"type": "grid", "breakpoints": {}, "items": []}),
            bob_app.id, tenant_id=client.user.tenant_id,
        )
        session.commit()
        bob_app_id = bob_app.id

    res = client.post("/configs", json=_bookmark_body(bob_app_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_cible_un_kind_non_app_rejetee(client):
    with client.session_factory() as session:
        from app.items import repository as items_repo

        map_item = items_repo.create_item(
            session, tenant_id=client.user.tenant_id, owner_id=client.user.id,
            resource_type="map", title="Une carte",
        )
        session.commit()
        map_item_id = map_item.id

    res = client.post("/configs", json=_bookmark_body(map_item_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_update_bookmark_app_inexistante_rejetee(client):
    app_item_id = client.post("/configs", json=_app_body()).json()["itemId"]
    created = client.post("/configs", json=_bookmark_body(app_item_id))
    item_id = created.json()["itemId"]
    bad_config = {
        "version": 1, "kind": "bookmark",
        "bookmark": {"appId": "inexistante", "pageId": "page-1"},
    }
    res = client.put(f"/configs/by-item/{item_id}", json=bad_config)
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_create_bookmark.py -v`
Expected: FAIL — `POST /configs` with `kind="bookmark"` currently returns 201 unconditionally (no validation runs yet), so `test_create_bookmark_app_inexistante_rejetee` and the two "rejected" tests fail (they expect 422 but get 201).

- [ ] **Step 3: Implement `bookmark_validation.py`**

Create `core/app/configs/bookmark_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Direct kind="bookmark" validation for app.configs. Unlike dataset_validation.py,
no registry indirection is needed here: appId always refers to an app/dashboard
item, and app.configs already imports app.items (see routes.py's _require_access),
so there is no forbidden cross-module dependency to route around (SP-14m §3).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_bookmark_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "bookmark":
        return
    payload = config.bookmark
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.appId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak app
        # existence, same convention as app.collections.dataset_validation.
        raise HTTPException(status_code=422, detail="app not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.appId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType not in ("app", "dashboard"):
        raise HTTPException(status_code=422, detail="app not found")
```

- [ ] **Step 4: Wire it into `core/app/configs/routes.py`**

Add the import next to the existing dataset one (near line 10):

```python
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
```

In `create_config` (around line 71), add the call right after the dataset one:

```python
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
```

In `update_config_by_item` (around line 224), same pattern:

```python
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_create_bookmark.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: same baseline plus the 6 (Task 1) + 5 (Task 2) new tests, no regressions — `validate_bookmark_payload` is a no-op for every other `kind`, so existing `app`/`dashboard`/`map`/`site`/`dataset` configs are unaffected.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/bookmark_validation.py core/app/configs/routes.py core/tests/test_create_bookmark.py
git commit -m "feat(core): validate bookmark appId readability on create/update (SP-14m)"
```

---

