## Task 2: `validate_report_payload` + wiring into `/configs` routes

**Files:**
- Create: `core/app/configs/report_validation.py`
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_report_validation.py`

**Interfaces:**
- Consumes: `BuilderConfig`, `ReportSchedulePayload` (Task 1); `items_repo.get_access_facts`/`get_item`, `can` (existing).
- Produces: `validate_report_payload(session, config, *, user) -> None` (raises `HTTPException(422)` on an unreadable/wrong-type bookmark), called at `POST /configs`, `PUT /configs/{id}`, `PUT /configs/by-item/{id}`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_validation.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.configs.report_validation import validate_report_payload
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _report_config(bookmark_item_id: str) -> BuilderConfig:
    return BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": bookmark_item_id,
            "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })


def test_ignores_non_report_kind():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        config = BuilderConfig.model_validate({"kind": "pipeline", "pipeline": {"nodes": [], "edges": []}})
        validate_report_payload(s, config, user=user)  # no raise


def test_rejects_unreadable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        config = _report_config("does-not-exist")
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_rejects_bookmark_item_id_pointing_at_non_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Not a bookmark",
        )
        s.commit()
        config = _report_config(item.id)
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_accepts_readable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="bookmark", title="A view",
        )
        s.commit()
        config = _report_config(item.id)
        validate_report_payload(s, config, user=user)  # no raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.configs.report_validation'`.

- [ ] **Step 3: Write `report_validation.py`**

```python
# core/app/configs/report_validation.py
# SPDX-License-Identifier: Apache-2.0
"""Direct kind="report" validation for app.configs. Mirrors
app.configs.alert_validation/bookmark_validation exactly: bookmarkItemId
always refers to an item of resourceType "bookmark", and app.configs already
imports app.items, so there is no forbidden cross-module dependency to route
around (SP-17b design §Modèle de données)."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_report_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "report":
        return
    payload = config.report
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak bookmark
        # existence, same convention as app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="bookmark not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "bookmark":
        raise HTTPException(status_code=422, detail="bookmark not found")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_validation.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire into `core/app/configs/routes.py`**

Add the import next to the other `_validate_*_payload` imports:
```python
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
from app.configs.report_validation import validate_report_payload as _validate_report_payload
```

Add one call right after every existing `_validate_alert_payload(...)` line — three call sites:

`create_config` (after `_validate_alert_payload(session, request.config, user=user)`):
```python
    _validate_alert_payload(session, request.config, user=user)
    _validate_report_payload(session, request.config, user=user)
```

`update_config` (after `_validate_alert_payload(session, config, user=user)`):
```python
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
```

`update_config_by_item` (after `_validate_alert_payload(session, config, user=user)`):
```python
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
```

- [ ] **Step 6: Run the full configs test suite**

Run: `cd core && uv run pytest tests/test_configs_routes.py tests/test_alert_routes.py -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/configs/report_validation.py core/app/configs/routes.py core/tests/test_report_validation.py
git commit -m "feat(core): validate ReportSchedule.bookmarkItemId on /configs writes (SP-17b)"
```

---

