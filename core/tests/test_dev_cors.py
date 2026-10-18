# SPDX-License-Identifier: Apache-2.0
"""AUD-132/135 : démarrage rapide (shell :8300 → cœur :8200 cross-origin),
version réelle, Swagger derrière un préfixe, quotas mal formés."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SHELL = "http://localhost:8300"
PREFLIGHT = {
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "authorization",
}


def test_preflight_from_listed_dev_origin_allows_authorization(monkeypatch):
    monkeypatch.setenv("CORE_CORS_ALLOWED_ORIGINS", f"{SHELL}, http://127.0.0.1:8300")
    r = TestClient(create_app()).options("/v1/me", headers={"Origin": SHELL, **PREFLIGHT})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == SHELL
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_simple_response_exposes_the_headers_the_shell_reads(monkeypatch):
    monkeypatch.setenv("CORE_CORS_ALLOWED_ORIGINS", SHELL)
    r = TestClient(create_app()).get("/health", headers={"Origin": SHELL})
    assert r.headers["access-control-allow-origin"] == SHELL
    exposed = r.headers["access-control-expose-headers"].lower()
    for h in ("etag", "retry-after", "content-disposition", "x-tile-truncated", "x-request-id"):
        assert h in exposed, h


def test_unlisted_origin_gets_no_cors_and_appexport_preflight_is_untouched(monkeypatch):
    monkeypatch.setenv("CORE_CORS_ALLOWED_ORIGINS", SHELL)
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    r = client.options("/v1/me", headers={"Origin": "https://evil.example", **PREFLIGHT})
    assert "access-control-allow-origin" not in r.headers
    # SP-18b : préflight d'une app exportée, origine quelconque → 204 `*`
    r = client.options(
        "/v1/collections/c1/aggregate",
        headers={"Origin": "https://app.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "*"


def test_no_cors_when_unset(monkeypatch):
    monkeypatch.delenv("CORE_CORS_ALLOWED_ORIGINS", raising=False)
    r = TestClient(create_app()).options("/v1/me", headers={"Origin": SHELL, **PREFLIGHT})
    assert "access-control-allow-origin" not in r.headers


def test_version_comes_from_the_deployed_tag(monkeypatch):
    monkeypatch.setenv("GEOSTUDIO_VERSION", "v0.2.0")
    assert create_app().version == "0.2.0"
    monkeypatch.delenv("GEOSTUDIO_VERSION")
    assert create_app().version == "dev"


def test_swagger_ui_fetches_the_schema_relatively():
    """Derrière Traefik (`/api` retiré), une URL absolue `/openapi.json`
    tombait sur le shell."""
    html = TestClient(create_app()).get("/docs").text
    assert "url: 'openapi.json'" in html
    assert "'/openapi.json'" not in html


@pytest.mark.parametrize(
    "var",
    [
        "CORE_QUOTA_MAX_ITEMS_PER_TENANT",
        "CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT",
        "CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT",
        "CORE_QUOTA_MAX_USERS_PER_TENANT",
        "CORE_QUOTA_MAX_ACTIVE_RUNS_PER_TENANT",
    ],
)
def test_malformed_quota_fails_fast_naming_the_variable(monkeypatch, var):
    monkeypatch.setenv(var, "10GB")
    with pytest.raises(RuntimeError, match=var):
        create_app()
