# `transform.httpCall` (HTTPCaller) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter l'op de pipeline `transform.httpCall` : un appel HTTP par ligne d'entrée (retry, pagination agrégée, multipart, concurrence/débit bornés, erreur capturée par ligne).

**Architecture:** Nouvelle op `transform` avec `execute=` (mécanisme `OperationContract.execute` de la Vague 2, jamais `compile`) ; code dans un nouveau module `core/app/pipelines/http_call_runtime.py`. Les expressions (URL/headers/corps) sont des expressions SQL DuckDB bornées, évaluées en une passe dans une table de staging `row_number()`-ée ; la boucle réseau (ThreadPoolExecutor) ne touche jamais la connexion DuckDB ; les résultats sont rejoints sur `__rn` (la géométrie d'entrée n'est donc jamais relue en Python). Auth/pagination/garde SSRF réutilisées de `connector_runtime.py`/`egress.py` (non modifiés, sauf extraction d'un helper de portée de secret).

**Tech Stack:** Python 3.12, DuckDB, pandas, `requests`, `dlt` (`RESTClient`), pydantic v2, pytest + `pytest-httpserver`.

Spec : `docs/superpowers/specs/2026-09-21-transform-http-call-design.md` (révisée 2026-10-11). Écarts de ce plan par rapport à la spec révisée, à consigner en Task 8 : (a) le champ de contrat s'appelle `needs_runtime_context` (et non `needs_secrets`) car il transmet aussi `preview` ; (b) mode aperçu : voir Global Constraints.

## Global Constraints

- Commandes depuis `core/` ; tests : `uv run pytest <chemin> -v`. Aucun test de ce plan ne requiert `CORE_TEST_DATABASE_URL` (DuckDB en mémoire + `pytest-httpserver`).
- Docs/messages utilisateur en **français**, identifiants/code en **anglais** ; commits conventional (`feat(core): …`), un sujet, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- `compile` et `execute` mutuellement exclusifs : `transform.httpCall` a `execute=` et `compile=None`. `compiler.py` n'est PAS modifié.
- `egress.py` n'est PAS modifié ; la garde est appliquée par `build_guarded_session()` à chaque tentative (retry maison).
- Aucun message d'erreur ne contient l'URL complète, un en-tête ni un jeton : uniquement un nom d'exception, `HTTP <code>` ou un message fixe.
- Bornes de schéma : `maxRetries` 0–10, `maxConcurrency` 1–16, `timeoutSeconds` 0<x≤120, `requestsPerSecond` >0, `initialBackoffSeconds` 0≤x≤60. Plafond de lignes `CORE_PIPELINES_HTTP_CALL_MAX_ROWS` (défaut 10000), plafond de réponse `CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES` (défaut 5 242 880), `Retry-After` plafonné à 60 s.
- Un secret REST est lié à `payload.baseUrl` (REV-294) : l'URL de **chaque ligne** doit être dans cette portée, sinon ligne en erreur **sans appel réseau** ; avec un secret, les redirections ne sont **pas suivies**.
- Mode aperçu (`preview_pipeline`) : seules les méthodes `GET` sont exécutées, et seulement pour les 20 premières lignes ; toute autre ligne a `httpStatus="skipped"` et `httpError="non exécuté en aperçu"`. (Décision de ce plan, évite des effets de bord POST/DELETE à chaque aperçu — à faire confirmer par Tanguy.)
- Pas de nouveau flag d'instance : l'op vit sous `CORE_ETL_ENABLED` comme tout le moteur de pipelines.
- Pagination (`paginator != "none"`) : méthodes `GET`/`POST` seulement, incompatible avec `bodyType="multipart"`.
- Colonnes de sortie par défaut : `responseBody`, `httpStatusCode`, `httpStatus` (`success`|`error`|`skipped`), `httpError`.

## File Structure

| Fichier | Rôle |
|---|---|
| `core/app/pipelines/ops/schemas.py` (modif.) | `MultipartField`, `TransformHttpCallParams` |
| `core/app/pipelines/http_call_runtime.py` (nouveau) | `execute_http_call(conn, *, input_view, view_name, params, secret_resolver=None, preview=False)` + helpers privés |
| `core/app/pipelines/ops/contracts.py` (modif.) | champ `needs_runtime_context`, entrée `OPERATIONS["transform.httpCall"]` |
| `core/app/pipelines/runtime.py` (modif.) | `_execute_transform_chain(..., secret_resolver=None, preview=False)` + 2 appelants |
| `core/app/pipelines/connector_runtime.py` (modif.) | extraction `_url_within_scope(scope, url)` |
| `core/tests/test_pipeline_http_call_runtime.py` (nouveau) | tous les tests d'exécution |
| `core/tests/test_pipeline_ops_schemas.py`, `test_pipeline_ops_contracts.py`, `test_pipeline_routes.py` (modif.) | compte/ensemble d'op, schéma |

---

### Task 1: Schéma `TransformHttpCallParams`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py` (ajout en fin de fichier)
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Produces: `MultipartField(name: str, valueExpr: str, isFile: bool=False, filename: str|None=None, contentType: str|None=None)` ; `TransformHttpCallParams` avec les champs/défauts de la spec §3 (`urlExpr`, `method`, `headersExpr`, `bodyType`, `bodyExpr`, `multipartFields`, `secretName`, `paginator`, `paginatorConfig`, `recordsPath`, `maxConcurrency=1`, `requestsPerSecond=None`, `maxRetries=3`, `initialBackoffSeconds=1.0`, `timeoutSeconds=30.0`, `responseColumn`, `statusCodeColumn`, `statusColumn`, `errorColumn`).

- [ ] **Step 1: Write the failing tests** (ajouter à `core/tests/test_pipeline_ops_schemas.py`)

```python
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import MultipartField, TransformHttpCallParams


def _http(**over):
    return TransformHttpCallParams(urlExpr="'https://x.example/'", **over)


def test_http_call_defaults():
    p = _http()
    assert (p.method, p.bodyType, p.paginator) == ("GET", "none", "none")
    assert (p.maxConcurrency, p.maxRetries, p.timeoutSeconds) == (1, 3, 30.0)
    assert (p.responseColumn, p.statusCodeColumn, p.statusColumn, p.errorColumn) == (
        "responseBody",
        "httpStatusCode",
        "httpStatus",
        "httpError",
    )


@pytest.mark.parametrize("body_type", ["json", "form", "raw"])
def test_http_call_body_expr_required_for_body_types(body_type):
    with pytest.raises(ValidationError, match="bodyExpr"):
        _http(bodyType=body_type)


def test_http_call_multipart_requires_fields():
    with pytest.raises(ValidationError, match="multipartFields"):
        _http(bodyType="multipart")
    _http(bodyType="multipart", multipartFields=[MultipartField(name="f", valueExpr="1")])


def test_http_call_output_columns_must_be_distinct():
    with pytest.raises(ValidationError, match="distinct"):
        _http(responseColumn="x", errorColumn="x")


def test_http_call_paginator_restrictions():
    with pytest.raises(ValidationError, match="GET ou POST"):
        _http(paginator="offset", method="PUT", paginatorConfig={"limit": 10})
    with pytest.raises(ValidationError, match="multipart"):
        _http(
            paginator="page_number",
            bodyType="multipart",
            multipartFields=[MultipartField(name="f", valueExpr="1")],
        )


@pytest.mark.parametrize(
    "over",
    [
        {"maxRetries": 11},
        {"maxConcurrency": 0},
        {"maxConcurrency": 17},
        {"timeoutSeconds": 0},
        {"timeoutSeconds": 121},
        {"requestsPerSecond": 0},
        {"initialBackoffSeconds": 61},
    ],
)
def test_http_call_numeric_bounds(over):
    with pytest.raises(ValidationError):
        _http(**over)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline_ops_schemas.py -k http_call -v`
Expected: FAIL (`ImportError: cannot import name 'MultipartField'`).

- [ ] **Step 3: Implement** (fin de `schemas.py` ; `Literal`, `Field`, `model_validator`, `Any` sont déjà importés)

```python
class MultipartField(BaseModel):
    """Champ d'un corps `multipart/form-data`. `valueExpr` est une expression SQL DuckDB bornée ;
    avec `isFile=True`, sa valeur (BLOB ou texte) est envoyée comme fichier."""

    name: str
    valueExpr: str
    isFile: bool = False
    filename: str | None = None
    contentType: str | None = None


class TransformHttpCallParams(BaseModel):
    """Appelle un service HTTP une fois par ligne d'entrée et ajoute la réponse en colonnes
    (corps, code HTTP, statut, erreur). L'URL, les en-têtes et le corps sont des expressions SQL
    évaluées sur chaque ligne ; l'authentification vient d'un secret (clé API, jeton, identifiants,
    OAuth2) dont l'URL de base doit couvrir chaque URL appelée. Réessaie sur délai dépassé/5xx/429
    (en respectant `Retry-After`), borne la concurrence et le débit ; un échec est consigné sur sa
    ligne sans interrompre l'exécution. Avec une pagination, toutes les pages sont agrégées en un
    tableau JSON dans la colonne de réponse. En aperçu, seuls des GET sont exécutés."""

    urlExpr: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    headersExpr: str | None = None
    bodyType: Literal["none", "json", "form", "raw", "multipart"] = "none"
    bodyExpr: str | None = None
    multipartFields: list[MultipartField] = Field(default_factory=list)
    secretName: str | None = Field(default=None, json_schema_extra={"format": "secret-name"})
    paginator: Literal["none", "page_number", "offset", "cursor"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)
    recordsPath: str | None = None
    maxConcurrency: int = Field(default=1, ge=1, le=16)
    requestsPerSecond: float | None = Field(default=None, gt=0)
    maxRetries: int = Field(default=3, ge=0, le=10)
    initialBackoffSeconds: float = Field(default=1.0, ge=0, le=60)
    timeoutSeconds: float = Field(default=30.0, gt=0, le=120)
    responseColumn: str = "responseBody"
    statusCodeColumn: str = "httpStatusCode"
    statusColumn: str = "httpStatus"
    errorColumn: str = "httpError"

    @model_validator(mode="after")
    def _check(self) -> "TransformHttpCallParams":
        if self.bodyType in {"json", "form", "raw"} and not self.bodyExpr:
            raise ValueError(f"bodyExpr est requis pour bodyType={self.bodyType!r}")
        if self.bodyType == "multipart" and not self.multipartFields:
            raise ValueError("multipartFields est requis pour bodyType='multipart'")
        outs = [self.responseColumn, self.statusCodeColumn, self.statusColumn, self.errorColumn]
        if len(set(outs)) != 4:
            raise ValueError("les 4 colonnes de sortie doivent être distinctes")
        if self.paginator != "none":
            if self.method not in {"GET", "POST"}:
                raise ValueError("une pagination exige la méthode GET ou POST")
            if self.bodyType == "multipart":
                raise ValueError("une pagination est incompatible avec bodyType='multipart'")
        return self
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pipeline_ops_schemas.py -k http_call -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): schéma TransformHttpCallParams (transform.httpCall)"
```

---

### Task 2: Plomberie contrat/runtime + exécution minimale (GET, sans retry)

**Files:**
- Create: `core/app/pipelines/http_call_runtime.py`
- Modify: `core/app/pipelines/ops/contracts.py` (champ + `__post_init__` + entrée + import), `core/app/pipelines/runtime.py:743-760,820-830,895-905,1308-1318`
- Test: `core/tests/test_pipeline_http_call_runtime.py` (nouveau), `core/tests/test_pipeline_ops_contracts.py`, `core/tests/test_pipeline_ops_schemas.py:~125-170` (ensemble d'op), `core/tests/test_pipeline_routes.py:83` (ensemble d'op exposées)

**Interfaces:**
- Consumes: `TransformHttpCallParams` (Task 1) ; `validate_bounded_expr(conn, expr)` ; `build_guarded_session()` ; `quote_ident_duckdb`.
- Produces: `execute_http_call(conn, *, input_view: str, view_name: str, params: dict, secret_resolver=None, preview: bool=False) -> None` (matérialise la TEMP TABLE `view_name`) ; `OperationContract.needs_runtime_context: bool` ; helpers privés `_Outcome`, `_RowError`, `_run_with_retry(p, attempt) -> _Outcome`, `_classify(code, body, headers, *, follows_redirects) -> _Outcome`, `_build_request_parts(p, body_raw, mp_vals) -> tuple[dict, dict]` (stub ici, complété Task 4).

- [ ] **Step 1: Write the failing tests** (créer `core/tests/test_pipeline_http_call_runtime.py`)

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.pipelines import egress as pipelines_egress
from app.pipelines.http_call_runtime import execute_http_call


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    # Comme test_pipeline_connector_runtime.py : pytest-httpserver écoute sur 127.0.0.1, que la
    # vraie garde bloque ; la garde elle-même est testée dans test_http_call_real_egress_guard.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def run(conn, params, *, ids=(1, 2), resolver=None, preview=False, extra_cols=""):
    values = ", ".join(f"({i})" for i in ids)
    conn.execute(f"CREATE TEMP TABLE inp AS SELECT * FROM (VALUES {values}) t(id)")
    if extra_cols:
        conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS SELECT *, {extra_cols} FROM inp")
    execute_http_call(
        conn,
        input_view="inp",
        view_name="out",
        params=params,
        secret_resolver=resolver,
        preview=preview,
    )
    return conn.execute("SELECT * FROM out ORDER BY id").fetchall()


def test_get_one_call_per_row_preserves_input_columns(conn, httpserver):
    httpserver.expect_request("/items/1").respond_with_data("one")
    httpserver.expect_request("/items/2").respond_with_data("two")
    base = httpserver.url_for("/items/")
    rows = run(conn, {"urlExpr": f"'{base}' || id"})
    # colonnes : id, responseBody, httpStatusCode, httpStatus, httpError
    assert rows == [(1, "one", 200, "success", None), (2, "two", 200, "success", None)]


def test_4xx_is_an_error_row_not_a_failed_run(conn, httpserver):
    httpserver.expect_request("/ok").respond_with_data("fine")
    httpserver.expect_request("/missing").respond_with_data("nope", status=404)
    base = httpserver.url_for("/")
    rows = run(conn, {"urlExpr": f"'{base}' || CASE WHEN id = 1 THEN 'ok' ELSE 'missing' END"})
    assert rows[0][3] == "success"
    assert rows[1] == (2, "nope", 404, "error", "HTTP 404")


def test_output_column_collision_with_input_is_refused(conn):
    from app.pipelines.errors import PipelineRuntimeError

    with pytest.raises(PipelineRuntimeError, match="responseBody"):
        run(conn, {"urlExpr": "'http://x/'"}, extra_cols="'a' AS responseBody")


def test_unbounded_expression_is_refused(conn):
    from app.analytics.sql_sandbox import SqlSandboxError

    conn.execute("CREATE TABLE secret_t AS SELECT 1 AS v")
    with pytest.raises(SqlSandboxError):
        run(conn, {"urlExpr": "(SELECT v FROM secret_t)"})


def test_geometry_column_survives(conn, httpserver):
    conn.execute("INSTALL spatial; LOAD spatial;")
    httpserver.expect_request("/g").respond_with_data("x")
    conn.execute("CREATE TEMP TABLE inp AS SELECT 1 AS id, ST_Point(1, 2) AS geometry")
    execute_http_call(
        conn,
        input_view="inp",
        view_name="out",
        params={"urlExpr": f"'{httpserver.url_for('/g')}'"},
    )
    assert conn.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0] == "POINT (1 2)"
```

Ajouter à `core/tests/test_pipeline_ops_contracts.py` :

```python
def test_needs_runtime_context_requires_execute():
    with pytest.raises(ValueError, match="needs_runtime_context"):
        OperationContract(
            op="transform.fake-ctx",
            kind="transform",
            params_schema=TransformFilterParams,
            compile=lambda params, **kw: "SELECT 1",
            needs_runtime_context=True,
        )
```

Et un test de plomberie runtime dans `core/tests/test_pipeline_http_call_runtime.py` :

```python
def test_runtime_passes_context_only_to_ops_that_ask(monkeypatch, conn):
    from types import SimpleNamespace

    from app.configs.schemas import PipelineNode
    from app.pipelines import runtime
    from app.pipelines.ops import contracts

    seen = {}

    def fake_execute(c, *, input_view, view_name, params, secret_resolver=None, preview=False):
        seen.update(resolver=secret_resolver, preview=preview)
        c.execute(f'CREATE TEMP TABLE "{view_name}" AS SELECT * FROM "{input_view}"')

    fake = contracts.OperationContract(
        op="transform.fake-http",
        kind="transform",
        params_schema=contracts.TransformFilterParams,
        execute=fake_execute,
        needs_runtime_context=True,
    )
    monkeypatch.setitem(contracts.OPERATIONS, "transform.fake-http", fake)
    conn.execute("CREATE TEMP TABLE node_r AS SELECT 1 AS id")
    nodes = [
        PipelineNode(id="r", kind="reader", op="reader.collection", params={}),
        PipelineNode(id="t", kind="transform", op="transform.fake-http", params={}),
    ]
    edges = [SimpleNamespace(id="e", **{"from": "r"}, to="t")]
    marker = object()
    runtime._execute_transform_chain(
        conn, nodes, edges, {"r": "node_r"}, {"r": 4326}, {}, secret_resolver=marker, preview=True
    )
    assert seen == {"resolver": marker, "preview": True}
```

> Si `PipelineNode`/`edges` n'ont pas cette forme dans le dépôt (vérifier `app/configs/schemas.py` et `compiler.predecessor_id`), adapter le montage ; l'assertion finale est le contrat du test.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline_http_call_runtime.py tests/test_pipeline_ops_contracts.py -k "http or runtime_context or get_one or 4xx or collision or unbounded or geometry" -v`
Expected: FAIL (`ModuleNotFoundError: app.pipelines.http_call_runtime`).

- [ ] **Step 3: Implement `http_call_runtime.py`** (créer)

```python
# SPDX-License-Identifier: Apache-2.0
"""`transform.httpCall` (HTTPCaller FME) — un appel HTTP par ligne d'entrée.

Design docs/superpowers/specs/2026-09-21-transform-http-call-design.md. Matérialise `view_name`
(mécanisme `OperationContract.execute`, jamais `compiler.py`). Les expressions SQL bornées sont
évaluées UNE fois dans une table de staging (colonne `__rn`) ; les threads réseau ne touchent
jamais la connexion DuckDB ; les résultats sont rejoints sur `__rn`, donc les colonnes d'entrée
(géométrie comprise) ne repassent jamais par Python. Imports lourds (dlt, egress) différés
dans les fonctions : `contracts.py` importe ce module au chargement."""

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd
import requests

from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_S = 60.0
_PREVIEW_MAX_CALLS = 20
_ERR_BODY_CHARS = 2000
_INTERNAL = ("__rn", "__http_url", "__http_headers", "__http_body")


class _RowError(Exception):
    """Ligne inexploitable (non retentée) : devient `httpStatus="error"` sur cette ligne."""


@dataclass
class _Outcome:
    code: int | None = None
    body: str | None = None
    error: str | None = None
    retryable: bool = False
    retry_after: float | None = None
    skipped: bool = False

    @property
    def status(self) -> str:
        return "skipped" if self.skipped else ("error" if self.error else "success")


def _max_rows() -> int:
    from app.pipelines import connector_runtime as cr

    return cr._env_int("CORE_PIPELINES_HTTP_CALL_MAX_ROWS", 10_000)


def _parse_retry_after(raw: str | None) -> float | None:
    # ponytail: secondes seulement (pas la forme HTTP-date) ; ajouter si un service l'exige.
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except ValueError:
        return None


def _classify(code: int, body: str, headers, *, follows_redirects: bool) -> _Outcome:
    if code in _RETRYABLE_STATUS:
        return _Outcome(
            code,
            body,
            error=f"HTTP {code}",
            retryable=True,
            retry_after=_parse_retry_after(headers.get("Retry-After")),
        )
    if code >= 400:
        return _Outcome(code, body, error=f"HTTP {code}")
    if 300 <= code < 400 and not follows_redirects:
        return _Outcome(code, body, error="redirection non suivie")
    return _Outcome(code, body)


def _delay(p, attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, _MAX_RETRY_AFTER_S)
    return p.initialBackoffSeconds * (2**attempt)


def _run_with_retry(p, attempt: Callable[[], _Outcome]) -> _Outcome:
    """Une seule tentative pour l'instant (le retry arrive à la Task 3)."""
    from app.pipelines import connector_runtime as cr

    try:
        return attempt()
    except _RowError as exc:
        return _Outcome(error=str(exc))
    except Exception as exc:  # noqa: BLE001 — toute erreur réseau devient une erreur de ligne
        blocked = cr._find_egress_blocked_cause(exc)
        if blocked is not None:
            return _Outcome(error=f"egress refusé : {blocked}")
        return _Outcome(error=type(exc).__name__)


def _as_obj(raw, what: str) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise _RowError(f"{what} n'est pas du JSON valide") from exc
    if not isinstance(raw, dict):
        raise _RowError(f"{what} doit être un objet JSON")
    return raw


def _build_request_parts(p, body_raw, mp_vals) -> tuple[dict, dict]:
    """(en-têtes additionnels, kwargs `requests` du corps). Complété à la Task 4."""
    return {}, {}


def _send_direct(p, url, headers, kwargs, auth, *, follows_redirects: bool) -> _Outcome:
    from app.pipelines.egress import build_guarded_session

    cap = _max_response_bytes()
    with build_guarded_session() as session:
        resp = session.request(
            p.method,
            url,
            headers=headers or None,
            auth=auth,
            timeout=p.timeoutSeconds,
            stream=True,
            allow_redirects=follows_redirects,
            **kwargs,
        )
        try:
            raw = resp.raw.read(cap + 1, decode_content=True)
        finally:
            resp.close()
    if len(raw) > cap:
        return _Outcome(resp.status_code, None, error="réponse trop volumineuse")
    text = raw.decode(resp.encoding or "utf-8", errors="replace")
    return _classify(resp.status_code, text, resp.headers, follows_redirects=follows_redirects)


def _max_response_bytes() -> int:
    from app.pipelines import connector_runtime as cr

    return cr._env_int("CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES", 5 * 1024 * 1024)


class _RateLimiter:
    def __init__(self, rps: float | None) -> None:
        self._interval = 1.0 / rps if rps else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self._interval:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            time.sleep(slot - now)


def _make_row_caller(p, secret_resolver, preview: bool) -> Callable[[tuple], _Outcome]:
    def call(row: tuple) -> _Outcome:
        rn, url, headers_raw, body_raw, *mp_vals = row
        if preview and (p.method != "GET" or rn >= _PREVIEW_MAX_CALLS):
            return _Outcome(error="non exécuté en aperçu", skipped=True)
        if not url:
            return _Outcome(error="URL vide")

        def attempt() -> _Outcome:
            headers = {str(k): str(v) for k, v in _as_obj(headers_raw, "headersExpr").items()}
            extra_headers, kwargs = _build_request_parts(p, body_raw, mp_vals)
            return _send_direct(
                p, url, {**extra_headers, **headers}, kwargs, None, follows_redirects=True
            )

        return _run_with_retry(p, attempt)

    return call


def _stage(conn, p, input_view: str, stage: str) -> None:
    from app.pipelines.expr_validation import validate_bounded_expr

    exprs = {
        "__http_url": p.urlExpr,
        "__http_headers": p.headersExpr or "NULL",
        "__http_body": p.bodyExpr or "NULL",
    }
    for i, f in enumerate(p.multipartFields):
        exprs[f"__mp_{i}"] = f.valueExpr
    for expr in exprs.values():
        validate_bounded_expr(conn, expr)
    cols = ", ".join(f"({e}) AS {_qi(k)}" for k, e in exprs.items())
    conn.execute(
        f"CREATE TEMP TABLE {_qi(stage)} AS "
        f"SELECT (row_number() OVER ()) - 1 AS __rn, *, {cols} FROM {_qi(input_view)}"
    )


def execute_http_call(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
) -> None:
    from app.pipelines import connector_runtime as cr
    from app.pipelines.ops.schemas import TransformHttpCallParams

    p = TransformHttpCallParams.model_validate(params)
    stage = f"{view_name}__stage"
    _stage(conn, p, input_view, stage)

    out_cols = [p.responseColumn, p.statusCodeColumn, p.statusColumn, p.errorColumn]
    existing = {d[0] for d in conn.execute(f"DESCRIBE {_qi(stage)}").fetchall()}
    clash = sorted(set(out_cols) & existing)
    if clash:
        raise PipelineRuntimeError(
            f"transform.httpCall : colonne(s) de sortie déjà présente(s) en entrée : {clash}"
        )

    mp_cols = [f"__mp_{i}" for i in range(len(p.multipartFields))]
    select = ", ".join(_qi(c) for c in ["__rn", "__http_url", "__http_headers", "__http_body", *mp_cols])
    rows = conn.execute(f"SELECT {select} FROM {_qi(stage)} ORDER BY __rn").fetchall()
    if len(rows) > _max_rows():
        raise PipelineRuntimeError(
            f"transform.httpCall : {len(rows)} lignes, plafond de {_max_rows()} dépassé"
        )

    try:
        call = _make_row_caller(p, secret_resolver, preview)
    except cr.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    limiter = _RateLimiter(p.requestsPerSecond)

    def one(row: tuple) -> _Outcome:
        limiter.wait()
        return call(row)

    with ThreadPoolExecutor(max_workers=p.maxConcurrency) as pool:
        outcomes = list(pool.map(one, rows))

    df = pd.DataFrame(
        {
            "__rn": [r[0] for r in rows],
            "r": [o.body for o in outcomes],
            "c": pd.array([o.code for o in outcomes], dtype="Int64"),
            "s": [o.status for o in outcomes],
            "e": [o.error for o in outcomes],
        }
    )
    conn.register("_http_call_results", df)
    try:
        excl = ", ".join(_qi(c) for c in [*_INTERNAL, *mp_cols])
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT t.* EXCLUDE ({excl}), "
            f"CAST(r.r AS VARCHAR) AS {_qi(p.responseColumn)}, "
            f"CAST(r.c AS INTEGER) AS {_qi(p.statusCodeColumn)}, "
            f"CAST(r.s AS VARCHAR) AS {_qi(p.statusColumn)}, "
            f"CAST(r.e AS VARCHAR) AS {_qi(p.errorColumn)} "
            f"FROM {_qi(stage)} t JOIN _http_call_results r ON r.__rn = t.__rn ORDER BY t.__rn"
        )
    finally:
        conn.unregister("_http_call_results")
        conn.execute(f"DROP TABLE {_qi(stage)}")
```

- [ ] **Step 4: Contrat et runtime**

`contracts.py` — champ après `execute` :

```python
    # Task 2 httpCall : quand True (et seulement avec `execute`), runtime.py passe en plus
    # `secret_resolver=` et `preview=` à `execute`. Les autres op `execute` gardent leur
    # signature (conn, *, input_view, view_name, params).
    needs_runtime_context: bool = False
```

`__post_init__` :

```python
        if self.needs_runtime_context and self.execute is None:
            raise ValueError(f"'{self.op}': needs_runtime_context exige execute")
```

Import (parmi les imports du haut) `from app.pipelines import http_call_runtime as _http_call`, import `TransformHttpCallParams` dans la liste de `from app.pipelines.ops.schemas import (…)`, et entrée à la fin de `OPERATIONS` (avant l'accolade fermante) :

```python
    "transform.httpCall": OperationContract(
        op="transform.httpCall",
        kind="transform",
        params_schema=TransformHttpCallParams,
        engine="python",
        engine_license="Apache-2.0 (requests) + Apache-2.0 (dlt, pagination)",
        execute=_http_call.execute_http_call,
        needs_runtime_context=True,
    ),
```

`runtime.py` — signature de `_execute_transform_chain` : ajouter `secret_resolver=None, preview: bool = False,` aux kwargs ; dispatch :

```python
            if contract.execute is not None:
                extra = (
                    {"secret_resolver": secret_resolver, "preview": preview}
                    if contract.needs_runtime_context
                    else {}
                )
                contract.execute(
                    conn,
                    input_view=input_view,
                    view_name=view_name,
                    params=node.params,
                    **extra,
                )
```

Dans `preview_pipeline` (appel ~l.897) ajouter `secret_resolver=_chain_resolver(session, tenant_id, user), preview=True,` ; dans `run_pipeline` (~l.1310) ajouter `secret_resolver=_chain_resolver(session, tenant_id, user),`. Helper (près de `_execute_transform_chain`) :

```python
def _chain_resolver(session, tenant_id: str, user):
    """Résolveur de secrets pour les op `execute` à contexte (transform.httpCall) ; None sans
    session (tests, contextes sans base) — l'op échoue alors proprement si elle exige un secret."""
    if session is None:
        return None
    return connector_runtime.PostgresSecretResolver(session, tenant_id, user)
```

`cr._resolve_secret` fait `assert resolver is not None` quand `secretName` est renseigné : dans `_make_row_caller`, convertir en erreur propre (Task 6).

- [ ] **Step 5: Mettre à jour les tests de compte/d'ensemble**

- `tests/test_pipeline_ops_contracts.py:168` : `assert len(OPERATIONS) == 61` et renommer `test_operations_registry_has_61_entries`.
- `tests/test_pipeline_ops_schemas.py` (ensemble `set(OP_PARAMS)` ~l.125-170) et `tests/test_pipeline_routes.py:83` (ensemble `set(body)`) : ajouter `"transform.httpCall"` ; mettre à jour le commentaire de compte (« 58 exposées »). Vérifier le compte réel : `uv run python -c "from app.pipelines.ops.contracts import OPERATIONS, ops_catalog; print(len(OPERATIONS), len(ops_catalog()))"` (attendu 61 et 59 si `writer.file`/`reader.file` sont masqués par flag).
- Ajouter à `test_pipeline_ops_contracts.py` : `test_every_registered_transform_has_exactly_one_of_compile_or_execute` existe déjà et couvre httpCall (execute seul).

- [ ] **Step 6: Run**

Run: `uv run pytest tests/test_pipeline_http_call_runtime.py tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py tests/test_pipeline_routes.py -v`
Expected: PASS. Falsifier : retirer temporairement `ORDER BY t.__rn` n'est pas détectable ; falsifier à la place la collision (supprimer le contrôle `clash`) → `test_output_column_collision…` doit échouer.

- [ ] **Step 7: Qualité + commit**

```bash
uv run ruff check . && uv run ruff format . && uv run lint-imports
git add core/app/pipelines core/tests
git commit -m "feat(core): transform.httpCall — plomberie execute+contexte, appel GET par ligne"
```

---

### Task 3: Retry exponentiel et `Retry-After`

**Files:**
- Modify: `core/app/pipelines/http_call_runtime.py` (`_run_with_retry`)
- Test: `core/tests/test_pipeline_http_call_runtime.py`

**Interfaces:**
- Consumes: `_Outcome`, `_classify`, `_delay`, `_RowError` (Task 2).
- Produces: `_run_with_retry(p, attempt)` retentant sur `requests.ConnectionError`/`Timeout` et sur `_Outcome.retryable`.

- [ ] **Step 1: Write the failing tests** (ajouter au fichier de test)

```python
import threading
import time

from werkzeug.wrappers import Response


def _recording_handler(statuses, stamps, headers=None):
    it = iter(statuses)
    lock = threading.Lock()

    def handler(request):
        with lock:
            stamps.append(time.monotonic())
            code = next(it, statuses[-1])
        return Response("body", status=code, headers=headers or {})

    return handler


def test_retry_503_then_200_waits_for_exponential_backoff(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/r").respond_with_handler(_recording_handler([503, 503, 200], stamps))
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/r')}'", "initialBackoffSeconds": 0.2, "maxRetries": 3},
        ids=(1,),
    )
    assert rows[0][2:] == (200, "success", None)
    assert len(stamps) == 3
    # attente 0.2 puis 0.4 s : on mesure les intervalles réels, pas la durée totale
    assert stamps[1] - stamps[0] >= 0.2
    assert stamps[2] - stamps[1] >= 0.4


def test_retry_after_header_overrides_backoff(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/r").respond_with_handler(
        _recording_handler([429, 200], stamps, headers={"Retry-After": "1"})
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/r')}'", "initialBackoffSeconds": 0.0},
        ids=(1,),
    )
    assert rows[0][4:] == ("success", None)
    assert stamps[1] - stamps[0] >= 1.0


def test_retries_exhausted_keeps_last_status_and_only_that_row_fails(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/bad").respond_with_handler(_recording_handler([500], stamps))
    httpserver.expect_request("/good").respond_with_data("ok")
    base = httpserver.url_for("/")
    rows = run(
        conn,
        {
            "urlExpr": f"'{base}' || CASE WHEN id = 1 THEN 'bad' ELSE 'good' END",
            "maxRetries": 2,
            "initialBackoffSeconds": 0.0,
        },
    )
    assert rows[0][2:] == (500, "error", "HTTP 500")
    assert rows[1][3] == "success"
    assert len(stamps) == 3  # 1 + 2 retries


def test_connection_error_is_retried_then_reported(conn):
    rows = run(
        conn,
        {"urlExpr": "'http://127.0.0.1:1/'", "maxRetries": 1, "initialBackoffSeconds": 0.0},
        ids=(1,),
    )
    assert rows[0][3:] == ("error", "ConnectionError")


def test_4xx_is_not_retried(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/n").respond_with_handler(_recording_handler([404], stamps))
    run(conn, {"urlExpr": f"'{httpserver.url_for('/n')}'"}, ids=(1,))
    assert len(stamps) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pipeline_http_call_runtime.py -k "retry or retries or connection_error or 4xx_is_not" -v` → FAIL (un seul essai).

- [ ] **Step 3: Implement** — remplacer `_run_with_retry` :

```python
def _run_with_retry(p, attempt: Callable[[], _Outcome]) -> _Outcome:
    """Retry maison (pas urllib3.Retry : backoff urllib3 2.x sans délai avant le 1er retry) ;
    la garde d'egress s'applique ainsi à chaque tentative. Retry sur délai/connexion et sur
    429/5xx ; délai = `Retry-After` (plafonné) sinon `initialBackoffSeconds * 2**n`."""
    from app.pipelines import connector_runtime as cr

    for n in range(p.maxRetries + 1):
        try:
            out = attempt()
        except _RowError as exc:
            return _Outcome(error=str(exc))
        except requests.HTTPError as exc:  # chemin paginé : dlt lève sur >= 400 (Task 5)
            resp = exc.response
            if resp is None:
                return _Outcome(error="HTTPError")
            out = _classify(
                resp.status_code, resp.text[:_ERR_BODY_CHARS], resp.headers, follows_redirects=True
            )
        except Exception as exc:  # noqa: BLE001 — toute erreur réseau devient une erreur de ligne
            blocked = cr._find_egress_blocked_cause(exc)
            if blocked is not None:
                return _Outcome(error=f"egress refusé : {blocked}")
            if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
                out = _Outcome(error=type(exc).__name__, retryable=True)
            else:
                return _Outcome(error=type(exc).__name__)
        if not out.retryable or n == p.maxRetries:
            return out
        time.sleep(_delay(p, n, out.retry_after))
    raise AssertionError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: Run** `uv run pytest tests/test_pipeline_http_call_runtime.py -v` → PASS. Falsification : mettre `time.sleep(0)` → les 2 premiers tests échouent ; remettre.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/http_call_runtime.py core/tests/test_pipeline_http_call_runtime.py
git commit -m "feat(core): transform.httpCall — retry exponentiel et Retry-After"
```

---

### Task 4: Types de corps (`json`/`form`/`raw`/`multipart`) et en-têtes

**Files:**
- Modify: `core/app/pipelines/http_call_runtime.py` (`_build_request_parts`)
- Test: `core/tests/test_pipeline_http_call_runtime.py`

**Interfaces:**
- Consumes: `_as_obj`, `_RowError`, `_make_row_caller` passe déjà `mp_vals` (valeurs `__mp_i` dans l'ordre de `p.multipartFields`).
- Produces: `_build_request_parts(p, body_raw, mp_vals) -> (extra_headers: dict[str,str], kwargs: dict)`.

- [ ] **Step 1: Write the failing tests**

```python
import json as _json


def _capture(httpserver, path="/c"):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["ctype"] = request.headers.get("Content-Type", "")
        seen["auth"] = request.headers.get("X-Test")
        seen["data"] = request.get_data()
        return Response("ok")

    httpserver.expect_request(path).respond_with_handler(handler)
    return seen


def test_json_body_and_headers(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "json",
            "bodyExpr": "json_object('id', id)",
            "headersExpr": "json_object('X-Test', 'v')",
        },
        ids=(7,),
    )
    assert seen["method"] == "POST"
    assert seen["ctype"].startswith("application/json")
    assert seen["auth"] == "v"
    assert _json.loads(seen["data"]) == {"id": 7}


def test_form_body(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "form",
            "bodyExpr": "json_object('a', 'x y', 'n', id)",
        },
        ids=(3,),
    )
    assert seen["ctype"].startswith("application/x-www-form-urlencoded")
    assert seen["data"] in (b"a=x+y&n=3", b"n=3&a=x+y")


def test_raw_body(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "PUT",
            "bodyType": "raw",
            "bodyExpr": "'hello ' || id",
        },
        ids=(1,),
    )
    assert seen["data"] == b"hello 1"


def test_multipart_with_file_from_blob_column(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "multipart",
            "multipartFields": [
                {"name": "title", "valueExpr": "'doc-' || id"},
                {
                    "name": "file",
                    "valueExpr": "CAST('PAYLOAD' AS BLOB)",
                    "isFile": True,
                    "filename": "a.bin",
                    "contentType": "application/octet-stream",
                },
            ],
        },
        ids=(1,),
    )
    assert seen["ctype"].startswith("multipart/form-data")
    assert b'name="title"' in seen["data"] and b"doc-1" in seen["data"]
    assert b'filename="a.bin"' in seen["data"] and b"PAYLOAD" in seen["data"]


def test_invalid_headers_json_is_a_row_error(conn, httpserver):
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/c')}'", "headersExpr": "'not json'"},
        ids=(1,),
    )
    assert rows[0][3:] == ("error", "headersExpr n'est pas du JSON valide")
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_pipeline_http_call_runtime.py -k "body or multipart or headers" -v` → FAIL.

- [ ] **Step 3: Implement** — remplacer `_build_request_parts` :

```python
def _as_bytes(v) -> bytes:
    return bytes(v) if isinstance(v, (bytes, bytearray, memoryview)) else str(v).encode()


def _build_request_parts(p, body_raw, mp_vals) -> tuple[dict, dict]:
    """(en-têtes additionnels, kwargs `requests` du corps). Lève `_RowError` si la valeur de
    la ligne ne convient pas au `bodyType`."""
    if p.bodyType == "none":
        return {}, {}
    if p.bodyType == "json":
        if body_raw is None:
            return {}, {}
        text = body_raw if isinstance(body_raw, str) else json.dumps(body_raw)
        return {"Content-Type": "application/json"}, {"data": text.encode()}
    if p.bodyType == "form":
        return {}, {"data": {k: str(v) for k, v in _as_obj(body_raw, "bodyExpr").items()}}
    if p.bodyType == "raw":
        return {}, {"data": b"" if body_raw is None else _as_bytes(body_raw)}
    data: dict[str, str] = {}
    files: dict[str, tuple] = {}
    for field, val in zip(p.multipartFields, mp_vals, strict=True):
        if val is None:
            continue
        if field.isFile:
            files[field.name] = (
                field.filename or field.name,
                _as_bytes(val),
                field.contentType or "application/octet-stream",
            )
        else:
            data[field.name] = str(val)
    return {}, {"data": data, "files": files}
```

Note : les en-têtes de `headersExpr` priment sur `extra_headers` (déjà `{**extra_headers, **headers}` en Task 2). Un `Content-Type` posé à la main avec `multipart` casserait la frontière : documenter dans la docstring du schéma uniquement si observé.

- [ ] **Step 4: Run** `uv run pytest tests/test_pipeline_http_call_runtime.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/http_call_runtime.py core/tests/test_pipeline_http_call_runtime.py
git commit -m "feat(core): transform.httpCall — corps json/form/raw/multipart et en-têtes"
```

---

### Task 5: Pagination agrégée en une ligne

**Files:**
- Modify: `core/app/pipelines/http_call_runtime.py` (`_make_row_caller`, nouvelle `_send_paginated`)
- Test: `core/tests/test_pipeline_http_call_runtime.py`

**Interfaces:**
- Consumes: `cr._build_paginator(paginator, config)`, `cr._max_pages()`, `cr._max_rows()` (plafonds existants du connecteur REST), `RESTClient`.
- Produces: `_send_paginated(p, url, headers, kwargs, auth, *, follows_redirects) -> _Outcome` (corps = `json.dumps(toutes les pages concaténées)`).

- [ ] **Step 1: Write the failing tests**

```python
def test_page_number_pagination_is_aggregated_into_one_cell(conn, httpserver):
    pages = {"1": [{"v": 1}, {"v": 2}], "2": [{"v": 3}], "3": []}

    def handler(request):
        return Response(
            _json.dumps(pages[request.args.get("page", "1")]), content_type="application/json"
        )

    httpserver.expect_request("/p").respond_with_handler(handler)
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/p')}'", "paginator": "page_number"},
        ids=(1,),
    )
    assert _json.loads(rows[0][1]) == [{"v": 1}, {"v": 2}, {"v": 3}]
    assert rows[0][3] == "success"


def test_pagination_records_path(conn, httpserver):
    httpserver.expect_request("/p").respond_with_json({"data": {"items": [{"v": 1}]}})
    rows = run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/p')}'",
            "paginator": "page_number",
            "paginatorConfig": {"maximumPage": 1},
            "recordsPath": "data.items",
        },
        ids=(1,),
    )
    assert _json.loads(rows[0][1]) == [{"v": 1}]


def test_paginated_5xx_retries_whole_pagination(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/p").respond_with_handler(_recording_handler([503], stamps))
    rows = run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/p')}'",
            "paginator": "page_number",
            "maxRetries": 1,
            "initialBackoffSeconds": 0.0,
        },
        ids=(1,),
    )
    assert rows[0][2:5] == (503, "error", "HTTP 503")
    assert len(stamps) == 2
```

- [ ] **Step 2: Run to verify failure** — `-k pagination or paginated` → FAIL (la pagination est ignorée : une seule page brute).

- [ ] **Step 3: Implement** — ajouter :

```python
def _send_paginated(p, url, headers, kwargs, auth, *, follows_redirects: bool) -> _Outcome:
    """Pages agrégées en une liste JSON. `RESTClient(base_url="")` accepte une URL absolue en
    `path` (dlt `join_url`). Une erreur HTTP lève `requests.HTTPError` (traité par
    `_run_with_retry`, qui rejoue toute la pagination — ponytail : reprise depuis la page 1)."""
    from dlt.sources.helpers.rest_client import RESTClient

    from app.pipelines import connector_runtime as cr
    from app.pipelines.egress import build_guarded_session

    client = RESTClient(
        base_url="",
        auth=auth,
        paginator=cr._build_paginator(p.paginator, p.paginatorConfig),
        data_selector=p.recordsPath,
        session=build_guarded_session(),
    )
    records: list = []
    for page_no, page in enumerate(
        client.paginate(
            url,
            method=p.method,
            headers=headers or None,
            timeout=p.timeoutSeconds,
            allow_redirects=follows_redirects,
            **kwargs,
        ),
        1,
    ):
        if page_no > cr._max_pages():
            return _Outcome(error=f"plafond de {cr._max_pages()} pages dépassé")
        records.extend(page)
        if len(records) > cr._max_rows():
            return _Outcome(error=f"plafond de {cr._max_rows()} enregistrements dépassé")
    body = json.dumps(records, default=str)
    if len(body.encode()) > _max_response_bytes():
        return _Outcome(error="réponse trop volumineuse")
    return _Outcome(200, body)
```

Dans `attempt()` de `_make_row_caller`, remplacer l'appel `_send_direct(...)` par :

```python
            send = _send_direct if p.paginator == "none" else _send_paginated
            return send(p, url, {**extra_headers, **headers}, kwargs, None, follows_redirects=True)
```

Note : `kwargs` de `_build_request_parts` contient `data=`/`files=` (jamais `files` en pagination, interdit par le schéma) ; `RESTClient.paginate` accepte `data=`. `httpStatusCode` d'une réponse paginée en succès = 200 (code de la dernière page non conservé : documenter en docstring du schéma si besoin).

- [ ] **Step 4: Run** → PASS. Si `paginate(... timeout=...)` est refusé par la version de dlt installée, vérifier `inspect.signature(RESTClient.paginate)` (kwargs → `requests`), c'est le comportement attendu d'après la docstring de la version courante.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/http_call_runtime.py core/tests/test_pipeline_http_call_runtime.py
git commit -m "feat(core): transform.httpCall — pagination agrégée en une ligne"
```

---

### Task 6: Auth par secret, portée REV-294, redirections

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py` (extraire `_url_within_scope`), `core/app/pipelines/http_call_runtime.py` (`_make_row_caller`)
- Test: `core/tests/test_pipeline_http_call_runtime.py` ; non-régression : `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `cr._resolve_secret(resolver, name)`, `cr._build_auth(payload)`, `cr.ConnectorRuntimeError`.
- Produces: `connector_runtime._url_within_scope(scope: str, url: str) -> bool` (frontière de segment, même schéma/hôte/port, sans identifiants, pas de `..`).

- [ ] **Step 1: Write the failing tests**

```python
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import connector_runtime
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture()
def resolver_factory(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session = make_session_factory(engine)()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="u1", username="u1", email=None,
        first_name="", last_name="",
    )

    def make(name, kind, payload):
        ct, nonce = encrypt(payload)
        secrets_repo.create_secret(
            session, tenant_id=tenant.id, created_by=user.id, name=name, kind=kind,
            ciphertext=ct, nonce=nonce,
        )
        return connector_runtime.PostgresSecretResolver(session, tenant.id, user)

    yield make
    session.close()
    engine.dispose()


def test_bearer_secret_is_sent_and_never_leaks_into_the_error_column(
    conn, httpserver, resolver_factory
):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return Response("denied", status=403)

    httpserver.expect_request("/s").respond_with_handler(handler)
    base = httpserver.url_for("/")
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "SECRET-TOKEN", "baseUrl": base}
    )
    rows = run(
        conn,
        {"urlExpr": f"'{base}s'", "secretName": "tok", "maxRetries": 0},
        ids=(1,),
        resolver=resolver,
    )
    assert seen["auth"] == "Bearer SECRET-TOKEN"
    assert "SECRET-TOKEN" not in repr(rows)


def test_url_outside_secret_scope_makes_no_request(conn, httpserver, resolver_factory):
    hits = []
    httpserver.expect_request("/o").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    resolver = resolver_factory(
        "tok",
        "bearer_token",
        {"kind": "bearer_token", "token": "T", "baseUrl": "https://api.allowed.example/v1"},
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/o')}'", "secretName": "tok"},
        ids=(1,),
        resolver=resolver,
    )
    assert hits == []
    assert rows[0][3:] == ("error", "URL hors de la portée du secret")


def test_secret_without_base_url_fails_the_node(conn, resolver_factory):
    from app.pipelines.errors import PipelineRuntimeError

    resolver = resolver_factory("tok", "bearer_token", {"kind": "bearer_token", "token": "T"})
    with pytest.raises(PipelineRuntimeError, match="baseUrl"):
        run(conn, {"urlExpr": "'http://x/'", "secretName": "tok"}, ids=(1,), resolver=resolver)


def test_secret_name_without_resolver_fails_cleanly(conn):
    from app.pipelines.errors import PipelineRuntimeError

    with pytest.raises(PipelineRuntimeError, match="secret"):
        run(conn, {"urlExpr": "'http://x/'", "secretName": "tok"}, ids=(1,), resolver=None)


def test_redirects_are_not_followed_when_a_secret_is_bound(conn, httpserver, resolver_factory):
    base = httpserver.url_for("/")
    httpserver.expect_request("/r").respond_with_data("", status=302, headers={"Location": base + "t"})
    httpserver.expect_request("/t").respond_with_data("target")
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "T", "baseUrl": base}
    )
    rows = run(conn, {"urlExpr": f"'{base}r'", "secretName": "tok"}, ids=(1,), resolver=resolver)
    assert rows[0][2:] == (302, "error", "redirection non suivie")


def test_http_call_real_egress_guard(conn, monkeypatch):
    # réactive la vraie garde : une cible loopback est refusée avant tout appel réseau
    monkeypatch.setattr(
        pipelines_egress, "assert_egress_allowed", _REAL_ASSERT_EGRESS_ALLOWED
    )
    rows = run(conn, {"urlExpr": "'http://127.0.0.1:9/'", "maxRetries": 0}, ids=(1,))
    assert rows[0][3] == "error" and rows[0][4].startswith("egress refusé")
```

Ajouter en haut du fichier de test (avant l'autouse) : `_REAL_ASSERT_EGRESS_ALLOWED = pipelines_egress.assert_egress_allowed`.

Si le payload du secret exige d'autres champs (vérifier `app/secrets/schemas.py`, `BearerTokenPayload`), ajuster le dict du test.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_pipeline_http_call_runtime.py -k "secret or redirect or egress" -v` → FAIL.

- [ ] **Step 3: Implement**

`connector_runtime.py` — extraire le prédicat de `_assert_url_within_secret_scope` (comportement inchangé) :

```python
def _url_within_scope(scope: str, url: str) -> bool:
    """Frontière de segment : même schéma/hôte/port, `url` sous le préfixe de chemin de
    `scope`, sans identifiants ni `..` (REV-294)."""
    s, t = urlsplit(scope), urlsplit(url)
    s_path = s.path.rstrip("/") + "/"
    t_path = t.path.rstrip("/") + "/"
    return (
        (s.scheme, (s.hostname or "").lower(), s.port)
        == (t.scheme, (t.hostname or "").lower(), t.port)
        and t.username is None
        and t_path.startswith(s_path)
        and ".." not in t.path.split("/")
    )
```

et dans `_assert_url_within_secret_scope` remplacer le bloc `s, t = …; within = (…)` par `within = _url_within_scope(scope, params.baseUrl)` (laisser le reste — vérification de `params.path` — intact).

`http_call_runtime.py` — remplacer `_make_row_caller` :

```python
def _make_row_caller(p, secret_resolver, preview: bool) -> Callable[[tuple], _Outcome]:
    from app.pipelines import connector_runtime as cr

    if p.secretName is not None and secret_resolver is None:
        raise cr.ConnectorRuntimeError(
            f"transform.httpCall : secret '{p.secretName}' indisponible (aucun résolveur de secrets)"
        )
    payload = cr._resolve_secret(secret_resolver, p.secretName)
    auth = cr._build_auth(payload)
    scope = payload.baseUrl if payload is not None else None
    if payload is not None and not scope:
        raise cr.ConnectorRuntimeError(
            "transform.httpCall : ce secret n'a pas de 'baseUrl' (exigé depuis REV-294) — "
            "éditez le secret pour y poser l'URL de base à laquelle il est lié"
        )
    follows_redirects = payload is None  # jamais de jeton/clé suivi vers une autre URL

    def call(row: tuple) -> _Outcome:
        rn, url, headers_raw, body_raw, *mp_vals = row
        if preview and (p.method != "GET" or rn >= _PREVIEW_MAX_CALLS):
            return _Outcome(error="non exécuté en aperçu", skipped=True)
        if not url:
            return _Outcome(error="URL vide")
        if scope is not None and not cr._url_within_scope(scope, url):
            return _Outcome(error="URL hors de la portée du secret")

        def attempt() -> _Outcome:
            headers = {str(k): str(v) for k, v in _as_obj(headers_raw, "headersExpr").items()}
            extra_headers, kwargs = _build_request_parts(p, body_raw, mp_vals)
            send = _send_direct if p.paginator == "none" else _send_paginated
            return send(
                p, url, {**extra_headers, **headers}, kwargs, auth, follows_redirects=follows_redirects
            )

        return _run_with_retry(p, attempt)

    return call
```

Le `resolver.get` peut lever `KeyError` converti par `_resolve_secret` en `ConnectorRuntimeError("secret 'x' not found")` ; `execute_http_call` le convertit déjà en `PipelineRuntimeError`.

- [ ] **Step 4: Run** `uv run pytest tests/test_pipeline_http_call_runtime.py tests/test_pipeline_connector_runtime.py -v` → PASS (le second prouve la non-régression de l'extraction). Falsification : retirer le contrôle `scope` → `test_url_outside_secret_scope…` échoue ; remettre.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines core/tests
git commit -m "feat(core): transform.httpCall — auth par secret, portée REV-294, redirections non suivies"
```

---

### Task 7: Bornes (lignes, taille de réponse), concurrence, débit, aperçu

**Files:**
- Test: `core/tests/test_pipeline_http_call_runtime.py` (le code existe déjà depuis Task 2/6 : cette tâche le **prouve** et corrige ce qui échoue)
- Modify si un test échoue : `core/app/pipelines/http_call_runtime.py`

**Interfaces:**
- Consumes: `_RateLimiter`, `_max_rows`, `_max_response_bytes`, `_PREVIEW_MAX_CALLS`.

- [ ] **Step 1: Write the tests**

```python
def test_row_cap_fails_the_node_before_any_call(conn, monkeypatch, httpserver):
    from app.pipelines.errors import PipelineRuntimeError

    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_ROWS", "2")
    hits = []
    httpserver.expect_request("/x").respond_with_handler(lambda r: (hits.append(1), Response("x"))[1])
    with pytest.raises(PipelineRuntimeError, match="plafond"):
        run(conn, {"urlExpr": f"'{httpserver.url_for('/x')}'"}, ids=(1, 2, 3))
    assert hits == []


def test_response_size_cap_is_a_row_error(conn, monkeypatch, httpserver):
    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES", "10")
    httpserver.expect_request("/big").respond_with_data("x" * 100)
    rows = run(conn, {"urlExpr": f"'{httpserver.url_for('/big')}'"}, ids=(1,))
    assert rows[0][3:] == ("error", "réponse trop volumineuse")


def test_max_concurrency_is_respected_by_measuring_overlap(conn, httpserver):
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def handler(request):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.2)
        with lock:
            state["now"] -= 1
        return Response("ok")

    httpserver.expect_request("/slow").respond_with_handler(handler)
    run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/slow')}'", "maxConcurrency": 2},
        ids=tuple(range(6)),
    )
    assert state["max"] == 2  # plafond atteint ET jamais dépassé


def test_requests_per_second_spaces_calls(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/q").respond_with_handler(_recording_handler([200], stamps))
    run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/q')}'", "requestsPerSecond": 5, "maxConcurrency": 4},
        ids=(1, 2, 3),
    )
    stamps.sort()
    assert stamps[1] - stamps[0] >= 0.15 and stamps[2] - stamps[1] >= 0.15  # 1/5 s = 0.2


def test_preview_only_runs_get_and_skips_the_rest(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(lambda r: (hits.append(1), Response("x"))[1])
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/pv')}'", "method": "POST"},
        ids=(1, 2),
        preview=True,
    )
    assert hits == []
    assert rows[0][3:] == ("skipped", "non exécuté en aperçu")


def test_preview_limits_get_calls(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(lambda r: (hits.append(1), Response("x"))[1])
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/pv')}'"},
        ids=tuple(range(25)),
        preview=True,
    )
    assert len(hits) == 20
    assert [r[3] for r in rows].count("skipped") == 5
```

- [ ] **Step 2: Run** `uv run pytest tests/test_pipeline_http_call_runtime.py -v`. Attendu : PASS (code déjà en place). Si un test échoue, corriger `http_call_runtime.py` (ex. `_RateLimiter` : l'intervalle mesuré doit être ≥ 0.15 s). Falsifier la concurrence : passer `max_workers=p.maxConcurrency + 1` → `test_max_concurrency…` doit échouer ; remettre.

- [ ] **Step 3: Test E2E runtime via `run_pipeline`** (patron de `test_run_pipeline_transform_triangulate_end_to_end`, `tests/test_pipeline_runtime.py:470`) : ajouter un test `test_run_pipeline_transform_http_call_end_to_end` qui monte `reader.collection → transform.httpCall (GET sur httpserver, urlExpr "'<url>' || id", noeud params complets) → writer.export (csv)` avec `session=None`, `_FakeS3`, et le fixture/monkeypatch d'egress neutralisé (`monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)`), puis asserte que le CSV contient les colonnes `responseBody` et `httpStatus` et que `stats` contient `transform.httpCall`. Run : `uv run pytest tests/test_pipeline_runtime.py -k http_call -v` → PASS. (Le test prouve que le dispatch `needs_runtime_context` est atteint de bout en bout avec `session=None`.)

- [ ] **Step 4: Commit**

```bash
git add core/tests core/app/pipelines/http_call_runtime.py
git commit -m "test(core): transform.httpCall — bornes, concurrence, débit, aperçu, bout en bout"
```

---

### Task 8: Surfaces générées, matrice FME, doc, portes de qualité

**Files:**
- Modify: `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts` (régénérés), `docs/revue/matrice-couverture-fme.jsonl` (+ `.md` régénéré), `docs/superpowers/specs/2026-09-21-transform-http-call-design.md` (écarts), `CHANGELOG.md`, `CLAUDE.md` (une ligne `### Livré`), `docs/superpowers/2026-08-27-historique-execution-continu.md` (entrée détaillée), `.env.example` si les 2 variables d'env sont à documenter (voir Step 3)

- [ ] **Step 1: Régénérer OpenAPI + types TS** (piège n°1)

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat
```
Attendu : diff probablement **vide** (le catalogue `GET /pipelines/ops` renvoie un JSON libre, pas un schéma typé) ; sinon committer le diff. Vérifier que `shell/src/api/generated/core-schema.d.ts` ne change pas de façon inattendue.

- [ ] **Step 2: Matrice FME** — dans `docs/revue/matrice-couverture-fme.jsonl`, ligne `"fme_transformer": "HTTPCaller"` : `"geostudio_equivalent": "transform.httpCall"`, `"engine": "python"`, `"engine_license": "Apache-2.0 (requests) + Apache-2.0 (dlt)"`, `"coverage_status": "implemented"`, et réécrire `notes` (retry maison, pagination agrégée, multipart, secret lié à `baseUrl`, aperçu GET-seulement). Puis :

```bash
cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --write && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --check
```
Attendu : `--check` OK. Les lignes sœurs `SQLExecutor`/`Geocoder`/`PythonCaller` restent `planned_duckdb` (leurs `notes` mentionnent HTTPCaller « à venir » : les laisser, hors périmètre).

- [ ] **Step 3: Variables d'env et déployabilité** — `uv run pytest tests/test_deployability.py -v`. Si la règle « substitution documentée » (`test_every_compose_substitution_is_documented`) ne concerne que le compose, rien à faire : les 2 variables (`CORE_PIPELINES_HTTP_CALL_MAX_ROWS`, `CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES`) ont des défauts et ne sont pas câblées au compose (même statut que `CORE_PIPELINES_CONNECT_TIMEOUT_S`). Vérifier par `grep -rn CORE_PIPELINES_CONNECT_TIMEOUT_S .env.example ../docker-compose*.yml ../docs` et reproduire exactement son traitement (documenter dans le même fichier de référence s'il y en a un).

- [ ] **Step 4: Inventaire des fonctionnalités** — aucune route/outil MCP/route shell nouvelle : `uv run pytest tests/test_feature_inventory.py -v` doit rester vert ; ajouter l'op à une entrée d'inventaire seulement si le test l'exige (sinon, ne rien inventer). Puis régénérer le bilan : `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write` (exige les suites complètes ; si impossible faute de couverture locale, le dire dans l'historique plutôt que de committer un instantané incohérent).

- [ ] **Step 5: Spec — écarts** — dans la section « Révision 2026-10-11 » de la spec, remplacer `needs_secrets` par `needs_runtime_context` (porte aussi `preview`), et ajouter : mode aperçu (GET seulement, 20 premières lignes, statut `skipped`), `httpStatus` ∈ {success,error,skipped}, redirections non suivies avec secret, statut HTTP d'une réponse paginée = 200.

- [ ] **Step 6: Documentation de clôture** — `CHANGELOG.md` (section Added : `transform.httpCall`) ; une ligne dans `CLAUDE.md` `### Livré` :

```
- **`transform.httpCall` (HTTPCaller)** — appel HTTP par ligne (op `execute` à contexte : secrets + aperçu), retry exponentiel/`Retry-After`, pagination agrégée, multipart, concurrence+débit bornés, erreurs par ligne, URL de chaque ligne bornée à la portée du secret (REV-294) ; aperçu limité aux GET ; catalogue 59 op exposées / 61 brutes.
```
et l'entrée détaillée dans l'historique (déviation retry maison vs `urllib3.Retry`, trou REV-294 de la spec, mode aperçu, bornes, résultats des suites). Ajouter la mise à jour des lignes de CLAUDE.md qui citent « 58 exposées / 60 brutes » si présentes (`grep -n "60 brutes\|58 op" CLAUDE.md`).

- [ ] **Step 7: Portes de qualité complètes**

```bash
cd core
uv run ruff check . && uv run ruff format --check . && uv run lint-imports
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles app/net_pin.py
uv run pytest -q          # suite complète, CORE_TEST_DATABASE_URL vers postgis-test réel
cd ../shell && npm run test -- --run src/builder/pipeline   # le formulaire d'inspecteur lit le schéma : non-régression
cd .. && uvx pre-commit run --all-files
```
Attendu : tout vert (échecs intermittents documentés : `test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented` — rejouer en isolation avant de s'imputer une régression).

- [ ] **Step 8: Vérification manuelle du formulaire d'inspecteur** — ouvrir un pipeline dans le shell (stack dev ou `npm run e2e -- pipeline-builder`) et confirmer que `transform.httpCall` apparaît dans la palette et que `multipartFields`/`paginatorConfig` (tableau/objet) sont éditables par le rendu générique ; si le rendu générique est inutilisable pour ces deux champs, l'écrire dans l'historique comme suivi (pas de composant dédié dans ce plan).

- [ ] **Step 9: Commit**

```bash
git add -A docs core shell CHANGELOG.md CLAUDE.md
git commit -m "docs: clôture transform.httpCall (matrice FME, historique, Livré)"
```

---

## Self-Review

**Couverture de la spec révisée :** op + schéma (T1), `execute` à contexte + staging + colonnes de sortie + collision (T2), retry/`Retry-After`/échec par ligne (T3), `none/json/form/raw/multipart` + en-têtes (T4), pagination agrégée (T5), auth/portée REV-294/redirections/garde d'egress réelle/non-fuite du jeton (T6), plafonds/concurrence/débit/aperçu/E2E `run_pipeline` (T7), OpenAPI/matrice FME/`CLAUDE.md`/historique/portes (T8). Non couvert volontairement : lecture de fichier multipart depuis une URL (hors périmètre spec §2.2), cache entre runs, `onError` configurable.

**Cohérence des noms :** `execute_http_call`, `needs_runtime_context`, `_Outcome`, `_RowError`, `_run_with_retry`, `_classify`, `_build_request_parts`, `_send_direct`/`_send_paginated`, `_make_row_caller`, `_url_within_scope`, `_chain_resolver` — identiques de la T2 à la T7. `rn` = `__rn` (0-based) sert à la limite d'aperçu.

**Risques à vérifier en exécution (piège n°3, texte du plan = hypothèse) :** forme de `PipelineNode`/arêtes dans le test de plomberie (T2) ; champs requis du payload de secret `bearer_token` (T6) ; `RESTClient.paginate(..., timeout=…, allow_redirects=…)` accepté par la version de dlt installée (T5) ; `resp.raw.read(n, decode_content=True)` retourne bien `n` octets sauf EOF avec le `urllib3` installé (T2) ; compte réel exposé/brut (T2 Step 5).
