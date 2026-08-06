# SP-15f — `reader.connector` dlt (REST + Postgres) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new Pipeline reader ops — `reader.connector.rest` (paginated
REST APIs) and `reader.connector.postgres` (arbitrary read-only SQL against a
remote Postgres) — both authenticated via the SP-15e secrets store by
**name only**, each materializing into the same node-by-node `TEMP TABLE`
convention every other reader already uses.

**Architecture:** A real `dlt` pipeline (extraction, normalization, schema
inference — all handled by dlt) runs per node into a **scratch DuckDB file**
(`tempfile`, deleted after the run); the pipeline runtime `ATTACH`es that
file read-only into its own DuckDB connection and selects the single
`records` table into a `TEMP TABLE`, then detaches and deletes the scratch
file. Outbound HTTP for the REST connector goes through a **duplicated SSRF
guard** (a `requests.HTTPAdapter`, since dlt's REST client uses `requests`,
not the `httpx` the existing `app.harvest.egress` guard is built on, and
`app.pipelines` cannot import `app.harvest` per the layers contract). The
Postgres connector's free-text query is checked **SELECT-only** at run time
by reusing `app.analytics.sql_sandbox.parse_ast`/`validate_select_only`
(the same mechanism `app.pipelines.expr_validation` already uses for bounded
expressions). Secret resolution happens only at execution — never at save
time, matching every other bounded/collection check in this module.

**Tech Stack:** Python/FastAPI (`core/`), `dlt` (Apache-2.0, new dependency),
`requests` (new direct dependency — dlt's REST client transport), DuckDB
(`ATTACH`), SQLAlchemy (raw SQL against the secret's DSN), pytest,
`pytest-httpserver` (new dev dependency, REST connector tests).

## Global Constraints

- **Design doc**: `docs/superpowers/specs/2026-08-06-sp15f-reader-connector-dlt-design.md`
  — every task below implements a specific section of it; section refs are
  noted per task.
- **No canvas change, no new MCP tool** (design §1, §8). `explain_pipeline`
  and `GET /pipelines/ops` pick up the two new ops for free via the existing
  generic `ops_catalog()` — no route/MCP code changes anywhere in this plan.
- **No save-time secret/SQL validation** (design §6). `app.pipelines.config_validation`
  is **not modified** — its `for _op in OP_PARAMS: register_pipeline_node_validator(_op, _validate_node)`
  loop (already generic) picks up the two new ops automatically; since
  neither appears in `_COLLECTION_PARAM_FIELD`, only param **shape** is
  checked at save time, which is the intended behavior, not a gap. Task 5
  adds a regression test proving this, but touches no `config_validation.py`
  code.
- **No new compose service.** Unlike the SP-15d QGIS sidecar, `dlt` runs
  in-process in the existing `worker`/`core` image. `Dockerfile` already
  installs everything from `pyproject.toml`'s `[project.dependencies]`
  (`core/Dockerfile:15`, verified) — adding a dependency to `pyproject.toml`
  is the only deployment change needed anywhere in this plan; **do not touch
  `Dockerfile`**.
- **No import-linter `layers` list change.** `app.pipelines` importing
  `app.secrets` and `app.analytics` is **already legal** under the existing
  contract (`app.secrets` sits below `app.pipelines`; `app.analytics` isn't
  in the `layers` list at all, confirmed by reading `core/pyproject.toml`'s
  `[[tool.importlinter.contracts]]` block in design). Do not edit the
  `layers` list. Task 2 still must run `lint-imports` to prove the new
  `app.pipelines.egress` module (duplicated, zero internal deps) doesn't
  accidentally introduce a forbidden edge.
- **The SSRF guard duplication must wrap `requests`, not `httpx`** (design
  §5.1). dlt's `RESTClient` uses `requests` internally — copying
  `app.harvest.egress`'s `httpx`-transport shape verbatim would silently
  guard nothing. Task 2 builds a `requests.adapters.HTTPAdapter` subclass.
- **Telemetry off.** dlt has anonymous telemetry enabled by default
  (`RUNTIME__DLTHUB_TELEMETRY` env var, confirmed against current dlt docs).
  Task 3 sets `os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")`
  at the top of the new `connector_runtime.py`, **before** `import dlt` —
  a worker process must never phone home by a forgotten env var, same
  fail-safe-default posture as `CORE_SECRETS_MASTER_KEY`'s eager boot check
  (SP-15e).
- **Every dlt pipeline run gets its own scratch directory** (`tempfile.mkdtemp()`),
  covering both the destination DuckDB file **and** dlt's own
  `pipelines_dir` (dlt keeps working-directory state — schema, trace —
  separate from the destination file; leaving it at the default
  `~/.dlt/pipelines/<name>` would accumulate untracked state in the
  worker's home directory across every run, forever). Both are removed in a
  `finally: shutil.rmtree(scratch_dir, ignore_errors=True)` — same pattern
  as `runtime.py`'s existing QGIS scratch cleanup.
- **`_qi()` is duplicated a third time**, in the new `connector_runtime.py`
  — same deliberate-duplication convention `runtime.py`'s own header comment
  already documents for `compiler.py`'s copy (a 2-line helper, not worth an
  inter-module import of a `_`-prefixed name).
- **Errors**: the new `connector_runtime.py` module raises its own
  `ConnectorRuntimeError` (not `PipelineRuntimeError`) — `runtime.py`
  imports `connector_runtime`, so `connector_runtime` importing
  `PipelineRuntimeError` back from `runtime.py` would be circular.
  `runtime.py`'s `_prepare()` (Task 5) catches `ConnectorRuntimeError` and
  re-raises `PipelineRuntimeError(str(exc))` — exact same translation
  pattern already used there for `compiler.transform_output_srid`'s
  `ValueError`.
- **No audit_log entries for these ops.** Readers never write audit rows in
  this module today (`reader.collection` doesn't either) — consistent, not
  a gap.
- **Postgres connector's `secretName` is required, REST's is optional**
  (design §2) — `ReaderConnectorPostgresParams.secretName: str`,
  `ReaderConnectorRestParams.secretName: str | None = None`.
- **Egress allowlist env var is `CORE_PIPELINES_EGRESS_ALLOWLIST`**, a
  *separate* variable from `app.harvest`'s `CORE_HARVEST_EGRESS_ALLOWLIST` —
  consistent with duplicating the guard code itself rather than sharing
  state across the layer boundary; document this choice with a one-line
  comment at the constant, not left implicit.

---

## Task 1: Op catalog — `ReaderConnectorRestParams` / `ReaderConnectorPostgresParams`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Produces: `app.pipelines.ops.schemas.ReaderConnectorRestParams`,
  `ReaderConnectorPostgresParams` (Pydantic `BaseModel`s), plus two new
  entries each in `OP_KINDS`/`OP_PARAMS` keyed `"reader.connector.rest"` /
  `"reader.connector.postgres"`. Consumed by Task 5 (`runtime.py`'s
  `_prepare()` dispatch) and Task 3/4 (`connector_runtime.py` functions take
  an already-validated instance of these models as their `params` argument).

- [ ] **Step 1: Write the failing tests**

Modify `core/tests/test_pipeline_ops_schemas.py` — change
`test_all_fifteen_ops_are_registered` (this test asserts an **exact** set
equality; adding two ops without updating it would break it) to:

```python
def test_all_seventeen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "writer.dataset",
        "transform.qgis",
        "reader.connector.rest", "reader.connector.postgres",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)
```

Append at the end of the file:

```python
def test_reader_connector_ops_are_kind_reader():
    assert OP_KINDS["reader.connector.rest"] == "reader"
    assert OP_KINDS["reader.connector.postgres"] == "reader"


def test_reader_connector_rest_minimal_params():
    params = parse_op_params("reader.connector.rest", {"baseUrl": "https://api.example.com/"})
    assert params.path == ""
    assert params.method == "GET"
    assert params.query == {}
    assert params.headers == {}
    assert params.recordsPath is None
    assert params.paginator == "none"
    assert params.paginatorConfig == {}
    assert params.secretName is None


def test_reader_connector_rest_rejects_non_http_base_url():
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.rest", {"baseUrl": "ftp://example.com/"})


def test_reader_connector_rest_full_params():
    params = parse_op_params("reader.connector.rest", {
        "baseUrl": "https://api.example.com/",
        "path": "v1/items",
        "method": "POST",
        "query": {"limit": "100"},
        "headers": {"User-Agent": "geostudio"},
        "recordsPath": "data.items",
        "paginator": "page_number",
        "paginatorConfig": {"pageParam": "page"},
        "secretName": "my-api-key",
    })
    assert params.path == "v1/items"
    assert params.method == "POST"
    assert params.recordsPath == "data.items"
    assert params.paginator == "page_number"
    assert params.secretName == "my-api-key"


def test_reader_connector_rest_rejects_unknown_paginator():
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.rest", {
            "baseUrl": "https://api.example.com/", "paginator": "not-a-paginator",
        })


def test_reader_connector_postgres_requires_secret_name_and_query():
    params = parse_op_params(
        "reader.connector.postgres",
        {"secretName": "warehouse-pg", "query": "SELECT * FROM towns"},
    )
    assert params.secretName == "warehouse-pg"
    assert params.query == "SELECT * FROM towns"
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"query": "SELECT 1"})
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"secretName": "x"})


def test_reader_connector_ops_appear_in_catalog():
    catalog = ops_catalog()
    assert catalog["reader.connector.rest"]["kind"] == "reader"
    assert "baseUrl" in catalog["reader.connector.rest"]["paramsSchema"]["properties"]
    assert catalog["reader.connector.postgres"]["kind"] == "reader"
    assert "query" in catalog["reader.connector.postgres"]["paramsSchema"]["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `test_all_seventeen_ops_are_registered` and every new
`reader_connector` test fail (`KeyError`/`ValueError: unknown op`), since
neither model nor catalog entry exists yet.

- [ ] **Step 3: Implement the two param models**

Modify `core/app/pipelines/ops/schemas.py` — add after `TransformQgisParams`
(before `OP_KINDS`):

```python
class ReaderConnectorRestParams(BaseModel):
    """Lecture d'une ressource REST paginée (design SP-15f §2). `secretName`
    référence un secret api_key/bearer_token/basic_auth/
    oauth2_client_credentials (SP-15e) ; None = endpoint public non
    authentifié. `recordsPath` est un chemin pointé vers le tableau
    d'enregistrements dans le corps de réponse (ex. "data.items") ; None =
    le corps de réponse EST le tableau."""
    baseUrl: str = Field(..., pattern=r"^https?://")
    path: str = ""
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    recordsPath: str | None = None
    paginator: Literal["none", "page_number", "cursor", "offset"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)
    secretName: str | None = None


class ReaderConnectorPostgresParams(BaseModel):
    """Lecture d'une requête SQL libre sur un Postgres distant (design
    SP-15f §2). `secretName` référence toujours un secret postgres_dsn
    (SP-15e) — pas de notion de DSN non authentifié, contrairement à REST.
    `query` n'est validée SELECT-only qu'à l'exécution (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (design §6)."""
    secretName: str
    query: str
```

Then extend `OP_KINDS`/`OP_PARAMS`:

```python
OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "transform.buffer": "transform",
    "transform.reproject": "transform",
    "transform.intersection": "transform",
    "transform.countWithin": "transform",
    "transform.h3Aggregate": "transform",
    "transform.qgis": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
    "reader.connector.rest": "reader",
    "reader.connector.postgres": "reader",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "transform.buffer": TransformBufferParams,
    "transform.reproject": TransformReprojectParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.h3Aggregate": TransformH3AggregateParams,
    "transform.qgis": TransformQgisParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
    "reader.connector.rest": ReaderConnectorRestParams,
    "reader.connector.postgres": ReaderConnectorPostgresParams,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass (17 ops registered, catalog exposes both new ops).

- [ ] **Step 5: Run the full pipelines test suite to confirm no regression**

Run: `cd core && uv run pytest tests/test_pipeline_*.py tests/test_mcp_tools_pipeline.py -v`
Expected: all pass — pure catalog addition, no behavior change to existing ops.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): pipelines — reader.connector.rest/postgres op catalog entries"
```

---

## Task 2: SSRF egress guard for `app.pipelines` — `app/pipelines/egress.py`

**Files:**
- Create: `core/app/pipelines/egress.py`
- Modify: `core/pyproject.toml` (add `requests` dependency)
- Test: `core/tests/test_pipeline_egress.py`

**Interfaces:**
- Produces: `app.pipelines.egress.EgressBlockedError`,
  `assert_egress_allowed(url: str) -> None`,
  `build_guarded_session() -> requests.Session`. Consumed by Task 3
  (`connector_runtime.materialize_rest_connector` passes the guarded
  session to dlt's `RESTClient`).

- [ ] **Step 1: Add the `requests` dependency**

Modify `core/pyproject.toml` — in `dependencies = [...]`, add after
`"httpx>=0.27",`:

```toml
    "requests>=2.31",  # SP-15f : garde SSRF pour reader.connector.rest — dlt's
                       # RESTClient utilise `requests`, pas httpx (que le reste
                       # du dépôt utilise déjà) ; déclaré ici en dépendance
                       # directe plutôt que de compter sur la transitive de dlt.
```

Run: `cd core && uv sync`
Expected: resolves; `requests` becomes a direct dependency (it was almost
certainly already present transitively via other packages, but wasn't
importable as a guaranteed direct dependency before this).

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_pipeline_egress.py` (mirrors
`core/tests/test_harvest_egress.py` exactly, adapted from `httpx` to
`requests`):

```python
# SPDX-License-Identifier: Apache-2.0
import socket

import pytest
import requests

from app.pipelines.egress import (
    EgressBlockedError,
    assert_egress_allowed,
    build_guarded_session,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
        "http://[fc00::1]/x",
        "http://0.0.0.0/x",
    ],
)
def test_assert_blocks_internal_ip_literals_without_dns(url):
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_assert_allows_public_ip_literal():
    assert_egress_allowed("https://93.184.216.34/x") is None


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("ftp://example.com/x")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_allows_hostname_resolving_to_public(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert_egress_allowed("https://public.example.com/x") is None


def test_allowlist_restricts_otherwise_allowed_public_host(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x") is None


def test_guarded_session_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectionError.
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://127.0.0.1:9/x", timeout=1.0)


def test_guarded_session_is_a_real_requests_session():
    session = build_guarded_session()
    assert isinstance(session, requests.Session)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_egress.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.egress'`.

- [ ] **Step 4: Implement `egress.py`**

Create `core/app/pipelines/egress.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF pour reader.connector.rest (design SP-15f §5.1) —
duplication délibérée de app.harvest.egress : app.pipelines est positionné
SOUS app.harvest dans le contrat de couches import-linter
(core/pyproject.toml [[tool.importlinter.contracts]]), donc ne peut pas
l'importer. Point d'application différent de l'original : dlt.sources.rest_api
utilise `requests`, pas `httpx` — copier le transport httpx de
app.harvest.egress ne garderait rien en pratique."""
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Variable dédiée, distincte de CORE_HARVEST_EGRESS_ALLOWLIST (app.harvest) :
# même logique de duplication que la garde elle-même, plutôt que de partager
# un état de configuration à travers la frontière de couches.
_ALLOWLIST_ENV = "CORE_PIPELINES_EGRESS_ALLOWLIST"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_egress_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise EgressBlockedError(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise EgressBlockedError(f"hôte d'egress absent dans l'URL : {url!r}")

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise EgressBlockedError(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")

    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")


class _GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_egress.py -v`
Expected: 8 passed.

- [ ] **Step 6: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — `egress.py` imports nothing from
any other `app.*` module, so this only confirms nothing else broke.

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/egress.py core/pyproject.toml core/uv.lock core/tests/test_pipeline_egress.py
git commit -m "feat(core): pipelines — SSRF egress guard for reader.connector.rest"
```

---

## Task 3: REST connector materialization — `app/pipelines/connector_runtime.py` (part 1)

**Files:**
- Create: `core/app/pipelines/connector_runtime.py`
- Modify: `core/pyproject.toml` (add `dlt` dependency, `pytest-httpserver` dev dependency)
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `app.pipelines.egress.build_guarded_session` (Task 2),
  `app.pipelines.ops.schemas.ReaderConnectorRestParams` (Task 1),
  `app.secrets.repository.get_secret_payload`,
  `app.secrets.schemas.SecretPayload` (SP-15e).
- Produces: `app.pipelines.connector_runtime.ConnectorRuntimeError`,
  `materialize_rest_connector(conn, *, session, tenant_id, node_id, params, view_name) -> None`.
  Consumed by Task 5 (`runtime.py`'s `_prepare()`). Task 4 adds
  `materialize_postgres_connector` to this same file/module.

- [ ] **Step 1: Add the `dlt` and `pytest-httpserver` dependencies**

Modify `core/pyproject.toml` — in `dependencies = [...]`, add after the
`requests` entry from Task 2:

```toml
    "dlt>=1.6",  # SP-15f : reader.connector.rest/postgres — extraction,
                # normalisation, inférence de schéma (design §3.1) ; destination
                # duckdb, aucun extra requis (core/déjà présent).
```

In `[dependency-groups] dev = [...]`, add:

```toml
    "pytest-httpserver>=1.0",  # SP-15f : serveur HTTP local réel pour tester
                               # reader.connector.rest sans réseau (dlt utilise
                               # `requests`, pas httpx — un mock httpx type respx
                               # n'intercepterait rien).
```

Run: `cd core && uv sync`
Expected: resolves; `dlt` and `pytest-httpserver` installed.

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_pipeline_connector_runtime.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.pipelines import connector_runtime
from app.pipelines import egress as pipelines_egress
from app.pipelines.ops.schemas import ReaderConnectorRestParams
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    # Ces tests exercent le CONNECTEUR (dlt, pagination, injection d'auth),
    # pas la garde SSRF elle-même (déjà couverte isolément par
    # test_pipeline_egress.py) — le serveur pytest-httpserver écoute sur
    # 127.0.0.1, que la vraie garde bloquerait légitimement en tant que cible
    # loopback. Neutralisée ici pour isoler ce que ce fichier teste.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


def _create_secret(session, tenant, *, name, kind, payload):
    ciphertext, nonce = encrypt(payload)
    return secrets_repo.create_secret(
        session, tenant_id=tenant.id, created_by="u1", name=name, kind=kind,
        ciphertext=ciphertext, nonce=nonce,
    )


def test_materialize_rest_connector_unauthenticated_no_pagination(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r1", params=params, view_name="node_r1",
    )
    rows = conn.execute("SELECT id, name FROM node_r1 ORDER BY id").fetchall()
    assert rows == [(1, "a"), (2, "b")]


def test_materialize_rest_connector_extracts_records_path(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json(
        {"data": {"items": [{"id": 1, "name": "a"}]}}
    )
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", recordsPath="data.items",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r2", params=params, view_name="node_r2",
    )
    rows = conn.execute("SELECT id, name FROM node_r2").fetchall()
    assert rows == [(1, "a")]


def test_materialize_rest_connector_injects_bearer_token(conn, session, tenant, httpserver):
    _create_secret(session, tenant, name="my-bearer", kind="bearer_token",
                    payload={"kind": "bearer_token", "token": "s3cr3t-tok"})
    httpserver.expect_request(
        "/items", headers={"Authorization": "Bearer s3cr3t-tok"},
    ).respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-bearer",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r3", params=params, view_name="node_r3",
    )
    assert conn.execute("SELECT id FROM node_r3").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_api_key_query_param(conn, session, tenant, httpserver):
    _create_secret(session, tenant, name="my-key", kind="api_key",
                    payload={"kind": "api_key", "location": "query", "key": "token", "value": "abc123"})
    httpserver.expect_request("/items", query_string="token=abc123").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-key",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r4", params=params, view_name="node_r4",
    )
    assert conn.execute("SELECT id FROM node_r4").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_basic_auth(conn, session, tenant, httpserver):
    _create_secret(session, tenant, name="my-basic", kind="basic_auth",
                    payload={"kind": "basic_auth", "username": "u", "password": "p"})
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-basic",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r5", params=params, view_name="node_r5",
    )
    request = httpserver.log[0][0]
    assert request.headers["Authorization"].startswith("Basic ")


def test_materialize_rest_connector_paginates_page_number(conn, session, tenant, httpserver):
    httpserver.expect_request("/items", query_string="page=1").respond_with_json([{"id": 1}])
    httpserver.expect_request("/items", query_string="page=2").respond_with_json([{"id": 2}])
    httpserver.expect_request("/items", query_string="page=3").respond_with_json([])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", paginator="page_number",
        paginatorConfig={"pageParam": "page", "basePage": 1},
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r6", params=params, view_name="node_r6",
    )
    rows = conn.execute("SELECT id FROM node_r6 ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]


def test_materialize_rest_connector_wrong_secret_kind_raises(conn, session, tenant, httpserver):
    _create_secret(session, tenant, name="pg-secret", kind="postgres_dsn",
                    payload={"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"})
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="pg-secret",
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.rest"):
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r7", params=params, view_name="node_r7",
        )


def test_materialize_rest_connector_missing_secret_raises(conn, session, tenant, httpserver):
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="does-not-exist",
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r8", params=params, view_name="node_r8",
        )


def test_materialize_rest_connector_drops_dlt_plumbing_columns(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r9", params=params, view_name="node_r9",
    )
    cols = {d[0] for d in conn.execute("SELECT * FROM node_r9 LIMIT 0").description}
    assert "_dlt_id" not in cols
    assert "_dlt_load_id" not in cols
    assert cols == {"id", "name"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.connector_runtime'`.

- [ ] **Step 4: Implement `connector_runtime.py` (REST half)**

Create `core/app/pipelines/connector_runtime.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Matérialisation dlt des deux op reader.connector.* (design SP-15f §3) —
chaque appel exécute un vrai pipeline dlt vers un fichier DuckDB scratch
dédié, l'ATTACH en lecture seule dans la connexion du runtime, sélectionne
la table racine "records" en TEMP TABLE, puis nettoie (finally). Aucun état
dlt ne survit à un appel (destination ET pipelines_dir scratch, supprimés
ensemble)."""
import os

# Doit précéder `import dlt` : la télémétrie anonyme de dlt est activée par
# défaut (design SP-15f Global Constraints) — un worker ne doit jamais
# téléphoner à l'extérieur par variable d'environnement oubliée.
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")

import shutil
import tempfile
import uuid

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import (
    APIKeyAuth,
    BearerTokenAuth,
    HttpBasicAuth,
    OAuth2ClientCredentials,
)
from dlt.sources.helpers.rest_client.paginators import (
    JSONResponseCursorPaginator,
    OffsetPaginator,
    PageNumberPaginator,
)
from sqlalchemy.orm import Session

from app.pipelines.egress import build_guarded_session
from app.pipelines.ops.schemas import ReaderConnectorRestParams
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SecretPayload

_REST_SECRET_KINDS = {"api_key", "bearer_token", "basic_auth", "oauth2_client_credentials"}


def _qi(name: str) -> str:
    # Duplication délibérée (3e copie du dépôt) — cf. runtime.py, même
    # rationale : helper de 2 lignes, pas un import inter-module d'un nom
    # `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


class ConnectorRuntimeError(Exception):
    """Traduite en PipelineRuntimeError par runtime.py (Task 5) — définie
    ici plutôt qu'importée de runtime.py pour éviter un import circulaire
    (runtime.py importe ce module)."""


def _resolve_secret(session: Session, tenant_id: str, secret_name: str | None) -> SecretPayload | None:
    if secret_name is None:
        return None
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=secret_name)
    if payload is None:
        raise ConnectorRuntimeError(f"secret '{secret_name}' not found")
    return payload


def _build_auth(payload: SecretPayload | None):
    if payload is None:
        return None
    if payload.kind not in _REST_SECRET_KINDS:
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.rest "
            f"(expected one of {sorted(_REST_SECRET_KINDS)})"
        )
    if payload.kind == "bearer_token":
        return BearerTokenAuth(token=payload.token)
    if payload.kind == "api_key":
        return APIKeyAuth(name=payload.key, api_key=payload.value, location=payload.location)
    if payload.kind == "basic_auth":
        return HttpBasicAuth(payload.username, payload.password)
    return OAuth2ClientCredentials(
        access_token_url=payload.tokenUrl, client_id=payload.clientId, client_secret=payload.clientSecret,
    )


def _build_paginator(paginator: str, config: dict):
    if paginator == "none":
        return None
    if paginator == "page_number":
        return PageNumberPaginator(
            base_page=config.get("basePage", 1), page_param=config.get("pageParam", "page"),
            maximum_page=config.get("maximumPage"),
        )
    if paginator == "offset":
        return OffsetPaginator(
            limit=config["limit"], offset_param=config.get("offsetParam", "offset"),
            limit_param=config.get("limitParam", "limit"), total_path=config.get("totalPath"),
        )
    if paginator == "cursor":
        return JSONResponseCursorPaginator(
            cursor_path=config.get("cursorPath", "cursors.next"), cursor_param=config.get("cursorParam", "cursor"),
        )
    raise ConnectorRuntimeError(f"unknown paginator '{paginator}'")


def _run_dlt_and_attach(conn, resource, *, node_id: str, view_name: str) -> None:
    scratch_dir = tempfile.mkdtemp(prefix=f"sp15f-{node_id}-")
    db_path = f"{scratch_dir}/extract.duckdb"
    try:
        pipeline = dlt.pipeline(
            pipeline_name=f"sp15f-{node_id}-{uuid.uuid4().hex}",
            destination=dlt.destinations.duckdb(db_path),
            dataset_name="pipeline_dataset",
            pipelines_dir=f"{scratch_dir}/dlt-home",
        )
        pipeline.run(resource)
        conn.execute(f"ATTACH '{db_path}' AS dlt_extract (READ_ONLY)")
        try:
            cols = [
                d[0] for d in conn.execute(
                    "SELECT * FROM dlt_extract.pipeline_dataset.records LIMIT 0"
                ).description
                if d[0] not in {"_dlt_id", "_dlt_load_id"}
            ]
            select_list = ", ".join(_qi(c) for c in cols)
            conn.execute(
                f"CREATE TEMP TABLE {_qi(view_name)} AS "
                f"SELECT {select_list} FROM dlt_extract.pipeline_dataset.records"
            )
        finally:
            conn.execute("DETACH dlt_extract")
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def materialize_rest_connector(
    conn, *, session: Session, tenant_id: str, node_id: str,
    params: ReaderConnectorRestParams, view_name: str,
) -> None:
    payload = _resolve_secret(session, tenant_id, params.secretName)
    auth = _build_auth(payload)
    client = RESTClient(
        base_url=params.baseUrl, headers=params.headers or None, auth=auth,
        paginator=_build_paginator(params.paginator, params.paginatorConfig),
        data_selector=params.recordsPath, session=build_guarded_session(),
    )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        for page in client.paginate(params.path, method=params.method, params=params.query or None):
            yield page

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/connector_runtime.py core/pyproject.toml core/uv.lock \
  core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(core): pipelines — reader.connector.rest materialization (dlt REST client)"
```

---

## Task 4: Postgres connector materialization — `connector_runtime.py` (part 2)

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `app.analytics.sql_sandbox.parse_ast`, `validate_select_only`,
  `SqlSandboxError` (existing, already imported the same way by
  `app.pipelines.expr_validation`).
- Produces: `app.pipelines.connector_runtime.materialize_postgres_connector(conn, *, session, tenant_id, node_id, params, view_name) -> None`.
  Consumed by Task 5 (`runtime.py`'s `_prepare()`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_connector_runtime.py`:

```python
from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams


def _pg_dsn(pg_engine) -> str:
    # Même conversion que conftest.py::pg_engine_with_procrastinate_schema :
    # CORE_TEST_DATABASE_URL est au format SQLAlchemy "postgresql+psycopg://",
    # le DSN d'un secret postgres_dsn est un DSN "postgresql://" ordinaire
    # (format vérifié par SP-15e's test_secrets_repository.py).
    return str(pg_engine.url).replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
def pg_secret(session, tenant, pg_engine):
    return _create_secret(
        session, tenant, name="warehouse-pg", kind="postgres_dsn",
        payload={"kind": "postgres_dsn", "dsn": _pg_dsn(pg_engine)},
    )


def test_materialize_postgres_connector_round_trips_query(conn, session, tenant, pg_engine, pg_secret):
    from sqlalchemy import text

    with pg_engine.begin() as db_conn:
        db_conn.execute(text("CREATE TABLE IF NOT EXISTS sp15f_towns (id int, name text)"))
        db_conn.execute(text("DELETE FROM sp15f_towns"))
        db_conn.execute(text("INSERT INTO sp15f_towns (id, name) VALUES (1, 'Nord'), (2, 'Sud')"))

    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="SELECT id, name FROM sp15f_towns ORDER BY id")
    connector_runtime.materialize_postgres_connector(
        conn, session=session, tenant_id=tenant.id, node_id="p1", params=params, view_name="node_p1",
    )
    rows = conn.execute("SELECT id, name FROM node_p1 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]


def test_materialize_postgres_connector_rejects_non_select(conn, session, tenant, pg_secret):
    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="DELETE FROM sp15f_towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p2", params=params, view_name="node_p2",
        )


def test_materialize_postgres_connector_wrong_secret_kind_raises(conn, session, tenant):
    _create_secret(session, tenant, name="bearer-secret", kind="bearer_token",
                    payload={"kind": "bearer_token", "token": "tok"})
    params = ReaderConnectorPostgresParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.postgres"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p3", params=params, view_name="node_p3",
        )


def test_materialize_postgres_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorPostgresParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p4", params=params, view_name="node_p4",
        )
```

These four tests need `pg_engine` (from `core/tests/conftest.py`) — add the
fixture to the test function signatures above (already done); no new
fixtures beyond `_pg_dsn`/`pg_secret` need to be added to `conftest.py`
itself. Tests using `pg_engine` transitively skip with
`pytest.skip("CORE_TEST_DATABASE_URL non défini...")` when no test database
is configured, same as every other `postgis`-marked test in this repo — no
new pytest marker needed (`conftest.py`'s existing `pg_engine` fixture
already handles the skip).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k postgres -v`
Expected: FAIL — `AttributeError: module 'app.pipelines.connector_runtime' has no attribute 'materialize_postgres_connector'`.

- [ ] **Step 3: Implement `materialize_postgres_connector`**

Modify `core/app/pipelines/connector_runtime.py` — add to the imports:

```python
import sqlalchemy as sa

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams, ReaderConnectorRestParams
```

(replacing the single-line `from app.pipelines.ops.schemas import ReaderConnectorRestParams` from Task 3).

Append at the end of the file:

```python
def materialize_postgres_connector(
    conn, *, session: Session, tenant_id: str, node_id: str,
    params: ReaderConnectorPostgresParams, view_name: str,
) -> None:
    # Défense en profondeur heuristique, pas une garantie (design §5.2) :
    # `params.query` cible Postgres mais est parsée avec le dialecte SQL de
    # DuckDB (même mécanisme que app.pipelines.expr_validation, appliqué ici
    # à un texte SQL complet plutôt qu'à une expression bornée). Vérifié à
    # l'exécution uniquement, jamais à la sauvegarde du pipeline.
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.postgres query rejected: {exc}") from exc

    payload = _resolve_secret(session, tenant_id, params.secretName)
    if payload.kind != "postgres_dsn":
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.postgres "
            "(expected postgres_dsn)"
        )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `CORE_TEST_DATABASE_URL=<your test db url> cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v`
Expected: all pass (REST tests from Task 3 unaffected; Postgres tests pass
if `CORE_TEST_DATABASE_URL` is set, otherwise skip cleanly — both are
acceptable outcomes, matching this repo's existing `postgis`-gated tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/connector_runtime.py core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(core): pipelines — reader.connector.postgres materialization (SELECT-only guard)"
```

---

## Task 5: Wire into the runtime — `_prepare()` dispatch, end-to-end tests

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`
- Test: `core/tests/test_pipeline_config_validation.py` (one new regression test, no code change to `config_validation.py`)

**Interfaces:**
- Consumes: `app.pipelines.connector_runtime.materialize_rest_connector`,
  `materialize_postgres_connector`, `ConnectorRuntimeError` (Tasks 3/4);
  `ReaderConnectorRestParams`, `ReaderConnectorPostgresParams` (Task 1).
- Produces: no new public interface — `_prepare()`'s reader-materialization
  loop now dispatches on `node.op` instead of assuming `reader.collection`.
  This is the terminal task of the plan.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py`:

```python
def test_preview_reader_connector_rest_feeds_downstream_filter(tmp_path, monkeypatch, httpserver):
    from app.pipelines import egress as pipelines_egress
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    httpserver.expect_request("/items").respond_with_json(
        [{"id": 1, "pop": 10}, {"id": 2, "pop": 5}, {"id": 3, "pop": 20}]
    )
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.connector.rest",
         "params": {"baseUrl": httpserver.url_for("/"), "path": "items"}},
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "pop > 8"}},
        {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "out.csv"}},
    ]
    edges = [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": edges})

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {1, 3}  # pop=5 filtered out


def test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error(tmp_path):
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.connector.postgres",
         "params": {"secretName": "does-not-exist", "query": "SELECT 1"}},
    ]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": []})

    from app.db import init_db, make_engine, make_session_factory
    from app.tenants.repository import get_or_create_default_tenant
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        with pytest.raises(runtime.PipelineRuntimeError, match="not found"):
            runtime.preview_pipeline(
                session=session, payload=payload, tenant_id=tenant.id, user=None, up_to="r1",
                endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
                base_uri=str(tmp_path), limit=50,
            )


def test_run_pipeline_reader_connector_rest_never_leaks_secret_value(tmp_path, monkeypatch, httpserver):
    from app.pipelines import egress as pipelines_egress
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    from app.db import init_db, make_engine, make_session_factory
    from app.secrets import repository as secrets_repo
    from app.secrets.crypto import encrypt
    from app.tenants.repository import get_or_create_default_tenant

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
        tenant = get_or_create_default_tenant(session)
        ciphertext, nonce = encrypt({"kind": "bearer_token", "token": "s3cr3t-leak-check"})
        secrets_repo.create_secret(
            session, tenant_id=tenant.id, created_by="u1", name="my-bearer", kind="bearer_token",
            ciphertext=ciphertext, nonce=nonce,
        )
        session.commit()

        httpserver.expect_request(
            "/items", headers={"Authorization": "Bearer s3cr3t-leak-check"},
        ).respond_with_json([{"id": 1, "name": "a"}])
        payload_nodes = [
            {"id": "r1", "kind": "reader", "op": "reader.connector.rest",
             "params": {"baseUrl": httpserver.url_for("/"), "path": "items", "secretName": "my-bearer"}},
        ]
        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": []})

        rows = runtime.preview_pipeline(
            session=session, payload=payload, tenant_id=tenant.id, user=None, up_to="r1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path), limit=50,
        )
        assert "s3cr3t-leak-check" not in str(rows)
```

Append to `core/tests/test_pipeline_config_validation.py`:

```python
def test_reader_connector_node_saves_without_secret_or_query_check(env):
    # Design §6 : seule la FORME des params est vérifiée à la sauvegarde —
    # ni l'existence de "does-not-exist" comme secret, ni la validité SQL de
    # "not even sql" sont vérifiées ici (elles échoueraient proprement à
    # l'EXÉCUTION, cf. test_pipeline_runtime.py). Une sauvegarde réussie ici
    # n'est pas un bug.
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append({
        "id": "r2", "kind": "reader", "op": "reader.connector.postgres",
        "params": {"secretName": "does-not-exist", "query": "not even sql"},
    })
    response = env.post("/configs", json=body)
    assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k reader_connector -v`
Expected: FAIL — `pydantic.ValidationError`/`PipelineRuntimeError: unknown reader op 'reader.connector.rest'`
(the `_prepare()` loop still hard-codes `ReaderCollectionParams.model_validate(node.params)` for every reader node).

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -k reader_connector -v`
Expected: this one already passes (config_validation.py needs no change) —
confirms the "no code change needed" claim from Global Constraints instead
of silently assuming it.

- [ ] **Step 3: Wire the dispatch into `_prepare()`**

Modify `core/app/pipelines/runtime.py` — add to the imports, after the
existing `from app.pipelines.ops.schemas import (...)` block:

```python
from app.pipelines import connector_runtime
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, ReaderConnectorPostgresParams, ReaderConnectorRestParams,
    TransformAggregateParams, TransformCountWithinParams, TransformDeriveParams,
    TransformFilterParams, TransformH3AggregateParams, TransformIntersectionParams,
    TransformJoinParams, TransformQgisParams, WriterCollectionParams, WriterDatasetParams,
    WriterExportParams,
)
```

Replace the reader-materialization loop inside `_prepare()` (currently):

```python
    for node in ordered:
        if node.kind != "reader":
            continue
        p = ReaderCollectionParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        view_name = f"node_{node.id}"
        _materialize_reader(
            conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.collectionId, table_info=table_info,
        )
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = table_info.srid or 4326
```

with:

```python
    for node in ordered:
        if node.kind != "reader":
            continue
        view_name = f"node_{node.id}"
        if node.op == "reader.collection":
            p = ReaderCollectionParams.model_validate(node.params)
            table_name = _require_readable_collection_id(
                session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
            )
            table_info = _table_info_for_collection(session, table_name)
            _materialize_reader(
                conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
                collection_id=p.collectionId, table_info=table_info,
            )
            srid_by_node[node.id] = table_info.srid or 4326
        elif node.op == "reader.connector.rest":
            p = ReaderConnectorRestParams.model_validate(node.params)
            try:
                connector_runtime.materialize_rest_connector(
                    conn, session=session, tenant_id=tenant_id, node_id=node.id,
                    params=p, view_name=view_name,
                )
            except connector_runtime.ConnectorRuntimeError as exc:
                raise PipelineRuntimeError(str(exc)) from exc
            srid_by_node[node.id] = 4326
        elif node.op == "reader.connector.postgres":
            p = ReaderConnectorPostgresParams.model_validate(node.params)
            try:
                connector_runtime.materialize_postgres_connector(
                    conn, session=session, tenant_id=tenant_id, node_id=node.id,
                    params=p, view_name=view_name,
                )
            except connector_runtime.ConnectorRuntimeError as exc:
                raise PipelineRuntimeError(str(exc)) from exc
            srid_by_node[node.id] = 4326
        else:
            raise PipelineRuntimeError(f"unknown reader op '{node.op}'")
        view_by_node[node.id] = view_name
```

(`srid_by_node[node.id] = 4326` for both connector ops is a harmless
default — design §3.2/non-goals: connector output carries no geometry
column in v0, so this value is never actually consulted by a spatial
transform; a pipeline author who chains a spatial op directly after a
connector reader gets a clean DuckDB error about the missing geometry
column, not a wrong-SRID bug.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: all pass, including the 3 new `reader_connector` tests.

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: all pass.

- [ ] **Step 5: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — `runtime.py` now imports
`app.pipelines.connector_runtime` (same layer, always allowed) and
transitively `app.secrets`/`app.analytics` (already-legal directions,
confirmed in Global Constraints); `app.pipelines.egress` still imports
nothing from `app.harvest`.

- [ ] **Step 6: Run the full core test suite to confirm no regression**

Run: `cd core && uv run pytest -v`
Expected: all pre-existing tests still pass — this plan is additive only
(2 new op catalog entries, 1 new guard module, 1 new connector-runtime
module, 1 dispatch branch in an existing loop; no route, MCP tool, or
existing op's behavior changed).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py \
  core/tests/test_pipeline_config_validation.py
git commit -m "feat(core): pipelines — wire reader.connector.rest/postgres into runtime dispatch"
```
