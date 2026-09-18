# SPDX-License-Identifier: Apache-2.0
import time

from app.configs.schemas import PipelinePayload
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry


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


def _file_to_file_payload(in_path: str, out_path: str) -> PipelinePayload:
    return PipelinePayload.model_validate(
        {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.file", "params": {"path": in_path}},
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.file",
                    "params": {"path": out_path},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )


def _wait_until_finished(
    registry: RunRegistry, item_id: str, run_id: str, *, timeout: float = 10.0
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = next(r for r in registry.list(item_id, limit=10, offset=0) if r["id"] == run_id)
        if record["status"] in ("succeeded", "failed"):
            return record
        time.sleep(0.05)
    raise AssertionError("run did not finish within timeout")


def test_start_run_returns_none_when_no_payload_stored():
    store = PipelineStore()
    registry = RunRegistry()
    assert start_run(store, registry, "no-such-item", base_uri="/tmp") is None


def test_start_run_executes_pipeline_and_marks_succeeded(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")
    store = PipelineStore()
    registry = RunRegistry()
    store.set("item-1", _file_to_file_payload(in_path, out_path))

    run_id = start_run(store, registry, "item-1", base_uri=str(tmp_path))
    assert run_id is not None

    record = _wait_until_finished(registry, "item-1", run_id)
    assert record["status"] == "succeeded"
    assert set(record["nodeStats"]) == {"r1", "w1"}
    import os

    assert os.path.exists(out_path)


def test_start_run_marks_failed_on_bad_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    store = PipelineStore()
    registry = RunRegistry()
    store.set(
        "item-1",
        _file_to_file_payload(str(tmp_path / "missing.geojson"), str(tmp_path / "out.gpkg")),
    )

    run_id = start_run(store, registry, "item-1", base_uri=str(tmp_path))
    record = _wait_until_finished(registry, "item-1", run_id)
    assert record["status"] == "failed"
    assert record["error"]


def test_pipeline_store_get_returns_none_for_unknown_item():
    store = PipelineStore()
    assert store.get("no-such-item") is None
