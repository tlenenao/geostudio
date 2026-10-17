# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 5 (AUD-084) : fuseau, plancher, circuit-breaker, propriétaire anonymisé,
idempotence du webhook, succès notifié au seul rétablissement."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.configs.pipeline_validation import _check_min_interval
from app.configs.schemas import PipelineRefreshPolicy
from app.pipelines import repository as pipelines_repo
from app.pipelines.models import PipelineRun
from tests.test_pipeline_routes import (
    _defer_collector,
    _make_app,
    _promote_owner_to_admin,
    _seed_webhook_pipeline,
)


def test_refresh_policy_validates_timezone():
    PipelineRefreshPolicy(enabled=True, cron="0 6 * * *", timezone="Europe/Paris")
    with pytest.raises(ValueError):
        PipelineRefreshPolicy(enabled=True, cron="0 6 * * *", timezone="Mars/Olympus")


@pytest.mark.parametrize("cron", ["* * * * *", "*/2 * * * *", "0,1 * * * *"])
def test_write_validation_refuses_sub_five_minute_cron(cron):
    with pytest.raises(HTTPException, match="5 minutes"):
        _check_min_interval(cron)
    # lecture : un cron trop fréquent déjà en base reste lisible
    PipelineRefreshPolicy(enabled=True, cron=cron)


def test_write_validation_accepts_five_minutes():
    _check_min_interval("*/5 * * * *")


@pytest.mark.parametrize(("enabled", "refused"), [(True, True), (False, False)])
def test_cron_floor_applies_only_to_an_enabled_schedule(monkeypatch, enabled, refused):
    """Revue L5 : une planification désactivée ne tourne pas, son cron reste enregistrable."""
    from app.configs import repository as configs_repo
    from app.configs.pipeline_validation import validate_pipeline_payload
    from app.configs.schemas import BuilderConfig
    from app.users.models import User

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    with client.session_factory() as s:
        body = configs_repo.get_config_by_item(s, item_id).config.model_dump(by_alias=True)
        body["pipeline"]["refreshPolicy"] = {"enabled": enabled, "cron": "* * * * *"}
        config = BuilderConfig.model_validate(body)
        user = s.get(User, client.user.id)
        if refused:
            with pytest.raises(HTTPException, match="5 minutes"):
                validate_pipeline_payload(s, config, user=user)
        else:
            # le pipeline semé pointe une collection absente : seule l'erreur de cron compte ici
            with pytest.raises(HTTPException) as exc:
                validate_pipeline_payload(s, config, user=user)
            assert "5 minutes" not in str(exc.value.detail)


def test_next_run_honours_timezone(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    r = client.get("/v1/pipelines/next-run", params={"cron": "0 6 * * *", "tz": "Europe/Paris"})
    assert r.status_code == 200
    nxt = datetime.fromisoformat(r.json()["nextRun"])
    assert nxt.utcoffset() in (timedelta(hours=1), timedelta(hours=2))
    assert nxt.hour == 6
    bad = client.get("/v1/pipelines/next-run", params={"cron": "0 6 * * *", "tz": "Mars/X"})
    assert bad.status_code == 400


def _schedule(client, item_id, cron="*/5 * * * *", tz="UTC"):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig

    with client.session_factory() as s:
        cfg = configs_repo.get_config_by_item(s, item_id)
        body = cfg.config.model_dump(by_alias=True)
        body["pipeline"]["refreshPolicy"] = {"enabled": True, "cron": cron, "timezone": tz}
        configs_repo.update_config(
            s, cfg.id, BuilderConfig.model_validate(body), tenant_id=client.tenant.id
        )
        s.commit()


def _add_runs(client, item_id, statuses):
    with client.session_factory() as s:
        for i, st in enumerate(statuses):
            s.add(
                PipelineRun(
                    id=f"r{i}",
                    tenant_id=client.tenant.id,
                    pipeline_item_id=item_id,
                    status=st,
                    created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10 - i),
                )
            )
        s.commit()


def test_circuit_breaker_skips_after_three_consecutive_failures(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "failed"])
    with client.session_factory() as s:
        assert pipelines_repo.list_due_pipelines(s) == []


def test_two_failures_then_success_is_still_scheduled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "succeeded"])
    with client.session_factory() as s:
        assert [i for i, _ in pipelines_repo.list_due_pipelines(s)] == [item_id]


def test_cancelled_run_does_not_reset_the_circuit(monkeypatch):
    """Revue L5 I7 : un run annulé n'est ni succès ni échec."""
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "failed", "cancelled"])
    with client.session_factory() as s:
        assert pipelines_repo.list_due_pipelines(s) == []
        assert pipelines_repo.schedule_suspended(s, item_id=item_id)


def test_next_run_exposes_the_suspended_schedule(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _add_runs(client, item_id, ["failed", "failed", "failed"])
    q = {"cron": "*/5 * * * *", "itemId": item_id}
    assert client.get("/v1/pipelines/next-run", params=q).json()["scheduleSuspended"] is True
    q.pop("itemId")
    assert client.get("/v1/pipelines/next-run", params=q).json()["scheduleSuspended"] is False


@pytest.mark.parametrize(
    ("statuses", "opened"),
    [
        (["succeeded", "failed", "failed", "failed"], True),
        (["failed", "failed", "failed"], True),
        (["failed", "failed", "failed", "failed"], False),
        (["failed", "failed"], False),
    ],
)
def test_circuit_just_opened(monkeypatch, statuses, opened):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _add_runs(client, item_id, statuses)
    with client.session_factory() as s:
        assert pipelines_repo.circuit_just_opened(s, item_id=item_id) is opened


def test_failure_that_opens_the_circuit_says_so_once(monkeypatch):
    from sqlalchemy import select

    from app.notifications.models import Notification
    from app.pipelines import jobs as pipeline_jobs

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "failed"])
    args = {"tenant_id": client.tenant.id, "item_id": item_id, "status": "failure"}
    pipeline_jobs._notify(client.session_factory, error="boom", **args)
    _add_runs_from(client, item_id, 3, ["failed"])
    pipeline_jobs._notify(client.session_factory, error="boom2", **args)
    with client.session_factory() as s:
        msgs = {
            n.error_message.split(" — ")[0]: n.error_message
            for n in s.scalars(select(Notification).where(Notification.item_id == item_id))
        }
    assert "planification suspendue" in msgs["boom"]
    assert msgs["boom2"] == "boom2"


def _add_runs_from(client, item_id, start, statuses):
    with client.session_factory() as s:
        for i, st in enumerate(statuses, start):
            s.add(
                PipelineRun(
                    id=f"r{i}", tenant_id=client.tenant.id, pipeline_item_id=item_id,
                    status=st, created_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )  # fmt: skip
        s.commit()


def test_erased_owner_is_never_scheduled(monkeypatch):
    from app.users.models import User

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["succeeded"])  # dû sans l'anonymisation
    with client.session_factory() as s:
        assert [i for i, _ in pipelines_repo.list_due_pipelines(s)] == [item_id]
        s.get(User, client.user.id).erased_at = datetime.now(UTC).replace(tzinfo=None)
        s.commit()
        assert pipelines_repo.list_due_pipelines(s) == []


def test_cron_is_evaluated_in_the_policy_timezone(monkeypatch):
    """« 0 6 * * * » à Paris (UTC+2 en été) tombe à 04:00 UTC, pas à 06:00 UTC."""
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id, cron="0 6 * * *", tz="Europe/Paris")
    with client.session_factory() as s:
        s.add(
            PipelineRun(
                id="r0",
                tenant_id=client.tenant.id,
                pipeline_item_id=item_id,
                status="succeeded",
                created_at=datetime(2026, 7, 1, 12, 0),
            )
        )
        s.commit()
        at_0430_utc = datetime(2026, 7, 2, 4, 30, tzinfo=UTC)
        assert [i for i, _ in pipelines_repo.list_due_pipelines(s, now=at_0430_utc)] == [item_id]
        at_0330_utc = datetime(2026, 7, 2, 3, 30, tzinfo=UTC)
        assert pipelines_repo.list_due_pipelines(s, now=at_0330_utc) == []


def test_previous_run_failed(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _add_runs(client, item_id, ["failed", "running"])
    with client.session_factory() as s:
        assert pipelines_repo.previous_run_failed(s, item_id=item_id, run_id="r1")
        assert not pipelines_repo.previous_run_failed(s, item_id=item_id, run_id="r0")


def test_webhook_idempotency_key_returns_the_same_run(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    raw = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    deferred = _defer_collector(client)
    h = {"Authorization": f"Bearer {raw}", "Idempotency-Key": "evt-42"}
    first = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    second = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["runId"] == second.json()["runId"]
    assert len(deferred) == 1


def test_concurrent_idempotency_collision_returns_the_existing_run(monkeypatch):
    """Revue L5 : la 2e livraison concurrente passe la 1re lecture (run pas encore committé)
    puis heurte l'index unique — elle renvoie le run existant, pas une 500."""
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    with client.session_factory() as s:
        s.add(
            PipelineRun(
                id="done", tenant_id=client.tenant.id, pipeline_item_id=item_id,
                status="succeeded", idempotency_key="evt-7",
            )
        )  # fmt: skip
        s.commit()
    real_find = pipelines_repo.find_run_by_idempotency_key
    calls = []

    def racing_find(*a, **kw):
        calls.append(1)
        return None if len(calls) == 1 else real_find(*a, **kw)

    monkeypatch.setattr(pipelines_repo, "find_run_by_idempotency_key", racing_find)
    raw = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    _defer_collector(client)
    h = {"Authorization": f"Bearer {raw}", "Idempotency-Key": "evt-7"}
    r = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    assert r.status_code == 202 and r.json()["runId"] == "done"


def test_webhook_409_carries_retry_after(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    raw = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    _defer_collector(client)
    h = {"Authorization": f"Bearer {raw}"}
    client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    r = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    assert r.status_code == 409 and r.headers["Retry-After"] == "60"


def test_file_trigger_passes_only_declared_object_params(monkeypatch):
    """AUD-084 : l'objet S3 déclencheur alimente les paramètres déclarés du pipeline (et
    seulement eux : resolve_params refuse tout paramètre inconnu)."""
    from sqlalchemy import select

    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig
    from app.db import init_db, make_engine, make_session_factory
    from app.outbox.models import FileTrigger
    from app.webhooks import triggers
    from tests.test_webhooks_outbox import KEY_B64, _lister, _pipeline, _seed

    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", KEY_B64)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    db = make_session_factory(engine)
    tenant_id, user_id = _seed(db)
    item_id = _pipeline(db, tenant_id, user_id)
    with db() as s:
        cfg = configs_repo.get_config_by_item(s, item_id)
        body = cfg.config.model_dump(by_alias=True)
        body["pipeline"]["parameters"] = [{"name": "objectKey", "required": True}]
        configs_repo.update_config(
            s, cfg.id, BuilderConfig.model_validate(body), tenant_id=tenant_id
        )
        s.commit()
    now = datetime.now(UTC).replace(tzinfo=None)
    with db() as s:
        t = s.get(FileTrigger, "t1")
        n = triggers.poll_trigger(
            s, t, defer_task=lambda r, tn: None, lister=_lister([("in/a.csv", "e1", now)])
        )
        assert n == 1 and t.last_error is None
        run = s.scalars(select(PipelineRun).where(PipelineRun.pipeline_item_id == item_id)).one()
        assert run.params == {"objectKey": "in/a.csv"}
