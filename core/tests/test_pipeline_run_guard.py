# SPDX-License-Identifier: Apache-2.0
"""AUD-083/AUD-029 : annulation et durée maximale d'un run, hors writers par lots."""

import threading

import duckdb
import pytest

from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.pipelines import runtime
from app.pipelines.errors import (
    PipelineCancelledError,
    PipelineRuntimeError,
    PipelineTerminatedError,
)
from app.pipelines.registries import READERS
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture partagée)
from tests.test_pipeline_run_retry import _exec, _new_run, _payload, _rows, rig  # noqa: F401

# Requête qui ne finit pas en un temps de test sans interruption.
_ENDLESS = "SELECT max(hash(r)) FROM range(100000000000) t(r)"


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    monkeypatch.setattr(runtime, "_GUARD_POLL_S", 0.05)


def test_cancel_interrupts_a_running_duckdb_query():
    conn = duckdb.connect()
    with pytest.raises(PipelineCancelledError):
        with runtime._RunGuard(conn, lambda: True, timeout_s=3600):
            conn.execute(_ENDLESS)


def test_deadline_terminates_the_run_without_retry():
    conn = duckdb.connect()
    with pytest.raises(PipelineTerminatedError, match="durée maximale"):
        with runtime._RunGuard(conn, None, timeout_s=0.1):
            conn.execute(_ENDLESS)


def test_an_interrupt_wrapped_by_an_op_is_still_translated():
    conn = duckdb.connect()
    with pytest.raises(PipelineCancelledError):
        with runtime._RunGuard(conn, lambda: True, timeout_s=3600):
            try:
                conn.execute(_ENDLESS)
            except duckdb.Error as exc:
                raise PipelineRuntimeError(str(exc)) from exc


def test_a_query_started_after_the_stop_request_is_still_interrupted():
    """Une demande d'arrêt tombée entre deux requêtes (code Python d'une op) ne doit pas
    laisser filer la requête DuckDB suivante."""
    conn = duckdb.connect()
    stop = threading.Event()
    with pytest.raises(PipelineCancelledError):
        with runtime._RunGuard(conn, stop.is_set, timeout_s=3600):
            stop.set()
            threading.Event().wait(0.3)  # plusieurs tours du fil, aucune requête en cours
            conn.execute(_ENDLESS)


def test_a_failing_cancel_probe_does_not_disable_the_deadline():
    def broken():
        raise RuntimeError("base indisponible")

    conn = duckdb.connect()
    with pytest.raises(PipelineTerminatedError):
        with runtime._RunGuard(conn, broken, timeout_s=0.3):
            conn.execute(_ENDLESS)


def test_guard_is_silent_when_nothing_happens():
    conn = duckdb.connect()
    with runtime._RunGuard(conn, lambda: False, timeout_s=3600) as guard:
        assert conn.execute("SELECT 1").fetchone() == (1,)
        guard.check()
        assert guard.should_stop() is False


@pytest.mark.postgis
def test_cancel_requested_during_the_read_stops_before_any_transform(rig, monkeypatch):  # noqa: F811
    _app, Session, tenant, user, item_id, state = rig
    state["fail_t3"] = False
    run_id = _new_run(Session, tenant, item_id)

    def cancelling_reader(conn, *, node_id, view_name, **_):
        with Session() as s:
            run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
            pipelines_repo.request_cancel(s, run)
            s.commit()
        conn.execute(
            f"CREATE TEMP TABLE {view_name} AS SELECT 'R' AS region, 1 AS pop, "
            "ST_Point(1, 45) AS geometry"
        )
        return 4326

    monkeypatch.setitem(READERS, "reader.connector.rest", cancelling_reader)
    run = _exec(Session, tenant, run_id)
    assert run.status == "cancelled"
    assert state["compiled"] == []  # avant AUD-083 : t1, t2, t3 exécutés malgré l'annulation
    assert _rows(Session) == 0


@pytest.mark.postgis
def test_append_writer_failure_rolls_back_and_is_retried(rig, monkeypatch):  # noqa: F811
    """AUD-083 : writer.collection écrit dans la transaction du run ; un échec APRÈS lui
    annule ses lignes, le retry automatique ne duplique rien."""
    _app, Session, tenant, user, item_id, state = rig
    state["fail_t3"] = False
    state["retry"] = {"max": 1, "backoff": "fixed", "delaySeconds": 1}

    def append_payload(retry):
        p = _payload(None).model_dump(by_alias=True)
        p["nodes"][-1]["params"].pop("mode")  # défaut = append
        p["retry"] = retry
        return runtime.PipelinePayload.model_validate(p)

    state["payload_fn"] = append_payload
    fail = {"on": True}

    def progress(factory, *, run_id, tenant_id):
        def cb(stat):
            if fail["on"] and getattr(stat, "nodeId", None) == "w1":
                raise PipelineRuntimeError("échec après l'écriture")

        return cb

    monkeypatch.setattr(pipeline_jobs, "_make_progress_callback", progress)
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    assert _rows(Session) == 0
    fail["on"] = False
    assert _exec(Session, tenant, run_id).status == "succeeded"
    assert _rows(Session) == 3


@pytest.mark.postgis
def test_append_rows_and_success_status_commit_together(rig, monkeypatch):  # noqa: F811
    """Revue finale L1b, I1 : un échec à l'écriture du statut `succeeded` après le commit
    des données faisait rejouer (retry auto ou reprise manuelle) un append déjà écrit."""
    _app, Session, tenant, user, item_id, state = rig
    state["fail_t3"] = False
    state["retry"] = {"max": 1, "backoff": "fixed", "delaySeconds": 1}

    def append_payload(retry):
        p = _payload(None).model_dump(by_alias=True)
        p["nodes"][-1]["params"].pop("mode")
        p["retry"] = retry
        return runtime.PipelinePayload.model_validate(p)

    state["payload_fn"] = append_payload
    real = pipelines_repo.mark_succeeded
    calls = {"n": 0}

    def flaky_mark_succeeded(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connexion perdue")
        return real(*a, **kw)

    monkeypatch.setattr(pipelines_repo, "mark_succeeded", flaky_mark_succeeded)
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    assert _rows(Session) == 0  # données et statut annulés ensemble
    assert _exec(Session, tenant, run_id).status == "succeeded"
    assert _rows(Session) == 3
