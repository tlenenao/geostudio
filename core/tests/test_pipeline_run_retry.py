# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F5 : retry automatique et reprise par nœud d'un run de pipeline."""

import os
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, PipelinePayload
from app.pipelines import checkpoints, compiler
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.pipelines.registries import READERS
from app.pipelines.service import retry_pipeline_run_service
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture partagée)


def _payload(retry):
    return PipelinePayload.model_validate(
        {
            "retry": retry,
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.connector.rest",
                    "params": {"baseUrl": "https://example.test"},
                },
                {
                    "id": "t1",
                    "kind": "transform",
                    "op": "transform.filter",
                    "params": {"expr": "pop >= 0"},
                },
                {
                    "id": "t2",
                    "kind": "transform",
                    "op": "transform.filter",
                    "params": {"expr": "region = 'R'"},
                },
                {
                    "id": "t3",
                    "kind": "transform",
                    "op": "transform.filter",
                    "params": {"expr": "pop >= 1"},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.collection",
                    "params": {"collectionId": "villes_propres", "mode": "replace"},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "t2"},
                {"id": "e3", "from": "t2", "to": "t3"},
                {"id": "e4", "from": "t3", "to": "w1"},
            ],
        }
    )


@pytest.fixture()
def rig(env, monkeypatch, tmp_path):  # noqa: F811
    app, Session, tenant, user, item_id = env
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_DIR", str(tmp_path / "ckpt"))
    state = {"reader_calls": 0, "fail_t3": True, "compiled": [], "retry": {"max": 0}}

    def fake_reader(conn, *, node_id, view_name, **_):
        state["reader_calls"] += 1
        conn.execute(
            f"CREATE TEMP TABLE {view_name} AS SELECT 'R' AS region, i AS pop, "
            "ST_Point(1, 45) AS geometry FROM range(1, 4) t(i)"
        )
        return 4326

    monkeypatch.setitem(READERS, "reader.connector.rest", fake_reader)
    real_compile = compiler.compile_transform_sql

    def spy_compile(op, params, **kw):
        state["compiled"].append(params.get("expr"))
        if state["fail_t3"] and params.get("expr") == "pop >= 1":
            raise duckdb.Error("boom simulé")
        return real_compile(op, params, **kw)

    monkeypatch.setattr(compiler, "compile_transform_sql", spy_compile)
    monkeypatch.setattr(
        pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: _payload(state["retry"])
    )
    with Session() as s:
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": _payload(None).model_dump(by_alias=True),
                }
            ),
            item_id=item_id,
            tenant_id=tenant.id,
        )
        s.commit()
    return app, Session, tenant, user, item_id, state


def _new_run(Session, tenant, item_id):
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        return run.id


def _exec(Session, tenant, run_id):
    pipeline_jobs.run_pipeline_task(run_id=run_id, tenant_id=tenant.id)  # appel synchrone
    with Session() as s:
        run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        s.expunge(run)
        return run


def _rows(Session):
    with Session() as s:
        return s.execute(text("SELECT count(*) FROM villes_propres")).scalar()


@pytest.mark.postgis
def test_manual_resume_does_not_replay_succeeded_nodes(rig):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert r1.status == "failed"
    assert state["compiled"] == ["pop >= 0", "region = 'R'", "pop >= 1"]
    assert state["reader_calls"] == 1
    assert checkpoints.exists(tenant.id, r1.id)

    state["fail_t3"] = False
    deferred: list = []
    with Session() as s:
        new_id = retry_pipeline_run_service(
            s, user=user, run_id=r1.id, defer_task=lambda *a: deferred.append(a)
        )
    assert deferred == [(new_id, tenant.id)]
    r2 = _exec(Session, tenant, new_id)
    assert r2.status == "succeeded", r2.error
    assert state["compiled"][3:] == ["pop >= 1"]  # seul t3 rejoué
    assert state["reader_calls"] == 1  # la source n'est pas relue
    assert _rows(Session) == 3
    assert r2.resume_of == r1.id
    assert not checkpoints.exists(tenant.id, r1.id)  # nettoyé après succès


@pytest.mark.postgis
def test_replay_from_start_reruns_everything(rig):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    state["fail_t3"] = False
    with Session() as s:
        new_id = retry_pipeline_run_service(
            s, user=user, run_id=r1.id, defer_task=lambda *a: None, from_start=True
        )
    r2 = _exec(Session, tenant, new_id)
    assert r2.status == "succeeded", r2.error
    assert state["reader_calls"] == 2
    assert r2.resume_of is None


@pytest.mark.postgis
def test_config_change_invalidates_checkpoints(rig):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert checkpoints.exists(tenant.id, r1.id)
    changed = _payload({"max": 0})
    changed.nodes[1].params["expr"] = "pop >= -1"
    assert (
        checkpoints.Checkpoint(tenant.id, r1.id, checkpoints.config_fingerprint(changed)).usable
        is False
    )


@pytest.mark.postgis
def test_concurrent_retry_is_refused_and_a_retry_can_be_cancelled(rig):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    with Session() as s:
        new_id = retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    with Session() as s, pytest.raises(HTTPException) as exc:
        retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    assert exc.value.status_code == 409
    with Session() as s:
        run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=new_id)
        assert pipelines_repo.request_cancel(s, run) == "cancelled"
        s.commit()
    # Le job déféré arrive après l'annulation : il ne doit rien exécuter.
    calls = state["reader_calls"]
    assert _exec(Session, tenant, new_id).status == "cancelled"
    assert state["reader_calls"] == calls
    # Seul un run échoué se reprend.
    with Session() as s, pytest.raises(HTTPException) as exc:
        retry_pipeline_run_service(s, user=user, run_id=new_id, defer_task=lambda *a: None)
    assert exc.value.status_code == 409


@pytest.mark.postgis
def test_automatic_retry_with_backoff_then_success(rig):
    app, Session, tenant, user, item_id, state = rig
    state["retry"] = {"max": 2, "backoff": "exponential", "delaySeconds": 5}
    run_id = _new_run(Session, tenant, item_id)
    r = _exec(Session, tenant, run_id)
    assert (r.status, r.attempt) == ("retrying", 2)
    assert r.next_retry_at is not None and r.error
    # Un run `retrying` compte comme actif (verrou).
    with Session() as s, pytest.raises(pipelines_repo.PipelineRunActive):
        pipelines_repo.create_run_unless_active(s, tenant_id=tenant.id, pipeline_item_id=item_id)

    state["fail_t3"] = False
    r = _exec(Session, tenant, run_id)  # le job planifié arrive
    assert r.status == "succeeded", r.error
    assert r.attempt == 2
    assert state["compiled"][3:] == ["pop >= 1"]
    assert state["reader_calls"] == 1
    assert _rows(Session) == 3


@pytest.mark.postgis
def test_automatic_retry_gives_up_after_max(rig):
    _app, Session, tenant, user, item_id, state = rig
    state["retry"] = {"max": 1, "backoff": "fixed", "delaySeconds": 1}
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    last = _exec(Session, tenant, run_id)
    assert last.status == "failed"
    assert last.attempt == 2


@pytest.mark.postgis
def test_cancelling_a_retrying_run(rig):
    _app, Session, tenant, user, item_id, state = rig
    state["retry"] = {"max": 3, "delaySeconds": 60}
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    with Session() as s:
        run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert pipelines_repo.request_cancel(s, run) == "cancelled"
        s.commit()
    calls = state["reader_calls"]
    assert _exec(Session, tenant, run_id).status == "cancelled"  # job planifié : sans effet
    assert state["reader_calls"] == calls


@pytest.mark.postgis
def test_sweep_requeues_retries_whose_defer_was_lost(rig):
    _app, Session, tenant, user, item_id, state = rig
    state["retry"] = {"max": 3, "delaySeconds": 60}
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    with Session() as s:
        assert pipelines_repo.requeue_overdue_retries(s) == []  # pas encore échu
        late = datetime.now(UTC) + timedelta(hours=1)
        assert pipelines_repo.requeue_overdue_retries(s, now=late) == [(run_id, tenant.id)]
        # La grâce repart : un 2e balayage immédiat ne re-défère pas.
        assert pipelines_repo.requeue_overdue_retries(s, now=late) == []
        s.commit()


def test_checkpoint_dir_is_purged_after_retention(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_DIR", str(tmp_path))
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_RETENTION_HOURS", "0")
    checkpoints.Checkpoint("t-1", "run-x", "fp")
    assert (tmp_path / "t-1" / "run-x").is_dir()
    assert checkpoints.purge_expired() == [("t-1", "run-x")]
    assert not (tmp_path / "t-1").exists()


def test_checkpoint_files_are_private_and_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_DIR", str(tmp_path / "base"))
    cp = checkpoints.Checkpoint("t-1", "run-x", "fp")
    conn = duckdb.connect()
    conn.execute("CREATE TEMP VIEW v AS SELECT 1 AS a")
    cp.save(conn, "n1", "v", 4326)
    mode = lambda p: os.stat(p).st_mode & 0o777  # noqa: E731
    assert mode(tmp_path / "base") == 0o700
    assert mode(tmp_path / "base" / "t-1") == 0o700
    assert mode(cp.dir) == 0o700
    assert {mode(os.path.join(cp.dir, f)) for f in os.listdir(cp.dir)} == {0o600}
    checkpoints.purge_tenant("t-1")
    assert not (tmp_path / "base" / "t-1").exists()


@pytest.mark.postgis
def test_purge_expired_clears_resumable(rig, monkeypatch):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert r1.status == "failed" and r1.resumable is True
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_RETENTION_HOURS", "0")
    expired = checkpoints.purge_expired()
    assert (tenant.id, r1.id) in expired
    with Session() as s:
        pipelines_repo.clear_resumable_for_roots(s, [r for _, r in expired])
        s.commit()
        assert pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=r1.id).resumable is False


def test_automatic_retry_with_append_writer_is_refused_at_validation():
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"].pop("mode")  # défaut = append
    payload["retry"] = {"max": 2}
    with pytest.raises(ValueError, match="upsert"):
        PipelinePayload.model_validate(payload)
    payload["retry"] = {"max": 0}  # sans reprise auto : accepté
    PipelinePayload.model_validate(payload)


@pytest.mark.postgis
def test_retry_route_refuses_append_writer(rig):
    _app, Session, tenant, user, item_id, state = rig
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    append = _payload(None).model_dump(by_alias=True)
    append["nodes"][-1]["params"].pop("mode")
    with Session() as s:  # nouvelle révision de config avec un writer append
        configs_repo.update_config(
            s,
            configs_repo.get_config_by_item(s, item_id).id,
            BuilderConfig.model_validate({"version": 1, "kind": "pipeline", "pipeline": append}),
            tenant_id=tenant.id,
        )
        s.commit()
    with Session() as s, pytest.raises(HTTPException) as exc:
        retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    assert exc.value.status_code == 409 and "upsert" in exc.value.detail
