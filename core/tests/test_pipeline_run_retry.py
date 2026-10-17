# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F5 : retry automatique et reprise par nœud d'un run de pipeline."""

import os
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, PipelinePayload, PipelineRetryPolicy
from app.pipelines import checkpoints, compiler, runtime
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.registries import READERS, WRITERS
from app.pipelines.runtime import NodeStat
from app.pipelines.service import retry_pipeline_run_service
from app.quotas.service import QuotaExceededError
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
        pipeline_jobs,
        "_get_pipeline_payload",
        lambda session, item_id: state.get("payload_fn", _payload)(state["retry"]),
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


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "../x"])
def test_purge_tenant_refuses_unsafe_tenant_id(bad, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_CHECKPOINT_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        checkpoints.purge_tenant(bad)


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


def test_automatic_retry_with_append_writer_is_accepted():
    """AUD-083 : l'append de writer.collection est dans la transaction du run."""
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"].pop("mode")  # défaut = append
    payload["retry"] = {"max": 2}
    assert PipelinePayload.model_validate(payload).append_writers() == []


@pytest.mark.postgis
def test_retry_route_accepts_append_writer(rig):
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
    with Session() as s:
        new_id = retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    assert isinstance(new_id, str)


@pytest.mark.parametrize("mode", ["upsert", "update", "delete", "replace"])
def test_automatic_retry_accepts_idempotent_writer_modes(mode):
    """K1×K2 (intégration vague 4) : les modes de writer.collection (F1) sont compatibles
    avec retry.max > 0 — `append`/`insert` compris depuis AUD-083."""
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"] = {"collectionId": "villes", "mode": mode, "keyColumns": ["id"]}
    payload["retry"] = {"max": 2}
    assert PipelinePayload.model_validate(payload).append_writers() == []


def test_automatic_retry_accepts_insert_alias_of_append():
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"] = {"collectionId": "villes", "mode": "insert"}
    payload["retry"] = {"max": 2}
    assert PipelinePayload.model_validate(payload).append_writers() == []


# --- Revue finale de branche (vague 4) : C1 / I1 ----------------------------------------


def _two_writers(retry):
    p = _payload(retry).model_dump(by_alias=True)
    p["nodes"][0]["params"]["incremental"] = {"cursorField": "pop"}
    p["nodes"].append(
        {
            "id": "w2",
            "kind": "writer",
            "op": "writer.collection",
            "params": {"collectionId": "villes_propres", "mode": "replace"},
        }
    )
    p["edges"].append({"id": "e5", "from": "t3", "to": "w2"})
    return PipelinePayload.model_validate(p)


def _spy_writers(monkeypatch, state):
    """w2 échoue tant que `fail_w2` (puis « réussit » sans écrire) ; w1 peut publier une
    progression puis buter sur un quota (`quota_w1`, une fois)."""
    real = WRITERS["writer.collection"]

    def spy(session, conn, *, node, **kw):
        if node.id == "w2":
            if state.get("fail_w2"):
                raise PipelineRuntimeError("boom w2")
            return NodeStat(node.id, node.op, 0)
        if state.get("quota_w1"):
            state["quota_w1"] = False
            kw["on_progress"](NodeStat(node.id, node.op, 2))  # commitée hors transaction du run
            raise QuotaExceededError("collections", 1, 1, "quota atteint")
        return real(session, conn, node=node, **kw)

    monkeypatch.setitem(WRITERS, "writer.collection", spy)


def _cursors(Session, tenant, item_id):
    with Session() as s:
        return pipelines_repo.get_reader_states(s, tenant_id=tenant.id, pipeline_item_id=item_id)


@pytest.mark.postgis
def test_retry_replays_a_writer_that_succeeded_before_the_failure(rig, monkeypatch):
    """C1 (a)+(c) : w1 réussit puis w2 échoue — la transaction du run (écritures de w1
    comprises) est annulée, mais la progression de w1 est commitée à part. Le retry doit
    rejouer w1 (sinon : run « succeeded » sans ligne écrite) et le curseur incrémental
    n'avance qu'avec les lignes réellement écrites."""
    _app, Session, tenant, user, item_id, state = rig
    state.update(
        fail_t3=False,
        fail_w2=True,
        retry={"max": 1, "backoff": "fixed", "delaySeconds": 1},
        payload_fn=_two_writers,
    )
    _spy_writers(monkeypatch, state)
    run_id = _new_run(Session, tenant, item_id)
    r = _exec(Session, tenant, run_id)
    assert r.status == "retrying" and "w1" in (r.node_stats or {})
    assert _rows(Session) == 0 and _cursors(Session, tenant, item_id) == {}

    state["fail_w2"] = False
    r = _exec(Session, tenant, run_id)
    assert r.status == "succeeded", r.error
    assert _rows(Session) == 3  # w1 rejoué : ses lignes sont bien là
    assert set(_cursors(Session, tenant, item_id)) == {"r1"}


@pytest.mark.postgis
def test_resume_after_a_quota_failure_mid_writer_never_succeeds_empty(rig, monkeypatch):
    """C1 (b) : un quota atteint après une progression publiée laisse `w1` dans node_stats ;
    la reprise doit écrire les lignes (ou échouer), jamais finir `succeeded` à vide."""
    _app, Session, tenant, user, item_id, state = rig
    state.update(fail_t3=False, quota_w1=True, retry={"max": 0})
    _spy_writers(monkeypatch, state)
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert r1.status == "failed" and "w1" in (r1.node_stats or {})
    with Session() as s:
        new_id = retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    r2 = _exec(Session, tenant, new_id)
    assert r2.status == "succeeded", r2.error
    assert _rows(Session) == 3


def _collection_reader(retry):
    p = _payload(retry).model_dump(by_alias=True)
    p["nodes"][0] = {
        "id": "r1",
        "kind": "reader",
        "op": "reader.collection",
        "params": {"collectionId": "villes"},
    }
    return PipelinePayload.model_validate(p)


@pytest.mark.postgis
@pytest.mark.parametrize("change", ["revoke", "mask"])
def test_resume_rechecks_reader_access_rights(rig, monkeypatch, change):
    """I1 : une reprise ne relit pas la source d'un reader déjà réussi — mais si le droit de
    lecture, les limites géographiques ou le masquage ont changé depuis l'échec, les points
    de reprise sont invalidés : la source est relue (et un accès retiré fait échouer)."""
    _app, Session, tenant, user, item_id, state = rig
    state["payload_fn"] = _collection_reader
    access = {"readable": True, "masked": frozenset()}

    def check(session, *, tenant_id, user, collection_id):
        if not access["readable"]:
            raise PipelineRuntimeError(f"collection '{collection_id}' not found")
        return collection_id

    monkeypatch.setattr(runtime, "_require_readable_collection_id", check)
    monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: access["masked"])
    connector = READERS["reader.connector.rest"]  # faux reader du rig

    def collection_reader(conn, *, session, tenant_id, params, user, **kw):
        runtime._require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=params["collectionId"]
        )
        return connector(conn, **kw)

    monkeypatch.setitem(READERS, "reader.collection", collection_reader)
    r1 = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert r1.status == "failed" and state["reader_calls"] == 1

    if change == "revoke":
        access["readable"] = False
    else:
        access["masked"] = frozenset({"pop"})
    state["fail_t3"] = False
    with Session() as s:
        new_id = retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    r2 = _exec(Session, tenant, new_id)
    if change == "revoke":
        assert r2.status == "failed" and "not found" in (r2.error or "")
    else:  # source relue sous le nouveau masquage (le point de reprise n'est pas réutilisé)
        assert state["reader_calls"] == 2


# --- Revue finale de branche FME : I1 (writers externes) / I2 (rasters publiés) -----------


def _email_then_failing_writer(retry):
    """w1 = writer.email (effet externe irréversible) réussit, puis w2 échoue."""
    p = _payload(None).model_dump(by_alias=True)
    p["nodes"][-1] = {
        "id": "w1",
        "kind": "writer",
        "op": "writer.email",
        "params": {"secretName": "smtp", "to": "a@example.org"},
    }
    p["nodes"].append(
        {
            "id": "w2",
            "kind": "writer",
            "op": "writer.collection",
            "params": {"collectionId": "villes_propres", "mode": "replace"},
        }
    )
    p["edges"].append({"id": "e5", "from": "t3", "to": "w2"})
    payload = PipelinePayload.model_validate(p)
    # Config stockée AVANT la garde de validation : retry.max > 0 malgré writer.email.
    payload.retry = None if retry is None else PipelineRetryPolicy.model_validate(retry)
    return payload


def test_automatic_retry_with_external_effect_writer_is_refused_at_validation():
    p = _email_then_failing_writer(None).model_dump(by_alias=True)
    p["retry"] = {"max": 2}
    with pytest.raises(ValueError, match="non idempotent"):
        PipelinePayload.model_validate(p)
    p["retry"] = {"max": 0}  # sans reprise auto : accepté (reprise manuelle refusée)
    assert PipelinePayload.model_validate(p).append_writers() == ["w1"]


@pytest.mark.postgis
def test_external_writer_is_never_replayed_by_retry_or_resume(rig, monkeypatch):
    """I1 de bout en bout : w1 (email) envoie, w2 échoue. Même avec une politique retry.max=2
    (config antérieure à la garde), le run finit `failed` sans retry automatique, et la reprise
    manuelle est refusée : les messages ne repartent jamais."""
    _app, Session, tenant, user, item_id, state = rig
    sent: list[str] = []
    state.update(
        fail_t3=False,
        retry={"max": 2, "backoff": "fixed", "delaySeconds": 1},
        payload_fn=_email_then_failing_writer,
    )

    def fake_email(session, conn, *, node, **kw):
        sent.append(node.id)
        return NodeStat(node.id, node.op, 3, {"sent": 3})

    def failing_collection(session, conn, *, node, **kw):
        raise PipelineRuntimeError("boom w2")

    monkeypatch.setitem(WRITERS, "writer.email", fake_email)
    monkeypatch.setitem(WRITERS, "writer.collection", failing_collection)
    r = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert r.status == "failed" and r.next_retry_at is None, (r.status, r.error)
    assert sent == ["w1"]
    with Session() as s:  # la config stockée porte le writer externe
        configs_repo.update_config(
            s,
            configs_repo.get_config_by_item(s, item_id).id,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": _email_then_failing_writer(None).model_dump(by_alias=True),
                }
            ),
            tenant_id=tenant.id,
        )
        s.commit()
    with Session() as s, pytest.raises(HTTPException) as exc:
        retry_pipeline_run_service(s, user=user, run_id=r.id, defer_task=lambda *a: None)
    assert exc.value.status_code == 409 and "w1" in exc.value.detail
    assert sent == ["w1"]


def _publishing_reader(monkeypatch, state):
    """r1 publie un raster (vraie chaîne publish_raster, S3/COG simulés) à chaque lecture."""
    from types import SimpleNamespace

    from app.raster import publish

    state["deleted"], state["uploaded"], state["items"] = [], [], []
    monkeypatch.setattr(publish, "can_publish", lambda session, user: True)
    monkeypatch.setattr(
        publish.ingest, "to_cog", lambda src, dst, **kw: open(dst, "wb").write(b"cog")
    )
    monkeypatch.setattr(
        publish.ingest,
        "read_metadata",
        lambda path: SimpleNamespace(
            srid=4326,
            bounds=[0, 0, 1, 1],
            width=1,
            height=1,
            dtype="uint8",
            nodata=None,
            bands=[],
        ),  # fmt: skip
    )
    monkeypatch.setattr(publish, "_upload", lambda s, t, key, path: state["uploaded"].append(key))
    monkeypatch.setattr(publish, "delete_key", lambda key: state["deleted"].append(key))

    def reader(conn, *, node_id, view_name, session, user, **_):
        state["reader_calls"] += 1
        tmp = os.path.join(os.environ["CORE_PIPELINE_CHECKPOINT_DIR"], "..", "pub.tif")
        pub = publish.publish_raster(
            session, user, tif_path=tmp, cog_path=tmp + ".cog", title="r",
            limit_collection_id=None, filename="r.tif",
        )  # fmt: skip
        state["items"].append(pub.item_id)
        conn.execute(
            f"CREATE TEMP TABLE {view_name} AS SELECT 'R' AS region, i AS pop, "
            "ST_Point(1, 45) AS geometry FROM range(1, 4) t(i)"
        )
        return 4326

    monkeypatch.setitem(READERS, "reader.connector.rest", reader)


@pytest.mark.postgis
def test_published_raster_is_never_resumed_from_a_checkpoint(rig, monkeypatch):
    """I2 : r1 publie un raster (item créé par flush dans la transaction du run), t3 échoue.
    Le rollback annule l'item : le COG du run est supprimé (quota de stockage cohérent) et
    aucun point de reprise n'est écrit après la publication — le retry republie au lieu de
    recharger un `raster_item_id` fantôme."""
    from app.raster.models import RasterAsset

    _app, Session, tenant, user, item_id, state = rig
    state["retry"] = {"max": 1, "backoff": "fixed", "delaySeconds": 1}
    _publishing_reader(monkeypatch, state)
    run_id = _new_run(Session, tenant, item_id)
    r = _exec(Session, tenant, run_id)
    assert r.status == "retrying", r.error
    assert state["deleted"] == state["uploaded"] and len(state["uploaded"]) == 1
    with Session() as s:
        assert s.get(RasterAsset, state["items"][0]) is None  # annulé avec la transaction

    state["fail_t3"] = False
    r = _exec(Session, tenant, run_id)
    assert r.status == "succeeded", r.error
    assert state["reader_calls"] == 2  # republié, jamais rechargé depuis un point de reprise
    assert len(state["uploaded"]) == 2 and state["deleted"] == state["uploaded"][:1]
    with Session() as s:
        assert s.get(RasterAsset, state["items"][1]) is not None
