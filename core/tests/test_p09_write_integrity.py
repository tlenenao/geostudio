# SPDX-License-Identifier: Apache-2.0
"""P09 (RC-9) : intégrité des écritures — commit annoncé avant d'avoir eu lieu
(c02-001)."""

from sqlalchemy.orm import Session as SASession

from app.main import create_app

_MAP = {
    "title": "Carte perdue",
    "config": {
        "kind": "map",
        "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
    },
}


def test_failing_commit_is_not_reported_as_success(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'p09.db'}")
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    from app.db import init_db, make_engine

    init_db(make_engine(f"sqlite+pysqlite:///{tmp_path / 'p09.db'}"))
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.headers["Authorization"] = "Bearer mock:alice"

    def failing_commit(self):
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as m:
        m.setattr(SASession, "commit", failing_commit)
        resp = client.post("/v1/configs", json=_MAP)

    assert resp.status_code >= 500
