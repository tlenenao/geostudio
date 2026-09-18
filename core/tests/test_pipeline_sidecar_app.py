# SPDX-License-Identifier: Apache-2.0
import asyncio
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


def _cyclic_payload_dict(in_path: str, out_path: str) -> dict:
    # r1 -> t1 -> t2 -> t1 (cycle) et t2 -> w1 : le PUT du sidecar ne
    # valide pas la forme du graphe (contrairement au cœur, cf. Fix 1) —
    # seul le POST preview/run le découvre, via
    # app.pipelines.compiler.topological_order (ValueError bare).
    return {
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.file", "params": {"path": in_path}},
            {
                "id": "t1",
                "kind": "transform",
                "op": "transform.filter",
                "params": {"expr": "true"},
            },
            {
                "id": "t2",
                "kind": "transform",
                "op": "transform.filter",
                "params": {"expr": "true"},
            },
            {"id": "w1", "kind": "writer", "op": "writer.file", "params": {"path": out_path}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"},
            {"id": "e2", "from": "t1", "to": "t2"},
            {"id": "e3", "from": "t2", "to": "t1"},
            {"id": "e4", "from": "t2", "to": "w1"},
        ],
    }


def test_preview_on_cyclic_graph_returns_400_not_500(client, tmp_path):
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")
    put_res = client.put("/pipelines/item-cycle", json=_cyclic_payload_dict(in_path, out_path))
    assert put_res.status_code == 204

    res = client.post("/pipelines/item-cycle/preview?upTo=t1")
    assert res.status_code == 400
    assert "acyclic" in res.json()["detail"]


def test_get_ops_excludes_session_dependent_ops(client):
    catalog = client.get("/pipelines/ops").json()
    for op in (
        "reader.collection",
        "writer.collection",
        "writer.dataset",
        "writer.export",
        "reader.connector.rest",
        "reader.connector.postgres",
        "reader.connector.snowflake",
    ):
        assert op not in catalog, f"{op} touche Session mais est exposé par le sidecar"


def test_get_ops_still_includes_transform_ops(client):
    catalog = client.get("/pipelines/ops").json()
    assert "transform.filter" in catalog
    assert catalog["transform.filter"]["kind"] == "transform"


def test_runs_rejects_negative_limit(client):
    res = client.get("/pipelines/item-1/runs?limit=-1")
    assert res.status_code == 422


def test_runs_rejects_negative_offset(client):
    res = client.get("/pipelines/item-1/runs?offset=-1")
    assert res.status_code == 422


def test_runs_large_limit_does_not_error(client):
    res = client.get("/pipelines/item-1/runs?limit=5000")
    assert res.status_code == 200
    assert res.json() == []


def test_default_app_has_no_auth_and_ignores_host(client):
    # Unauthenticated fixture (token=None, the default) — behavior for
    # every other test in this file must stay exactly as before this task.
    res = client.get("/pipelines/ops", headers={"Host": "anything-goes.example"})
    assert res.status_code == 200


@pytest.fixture
def authed_client(tmp_path):
    app = create_sidecar_app(base_uri=str(tmp_path), token="s3cr3t")
    return TestClient(app, base_url="http://127.0.0.1")


def test_authed_app_rejects_missing_authorization_header(authed_client):
    res = authed_client.get("/pipelines/ops")
    assert res.status_code == 401


def test_authed_app_rejects_wrong_token(authed_client):
    res = authed_client.get("/pipelines/ops", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_authed_app_accepts_correct_token(authed_client):
    res = authed_client.get("/pipelines/ops", headers={"Authorization": "Bearer s3cr3t"})
    assert res.status_code == 200


def test_authed_app_rejects_spoofed_host_header(authed_client):
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t", "Host": "evil.example.com"},
    )
    assert res.status_code == 400


def test_authed_app_accepts_host_with_port_suffix(authed_client):
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t", "Host": "127.0.0.1:9999"},
    )
    assert res.status_code == 200


def test_authed_app_allows_missing_host_header(authed_client):
    # httpx always sends Host in practice; this documents the deliberate
    # choice (design §4) to only reject a Host header that is PRESENT and
    # wrong, never to require one — see the plan's rationale in Task 1.
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t"},
        extensions={},
    )
    assert res.status_code == 200


def test_authed_app_rejects_non_ascii_authorization_header_without_crashing(tmp_path):
    # Regression test: non-ASCII in Authorization header must return 401, not 500.
    # TestClient/httpx can't send raw non-ASCII headers (client-side validation),
    # so drive the ASGI app directly with a raw scope.
    app = create_sidecar_app(base_uri=str(tmp_path), token="s3cr3t")

    async def run():
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/pipelines/ops",
            "headers": [(b"authorization", b"Bearer \xe9")],
            "query_string": b"",
            "server": ("127.0.0.1", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "root_path": "",
        }
        status_holder = {}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]

        await app(scope, receive, send)
        return status_holder.get("status")

    status = asyncio.run(run())
    assert status == 401
