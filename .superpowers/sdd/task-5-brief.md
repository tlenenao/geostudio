### Task 5: narrow, capability-gated CORS middleware

**Files:**
- Modify: `core/app/main.py`
- Create: `core/tests/test_appexport_cors.py`

**Interfaces:**
- Produces: when `CORE_APPEXPORT_ENABLED=true`, `OPTIONS`/`GET`/`POST` on a
  fixed allowlist of already-anonymous-capable read paths (`/collections`,
  `/collections/{id}`, `/collections/{id}/schema`, `/collections/{id}/items`,
  `/collections/{id}/items/{fid}`, `/collections/{id}/aggregate`,
  `/extensions`) get `Access-Control-Allow-Origin: *` on the response (and a
  204 with the matching preflight headers for `OPTIONS`). Every other path,
  and every path when the flag is off, is untouched.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_appexport_cors.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def test_cors_header_present_on_matched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/collections")
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_header_absent_when_disabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    client = TestClient(create_app())
    response = client.get("/collections")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_responds_on_matched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.options("/collections/col1/aggregate")
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "content-type" in response.headers.get("access-control-allow-headers", "").lower()


def test_cors_header_absent_on_unmatched_path_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_cors.py -v`
Expected: FAIL — `test_cors_header_present_on_matched_path_when_enabled` and
`test_cors_preflight_responds_on_matched_path_when_enabled` fail (no header
present / 405 instead of 204); the other two pass already (nothing to
regress).

- [ ] **Step 3: Add the middleware in `main.py`**

In `core/app/main.py`, change the import line:

```python
from fastapi.responses import JSONResponse
```

to:

```python
from fastapi.responses import JSONResponse, Response
```

Then, directly below the existing `_EXPORT_PATH_RE` definition, add:

```python
# CORS narrow allowlist (SP-18b) : uniquement les endpoints déjà
# anonymes-capables (get_current_user_optional) qu'un bundle d'export
# Connecté appelle en direct depuis un domaine tiers arbitraire — jamais
# toute l'API. Wildcard origin sûr ici précisément parce qu'aucune
# credential/cookie ne traverse cette frontière (Bearer-ou-rien).
_APPEXPORT_CORS_PATH_RE = re.compile(
    r"^/collections(/[^/]+)?$"
    r"|^/collections/[^/]+/schema$"
    r"|^/collections/[^/]+/items(/[^/]+)?$"
    r"|^/collections/[^/]+/aggregate$"
    r"|^/extensions$"
)
```

Then, inside `create_app()`, directly after the existing `read_only_guard`
middleware function definition (right before `def get_session() ->
Iterator[Session]:`), add:

```python
    if is_appexport_enabled():
        @app.middleware("http")
        async def appexport_cors(request: Request, call_next):
            if not _APPEXPORT_CORS_PATH_RE.match(request.url.path):
                return await call_next(request)
            if request.method == "OPTIONS":
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                    },
                )
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
```

(evaluated once at `create_app()` time, same timing convention as the
existing `if is_appexport_enabled(): app.include_router(appexport_routes.router)`
a few lines below it — not re-checked per request.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_cors.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full core suite to confirm nothing broke**

Run: `cd core && uv run pytest -q`
Expected: PASS (no regressions — the middleware only touches responses on
the narrow matched-path allowlist).

- [ ] **Step 6: Commit**

```bash
git add core/app/main.py core/tests/test_appexport_cors.py
git commit -m "feat(core): narrow CORS allowlist for connected app exports (SP-18b)"
```

---

