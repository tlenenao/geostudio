# SPDX-License-Identifier: Apache-2.0
"""P09 (RC-9) : intégrité des écritures — commit annoncé avant d'avoir eu lieu
(c02-001) et suppression d'un item portant de l'historique (c03-001)."""

from sqlalchemy.orm import Session as SASession

from app.main import create_app
from app.pipelines import repository as pipelines_repo
from tests.test_pipeline_routes import _make_app, _promote_owner_to_admin, _seed_webhook_pipeline

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


def test_delete_pipeline_item_with_run_history_succeeds(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    with client.session_factory() as s:
        pipelines_repo.create_run(s, tenant_id=client.tenant.id, pipeline_item_id=item_id)
        s.commit()
    assert client.post(f"/v1/pipelines/{item_id}/webhook-tokens").status_code in (200, 201)

    assert client.delete(f"/v1/items/{item_id}").status_code == 204
