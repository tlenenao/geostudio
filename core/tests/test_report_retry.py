# SPDX-License-Identifier: Apache-2.0
"""AUD-058 : rejeu d'un rendu de rapport en erreur, résolution d'export, format du rapport."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, PrintLayout
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.export.rendering import export_scale
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_CRON = "0 3 1 1 *"  # annuel : seul le rattrapage peut rendre le rapport « dû »


def _body(retry: dict | None) -> dict:
    report: dict = {
        "bookmarkItemId": "bookmark-1",
        "refreshPolicy": {"enabled": True, "cron": _CRON},
        "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
    }
    if retry is not None:
        report["retry"] = retry
    return {"kind": "report", "report": report}


def test_failed_render_is_retried_after_the_delay_until_attempts_run_out():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="report", title="R"
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(_body({"maxAttempts": 2, "delayMinutes": 15})),
            item_id=item.id,
            tenant_id=tenant.id,
        )
        s.commit()

        def failed_run(age_minutes: int):
            job = export_repo.create_job(
                s, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
            )
            export_repo.mark_error(s, job_id=job.id, error="boom")
            run = reports_repo.create_run(
                s, tenant_id=tenant.id, report_item_id=item.id, export_job_id=job.id
            )
            run.created_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
            s.commit()
            return run

        first = failed_run(5)
        assert reports_repo.list_due_reports(s) == []  # délai de 15 min non écoulé
        assert reports_repo.retry_scheduled(s, first)

        first.created_at = datetime.now(UTC) - timedelta(minutes=20)
        s.commit()
        assert (item.id, tenant.id) in reports_repo.list_due_reports(s)

        second = failed_run(20)  # 2e essai raté : maxAttempts (2) atteint
        first.created_at = datetime.now(UTC) - timedelta(minutes=40)
        s.commit()
        assert reports_repo.list_due_reports(s) == []
        assert not reports_repo.retry_scheduled(s, second)


def test_report_format_and_retry_are_validated():
    cfg = BuilderConfig.model_validate(_body(None))
    assert cfg.report.format == "pdf" and cfg.report.retry is None
    body = _body({"maxAttempts": 9})
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
    body = _body(None)
    body["report"]["format"] = "docx"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_export_scale_follows_dpi_and_caps_the_long_side():
    assert export_scale(None) == 150 / 96
    assert export_scale(PrintLayout(dpi=96)) == 1.0
    big = export_scale(PrintLayout(pageSize="a3", dpi=600))
    assert 1.0 <= big < 600 / 96
