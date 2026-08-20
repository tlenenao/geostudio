## Task 2: Core — `is_copilot_enabled()` + `GET /instance.copilotEnabled`

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/app/instance/routes.py`
- Create: `core/tests/test_copilot_enabled_flag.py`
- Modify: `core/tests/test_etl_enabled_flag.py`, `core/tests/test_export_enabled_flag.py`, `core/tests/test_read_only_mode.py` (their `GET /instance` exact-dict assertions gain a `copilotEnabled` key — see Step 4)

**Interfaces:**
- Produces: `is_copilot_enabled() -> bool` in `app.auth.dependency`, importable by `core/app/main.py` (Task 5).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_copilot_enabled_flag.py`, mirroring `core/tests/test_etl_enabled_flag.py` exactly:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_copilot_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_copilot_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    assert is_copilot_enabled() is False


def test_is_copilot_enabled_true_for_any_non_empty_provider(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "openai")
    assert is_copilot_enabled() is True
    monkeypatch.setenv("CORE_LLM_PROVIDER", "fake")
    assert is_copilot_enabled() is True


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


def test_instance_reports_copilot_disabled_by_default(env, monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["copilotEnabled"] is False


def test_instance_reports_copilot_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "openai")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["copilotEnabled"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_copilot_enabled'`.

- [ ] **Step 3: Implement**

In `core/app/auth/dependency.py`, add right after `is_terrain3d_enabled()` (before `admin_subs()`):

```python
def is_copilot_enabled() -> bool:
    """CORE_LLM_PROVIDER (SP-20) — contrairement aux autres capacités
    instance-wide ci-dessus (is_etl_enabled et consorts), ce n'est pas un
    booléen dédié : le copilote est actif dès qu'un fournisseur LLM est
    configuré, quelle que soit sa valeur (CORE_LLM_PROVIDER=openai, ou
    toute chaîne non vide). Lue à chaque appel, sans cache, même
    convention que is_read_only_mode ci-dessus."""
    return bool(os.environ.get("CORE_LLM_PROVIDER"))
```

In `core/app/instance/routes.py`, update the import and response dict:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import (
    is_appexport_enabled, is_copilot_enabled, is_etl_enabled, is_export_enabled,
    is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "appExportEnabled": is_appexport_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
        "terrain3dEnabled": is_terrain3d_enabled(),
        "copilotEnabled": is_copilot_enabled(),
    }
```

- [ ] **Step 4: Fix the three existing tests with brittle exact-dict assertions**

`GET /instance` is now a 7-key dict; three existing test files assert exact dict equality on the old 6-key shape and will break. Add `"copilotEnabled": False` to each:

In `core/tests/test_etl_enabled_flag.py`, both occurrences of:
```python
        "readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False,
    }
```
and
```python
        "readOnly": False, "etlEnabled": True, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False,
    }
```
become (append the key on its own trailing line before the closing brace):
```python
        "readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False, "copilotEnabled": False,
    }
```
(and the `etlEnabled: True` variant keeps `copilotEnabled: False` — this file never sets `CORE_LLM_PROVIDER`).

In `core/tests/test_export_enabled_flag.py`, the one occurrence starting `"readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,` gets the same `"copilotEnabled": False,` appended.

In `core/tests/test_read_only_mode.py`, both occurrences (`"readOnly": False, ...` and `"readOnly": True, ...`) get `"copilotEnabled": False,` appended the same way.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_enabled_flag.py tests/test_etl_enabled_flag.py tests/test_export_enabled_flag.py tests/test_read_only_mode.py tests/test_tileset3d_enabled_flag.py tests/test_terrain3d_enabled_flag.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py core/tests/test_copilot_enabled_flag.py core/tests/test_etl_enabled_flag.py core/tests/test_export_enabled_flag.py core/tests/test_read_only_mode.py
git commit -m "$(cat <<'EOF'
feat(core): capacité copilotEnabled sur GET /instance (SP-20)

is_copilot_enabled() reflète la présence de CORE_LLM_PROVIDER (pas un
booléen dédié, contrairement aux autres capacités) ; GET /instance
l'expose pour que le shell affiche ou non l'onglet copilote.
EOF
)"
```

---

