# SPDX-License-Identifier: Apache-2.0
"""Jobs procrastinate du moteur de moissonnage (SP-12c) — run manuel
(POST /harvest/sources/{id}/run) et balayage périodique des sources dues.
Tourne dans le worker partagé (docker-compose.yml, cf. app.jobs pour la
raison de import_paths). Court-circuite en mode lecture seule/démo (SP-9) :
mutation hors requête HTTP, invisible au middleware ASGI read_only_guard."""

import logging

from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.jobs import app
from app.jobs.common import notify_best_effort
from app.jobs.engine import session_factory as common_session_factory

logger = logging.getLogger(__name__)


def _session_factory():
    return common_session_factory()


@app.task(queue="harvest")
def run_harvest_task(source_id: str, tenant_id: str) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : moissonnage de la source %s ignoré", source_id)
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        if not harvest_repo.mark_running(session, tenant_id=tenant_id, source_id=source_id):
            logger.warning("harvest source %s non prenable (déjà en cours ?)", source_id)
            return
    with request_scoped_session(session_factory) as session:
        source = harvest_repo.get_source(session, tenant_id=tenant_id, source_id=source_id)
        if source is None:
            logger.error("harvest source %s introuvable (tenant %s)", source_id, tenant_id)
            return
        service.harvest_source(session, source)
        outcome = (source.owner_id, source.url, source.last_status, source.last_error)
    # P20.12 : un moissonnage en échec prévient son propriétaire (best-effort,
    # session dédiée). Succès non notifié : le balayage tourne toutes les 15 min.
    if outcome[2] == "error":
        notify_best_effort(
            session_factory,
            tenant_id=tenant_id,
            recipient_user_id=outcome[0],
            kind="harvest",
            status="failure",
            item_id=None,
            item_resource_type=None,
            item_title=outcome[1],
            error=outcome[3],
        )


@app.periodic(cron="*/15 * * * *")
@app.task(queue="harvest", queueing_lock="run_harvest_sweep_task")
def run_harvest_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de moissonnage ignoré")
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = harvest_repo.list_due_sources(session)
        for source in due:
            run_harvest_task.defer(source_id=source.id, tenant_id=source.tenant_id)
