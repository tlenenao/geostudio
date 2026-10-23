# SPDX-License-Identifier: Apache-2.0
"""Réservation d'une opération client dans la transaction de l'écriture (même rollback)."""

import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collect.models import CollectClientOp

RETENTION_DAYS = 30
_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def parse_key(raw: str | None) -> str | None:
    """Valide l'en-tête `Idempotency-Key` (UUID du client) ; absent = pas d'idempotence."""
    if raw is None:
        return None
    if not _KEY_RE.match(raw):
        raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
    return raw


def claim(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    actor_id: str,
    kind: str,
    client_op_id: str,
) -> tuple[CollectClientOp, bool]:
    """Réserve (tenant, collection, acteur, kind, op). Retourne `(ligne, rejeu)`.

    `rejeu=True` : l'op existait déjà, `ligne.result` donne le résultat d'origine et l'appelant
    n'écrit rien. Course : la contrainte unique tranche (la perdante attend la fin de la
    gagnante, puis relit) ; si la gagnante annule, la perdante réussit son insertion."""
    row = CollectClientOp(
        tenant_id=tenant_id,
        collection_id=collection_id,
        actor_id=actor_id,
        kind=kind,
        client_op_id=client_op_id,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.execute(
            select(CollectClientOp).where(
                CollectClientOp.tenant_id == tenant_id,
                CollectClientOp.collection_id == collection_id,
                CollectClientOp.actor_id == actor_id,
                CollectClientOp.kind == kind,
                CollectClientOp.client_op_id == client_op_id,
            )
        ).scalar_one()
        session.refresh(existing)
        return existing, True
    return row, False


def record_result(session: Session, row: CollectClientOp, result: dict) -> None:
    row.result = result
    session.flush()


def purge_expired(session: Session, *, now: datetime | None = None) -> int:
    """Rétention de 30 jours (balayage cron des opérations déjà rejouables)."""
    cutoff = (now or datetime.now(UTC)).replace(tzinfo=None) - timedelta(days=RETENTION_DAYS)
    res = session.execute(delete(CollectClientOp).where(CollectClientOp.created_at < cutoff))
    return int(getattr(res, "rowcount", 0) or 0)
