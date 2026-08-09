# SPDX-License-Identifier: Apache-2.0
"""Procrastinate task for ReportSchedule (design SP-17b §2) — mirrors
app.alerts.jobs/app.pipelines.jobs exactly: a periodic sweep, two steps per
tick (trigger due schedules, then notify runs whose render finished),
commit-before-defer inside the per-item loop for the same reason as
run_pipeline_sweep_task. Permission is re-verified at trigger time against
the report's OWNER (not the schedule's creator, if those ever diverge —
mirrors app.alerts.jobs._owner_user): a report whose owner lost read access
to its bookmark/app fails cleanly (audited, no render) rather than either
crashing the sweep or silently rendering with elevated rights."""
import logging
import os

from sqlalchemy import select

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task
from app.items import repository as items_repo
from app.items.models import Item
from app.jobs import app
from app.reports import repository as reports_repo
from app.reports.ctx import encode_analytics_context
from app.sharing.authorization import can
from app.users.models import User

logger = logging.getLogger(__name__)


class ReportTriggerError(Exception):
    """Anything that keeps a due report from being rendered — always caught,
    always turns into an audit_log entry, never a crash of the sweep."""


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _owner_user(session, *, tenant_id: str, item_id: str) -> User:
    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise ReportTriggerError(f"report schedule '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _trigger_due_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        due = reports_repo.list_due_reports(session)
        for item_id, tenant_id in due:
            try:
                config = configs_repo.get_config_by_item(session, item_id)
                if config is None or config.kind != "report":
                    continue
                payload = config.config.report
                assert payload is not None

                owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)

                bookmark_facts = items_repo.get_access_facts(
                    session, tenant_id=tenant_id, item_id=payload.bookmarkItemId,
                )
                if bookmark_facts is None or not can(session, user_id=owner.id, action="read", item=bookmark_facts):
                    raise ReportTriggerError("bookmark not readable by report owner")

                bookmark_config = configs_repo.get_config_by_item(session, payload.bookmarkItemId)
                if bookmark_config is None or bookmark_config.kind != "bookmark":
                    raise ReportTriggerError("bookmark config not found")
                bookmark = bookmark_config.config.bookmark
                assert bookmark is not None

                app_facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=bookmark.appId)
                if app_facts is None or not can(session, user_id=owner.id, action="read", item=app_facts):
                    raise ReportTriggerError("target app not readable by report owner")

                ctx = encode_analytics_context(bookmark)
                job = export_repo.create_job(
                    session, tenant_id=tenant_id, item_id=bookmark.appId, user_id=owner.id, format="pdf",
                    page_id=bookmark.pageId, ctx=ctx,
                )
                run = reports_repo.create_run(
                    session, tenant_id=tenant_id, report_item_id=item_id, export_job_id=job.id,
                )
                write_audit(
                    session, tenant_id=tenant_id, actor_id=owner.id, actor_kind="agent",
                    action="report.run", object_type="report_run", object_id=run.id,
                    payload={"reportItemId": item_id, "exportJobId": job.id, "success": True},
                )
                session.commit()
                render_export_task.defer(job_id=job.id, tenant_id=tenant_id)
            except ReportTriggerError as exc:
                logger.warning("report %s trigger failed: %s", item_id, exc)
                write_audit(
                    session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                    action="report.run", object_type="item", object_id=item_id,
                    payload={"success": False, "error": str(exc)},
                )
                session.commit()
        export_repo.reclaim_stuck_jobs(session)
        session.commit()
