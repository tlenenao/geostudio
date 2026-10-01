# SPDX-License-Identifier: Apache-2.0
"""Fabrique de sessions des tâches worker, sans autre dépendance que app.db
(importable depuis app.items/app.collections sans violer le contrat de couches)."""

import os

from sqlalchemy import Engine
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


def session_factory() -> sessionmaker[Session]:
    """Engine + session factory depuis `DATABASE_URL` (repli SQLite mémoire pour ne
    jamais casser la collecte pytest sur un process sans cette variable)."""
    return make_session_factory(
        _engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    )
