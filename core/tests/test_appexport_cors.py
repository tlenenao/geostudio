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
