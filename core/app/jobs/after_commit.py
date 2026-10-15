# SPDX-License-Identifier: Apache-2.0
"""Exécute un callback (typiquement un `.defer()` procrastinate) APRÈS le commit de
la session, jamais avant : un job déféré avant le commit peut démarrer alors que la
ligne n'est pas encore visible, et reste orphelin si la transaction échoue
(piège n°14, REV-346). Un rollback abandonne les callbacks en attente.

Module sans dépendance interne : importable depuis les repositories sans cycle."""

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

_KEY = "after_commit_callbacks"


def run_after_commit(session: Session, callback: Callable[[], None]) -> None:
    session.info.setdefault(_KEY, []).append(callback)


@event.listens_for(Session, "after_commit")
def _fire(session: Session) -> None:
    for callback in session.info.pop(_KEY, []):
        callback()


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_KEY, None)
