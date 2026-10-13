# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F4 : lecture incrémentale des readers connecteurs."""

import duckdb
import pytest
from sqlalchemy import text

from app.configs.schemas import PipelinePayload
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.reader_state import apply_incremental
from app.pipelines.registries import READERS
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture partagée)


def _table(rows):
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t(id INTEGER, ts TIMESTAMP)")
    for i, ts in rows:
        conn.execute("INSERT INTO t VALUES (?, ?)", [i, ts])
    return conn


def test_apply_incremental_first_run_keeps_everything_and_returns_max():
    conn = _table([(1, "2026-01-01"), (2, "2026-01-02")])
    assert apply_incremental(conn, "t", "ts", None) == "2026-01-02 00:00:00"
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 2


def test_apply_incremental_keeps_only_strictly_newer_rows():
    conn = _table([(1, "2026-01-01"), (2, "2026-01-02"), (3, "2026-01-03")])
    cursor = apply_incremental(conn, "t", "ts", "2026-01-02 00:00:00")
    assert cursor == "2026-01-03 00:00:00"
    assert conn.execute("SELECT id FROM t").fetchall() == [(3,)]


def test_apply_incremental_empty_delta_keeps_cursor():
    conn = _table([(1, "2026-01-01")])
    assert apply_incremental(conn, "t", "ts", "2026-02-01 00:00:00") == "2026-02-01 00:00:00"
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 0


def test_apply_incremental_stored_cursor_is_bound_not_interpolated():
    conn = _table([(1, "2026-01-01")])
    with pytest.raises(PipelineRuntimeError):
        apply_incremental(conn, "t", "ts", "1'); DROP TABLE t; --")
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1


def test_apply_incremental_unknown_column():
    with pytest.raises(PipelineRuntimeError, match="absente"):
        apply_incremental(_table([]), "t", "nope", None)


def _payload(expr="true"):
    return PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.connector.rest",
                    "params": {
                        "baseUrl": "https://example.test",
                        "incremental": {"cursorField": "pop"},
                    },
                },
                {
                    "id": "t1",
                    "kind": "transform",
                    "op": "transform.filter",
                    "params": {"expr": expr},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.collection",
                    "params": {"collectionId": "villes_propres"},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "w1"},
            ],
        }
    )


def _run(app, Session, tenant, item_id):
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id
    pipeline_jobs.run_pipeline_task(run_id=run_id, tenant_id=tenant.id)  # appel synchrone
    with Session() as s:
        return pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)


@pytest.mark.postgis
def test_second_run_only_brings_newer_rows_and_failure_keeps_cursor(env, monkeypatch):  # noqa: F811
    app, Session, tenant, user, item_id = env
    source = {"max": 3}

    def fake_reader(conn, *, node_id, view_name, **_):
        conn.execute(
            f"CREATE TEMP TABLE {view_name} AS SELECT 'R' AS region, i AS pop, "
            f"ST_Point(1, 45) AS geometry FROM range(1, {source['max'] + 1}) t(i)"
        )
        return 4326

    monkeypatch.setitem(READERS, "reader.connector.rest", fake_reader)
    current = {"payload": _payload()}
    monkeypatch.setattr(
        pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: current["payload"]
    )

    def count():
        with Session() as s:
            return s.execute(text("SELECT count(*) FROM villes_propres")).scalar()

    def cursors():
        with Session() as s:
            return pipelines_repo.get_reader_states(
                s, tenant_id=tenant.id, pipeline_item_id=item_id
            )

    assert _run(app, Session, tenant, item_id).status == "succeeded"
    assert count() == 3
    assert cursors() == {"r1": "3"}

    # Échec en aval : le curseur n'avance pas, rien n'est (re)lu comme « déjà vu ».
    source["max"] = 5
    current["payload"] = _payload(expr="CAST('x' AS INTEGER) > 1")
    failed = _run(app, Session, tenant, item_id)
    assert failed.status == "failed"
    assert cursors() == {"r1": "3"}
    assert count() == 3

    current["payload"] = _payload()
    assert _run(app, Session, tenant, item_id).status == "succeeded"
    assert count() == 5  # seules pop 4 et 5 ajoutées
    assert cursors() == {"r1": "5"}

    # Pas de nouvelle donnée : 0 ligne ajoutée.
    assert _run(app, Session, tenant, item_id).status == "succeeded"
    assert count() == 5

    # Réinitialisation : tout est relu.
    with Session() as s:
        pipelines_repo.delete_reader_states(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
    assert _run(app, Session, tenant, item_id).status == "succeeded"
    assert count() == 10


@pytest.mark.postgis
def test_reader_state_is_deleted_with_the_pipeline_item(env):  # noqa: F811
    _app, Session, tenant, _user, item_id = env
    with Session() as s:
        pipelines_repo.upsert_reader_states(
            s, tenant_id=tenant.id, pipeline_item_id=item_id, cursors={"r1": "9"}
        )
        s.commit()
        s.execute(text("DELETE FROM pipeline_runs"))
        s.execute(text("DELETE FROM items WHERE id = :i"), {"i": item_id})
        s.commit()
        assert s.execute(text("SELECT count(*) FROM pipeline_reader_state")).scalar() == 0
