# SPDX-License-Identifier: Apache-2.0
"""Jobs procrastinate du moteur de moissonnage (SP-12c) — run manuel
(POST /harvest/sources/{id}/run) et balayage périodique des sources dues.
Tourne dans le worker partagé (docker-compose.yml, cf. app.jobs pour la
raison de import_paths). Court-circuite en mode lecture seule/démo (SP-9) :
mutation hors requête HTTP, invisible au middleware ASGI read_only_guard."""
import logging
import os

from app.auth.dependency import is_read_only_mode
from app.db import make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


@app.task(queue="harvest")
def run_harvest_task(source_id: str, tenant_id: str) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : moissonnage de la source %s ignoré", source_id)
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        harvest_repo.mark_running(session, tenant_id=tenant_id, source_id=source_id)
    with request_scoped_session(session_factory) as session:
        source = harvest_repo.get_source(session, tenant_id=tenant_id, source_id=source_id)
        if source is None:
            logger.error("harvest source %s introuvable (tenant %s)", source_id, tenant_id)
            return
        service.harvest_source(session, source)


@app.periodic(cron="*/15 * * * *")
@app.task(queue="harvest")
def run_harvest_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de moissonnage ignoré")
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = harvest_repo.list_due_sources(session)
        for source in due:
            run_harvest_task.defer(source_id=source.id, tenant_id=source.tenant_id)
