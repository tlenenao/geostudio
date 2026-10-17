# SPDX-License-Identifier: Apache-2.0
"""AUD-040 : identifiant de requête corrélable (en-tête, span, logs) et
tenant/utilisateur sur le span serveur."""

import logging
import subprocess
import sys
import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import observability


def _app() -> FastAPI:
    app = FastAPI()
    seen: dict = {}

    @app.get("/ping")
    def ping():
        record = logging.getLogger("rid").makeRecord("rid", logging.INFO, "f", 1, "x", (), None)
        seen["log_request_id"] = getattr(record, "request_id", None)
        return {"rid": observability.current_request_id()}

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    app.add_middleware(observability.RequestIdMiddleware)
    app.state.seen = seen
    return app


def test_generates_and_echoes_a_request_id():
    observability.setup()
    app = _app()
    r = TestClient(app).get("/ping")
    rid = r.headers["x-request-id"]
    assert len(rid) == 32 and r.json()["rid"] == rid
    assert app.state.seen["log_request_id"] == rid


def test_keeps_a_well_formed_incoming_id():
    r = TestClient(_app()).get("/ping", headers={"X-Request-ID": "abc-123.DEF_4"})
    assert r.headers["x-request-id"] == "abc-123.DEF_4"
    assert r.json()["rid"] == "abc-123.DEF_4"


@pytest.mark.parametrize("bad", ["a" * 129, "evilé", "a b", "<script>", ""])
def test_replaces_a_malformed_incoming_id(bad):
    r = TestClient(_app()).get("/ping", headers={"X-Request-ID": bad.encode("utf-8")})
    assert r.headers["x-request-id"] != bad and len(r.headers["x-request-id"]) == 32


def test_request_id_on_unhandled_500_of_the_real_app(monkeypatch, tmp_path):
    """Le 500 est produit par ServerErrorMiddleware, HORS des middlewares
    applicatifs : c'est la réponse où l'identifiant compte le plus."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/x.db")
    from app.main import create_app

    app = create_app()

    @app.get("/v1/__boom")
    def _boom():
        raise RuntimeError("boom")

    # Avant le montage MCP racine (« / »), qui avalerait la route sinon.
    app.router.routes.insert(0, app.router.routes.pop())

    r = TestClient(app, raise_server_exceptions=False).get(
        "/v1/__boom", headers={"X-Request-ID": "rid-500"}
    )
    assert r.status_code == 500
    assert r.headers["x-request-id"] == "rid-500"
    assert r.json()["requestId"] == "rid-500"


def test_span_carries_request_tenant_and_user(tmp_path):
    """Sous-processus neuf : le TracerProvider global ne se pose qu'une fois
    par process (setup() mémoïsé), on y branche un exportateur mémoire."""
    script = textwrap.dedent(
        f"""
        import os
        os.environ["DATABASE_URL"] = "sqlite+pysqlite:///{tmp_path}/s.db"
        os.environ["CORE_AUTH_MODE"] = "mock"
        os.environ["CORE_ENV"] = "development"
        os.environ.setdefault(
            "CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
        )
        from opentelemetry import trace
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from app import observability
        observability.setup()
        exporter = InMemorySpanExporter()
        trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
        from fastapi.testclient import TestClient
        from app.main import create_app
        r = TestClient(create_app()).get(
            "/v1/me", headers={{"Authorization": "Bearer x", "X-Request-ID": "rid-span"}}
        )
        assert r.status_code == 200, r.text
        servers = [s for s in exporter.get_finished_spans() if s.kind.name == "SERVER"]
        attrs = dict(servers[-1].attributes)
        assert attrs["http.request_id"] == "rid-span", attrs
        assert attrs["enduser.id"] and attrs["geostudio.tenant_id"], attrs
        print("OK")
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=".", timeout=120
    )
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr[-3000:]
