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

