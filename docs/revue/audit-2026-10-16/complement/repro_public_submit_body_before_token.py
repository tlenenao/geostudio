"""Repro : le corps multipart (fichier) est integralement recu et spoole sur disque AVANT que
la route ne verifie rate-limit IP et jeton (parse par FastAPI/Starlette avant le corps de submit()).
Lancer depuis core/ avec les memes variables d'env que repro_terrain3d_key_reuse.py (--no-cov)."""
import pytest
from fastapi.testclient import TestClient
from starlette import datastructures

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app


def test_unknown_token_still_spools_whole_file(monkeypatch):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    S = make_session_factory(engine)
    app = create_app()

    def override():
        with request_scoped_session(S) as s:
            yield s

    app.dependency_overrides[db.get_session] = override
    from app.attachments.routes import get_s3_client
    from app.collections.routes import get_introspector

    app.dependency_overrides[get_s3_client] = lambda: object()
    app.dependency_overrides[get_introspector] = lambda: (lambda *_a, **_k: None)
    written = []
    orig = datastructures.UploadFile.write

    async def spy(self, data):
        written.append(len(data))
        return await orig(self, data)

    monkeypatch.setattr(datastructures.UploadFile, "write", spy)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (30 * 1024 * 1024)
    r = TestClient(app).post(
        "/v1/public/submit/gss_unknowntoken_x",
        data={"payload": "{}"},
        files={"file": ("a.png", big, "image/png")},
    )
    print("status", r.status_code, "octets spooles avant le 404:", sum(written))
    assert r.status_code == 404
    assert sum(written) >= 30 * 1024 * 1024
