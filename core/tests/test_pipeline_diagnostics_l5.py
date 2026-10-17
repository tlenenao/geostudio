# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 6 : nœud fautif, expression refusée en 400, aperçu d'un brouillon non
enregistré, horodatages UTC explicites."""

from datetime import datetime

import pytest
from sqlalchemy import text

from app.analytics.sql_sandbox import SqlSandboxError
from app.configs.schemas import PipelineNode
from app.db import Base, make_session_factory
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.routes import iso_utc
from app.pipelines.runtime import _node_error
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_pipeline_routes import _make_app, _seed_preview_pipeline

DRAFT = {
    "nodes": [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "y"}},
        {
            "id": "w1",
            "kind": "writer",
            "op": "writer.export",
            "params": {"format": "csv", "key": "o.csv"},
        },
    ],
    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
}


def test_node_error_carries_the_node_id():
    node = PipelineNode(id="n7", kind="transform", op="transform.filter", params={"expr": "1"})
    assert _node_error(node, Exception("boom")).node_id == "n7"
    assert PipelineRuntimeError("x").node_id is None


def test_iso_utc_marks_naive_datetimes_as_utc():
    assert iso_utc(None) is None
    assert iso_utc(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05+00:00"


def test_unsaved_draft_preview_route(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    seen = {}

    def fake(*, payload, **kw):
        seen["c"] = payload.nodes[0].params["collectionId"]
        return [{"id": 1}]

    monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake)
    r = client.post("/v1/pipelines/preview?upTo=r1", json={"pipeline": DRAFT})
    assert r.status_code == 200 and seen["c"] == "y"


def test_unsaved_draft_preview_requires_a_body(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    assert client.post("/v1/pipelines/preview?upTo=r1", json={}).status_code == 422


def test_preview_maps_sandbox_and_value_errors_to_400(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_preview_pipeline(client)
    for exc in (SqlSandboxError("fonction interdite"), ValueError("param invalide")):

        def fake(*, payload, _e=exc, **kw):
            raise _e

        monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake)
        r = client.post(f"/v1/pipelines/{item_id}/preview?upTo=r1")
        assert r.status_code == 400, exc


@pytest.mark.postgis
def test_mark_failed_stores_a_long_node_id_on_postgres(pg_engine):
    """Revue L5 I3 : un id de nœud non borné ne doit pas faire lever mark_failed
    (StringDataRightTruncation → run zombie). SQLite n'impose aucune longueur."""
    Base.metadata.create_all(pg_engine)
    factory = make_session_factory(pg_engine)
    node_id = "n" * 300
    with factory() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="l5-i3", username="l5-i3",
            email=None, first_name="", last_name="",
        )  # fmt: skip
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="P"
        )
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item.id)
        s.commit()
        run_id, item_id = run.id, item.id
    try:
        with factory() as s:
            pipelines_repo.mark_failed(s, run_id=run_id, error="boom", failed_node_id=node_id)
            s.commit()
        with factory() as s:
            run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
            assert run is not None and run.failed_node_id == node_id
    finally:
        with factory() as s:
            s.execute(text("DELETE FROM pipeline_runs WHERE id = :r"), {"r": run_id})
            s.execute(text("DELETE FROM items WHERE id = :i"), {"i": item_id})
            s.commit()
