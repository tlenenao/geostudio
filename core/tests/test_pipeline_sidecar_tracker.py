# SPDX-License-Identifier: Apache-2.0
from app.pipelines.sidecar.tracker import RunRegistry


def test_create_returns_queued_record():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    records = registry.list("item-1", limit=10, offset=0)
    assert len(records) == 1
    assert records[0]["id"] == run_id
    assert records[0]["status"] == "queued"
    assert records[0]["startedAt"] is None
    assert records[0]["finishedAt"] is None
    assert records[0]["error"] is None
    assert records[0]["nodeStats"] == {}


def test_tracker_mark_running_sets_status_and_started_at():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_running()
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "running"
    assert record["startedAt"] is not None
    assert record["finishedAt"] is None


def test_tracker_mark_succeeded_sets_status_finished_at_and_stats():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_running()
    tracker.mark_succeeded({"n1": {"nodeId": "n1", "op": "reader.file", "rowCount": 2}})
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "succeeded"
    assert record["finishedAt"] is not None
    assert record["error"] is None
    assert record["nodeStats"] == {"n1": {"nodeId": "n1", "op": "reader.file", "rowCount": 2}}


def test_tracker_mark_failed_sets_status_and_error():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_failed("boom")
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "failed"
    assert record["error"] == "boom"
    assert record["finishedAt"] is not None


def test_list_orders_most_recent_first_and_paginates():
    registry = RunRegistry()
    run_a = registry.create("item-1")
    run_b = registry.create("item-1")
    records = registry.list("item-1", limit=1, offset=0)
    assert [r["id"] for r in records] == [run_b]
    records = registry.list("item-1", limit=1, offset=1)
    assert [r["id"] for r in records] == [run_a]


def test_list_unknown_item_id_returns_empty_list():
    registry = RunRegistry()
    assert registry.list("no-such-item", limit=10, offset=0) == []


def test_list_isolates_records_by_item_id():
    registry = RunRegistry()
    registry.create("item-1")
    assert registry.list("item-2", limit=10, offset=0) == []


def test_list_returns_a_snapshot_not_the_live_record():
    registry = RunRegistry()
    registry.create("item-1")

    records = registry.list("item-1", limit=10, offset=0)
    records[0]["nodeStats"]["x"] = 1

    records_again = registry.list("item-1", limit=10, offset=0)
    assert records_again[0]["nodeStats"] == {}
