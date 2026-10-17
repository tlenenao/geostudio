# SPDX-License-Identifier: Apache-2.0
"""Rétention du journal d'audit (AUD-092) : archive JSONL sur S3, PUIS suppression.

`CORE_AUDIT_RETENTION_DAYS` (0 ou absent = conservation illimitée, défaut). Une ligne n'est
supprimée qu'une fois scellée ET archivée (archive = lignes complètes, payload compris, avec
la chaîne de hachage : vérifiable hors base). Un échec S3 n'efface rien."""

import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.audit.chain import audit_maintenance, seal_all
from app.audit.models import AuditLog
from app.audit.store import put_object

MAX_ROWS_PER_PASS = 5000


def retention_days() -> int:
    try:
        return max(int(os.environ.get("CORE_AUDIT_RETENTION_DAYS", "0")), 0)
    except ValueError:
        return 0


def row_to_dict(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "tenantId": row.tenant_id,
        "actorId": row.actor_id,
        "actorKind": row.actor_kind,
        "action": row.action,
        "objectType": row.object_type,
        "objectId": row.object_id,
        "payload": row.payload,
        "createdAt": row.created_at.isoformat(),
        "chainSeq": row.chain_seq,
        "prevHash": row.prev_hash,
        "hash": row.hash,
    }


def apply_retention(
    session: Session, s3, *, days: int | None = None, now: datetime | None = None
) -> int:
    """Archive puis supprime les lignes plus vieilles que `days`. Retourne le nombre supprimé."""
    days = retention_days() if days is None else days
    if days <= 0:
        return 0
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=days)).replace(tzinfo=None)
    tenants = session.scalars(
        select(AuditLog.tenant_id).where(AuditLog.created_at < cutoff).distinct()
    ).all()
    deleted = 0
    for tenant_id in tenants:
        seal_all(session, tenant_id)
        # Les lignes périmées forment un préfixe de la chaîne : on coupe au plus grand
        # chain_seq périmé, jamais au milieu d'un lot de lignes plus récentes.
        last = session.scalar(
            select(func.max(AuditLog.chain_seq)).where(
                AuditLog.tenant_id == tenant_id, AuditLog.created_at < cutoff
            )
        )
        if last is None:
            continue
        rows = session.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id, AuditLog.chain_seq <= last)
            .order_by(AuditLog.chain_seq)
            .limit(MAX_ROWS_PER_PASS)
        ).all()
        if not rows:
            continue
        key = f"audit/{tenant_id}/{rows[0].chain_seq:012d}-{rows[-1].chain_seq:012d}.jsonl"
        put_object(s3, key, "\n".join(json.dumps(row_to_dict(r)) for r in rows).encode())
        with audit_maintenance(session):
            session.execute(
                delete(AuditLog).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.chain_seq >= rows[0].chain_seq,
                    AuditLog.chain_seq <= rows[-1].chain_seq,
                )
            )
        deleted += len(rows)
    return deleted
