# SPDX-License-Identifier: Apache-2.0
"""SP-57b : les 31+ routeurs de l'API sont désormais imbriqués sous /v1 —
/health et le montage /mcp restent hors versionnement (contrats externes à
protocole fixe : healthcheck Docker, découverte OAuth MCP)."""

from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    return TestClient(create_app())


def test_v1_prefixed_route_responds(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/v1/items")
    assert response.status_code != 404


def test_unprefixed_route_is_gone_no_backward_compat_alias(monkeypatch):
    # Décision assumée (spec SP-57b §2.6) : migration directe, pas de double
    # montage /items ET /v1/items en parallèle.
    client = _client(monkeypatch)
    response = client.get("/items")
    assert response.status_code == 404


def test_health_stays_unprefixed(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_under_v1_does_not_exist(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/v1/health")
    assert response.status_code == 404


def test_mcp_mount_is_unaffected(monkeypatch):
    client = _client(monkeypatch)
    # Même assertion que test_mcp_routes.py::test_mcp_endpoint_exists_and_requires_a_session
    # — la route doit exister (pas 404), preuve que le montage ASGI /mcp
    # n'a pas bougé sous /v1.
    response = client.get("/mcp")
    assert response.status_code != 404


def test_mcp_under_v1_does_not_exist(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/v1/mcp")
    assert response.status_code == 404
