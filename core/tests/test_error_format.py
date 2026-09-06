# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def test_unhandled_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()

    @app.get("/__boom")
    def boom():
        raise ValueError("kaboom")

    # create_app() monte le serveur MCP en Mount("/") avant de retourner ;
    # un Mount à la racine matche tout chemin en Match.FULL (préfixe "/")
    # et intercepte donc toute route ajoutée après lui dans la table de
    # routage — la nouvelle route doit être déplacée avant ce montage pour
    # être effectivement atteinte par TestClient.
    app.router.routes.insert(0, app.router.routes.pop())

    client = TestClient(app, raise_server_exceptions=False)
    # /__boom est ajoutée directement sur app.router (pas sur v1_router) par
    # ce test — elle vit donc à la racine, jamais sous /v1.
    response = client.get("/__boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 500
    assert body["title"]
    assert body["detail"] == "internal server error"
    assert "kaboom" not in response.text  # jamais fuiter le message interne


def test_plain_http_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app())
    response = client.get("/v1/collections/does-not-exist/items/does-not-exist")
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == response.status_code
    assert isinstance(body["detail"], str)
    assert "errors" not in body  # pas de validation structurée sur ce chemin


def test_validation_exception_carries_top_level_errors(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    # get_duckdb_connection_factory (non overridé, pas de dependency_overrides
    # ici) exige ces trois variables ; open_connection() ne fait que poser de
    # la config DuckDB in-process, aucun accès réseau réel n'est déclenché
    # avant que le SQL invalide n'échoue au sandbox.
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    client = TestClient(create_app())
    # /analytics/sql exige get_current_user (Bearer requis) ; en mode mock
    # le contenu du jeton n'est pas vérifié, seul le préfixe "Bearer " l'est.
    response = client.post(
        "/v1/analytics/sql",
        json={"sql": "not valid sql at all"},
        headers={"Authorization": "Bearer mock"},
    )
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert isinstance(body["detail"], str)  # jamais un dict désormais
    assert isinstance(body["errors"], list)
    assert body["errors"][0]["field"] == "sql"
