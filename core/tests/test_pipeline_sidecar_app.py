# SPDX-License-Identifier: Apache-2.0
import time

import pytest
from fastapi.testclient import TestClient

from app.pipelines.sidecar.app import create_sidecar_app


def _write_geojson(tmp_path, name: str):
    path = tmp_path / name
    path.write_text(
        '{"type":"FeatureCollection","features":['
        '{"type":"Feature","properties":{"label":"a"},'
        '"geometry":{"type":"Point","coordinates":[1,2]}},'
        '{"type":"Feature","properties":{"label":"b"},'
        '"geometry":{"type":"Point","coordinates":[3,4]}}]}'
    )
    return str(path)


def _payload_dict(in_path: str, out_path: str) -> dict:
    return {
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.file", "params": {"path": in_path}},
            {"id": "w1", "kind": "writer", "op": "writer.file", "params": {"path": out_path}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    }


@pytest.fixture
def client(tmp_path):
    app = create_sidecar_app(base_uri=str(tmp_path))
    return TestClient(app)


def test_get_ops_includes_reader_file_and_writer_file(client):
    res = client.get("/pipelines/ops")
    assert res.status_code == 200
    catalog = res.json()
    assert "reader.file" in catalog
    assert "writer.file" in catalog
    assert catalog["reader.file"]["kind"] == "reader"


def test_run_without_stored_payload_returns_404(client):
    res = client.post("/pipelines/no-such-item/run")
    assert res.status_code == 404


def test_put_then_run_then_poll_runs_until_succeeded(client, tmp_path):
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")

    put_res = client.put("/pipelines/item-1", json=_payload_dict(in_path, out_path))
    assert put_res.status_code == 204

    run_res = client.post("/pipelines/item-1/run")
    assert run_res.status_code == 202
    run_id = run_res.json()["runId"]
    assert isinstance(run_id, str) and run_id

    deadline = time.monotonic() + 10.0
    latest = None
    while time.monotonic() < deadline:
        runs_res = client.get("/pipelines/item-1/runs")
        assert runs_res.status_code == 200
        runs = runs_res.json()
        assert runs[0]["id"] == run_id
        if runs[0]["status"] in ("succeeded", "failed"):
            latest = runs[0]
            break
        time.sleep(0.05)
    assert latest is not None
    assert latest["status"] == "succeeded"
    assert set(latest["nodeStats"]) == {"r1", "w1"}


def test_runs_pagination_params_are_accepted(client):
    res = client.get("/pipelines/item-1/runs?limit=5&offset=0")
    assert res.status_code == 200
    assert res.json() == []


def test_preview_without_stored_payload_returns_404(client):
    res = client.post("/pipelines/no-such-item/preview?upTo=r1")
    assert res.status_code == 404


def test_put_then_preview_returns_rows(client, tmp_path):
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")
    client.put("/pipelines/item-2", json=_payload_dict(in_path, out_path))

    res = client.post("/pipelines/item-2/preview?upTo=r1")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert {row["label"] for row in rows} == {"a", "b"}
