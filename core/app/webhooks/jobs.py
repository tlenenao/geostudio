# SPDX-License-Identifier: Apache-2.0
"""Tâches périodiques de l'outbox et des déclencheurs fichier (ARC4-F6, ADR 0027).
L'émission n'ouvre aucun `.defer()` (elle est dans la transaction de l'écriture) : le
balayage est donc à la fois le mécanisme de livraison et la reprise des lignes
`pending` (piège n°14). Latence de livraison = période du balayage."""

import logging

from sqlalchemy import select

from app.auth.dependency import is_etl_enabled, is_read_only_mode
from app.db import request_scoped_session
from app.jobs import app
from app.jobs.common import session_factory as _session_factory
from app.outbox.models import FileTrigger
from app.pipelines.service import default_task_deferrer
from app.webhooks import delivery, triggers

logger = logging.getLogger(__name__)


@app.periodic(cron="* * * * *")
@app.task(queue="etl", queueing_lock="deliver_outbox_task")
def deliver_outbox_task(timestamp: int) -> None:
    if is_read_only_mode():
        return
    with request_scoped_session(_session_factory()) as session:
        delivery.deliver_due(session)


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl", queueing_lock="poll_file_triggers_task")
def poll_file_triggers_task(timestamp: int) -> None:
    if is_read_only_mode() or not is_etl_enabled():
        return
    defer = default_task_deferrer()
    with request_scoped_session(_session_factory()) as session:
        ids = session.scalars(select(FileTrigger.id).where(FileTrigger.enabled.is_(True))).all()
        for trigger_id in ids:
            trigger = session.get(FileTrigger, trigger_id)
            if trigger is not None:
                triggers.poll_trigger(session, trigger, defer_task=defer)
