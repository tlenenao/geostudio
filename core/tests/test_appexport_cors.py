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


def test_cors_header_absent_on_post_collections_when_enabled(monkeypatch):
    # POST /collections (create collection, admin-only) shares the
    # /collections path prefix with the allowlisted GET /collections but
    # must never get CORS exposure — it isn't in the plan's 7-entry
    # allowlist and requires real auth.
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.post("/collections", json={})
    assert "access-control-allow-origin" not in response.headers


def test_cors_header_absent_on_collections_candidates_when_enabled(monkeypatch):
    # GET /collections/candidates (admin-only) was previously over-matched
    # by the path-only regex's `(/[^/]+)?` branch, which treated
    # "candidates" as if it were a collection id.
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/collections/candidates")
    assert "access-control-allow-origin" not in response.headers


def test_cors_header_absent_on_collection_write_endpoints_when_enabled(monkeypatch):
    # PATCH/DELETE /collections/{id} and write endpoints under
    # /collections/{id}/items require real auth and must never receive
    # Access-Control-Allow-Origin even though GET on the same paths is
    # allowlisted.
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    assert "access-control-allow-origin" not in client.patch("/collections/col1", json={}).headers
    assert "access-control-allow-origin" not in client.delete("/collections/col1").headers
    assert (
        "access-control-allow-origin" not in client.post("/collections/col1/items", json={}).headers
    )
    assert (
        "access-control-allow-origin"
        not in client.put("/collections/col1/items/fid1", json={}).headers
    )
    assert (
        "access-control-allow-origin" not in client.delete("/collections/col1/items/fid1").headers
    )


def test_cors_preflight_still_204_on_write_paths_when_enabled(monkeypatch):
    # A browser preflights OPTIONS before it knows whether the follow-up
    # real request will be an allowlisted GET or a write method the server
    # will reject — the preflight itself must stay path-only and succeed;
    # it's the real request (tested above) that must be blocked.
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.options("/collections/col1/items")
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_header_present_on_public_items_when_enabled(monkeypatch):
    # GET /public/items (core/app/public/routes.py) is fully anonymous —
    # no auth dependency at all — and is what the builtin Gallery widget
    # calls at runtime via client.listPublicItems(). It was missing from
    # the SP-18b allowlist (review finding I3), so a Connecté export
    # containing a Gallery widget got CORS-blocked and rendered empty.
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.get("/public/items")
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_preflight_responds_on_public_items_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    client = TestClient(create_app())
    response = client.options("/public/items")
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"
