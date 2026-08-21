# SPDX-License-Identifier: Apache-2.0
import uuid

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports.models import ReportRun
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_report_run_persists_and_defaults_notified_at_to_none():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
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
        report_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="report",
            title="Weekly report",
        )
        s.commit()

        run = ReportRun(
            id=uuid.uuid4().hex,
            tenant_id=tenant.id,
            report_item_id=report_item.id,
            export_job_id="job-1",
        )
        s.add(run)
        s.commit()
        s.refresh(run)

        assert run.notified_at is None
        assert run.created_at is not None
