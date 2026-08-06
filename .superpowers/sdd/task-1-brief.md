## Task 1: `CORE_ETL_ENABLED` capability flag

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/app/instance/routes.py`
- Modify: `.env.example`
- Modify: `core/tests/test_read_only_mode.py` (two exact-dict assertions break once `/instance` gains a key)
- Test: `core/tests/test_etl_enabled_flag.py`

**Interfaces:**
- Produces: `is_etl_enabled() -> bool` in `app.auth.dependency`, imported by
  every later task that needs to gate a surface (Tasks 4, 9 doc-only, 10, 11).
  `GET /instance` response gains `"etlEnabled": bool`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_etl_enabled_flag.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_etl_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_etl_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_ETL_ENABLED", raising=False)
    assert is_etl_enabled() is False


def test_is_etl_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    assert is_etl_enabled() is True
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    assert is_etl_enabled() is False


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


def test_instance_reports_etl_disabled_by_default(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": False}


def test_instance_reports_etl_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": True}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_etl_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_etl_enabled'`

- [ ] **Step 3: Implement `is_etl_enabled()`**

In `core/app/auth/dependency.py`, add right after `is_read_only_mode` (after line 23):

```python
def is_etl_enabled() -> bool:
    """CORE_ETL_ENABLED (SP-15a) — capacité instance-wide optionnelle, même
    convention que is_read_only_mode : lue à chaque appel, sans cache, pour
    que les tests basculent via monkeypatch sans recréer l'app. Défaut
    false : une instance qui monte en version ne voit rien de nouveau tant
    qu'elle n'a pas explicitement activé la capacité (cf. design SP-15a §3)."""
    return os.environ.get("CORE_ETL_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Wire it into `GET /instance`**

Replace the full contents of `core/app/instance/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_etl_enabled, is_read_only_mode

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {"readOnly": is_read_only_mode(), "etlEnabled": is_etl_enabled()}
```

- [ ] **Step 5: Fix the two existing exact-dict assertions**

In `core/tests/test_read_only_mode.py`, update:

```python
def test_instance_defaults_to_read_write(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": False}


def test_instance_reports_read_only_without_needing_auth(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": True, "etlEnabled": False}
```

- [ ] **Step 6: Add `.env.example` entry**

In `.env.example`, right after the `CORE_READ_ONLY_MODE=false` line, add:

```
CORE_ETL_ENABLED=false
```

- [ ] **Step 7: Run all affected tests**

Run: `cd core && uv run pytest tests/test_etl_enabled_flag.py tests/test_read_only_mode.py -v`
Expected: PASS (all tests green)

- [ ] **Step 8: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py .env.example \
  core/tests/test_read_only_mode.py core/tests/test_etl_enabled_flag.py
git commit -m "feat(core): add CORE_ETL_ENABLED instance-wide capability flag"
```

---

