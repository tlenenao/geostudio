# SPDX-License-Identifier: Apache-2.0
import duckdb
from fastapi.testclient import TestClient

from app.features import routes as features_routes
from app.main import create_app


def _fake_duckdb_factory():
    return duckdb.connect(":memory:")


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    # /analytics/sql exécute réellement son endpoint pour les requêtes sous
    # le budget (seule la 11e est court-circuitée par le middleware) — sans
    # cet override, get_duckdb_connection_factory lève un KeyError sur
    # S3_ENDPOINT_URL (non défini hors stack docker), non lié à ce qu'on
    # teste ici. Même patron que tests/test_analytics_sql_routes.py. Le SQL
    # utilisé ("select 1") ne référence aucune table, donc aucune extension
    # DuckDB supplémentaire (spatial/httpfs) n'est nécessaire.
    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        _fake_duckdb_factory
    )
    return TestClient(app)


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
