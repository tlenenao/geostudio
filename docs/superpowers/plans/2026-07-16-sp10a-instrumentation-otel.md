# SP-10a — Instrumentation OTel (cœur + worker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument `core`/`worker` with OpenTelemetry (traces, metrics, correlated JSON logs) so a deployment pointing `OTEL_EXPORTER_OTLP_ENDPOINT` at a collector gets end-to-end traces and business metrics — with zero behavior change when that variable is unset (the default for `docker compose up` and for the whole test suite).

**Architecture:** A new `core/app/observability.py` owns process-wide OTel provider setup (idempotent — `create_app()` runs dozens of times across the test suite), plus small per-instance helpers (`instrument_app`, `instrument_engine`, `make_worker_middleware`) that accept an optional injected `tracer_provider` so every test can assert against its own in-memory exporter instead of fighting global SDK state. Business-metric counters live next to the repository functions they measure (`app.items.repository`) so REST and MCP callers are counted uniformly; the one exception is `geostudio.apps.runtime_executions`, which is inherently a route-level concept (driven by a `mode=runtime` query param with no repository equivalent) and lives in `app/configs/routes.py` instead.

**Tech Stack:** `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` (no `grpcio` dependency — HTTP/protobuf only, per design), `opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx,botocore}`. Python 3.12+, FastAPI, SQLAlchemy, procrastinate 3.9 (existing).

## Global Constraints

- No `docker-compose.yml` changes in this sub-part — `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME` stay unset by default; SP-10b (separate plan) wires the `--profile observability` service and sets these per container.
- OTLP export protocol is fixed to HTTP/protobuf in code (only the `-proto-http` exporter package is a dependency) — `OTEL_EXPORTER_OTLP_PROTOCOL` is not read or honored.
- Env var names for OTel config are the **standard** OTel ones (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`), never `CORE_`-prefixed.
- Without `OTEL_EXPORTER_OTLP_ENDPOINT` set: zero exporters attached, zero network calls, zero behavior change — every existing test must stay green after every task.
- `core/Dockerfile`'s `uv pip install --system` list is hand-synced with `core/pyproject.toml`'s `[project.dependencies]` (existing, documented convention) — any dependency added to one must be added to the other in the same task.
- Business-metric counters (`geostudio.items.created`, `geostudio.configs.published`) live in `app/items/repository.py` functions, not in REST routes, so MCP callers (which share these functions, cf. SP-2/SP-7) are counted too.

---

### Task 1: OTel providers + idempotent setup + JSON logging

**Files:**
- Create: `core/app/observability.py`
- Create: `core/tests/test_observability.py`
- Modify: `core/pyproject.toml` (add `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` to `[project.dependencies]`)
- Modify: `core/Dockerfile` (add same two packages to the `uv pip install --system` line)

**Interfaces:**
- Produces: `app.observability.setup() -> None` (idempotent, reads `OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_ENDPOINT` from `os.environ`), `app.observability.JSONFormatter` (a `logging.Formatter` subclass), `app.observability._build_tracer_provider(resource, endpoint) -> TracerProvider` and `_build_meter_provider(resource, endpoint) -> MeterProvider` (pure construction, no global registration — what tests call directly), module-level `app.observability._configured: bool`.

- [ ] **Step 1: Add the two dependencies**

Edit `core/pyproject.toml`, in `[project] dependencies = [...]`, add after `"pgvector>=0.3",`:

```toml
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
```

Edit `core/Dockerfile`'s `RUN uv pip install --system --no-cache \` block, add at the end of the backslash-continued list:

```
    "opentelemetry-sdk>=1.27" "opentelemetry-exporter-otlp-proto-http>=1.27"
```

Run: `cd core && uv lock && uv sync`
Expected: lock file updated, `.venv` now has `opentelemetry-*` packages installed, no errors.

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_observability.py`. Note why the two provider-construction tests call `observability._build_tracer_provider(...)` directly instead of going through `setup()` + `trace.get_tracer_provider()`: the OTel API only allows the *global* tracer/meter provider to be set **once** per process (a second `trace.set_tracer_provider()` call anywhere logs a warning and is silently ignored, independent of our own `_configured` flag) — since dozens of other tests in this suite call `create_app()` → `observability.setup()` too, a test that reset `_configured` and re-ran `setup()` could end up observing a completely different, earlier test's provider instead of its own. Testing the pure builder function sidesteps that trap entirely:

```python
# SPDX-License-Identifier: Apache-2.0
import json
import logging

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

from app import observability


def test_build_tracer_provider_without_endpoint_has_no_span_processor():
    provider = observability._build_tracer_provider(Resource.create({"service.name": "x"}), None)
    assert provider._active_span_processor._span_processors == ()


def test_build_tracer_provider_with_endpoint_attaches_a_span_processor():
    provider = observability._build_tracer_provider(
        Resource.create({"service.name": "x"}), "http://localhost:4318",
    )
    assert len(provider._active_span_processor._span_processors) == 1


def test_setup_only_builds_providers_once(monkeypatch):
    monkeypatch.setattr(observability, "_configured", False)
    calls = {"n": 0}
    original = observability._build_tracer_provider

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(observability, "_build_tracer_provider", counting_build)
    observability.setup()
    observability.setup()
    assert calls["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_observability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.observability'`

- [ ] **Step 3: Write `app/observability.py` (providers + idempotence only)**

Create `core/app/observability.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Instrumentation OTel du cœur — SP-10a. setup() configure les providers
process-wide une seule fois (mémoïsation module-level via _configured) :
create_app() est appelé des dizaines de fois par la suite de tests
(DATABASE_URL/CORE_AUTH_MODE différents par test), un second appel ne doit
ni lever, ni reconstruire de providers (et de toute façon, l'API OTel logue
un warning et no-op sur un second set_tracer_provider/set_meter_provider,
indépendamment de ce flag). Sans OTEL_EXPORTER_OTLP_ENDPOINT (comportement
par défaut, toute la suite de tests), aucun exportateur n'est attaché :
spans/métriques/logs sont créés mais jamais envoyés, coût négligeable, zéro
appel réseau."""
import json
import logging
import os
import sys

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_configured = False


class JSONFormatter(logging.Formatter):
    """Une ligne JSON par log, trace_id/span_id du span actif inclus (None
    si aucun span n'est actif). Toujours utilisé, endpoint OTLP configuré ou
    non — `docker compose logs` reste corrélable dans les deux cas."""

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": format(span_context.trace_id, "032x") if span_context.is_valid else None,
            "span_id": format(span_context.span_id, "016x") if span_context.is_valid else None,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _otlp_endpoint() -> str | None:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")


def _build_tracer_provider(resource: Resource, endpoint: str | None) -> TracerProvider:
    provider = TracerProvider(resource=resource)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def _build_meter_provider(resource: Resource, endpoint: str | None) -> MeterProvider:
    metric_readers = []
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        metric_readers = [PeriodicExportingMetricReader(OTLPMetricExporter())]
    return MeterProvider(resource=resource, metric_readers=metric_readers)


def setup() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    service_name = os.environ.get("OTEL_SERVICE_NAME", "geostudio-core")
    resource = Resource.create({"service.name": service_name})
    endpoint = _otlp_endpoint()

    trace.set_tracer_provider(_build_tracer_provider(resource, endpoint))
    metrics.set_meter_provider(_build_meter_provider(resource, endpoint))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_observability.py -v`
Expected: 3 passed

- [ ] **Step 5: Add the JSON formatter tests**

Append to `core/tests/test_observability.py`:

```python
def test_json_formatter_includes_trace_and_span_id_when_a_span_is_active():
    # TracerProvider local, pas le global : ce test ne doit pas dépendre de
    # si observability.setup() a déjà tourné ailleurs dans la session pytest.
    tracer = SDKTracerProvider().get_tracer(__name__)
    record_holder: dict = {}

    class _Capture(logging.Handler):
        def emit(self, record):
            record_holder["record"] = record

    logger = logging.getLogger("test_observability_capture")
    logger.setLevel(logging.INFO)
    logger.addHandler(_Capture())
    logger.propagate = False

    with tracer.start_as_current_span("test-span") as span:
        logger.info("hello")
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
        expected_span_id = format(span.get_span_context().span_id, "016x")

    formatted = observability.JSONFormatter().format(record_holder["record"])
    payload = json.loads(formatted)
    assert payload["message"] == "hello"
    assert payload["trace_id"] == expected_trace_id
    assert payload["span_id"] == expected_span_id


def test_json_formatter_has_null_ids_without_an_active_span():
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="no span", args=(), exc_info=None,
    )
    payload = json.loads(observability.JSONFormatter().format(record))
    assert payload["trace_id"] is None
    assert payload["span_id"] is None
```

- [ ] **Step 6: Run all observability tests**

Run: `cd core && uv run pytest tests/test_observability.py -v`
Expected: 5 passed

- [ ] **Step 7: Run the full core suite to confirm zero regressions**

Run: `cd core && uv run pytest`
Expected: same pass count as before plus 5 (baseline was 410 passed/65 skipped without a real Postgres — confirm your local count with `uv run pytest -q | tail -5` before this task if unsure), no new failures.

- [ ] **Step 8: Commit**

```bash
git add core/pyproject.toml core/Dockerfile core/uv.lock core/app/observability.py core/tests/test_observability.py
git commit -m "feat(core): SP-10a — OTel providers, idempotent setup, JSON logs"
```

---

### Task 2: FastAPI + SQLAlchemy auto-instrumentation

**Files:**
- Modify: `core/app/observability.py`
- Modify: `core/app/main.py:1-46` (add import, wire `observability.setup()`/`instrument_engine`/`instrument_app` into `create_app()`)
- Modify: `core/pyproject.toml`, `core/Dockerfile` (add `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`)
- Create: `core/tests/test_observability_web.py`

**Interfaces:**
- Consumes: `app.observability.setup()` (Task 1).
- Produces: `app.observability.instrument_app(app: FastAPI, *, tracer_provider=None) -> None`, `app.observability.instrument_engine(engine: Engine, *, tracer_provider=None) -> None`.

- [ ] **Step 1: Add the two dependencies**

Edit `core/pyproject.toml`, add after the two packages from Task 1:

```toml
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.48b0",
```

Edit `core/Dockerfile`'s install line, append:

```
    "opentelemetry-instrumentation-fastapi>=0.48b0" "opentelemetry-instrumentation-sqlalchemy>=0.48b0"
```

Run: `cd core && uv lock && uv sync`
Expected: no errors, packages installed.

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_observability_web.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import InMemorySpanExporter, SimpleSpanProcessor
from sqlalchemy import text

from app import observability
from app.db import init_db, make_engine, make_session_factory


def test_fastapi_and_sqlalchemy_requests_produce_spans():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    observability.instrument_engine(engine, tracer_provider=provider)
    session_factory = make_session_factory(engine)

    app = FastAPI()
    observability.instrument_app(app, tracer_provider=provider)

    @app.get("/ping")
    def ping():
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"ok": True}

    response = TestClient(app).get("/ping")
    assert response.status_code == 200

    scopes = {span.instrumentation_scope.name for span in exporter.get_finished_spans()}
    assert "opentelemetry.instrumentation.fastapi" in scopes
    assert "opentelemetry.instrumentation.sqlalchemy" in scopes
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_observability_web.py -v`
Expected: FAIL — `AttributeError: module 'app.observability' has no attribute 'instrument_engine'`

- [ ] **Step 4: Add `instrument_app`/`instrument_engine` to observability.py**

In `core/app/observability.py`, add at the end of the file:

```python
def instrument_app(app, *, tracer_provider=None) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)


def instrument_engine(engine, *, tracer_provider=None) -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_observability_web.py -v`
Expected: PASS

- [ ] **Step 6: Wire into `create_app()`**

In `core/app/main.py`, replace the line:

```python
from app import db
```

with:

```python
from app import db, observability
```

Modify the top of `create_app()`:

```python
def create_app() -> FastAPI:
    observability.setup()
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    observability.instrument_engine(engine)
    init_db(engine)
    session_factory = make_session_factory(engine)
```

And right after `app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)`:

```python
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)
    observability.instrument_app(app)
```

- [ ] **Step 7: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: previous count + 1 (this task's test), no failures. This is the first real exercise of `create_app()` being called dozens of times with instrumentation wired in — watch specifically for any "already instrumented" errors across the suite.

- [ ] **Step 8: Commit**

```bash
git add core/pyproject.toml core/Dockerfile core/uv.lock core/app/observability.py core/app/main.py core/tests/test_observability_web.py
git commit -m "feat(core): SP-10a — FastAPI/SQLAlchemy auto-instrumentation"
```

---

### Task 3: httpx + botocore instrumentation

**Files:**
- Modify: `core/app/observability.py` (`setup()` gains two `.instrument()` calls)
- Modify: `core/pyproject.toml`, `core/Dockerfile` (add `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-botocore`)
- Create: `core/tests/test_observability_httpx_botocore.py`

**Interfaces:**
- Consumes: `app.observability.setup()` (Task 1, extended here).

- [ ] **Step 1: Add the two dependencies**

Edit `core/pyproject.toml`, add:

```toml
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "opentelemetry-instrumentation-botocore>=0.48b0",
```

Edit `core/Dockerfile`'s install line, append:

```
    "opentelemetry-instrumentation-httpx>=0.48b0" "opentelemetry-instrumentation-botocore>=0.48b0"
```

Run: `cd core && uv lock && uv sync`

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_observability_httpx_botocore.py`. This spawns a fresh subprocess (same pattern as `tests/test_jobs.py::test_import_paths_registers_all_domain_tasks`) because `HTTPXClientInstrumentor`/`BotocoreInstrumentor` are process-wide singletons: if any earlier test in the same pytest session already triggered `observability.setup()` (near-certain, since dozens of tests call `create_app()`), a second `.instrument()` call in-process would just warn-and-no-op, making the assertion meaningless.

```python
# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path


def test_setup_instruments_httpx_and_botocore_globally():
    core_dir = Path(__file__).resolve().parents[1]
    script = (
        "from app import observability\n"
        "observability.setup()\n"
        "from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor\n"
        "from opentelemetry.instrumentation.botocore import BotocoreInstrumentor\n"
        "print(HTTPXClientInstrumentor().is_instrumented_by_opentelemetry)\n"
        "print(BotocoreInstrumentor().is_instrumented_by_opentelemetry)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=core_dir, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"sous-process a échoué : {result.stderr}"
    assert result.stdout.strip().splitlines() == ["True", "True"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_observability_httpx_botocore.py -v`
Expected: FAIL — subprocess stdout is `["False", "False"]` (or an import error if the packages aren't wired yet).

- [ ] **Step 4: Wire the two instrumentors into `setup()`**

In `core/app/observability.py`, inside `setup()`, right after `metrics.set_meter_provider(...)`:

```python
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()
    BotocoreInstrumentor().instrument()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_observability_httpx_botocore.py -v`
Expected: PASS

- [ ] **Step 6: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: previous count + 1, no failures (in particular: no test that exercises `httpx`/`boto3` calls, e.g. `tests/test_search_providers.py` or ingestion S3 tests, should start failing).

- [ ] **Step 7: Commit**

```bash
git add core/pyproject.toml core/Dockerfile core/uv.lock core/app/observability.py core/tests/test_observability_httpx_botocore.py
git commit -m "feat(core): SP-10a — httpx/botocore global instrumentation"
```

---

### Task 4: procrastinate job spans

**Files:**
- Modify: `core/app/observability.py` (add `make_worker_middleware`)
- Modify: `core/app/jobs.py` (wire `worker_defaults={"worker_middleware": [...]}`)
- Create: `core/tests/test_jobs_observability.py`

**Interfaces:**
- Produces: `app.observability.make_worker_middleware(*, tracer_provider=None) -> Callable` (an async procrastinate worker middleware, signature `(call_next, context, worker)`), `app.observability.otel_worker_middleware` (the default instance, built with the global provider).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_jobs_observability.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import InMemorySpanExporter, SimpleSpanProcessor
from procrastinate.job_context import JobContext
from procrastinate.jobs import Job

from app import observability


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_context(*, task_name="app.demo.task", queue="default", job_id=7):
    job = Job(id=job_id, status="doing", queue=queue, lock=None, queueing_lock=None, task_name=task_name)
    return JobContext(app=None, job=job, start_timestamp=0.0, abort_reason=lambda: None)


@pytest.mark.anyio
async def test_worker_middleware_wraps_job_execution_in_a_span(anyio_backend):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    middleware = observability.make_worker_middleware(tracer_provider=provider)

    async def call_next():
        return "ok"

    result = await middleware(call_next, _make_context(), worker=None)

    assert result == "ok"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "procrastinate.job.app.demo.task"
    assert spans[0].attributes["procrastinate.job.task_name"] == "app.demo.task"
    assert spans[0].attributes["procrastinate.job.queue"] == "default"
    assert spans[0].attributes["procrastinate.job.id"] == 7
    assert spans[0].status.status_code.name == "UNSET"


@pytest.mark.anyio
async def test_worker_middleware_records_exception_and_reraises(anyio_backend):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    middleware = observability.make_worker_middleware(tracer_provider=provider)

    async def call_next():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await middleware(call_next, _make_context(), worker=None)

    spans = exporter.get_finished_spans()
    assert spans[0].status.status_code.name == "ERROR"
    assert spans[0].events[0].name == "exception"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_jobs_observability.py -v`
Expected: FAIL — `AttributeError: module 'app.observability' has no attribute 'make_worker_middleware'`

- [ ] **Step 3: Add `make_worker_middleware` to observability.py**

In `core/app/observability.py`, add at the end of the file:

```python
def make_worker_middleware(*, tracer_provider=None):
    from opentelemetry.trace import Status, StatusCode

    tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(__name__)

    async def _otel_worker_middleware(call_next, context, worker):
        job = context.job
        with tracer.start_as_current_span(
            f"procrastinate.job.{job.task_name}",
            attributes={
                "procrastinate.job.id": job.id if job.id is not None else -1,
                "procrastinate.job.task_name": job.task_name,
                "procrastinate.job.queue": job.queue,
            },
        ) as span:
            try:
                return await call_next()
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    return _otel_worker_middleware


otel_worker_middleware = make_worker_middleware()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_jobs_observability.py -v`
Expected: PASS

- [ ] **Step 5: Wire into `app/jobs.py`**

Read `core/app/jobs.py` first (its existing comments explain why `import_paths` matters — don't disturb that). Add the import and `worker_defaults` kwarg:

```python
import os

import procrastinate

from app import observability
```

```python
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
    import_paths=["app.ingestion.tasks", "app.items.jobs", "app.collections.jobs"],
    worker_defaults={"worker_middleware": [observability.otel_worker_middleware]},
)
```

- [ ] **Step 6: Run the jobs test file + full core suite**

Run: `cd core && uv run pytest tests/test_jobs.py tests/test_jobs_observability.py -v`
Expected: all pass, including the existing subprocess test (`test_import_paths_registers_all_domain_tasks`) — confirms `app/jobs.py` still imports cleanly in a fresh subprocess with the new `observability` import.

Run: `cd core && uv run pytest`
Expected: previous count + 2, no failures.

- [ ] **Step 7: Commit**

```bash
git add core/app/observability.py core/app/jobs.py core/tests/test_jobs_observability.py
git commit -m "feat(core): SP-10a — procrastinate job spans via worker_middleware"
```

---

### Task 5: business metrics — items created + published

**Files:**
- Modify: `core/app/items/repository.py` (add counters, increment in `create_item`/`update_item`)
- Modify: `core/tests/test_items_repository.py` (append tests)

**Interfaces:**
- Consumes: nothing new (uses `opentelemetry.metrics` API directly, works via the proxy meter even before `observability.setup()` has run — see design doc SP-10a §Métriques métier).
- Produces: `app.items.repository._items_created_counter`, `app.items.repository._items_published_counter` (module-level, for tests to monkeypatch).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_items_repository.py`:

```python
from unittest.mock import Mock


def test_create_item_increments_items_created_counter(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    mock_counter = Mock()
    monkeypatch.setattr(repo, "_items_created_counter", mock_counter)

    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incident")

    mock_counter.add.assert_called_once_with(1)


def test_update_item_increments_published_counter_only_when_publishing(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incident")
    mock_counter = Mock()
    monkeypatch.setattr(repo, "_items_published_counter", mock_counter)

    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title=None, abstract=None, keywords=None, is_published=None,
    )
    mock_counter.add.assert_not_called()

    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title=None, abstract=None, keywords=None, is_published=False,
    )
    mock_counter.add.assert_not_called()

    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title=None, abstract=None, keywords=None, is_published=True,
    )
    mock_counter.add.assert_called_once_with(1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_repository.py -k "counter" -v`
Expected: FAIL — `AttributeError: <module 'app.items.repository'> does not have the attribute '_items_created_counter'`

- [ ] **Step 3: Add the counters and increments**

In `core/app/items/repository.py`, replace the import block:

```python
import logging
import uuid
from datetime import datetime, timezone

import procrastinate
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.schemas import ItemPage, ItemRead
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
from app.users.models import User
```

with:

```python
import logging
import uuid
from datetime import datetime, timezone

import procrastinate
from opentelemetry import metrics
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.schemas import ItemPage, ItemRead
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
from app.users.models import User
```

Then add the counters right after `_RRF_CANDIDATE_LIMIT = 200`:

```python
_meter = metrics.get_meter(__name__)
_items_created_counter = _meter.create_counter(
    "geostudio.items.created", unit="1", description="Items created via REST or MCP",
)
_items_published_counter = _meter.create_counter(
    "geostudio.configs.published", unit="1", description="Items patched with isPublished=True",
)
```

In `create_item`, add the increment right before `return item`:

```python
def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str
) -> Item:
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title,
    )
    session.add(item)
    session.flush()
    session.refresh(item)
    _enqueue_embedding(item.id, tenant_id)
    _items_created_counter.add(1)
    return item
```

In `update_item`, add the increment right after the `is_published` assignment:

```python
    if is_published is not None:
        item.is_published = is_published
    if is_published is True:
        _items_published_counter.add(1)
    session.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: all pass (existing tests in this file + the 2 new ones).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: previous count + 2, no failures.

- [ ] **Step 6: Commit**

```bash
git add core/app/items/repository.py core/tests/test_items_repository.py
git commit -m "feat(core): SP-10a — items.created/configs.published metrics"
```

---

### Task 6: `mode=runtime` plumbing + apps.runtime_executions metric

**Files:**
- Modify: `core/app/configs/routes.py` (query param + counter)
- Modify: `core/tests/test_routes.py` (append test)
- Modify: `shell/src/api/types.ts:126` (`ItemClient.getAppConfig` signature)
- Modify: `shell/src/api/itemClient.ts:456-479` (`getAppConfig` implementation)
- Modify: `shell/src/api/itemClient.test.ts` (append test)
- Modify: `shell/src/api/hooks.ts:199-206` (`useAppConfig` forwards `mode`)
- Modify: `shell/src/api/hooks.test.tsx` (append test)
- Modify: `shell/src/pages/AppRuntimePage.tsx:18` (pass `mode: "runtime"`)

**Interfaces:**
- Produces (core): `GET /configs/by-item/{item_id}?mode=runtime` increments `geostudio.apps.runtime_executions`; without the param (or any other value), no increment.
- Produces (shell): `ItemClient.getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig>`; `useAppConfig(pk, { enabled?, mode? })`.

- [ ] **Step 1: Write the failing core test**

Append to `core/tests/test_routes.py`:

```python
from unittest.mock import Mock


def test_get_config_by_item_with_mode_runtime_increments_counter(client, monkeypatch):
    body = _create(client)
    item_id = body["itemId"]
    mock_counter = Mock()
    monkeypatch.setattr(routes, "_apps_runtime_executions_counter", mock_counter)

    client.get(f"/configs/by-item/{item_id}")
    mock_counter.add.assert_not_called()

    response = client.get(f"/configs/by-item/{item_id}", params={"mode": "runtime"})
    assert response.status_code == 200
    mock_counter.add.assert_called_once_with(1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_routes.py -k mode_runtime -v`
Expected: FAIL — `AttributeError: <module 'app.configs.routes'> does not have the attribute '_apps_runtime_executions_counter'`

- [ ] **Step 3: Add the query param + counter to the core route**

In `core/app/configs/routes.py`, replace the import block:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as repo
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.configs.extension_permissions import ExtensionPermissionError, validate_extension_permissions
from app.db import get_session
from app.items import repository as items_repo
from app.items.models import Item
from app.sharing.authorization import can
from app.users.models import User
```

with:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from opentelemetry import metrics
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as repo
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.configs.extension_permissions import ExtensionPermissionError, validate_extension_permissions
from app.db import get_session
from app.items import repository as items_repo
from app.items.models import Item
from app.sharing.authorization import can
from app.users.models import User
```

Then add the counter right after `router = APIRouter()`:

```python
_meter = metrics.get_meter(__name__)
_apps_runtime_executions_counter = _meter.create_counter(
    "geostudio.apps.runtime_executions", unit="1", description="GET config calls with mode=runtime",
)
```

Modify `get_config_by_item`:

```python
@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str,
    mode: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_access(session, user=user, item_id=item_id, action="read")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if mode == "runtime":
        _apps_runtime_executions_counter.add(1)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_routes.py -k mode_runtime -v`
Expected: PASS

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: previous count + 1, no failures.

- [ ] **Step 6: Shell — extend `ItemClient.getAppConfig` and `itemClient.ts`**

In `shell/src/api/types.ts`, change line 126:

```typescript
  getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig>;
```

In `shell/src/api/itemClient.ts`, modify `getAppConfig` (around line 456):

```typescript
    async getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig> {
      const qs = mode ? `?mode=${mode}` : "";
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
        };
      }>("GET", `/configs/by-item/${pk}${qs}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
      };
    },
```

- [ ] **Step 7: Write the failing shell tests**

Append to `shell/src/api/itemClient.test.ts` (near the existing `getAppConfig` tests around line 320):

```typescript
test("getAppConfig appends ?mode=runtime when a mode is passed", async () => {
  let requestedUrl = "";
  server.use(
    http.get("https://core.test/configs/by-item/5", ({ request }) => {
      requestedUrl = request.url;
      return HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: { kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] } },
      });
    }),
  );
  await makeClient().getAppConfig("5", "runtime");
  expect(requestedUrl).toContain("mode=runtime");
});
```

Append to `shell/src/api/hooks.test.tsx` (near the existing `useAppConfig` test around line 166):

```typescript
test("useAppConfig forwards mode to the client", async () => {
  const cfg = { kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] } };
  const client = { getAppConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useAppConfig("5", { mode: "runtime" }), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(client.getAppConfig).toHaveBeenCalledWith("5", "runtime");
});
```

- [ ] **Step 8: Run the two new shell tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx`
Expected: FAIL — `getAppConfig` doesn't yet accept a second arg / `useAppConfig` doesn't yet forward `mode` (the `itemClient.test.ts` one may actually pass by accident since `mode` isn't threaded yet but the URL won't contain `mode=runtime` — confirm the assertion actually fails before moving on).

- [ ] **Step 9: Update `useAppConfig` and `AppRuntimePage`**

In `shell/src/api/hooks.ts`, modify `useAppConfig` (around line 199):

```typescript
export function useAppConfig(pk: string, options?: { enabled?: boolean; mode?: "runtime" }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["app", pk, options?.mode],
    queryFn: () => client.getAppConfig(pk, options?.mode),
    enabled: options?.enabled ?? true,
  });
}
```

In `shell/src/pages/AppRuntimePage.tsx`, modify line 18:

```typescript
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess, mode: "runtime" });
```

- [ ] **Step 10: Run the shell tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx src/pages/AppRuntimePage.test.tsx`
Expected: all pass.

- [ ] **Step 11: Run the full shell suite + typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all tests pass, `tsc --noEmit` clean.

- [ ] **Step 12: Commit**

```bash
git add core/app/configs/routes.py core/tests/test_routes.py \
  shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts \
  shell/src/api/hooks.ts shell/src/api/hooks.test.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat: SP-10a — mode=runtime plumbing + apps.runtime_executions metric"
```

---

### Task 7: Full regression check + E2E

**Files:** none created/modified — verification only.

- [ ] **Step 1: Full core suite**

Run: `cd core && uv run pytest`
Expected: no failures. `postgis`-marked tests skip without `CORE_TEST_DATABASE_URL` (existing behavior, unaffected by this plan).

- [ ] **Step 2: Import-linter (layering contract)**

Run: `cd core && uv run lint-imports`
Expected: clean. `app.observability` is not listed in `[tool.importlinter] layers` (same convention as `app.db` — foundational/cross-cutting, importable from anywhere), so no contract edit is needed; this step just confirms nothing else broke.

- [ ] **Step 3: Full shell suite + typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: no failures, clean typecheck.

- [ ] **Step 4: E2E — the app-runtime-touching specs**

Run: `cd shell && npm run e2e -- --grep "runtime|incident|expr"`
Expected: green. These specs exercise `AppRuntimePage` (now sending `?mode=runtime`) most directly; a broader run (`npm run e2e`) is the real gate before merge but this narrower run is a fast first check.

- [ ] **Step 5: Full E2E suite**

Run: `cd shell && npm run e2e`
Expected: all specs green (37/37 as of the last recorded count in `CLAUDE.md` — confirm the current count hasn't drifted before asserting parity).

- [ ] **Step 6: Manual smoke — OTLP endpoint actually produces a trace**

This is the one acceptance criterion (design doc §Critères d'acceptation #1) that automated tests don't cover end-to-end (they use in-memory exporters by design, never a real collector). Manually verify once:

```bash
docker run -d --name otel-smoke -p 4318:4318 -p 3000:3000 grafana/otel-lgtm
cd core
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_SERVICE_NAME=geostudio-core-smoke \
  DATABASE_URL=sqlite+pysqlite:///:memory: uv run uvicorn app.main:app --port 8200 &
curl -s http://localhost:8200/health
sleep 5  # laisser le BatchSpanProcessor exporter par lot
# Ouvrir http://localhost:3000 (Grafana, admin/admin), Explore → Tempo → chercher service.name="geostudio-core-smoke"
```

Expected: a trace for the `/health` request appears in Tempo, with a span from the FastAPI instrumentation. Tear down: `kill %1; docker rm -f otel-smoke`.

- [ ] **Step 7: Update `CLAUDE.md`**

Add an entry under "État au 2026-07-16" (or the current date if this runs later) documenting SP-10a as delivered — new test counts, brief summary of what shipped, explicit note that SP-10b (compose profile, dashboards, SLO alerts) is still pending. Follow the exact style of the existing SP-9 sub-part entries (one paragraph, what shipped, test counts, what's next).

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md — SP-10a instrumentation OTel livré"
```
