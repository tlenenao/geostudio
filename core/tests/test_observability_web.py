# SPDX-License-Identifier: Apache-2.0
"""FastAPIInstrumentor instruments per-app-instance and would work fine
in-process. SQLAlchemyInstrumentor, however, is a process-wide singleton
(BaseInstrumentor.__new__ always returns the same instance, and
_is_instrumented_by_opentelemetry is a one-shot flag on that instance):
dozens of earlier tests in the same pytest session call create_app(), which
calls observability.instrument_engine() on their own throwaway engine — the
very first such call permanently flips the singleton's flag, and every
subsequent .instrument(engine=...) call (including this test's own engine)
silently no-ops ("Attempting to instrument while already instrumented"),
so no sqlalchemy spans would ever be produced when run as part of the full
suite. Running the whole scenario in a fresh subprocess (same pattern as
tests/test_jobs.py::test_import_paths_registers_all_domain_tasks and
tests/test_observability_httpx_botocore.py) gives both instrumentors a
virgin process, so each succeeds on its first (and only) .instrument()
call."""
import subprocess
import sys
from pathlib import Path


def test_fastapi_and_sqlalchemy_requests_produce_spans():
    core_dir = Path(__file__).resolve().parents[1]
    script = """
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from app import observability
from app.db import init_db, make_engine, make_session_factory

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
assert "opentelemetry.instrumentation.fastapi" in scopes, scopes
assert "opentelemetry.instrumentation.sqlalchemy" in scopes, scopes
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=core_dir, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"sous-process a échoué : {result.stderr}"
    assert result.stdout.strip().splitlines()[-1] == "OK"
