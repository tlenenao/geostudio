# SPDX-License-Identifier: Apache-2.0
"""AUD-153 : le corps d'une soumission publique est refusé AVANT le parsing multipart."""

from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ENV", "development")
    return TestClient(create_app())


def test_oversized_public_submit_is_413_before_parsing(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/public/submit/gss_bidon",
        content=b"x" * 10,
        headers={
            "Content-Length": str(30 * 1024 * 1024),
            "Content-Type": "multipart/form-data; boundary=b",
        },
    )
    assert resp.status_code == 413
    assert "submission too large" in resp.json()["detail"]


def test_public_submit_without_length_is_411(monkeypatch):
    client = _client(monkeypatch)

    def gen():
        yield b"--b--"

    resp = client.post(
        "/v1/public/submit/gss_bidon",
        content=gen(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert resp.status_code == 411
