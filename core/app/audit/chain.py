# SPDX-License-Identifier: Apache-2.0
"""Intégrité du journal d'audit (AUD-092) : maintenance explicite, scellement et vérification.

`audit_log` est append-only (trigger `audit_log_guard`, migration 0120). Deux exceptions,
toutes deux explicites :
- `audit_maintenance(session)` : rétention, purge de tenant, effacement RGPD du payload ;
- le scellement (`seal`) : pose `chain_seq`/`prev_hash`/`hash` sur des lignes qui n'en ont pas.

Le scellement vit HORS du chemin d'écriture (tâche périodique, ou à la demande avant un
export/une vérification) : un verrou par tenant tenu pendant toute la transaction d'une
requête aurait créé des interblocages avec les verrous de ligne des autres écritures."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit.models import AuditLog

SEAL_BATCH = 1000


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


@contextmanager
def audit_maintenance(session: Session) -> Iterator[None]:
    """Autorise UPDATE/DELETE sur `audit_log` dans la transaction courante, le temps du bloc."""
    if _is_postgres(session):
        session.execute(text("SELECT set_config('app.audit_maintenance', 'on', true)"))
    try:
        yield
    finally:
        if _is_postgres(session):
            session.flush()
            session.execute(text("SELECT set_config('app.audit_maintenance', 'off', true)"))


def digest(seq: int, prev_hash: str, row: AuditLog) -> str:
    created = row.created_at.replace(tzinfo=None).isoformat(timespec="microseconds")
    material = [
        seq,
        prev_hash,
        row.tenant_id,
        row.actor_id,
        row.actor_kind,
        row.action,
        row.object_type,
        row.object_id,
        created,
    ]
    return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def seal(session: Session, tenant_id: str, *, limit: int = SEAL_BATCH) -> int:
    """Chaîne les lignes non scellées du tenant (ordre d'id). Retourne le nombre scellé."""
    if _is_postgres(session):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit-seal:{tenant_id}"}
        )
    head = session.execute(
        select(AuditLog.chain_seq, AuditLog.hash)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.hash.is_not(None))
        .order_by(AuditLog.chain_seq.desc())
        .limit(1)
    ).first()
    seq, prev = (head[0], head[1]) if head else (0, "")
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.hash.is_(None))
        .order_by(AuditLog.id)
        .limit(limit)
    ).all()
    for row in rows:
        seq += 1
        row.chain_seq = seq
        row.prev_hash = prev
        row.hash = prev = digest(seq, prev, row)
    session.flush()
    return len(rows)


def seal_all(session: Session, tenant_id: str) -> int:
    total = 0
    while n := seal(session, tenant_id):
        total += n
    return total


def head(session: Session, tenant_id: str) -> tuple[int, str] | None:
    row = session.execute(
        select(AuditLog.chain_seq, AuditLog.hash)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.hash.is_not(None))
        .order_by(AuditLog.chain_seq.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def verify(session: Session, tenant_id: str) -> dict:
    """Recalcule la chaîne. La 1re ligne conservée sert d'ancre (la rétention retire les plus
    anciennes). Une suppression de la queue n'est détectable qu'avec l'empreinte de tête
    conservée ailleurs (reçu de purge, archive de rétention)."""
    checked, last_seq, prev = 0, None, None
    broken: int | None = None
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.hash.is_not(None))
        .order_by(AuditLog.chain_seq)
        .execution_options(yield_per=1000)
    )
    for row in session.scalars(stmt):
        if prev is not None and (row.chain_seq != last_seq + 1 or row.prev_hash != prev):
            broken = row.chain_seq
            break
        if digest(row.chain_seq, row.prev_hash or "", row) != row.hash:
            broken = row.chain_seq
            break
        checked, last_seq, prev = checked + 1, row.chain_seq, row.hash
    unsealed = session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.hash.is_(None))
    )
    return {
        "ok": broken is None,
        "checked": checked,
        "lastSeq": last_seq,
        "headHash": prev,
        "brokenAtSeq": broken,
        "unsealed": unsealed or 0,
    }
