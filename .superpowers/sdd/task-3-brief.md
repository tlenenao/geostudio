### Task 3: `app/configs/alert_validation.py` — dataset reference check, wired into `/configs`

**Files:**
- Create: `core/app/configs/alert_validation.py`
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_alert_validation.py`

**Interfaces:**
- Consumes: `app.items.repository.{get_access_facts, get_item}`, `app.sharing.authorization.can` (all existing).
- Produces: `validate_alert_payload(session, config, *, user) -> None` (raises `HTTPException(422)`), called from `create_config`/`update_config`/`update_config_by_item` in `configs/routes.py`, mirroring the 3 existing `_validate_*_payload` calls.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_validation.py
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _client_and_user(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'alert_validation.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, tenant, user, Session


def _alert_body(dataset_item_id: str) -> dict:
    return {
        "title": "High counts",
        "config": {
            "kind": "alert",
            "alert": {
                "datasetItemId": dataset_item_id,
                "query": {"agg": "count"},
                "condition": {"expr": "value > 100"},
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        },
    }


def test_create_alert_rule_rejects_a_nonexistent_dataset(monkeypatch, tmp_path):
    client, *_ = _client_and_user(monkeypatch, tmp_path)
    resp = client.post("/configs", json=_alert_body("does-not-exist"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dataset not found"


def test_create_alert_rule_rejects_a_non_dataset_item(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="Not a dataset",
        )
        s.commit()
        other_item_id = item.id
    resp = client.post("/configs", json=_alert_body(other_item_id))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dataset not found"


def test_create_alert_rule_succeeds_against_a_readable_dataset(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="My dataset",
        )
        s.commit()
        dataset_item_id = item.id
    resp = client.post("/configs", json=_alert_body(dataset_item_id))
    assert resp.status_code == 201
    assert resp.json()["kind"] == "alert"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_validation.py`
Expected: FAIL — the first two currently return `201` (no validation exists yet), the third fails for an unrelated reason or passes by accident; all three should fail against the intended assertions.

- [ ] **Step 3: Write the implementation**

```python
# core/app/configs/alert_validation.py
# SPDX-License-Identifier: Apache-2.0
"""Direct kind="alert" validation for app.configs. Mirrors
app.configs.bookmark_validation exactly: datasetItemId always refers to an
item of resourceType "dataset", and app.configs already imports app.items
(routes.py's _require_access), so there is no forbidden cross-module
dependency to route around. The condition expression itself is already
validated at the Pydantic level (AlertCondition._require_valid_expr,
Task 2) — nothing to re-check here."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_alert_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "alert":
        return
    payload = config.alert
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.datasetItemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak dataset
        # existence, same convention as app.configs.bookmark_validation.
        raise HTTPException(status_code=422, detail="dataset not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.datasetItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "dataset":
        raise HTTPException(status_code=422, detail="dataset not found")
```

Wire it into `core/app/configs/routes.py`:

```python
# Add to the import block:
from app.configs.alert_validation import validate_alert_payload as _validate_alert_payload
```

```python
# In create_config, alongside the other three _validate_*_payload calls:
    _validate_alert_payload(session, request.config, user=user)
```

```python
# In update_config, alongside the other three:
    _validate_alert_payload(session, config, user=user)
```

```python
# In update_config_by_item, alongside the other three:
    _validate_alert_payload(session, config, user=user)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_validation.py`
Expected: `3 passed`

Run the full configs-routes regression suite:

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_configs_models.py`
Expected: unchanged, all passing.

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/alert_validation.py core/app/configs/routes.py core/tests/test_alert_validation.py
git commit -m "feat(core): SP-16b — validate AlertRule.datasetItemId on /configs writes"
```

---

