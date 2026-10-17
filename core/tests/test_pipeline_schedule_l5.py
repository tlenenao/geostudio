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
