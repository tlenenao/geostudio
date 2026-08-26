## Task 3: Format d'erreur unique RFC 7807 (3.5a)

**Files:**
- Create: `core/app/errors.py`
- Modify: `core/app/main.py` (register 3 exception handlers)
- Modify: `core/app/features/routes.py:107-108` (`_validation_error` reuses the new exception class)
- Modify: `core/app/harvest/routes.py` (6 inline `HTTPException(status_code=400, detail={"errors": [...]})` sites)
- Modify: `shell/src/api/itemClient.ts` (2 call sites: `requestFeatureWrite`, `requestAnalyticsSql`)
- Modify: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` (regenerated)
- Test: `core/tests/test_error_format.py` (new), `core/tests/test_features_routes_write.py` (existing — verify still green with the new `errors` top-level shape), `shell/src/api/itemClient.test.ts` (existing — update 2 assertions)

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `ValidationHTTPException(errors: list[dict], status_code: int = 400)` from `core/app/errors.py`, used by Task 4 (rate limiter) for its 429 responses.

**Context:** `core/app/features/routes.py:107-108` defines the single helper `_validation_error` used by 11 call sites in that file; `core/app/harvest/routes.py` has 6 more sites constructing the identical `HTTPException(status_code=400, detail={"errors": [...]})` shape inline (`live_query.ArcgisQueryError` handling). `core/app/errors.py` is a new standalone module, following the precedent of `core/app/db.py`/`core/app/observability.py` — top-level modules **not** listed in `[tool.importlinter]`'s `layers` in `core/pyproject.toml`, so both `app.features` and `app.harvest` (different, non-adjacent layers) can import it without any layer-contract change.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_error_format.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def test_unhandled_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()

    @app.get("/__boom")
    def boom():
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 500
    assert body["title"]
    assert body["detail"] == "internal server error"
    assert "kaboom" not in response.text  # jamais fuiter le message interne


def test_plain_http_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app())
    response = client.get("/collections/does-not-exist/items/does-not-exist")
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == response.status_code
    assert isinstance(body["detail"], str)
    assert "errors" not in body  # pas de validation structurée sur ce chemin


def test_validation_exception_carries_top_level_errors(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app())
    response = client.post("/analytics/sql", json={"sql": "not valid sql at all"})
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert isinstance(body["detail"], str)  # jamais un dict désormais
    assert isinstance(body["errors"], list)
    assert body["errors"][0]["field"] == "sql"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd core
uv run pytest tests/test_error_format.py -v
```

Expected: all 3 FAIL — no `application/problem+json` content-type exists yet, and `/analytics/sql`'s current error body nests `errors` under `detail`, not at the top level.

- [ ] **Step 3: Create the shared exception class**

Create `core/app/errors.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Module bas de la pile (hors du contrat de couches import-linter, même
précédent que app.db/app.observability) : ValidationHTTPException est
importée à la fois par app.features et app.harvest, deux couches non
adjacentes du contrat — un module de contrat aurait dû se placer entre les
deux sans raison métier, donc il reste en dehors, comme app.db."""

from fastapi import HTTPException


class ValidationHTTPException(HTTPException):
    """HTTPException porteuse d'erreurs de validation structurées. Le corps
    RFC 7807 (main.py) les expose sous un membre d'extension `errors` au
    premier niveau — jamais imbriqué sous `detail`, qui reste une chaîne
    (design SP-26 §3.5a/§4.4, changement cassant assumé vis-à-vis de la
    forme précédente {"errors": [...]} nichée sous detail)."""

    def __init__(self, errors: list[dict], status_code: int = 400) -> None:
        super().__init__(status_code=status_code, detail="validation failed")
        self.errors = errors
```

- [ ] **Step 4: Register the three exception handlers in `main.py`**

Add near the top of `core/app/main.py`, after the existing imports:

```python
from http import HTTPStatus

from app.errors import ValidationHTTPException
```

Inside `create_app()`, after `app = FastAPI(...)` and `observability.instrument_app(app)` (before the existing `read_only_guard` middleware definition, order doesn't matter for exception handlers vs. middleware — FastAPI registers them independently):

```python
    @app.exception_handler(ValidationHTTPException)
    async def _validation_exception_handler(request: Request, exc: ValidationHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail,
                "errors": exc.errors,
            },
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail if isinstance(exc.detail, str) else "request failed",
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        observability.record_unhandled_exception(exc)  # cf. Step 4b ci-dessous
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
                "status": 500,
                "detail": "internal server error",
            },
        )
```

- [ ] **Step 4b: Check whether `observability.record_unhandled_exception` already exists before calling it**

```bash
cd core
grep -n "def record_unhandled_exception\|def.*exception" app/observability.py
```

If nothing matches, the unhandled-exception handler should NOT invent a new observability function speculatively — instead just log via the standard library and rely on OTel's existing FastAPI auto-instrumentation (`observability.instrument_app(app)`, already called, typically captures unhandled exceptions as span events automatically for `opentelemetry-instrumentation-fastapi`). Replace the call with:

```python
    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        import logging

        logging.getLogger("app.errors").exception("unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
                "status": 500,
                "detail": "internal server error",
            },
        )
```

Use whichever of the two forms matches what actually exists in `app/observability.py` — don't leave a call to a function you haven't confirmed exists.

- [ ] **Step 5: Convert `_validation_error` in `features/routes.py`**

Edit `core/app/features/routes.py:107-108`:

```python
def _validation_error(errors: list[dict], status: int = 400):
    return ValidationHTTPException(errors=errors, status_code=status)
```

Add the import near the top of the file:

```python
from app.errors import ValidationHTTPException
```

- [ ] **Step 6: Convert the 6 inline sites in `harvest/routes.py`**

For each of the 6 occurrences found by `grep -n '"errors":' core/app/harvest/routes.py` (lines 313, 363, 396, 425, 477, 524 as of this writing — re-check with the grep since line numbers shift as earlier steps land), replace the pattern:

```python
raise HTTPException(
    status_code=400,
    detail={
        "errors": [{"field": exc.field, "code": "invalid_filter", "message": exc.message}]
    },
) from exc
```

with:

```python
raise ValidationHTTPException(
    errors=[{"field": exc.field, "code": "invalid_filter", "message": exc.message}],
    status_code=400,
) from exc
```

Preserve each site's exact `errors` list content (some of the 6 have different shapes — check each one individually with `sed -n '<line>,<line+10>p' core/app/harvest/routes.py` before editing, don't assume they're identical to the one shown above). Add `from app.errors import ValidationHTTPException` to the file's imports; the plain `HTTPException` import stays if used elsewhere in the file (check with `grep -c "HTTPException(" core/app/harvest/routes.py` before removing the import).

- [ ] **Step 7: Run the new tests and the two existing route test files**

```bash
cd core
uv run pytest tests/test_error_format.py tests/test_features_routes_write.py tests/test_analytics_sql_routes.py tests/test_harvest_routes.py -v
```

Expected: all pass. If `test_features_routes_write.py` or `test_harvest_routes.py` has an existing assertion checking `response.json()["detail"]["errors"]` (the old nested shape), update it to `response.json()["errors"]` — grep first: `grep -n '\["detail"\]\["errors"\]\|detail.*errors' core/tests/test_features_routes_write.py core/tests/test_harvest_*.py` and fix each hit found.

- [ ] **Step 8: Update the shell's two call sites**

Edit `shell/src/api/itemClient.ts`'s `requestFeatureWrite` (around line 236 as of this writing — re-check with `grep -n "data?.detail?.errors" shell/src/api/itemClient.ts`):

```typescript
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { errors?: FieldError[] } | null;
    throw new FeatureValidationError(data?.errors ?? []);
  }
```

And `requestAnalyticsSql` (around line 290):

```typescript
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as {
      errors?: FieldError[];
    } | null;
    throw new SqlQueryError(data?.errors?.[0]?.message ?? "Requête SQL invalide.");
  }
```

The generic `!res.ok` branch in `requestFeatureWrite` (reading `data?.detail` as a string) stays unchanged — `detail` is still a plain string for every non-validation error path.

- [ ] **Step 9: Update the shell test file**

```bash
cd shell
grep -n "detail.*errors\|errors.*detail" src/api/itemClient.test.ts
```

Update any mock response fixture in that file from `{ detail: { errors: [...] } }` to `{ errors: [...] }` to match the new server shape. Run:

```bash
npx vitest run src/api/itemClient.test.ts
```

Expected: all pass.

- [ ] **Step 10: Regenerate OpenAPI + TS types**

```bash
cd core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= uv run python scripts/export_openapi.py openapi.json
cd ../shell
npm run gen:api-types
git diff --stat -- ../core/openapi.json src/api/generated/core-schema.d.ts
```

Expected this time: a **non-empty** diff (unlike capability flags gated off in CI) — the global exception handler changes the documented error response shape for every route. Review the diff briefly to confirm it's limited to error-response schemas, not an unrelated drift.

- [ ] **Step 11: Run the full non-regression suite**

```bash
cd core
uv run pytest -x -q
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
cd ../shell
npx vitest run
npm run lint && npm run format:check && npm run build
```

Expected: no regressions vs. the Global Constraints baseline (core count grows by 3 new tests in `test_error_format.py`; shell count unchanged unless `itemClient.test.ts` gained assertions).

- [ ] **Step 12: Commit**

```bash
git add core/app/errors.py core/app/main.py core/app/features/routes.py core/app/harvest/routes.py core/tests/test_error_format.py core/openapi.json
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): format d'erreur RFC 7807 unique sur toute l'API

Handler d'exception global (application/problem+json) sur
HTTPException/Exception non gérée. Les erreurs de validation
structurées migrent vers un membre d'extension `errors` au premier
niveau, plus imbriquées sous `detail` — changement cassant scopé à 2
sites d'appel shell (ARC-04, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

