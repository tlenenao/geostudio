# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (ARC-14) : évalue les règles `constraint`/`batch` d'une collection sur
toutes ses entités et écrit un rapport de qualité (jamais de modification des données)."""

import dataclasses
import logging

from app.auth.dependency import is_read_only_mode
from app.collections import repository as collections_repo
from app.collections.domains import strip_hidden_rules, with_attribute_rules
from app.collections.introspection import hide_sensitive_columns
from app.collections.introspection_pg import introspect_table
from app.db import request_scoped_session
from app.jobs import app
from app.jobs.common import session_factory
from app.quality import repository as quality_repo
from app.quality.runner import run_batch

logger = logging.getLogger(__name__)


@app.task(queue="etl")
def run_quality_check_task(report_id: str, tenant_id: str) -> None:
    factory = session_factory()
    try:
        with request_scoped_session(factory) as session:
            report = quality_repo.get_report(session, report_id, tenant_id)
            if report is None:
                logger.error("rapport de qualité %s introuvable", report_id)
                return
            if not quality_repo.mark_running(session, report_id):
                return
            col = collections_repo.get_collection(
                session, tenant_id=tenant_id, collection_id=report.collection_id
            )
            if col is None:
                quality_repo.mark_failed(session, report_id, "collection not found")
                return
            info = with_attribute_rules(introspect_table(session, col.table_name), col)
            masked = report.masked
            if masked:
                info = hide_sensitive_columns(info, col.sensitive_fields)
                rules = strip_hidden_rules(info.rules, col.sensitive_fields)
                info = dataclasses.replace(info, rules=rules)
        with request_scoped_session(factory) as session:
            checked, summary, violations = run_batch(
                session, info, tenant_id=tenant_id, masked=masked
            )
        with request_scoped_session(factory) as session:
            quality_repo.mark_done(
                session, report_id, checked=checked, summary=summary, violations=violations
            )
    except Exception as exc:  # jamais de rapport zombie
        logger.exception("rapport de qualité %s : échec", report_id)
        with request_scoped_session(factory) as session:
            quality_repo.mark_failed(session, report_id, f"erreur interne : {exc}")


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl", queueing_lock="sweep_quality_reports_task")
def sweep_quality_reports_task(timestamp: int) -> None:
    """Reprise : `pending` au defer perdu (piège n°14) et `running` d'un worker tué."""
    if is_read_only_mode():
        return
    factory = session_factory()
    with request_scoped_session(factory) as session:
        quality_repo.reclaim_stuck_running(session)
        session.commit()
        for report_id, tenant_id in quality_repo.stale_pending_ids(session):
            run_quality_check_task.defer(report_id=report_id, tenant_id=tenant_id)
