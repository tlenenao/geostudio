## Task 4: Rate limiting différencié (3.4)

**Files:**
- Create: `core/app/ratelimit/__init__.py`
- Create: `core/app/ratelimit/limiter.py`
- Modify: `core/app/main.py` (mount the middleware, define the 4 route-group regexes)
- Test: `core/tests/test_ratelimit.py` (new)

**Interfaces:**
- Consumes: `ValidationHTTPException`-style RFC 7807 shape from Task 3 for the 429 body (reuses the plain `HTTPException` path — a 429 isn't a validation error, so it goes through the `HTTPException` handler registered in Task 3, not `ValidationHTTPException`).
- Produces: nothing consumed by later tasks.

**Context:** `core/app/main.py`'s existing `read_only_guard` (defined via `@app.middleware("http")` inside `create_app()`) proves the pattern needed here: a `@app.middleware("http")` function sees every request, including the `/mcp` ASGI mount (`app.mount("/", mcp_server.streamable_http_app())`), because Starlette middleware wraps the whole app before routing/mounting dispatch. `_EXPORT_PATH_RE` (`core/app/main.py:53-55`) already matches `/export`, `/app-exports`, `/collections/{id}/export(/items)?`, `/datasets/{id}/arcgis/export` — reuse it directly rather than redefining. Confirmed route literals: `/analytics/sql` (`features/routes.py:420`), `/copilot/turn` (`copilot/routes.py:183`), `/mcp` (mount root, matched exactly by `read_only_guard`'s own check), `/harvest/*` (6+ distinct literal paths in `harvest/routes.py`, no shared router prefix — match by `^/harvest/` prefix).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_ratelimit.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    return TestClient(create_app())


def test_sql_route_rate_limited_after_budget_exhausted(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    assert response.status_code == 429
    assert "retry-after" in {k.lower() for k in response.headers.keys()}
    assert response.headers["content-type"] == "application/problem+json"


def test_different_callers_have_independent_budgets(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(10):
        client.post(
            "/analytics/sql",
            json={"sql": "select 1"},
            headers={"Authorization": "Bearer caller-a"},
        )
    # caller-a est épuisé, mais caller-b démarre avec un budget frais
    response = client.post(
        "/analytics/sql", json={"sql": "select 1"}, headers={"Authorization": "Bearer caller-b"}
    )
    assert response.status_code != 429


def test_health_endpoint_not_rate_limited_by_sql_budget(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.get("/health", headers=headers)
    assert response.status_code != 429
```

(Check `GET /health` actually exists first: `grep -n '"/health"' core/app/main.py` — if the route is named differently, use the real path.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd core
uv run pytest tests/test_ratelimit.py -v
```

Expected: `test_sql_route_rate_limited_after_budget_exhausted` FAILS (no 429 ever returned — no rate limiting exists yet). The other two currently pass vacuously (nothing to break).

- [ ] **Step 3: Implement the limiter**

Create `core/app/ratelimit/__init__.py` (empty, just makes it a package).

Create `core/app/ratelimit/limiter.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Rate limiting en mémoire process, par (clé d'appelant, groupe de route)
— design SP-26 §3.4. Clé d'appelant = l'en-tête Authorization brut, pas un
user_id résolu : ce middleware tourne AVANT l'injection de dépendances
FastAPI (donc avant get_current_user), et /mcp est un mount ASGI brut sans
dépendances du tout — décoder/vérifier le JWT ici dupliquerait toute la
logique de app.auth.dependency pour un usage qui n'a besoin que d'une clé
stable, pas d'une identité vérifiée. Limite assumée : ne tient pas
multi-process (pas de --workers aujourd'hui côté uvicorn, cf. C2/vague 0)."""

import re
import time
from collections import defaultdict, deque

_SQL_RE = re.compile(r"^/analytics/sql$")
_LLM_RE = re.compile(r"^/mcp$|^/copilot/turn$")
_HARVEST_RE = re.compile(r"^/harvest/")

# Budgets par groupe de coût réel (requêtes / 60s). Réutilise _EXPORT_PATH_RE
# de app.main pour le groupe "jobs" plutôt que de le redéfinir ici.
_BUDGETS = {
    "sql": 10,
    "llm": 20,
    "jobs": 15,
    "harvest": 10,
}
_WINDOW_SECONDS = 60.0


def route_group(path: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if _HARVEST_RE.match(path):
        return "harvest"
    return None


class RateLimiter:
    """Compteur glissant par (clé, groupe) — deque d'horodatages, purgée à
    chaque appel. Pas de nettoyage périodique en arrière-plan : une clé
    inactive garde une deque vide en mémoire indéfiniment, coût négligeable
    face au volume de callers distincts attendu (limite documentée, pas un
    bug — cf. design §7)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, key: str, group: str) -> bool:
        budget = _BUDGETS[group]
        now = time.monotonic()
        bucket = self._hits[(key, group)]
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= budget:
            return False
        bucket.append(now)
        return True
```

- [ ] **Step 4: Mount the middleware in `main.py`**

Add the import near the top of `core/app/main.py`:

```python
from app.ratelimit.limiter import RateLimiter, route_group
```

Inside `create_app()`, after `app = FastAPI(...)` / `observability.instrument_app(app)` and before (or after — independent of) the `read_only_guard` middleware, add a new middleware and a module-level-per-app limiter instance:

```python
    rate_limiter = RateLimiter()

    @app.middleware("http")
    async def rate_limit_guard(request: Request, call_next):
        group = route_group(request.url.path, _EXPORT_PATH_RE)
        if group is not None:
            caller_key = request.headers.get("authorization", "")
            if not rate_limiter.allow(caller_key, group):
                return JSONResponse(
                    status_code=429,
                    media_type="application/problem+json",
                    headers={"Retry-After": "60"},
                    content={
                        "type": "about:blank",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": f"rate limit exceeded for {group}",
                    },
                )
        return await call_next(request)
```

`rate_limiter = RateLimiter()` is created inside `create_app()`, not at module level — matches the existing pattern where per-app state (like `mcp_server`) is scoped to one `create_app()` call, since the test suite calls `create_app()` repeatedly per test and a module-level singleton would leak rate-limit state across unrelated tests (the exact same reasoning already documented in `main.py`'s comment about `mcp_server` not being memoized process-wide).

- [ ] **Step 5: Run the new tests and the full suite**

```bash
cd core
uv run pytest tests/test_ratelimit.py -v
uv run pytest -x -q
```

Expected: 3 new tests pass; full suite count grows by 3, no other regressions.

- [ ] **Step 6: Verify `/mcp` is actually covered (the reason this had to be middleware, not a route dependency)**

```bash
cd core
uv run python -c "
from app.ratelimit.limiter import route_group
import re
export_re = re.compile(r'^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?\$|^/export\$|^/app-exports\$')
assert route_group('/mcp', export_re) == 'llm'
assert route_group('/copilot/turn', export_re) == 'llm'
assert route_group('/analytics/sql', export_re) == 'sql'
assert route_group('/export', export_re) == 'jobs'
assert route_group('/app-exports', export_re) == 'jobs'
assert route_group('/harvest/sources', export_re) == 'harvest'
assert route_group('/health', export_re) is None
print('all route groups correct')
"
```

- [ ] **Step 7: Commit**

```bash
git add core/app/ratelimit/ core/app/main.py core/tests/test_ratelimit.py
git commit -m "$(cat <<'EOF'
feat(core): rate limiting différencié par route sensible

Middleware ASGI (couvre /mcp, un mount brut hors du routage FastAPI,
comme le fait déjà read_only_guard) — compteur en mémoire par (en-tête
Authorization, groupe de route), budgets distincts sql/llm/jobs/harvest
(I4, revue de projet 2026-08-20). Limite assumée : par process, pas de
Redis.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

