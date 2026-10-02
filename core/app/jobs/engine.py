# SPDX-License-Identifier: Apache-2.0
"""Fabrique de sessions des tâches worker, sans autre dépendance que app.db
(importable depuis app.items/app.collections sans violer le contrat de couches)."""

import logging
import os

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine, make_session_factory

_engines: dict[str, Engine] = {}


def _engine(url: str) -> Engine:
    """Un Engine par URL et par process worker, créé paresseusement (c02-013) :
    avant, chaque exécution de tâche en créait un (pool compris), jamais libéré.
    SQLite mémoire exclu du cache : chaque appel y est volontairement une base
    neuve (tests)."""
    if "memory" in url:
        return make_engine(url)
    if url not in _engines:
        _engines[url] = make_engine(url)
    return _engines[url]


logger = logging.getLogger(__name__)


def session_factory() -> sessionmaker[Session]:
    """Engine + session factory depuis `DATABASE_URL` (repli SQLite mémoire pour ne
    jamais casser la collecte pytest sur un process sans cette variable)."""
    return make_session_factory(
        _engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    )


def jobs_backlog() -> dict | None:
    """Santé de la file procrastinate (t02-013/j09-014) : nombre de jobs `todo` et
    âge du plus ancien. Un worker arrêté se voit à un âge qui grandit. None si la
    table est absente ou la base injoignable (la route reste disponible)."""
    try:
        with session_factory()() as session:
            n, oldest = session.execute(
                text(
                    # scheduled_at est NULL pour un defer() immédiat : l'âge se lit alors
                    # sur l'événement « deferred » (un seul par job).
                    "SELECT COUNT(*), "
                    "EXTRACT(EPOCH FROM now() - MIN(COALESCE(j.scheduled_at, e.at))) "
                    "FROM procrastinate_jobs j LEFT JOIN procrastinate_events e "
                    "ON e.job_id = j.id AND e.type = 'deferred' "
                    "WHERE j.status = 'todo' "
                    "AND (j.scheduled_at IS NULL OR j.scheduled_at <= now())"
                )
            ).one()
    except Exception:
        logger.debug("file de jobs illisible pour /health", exc_info=True)
        return None
    return {"todo": int(n), "oldestTodoAgeSeconds": None if oldest is None else int(oldest)}
