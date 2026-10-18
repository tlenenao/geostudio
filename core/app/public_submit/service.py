# SPDX-License-Identifier: Apache-2.0
"""Soumission publique modérée (ARC-10, ADR 0017) : jetons, file d'attente, anti-abus.
Datetimes naïfs UTC en base (convention du dépôt)."""

import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.collections.models import Collection
from app.notifications import repository as notifications_repo
from app.outbox.emit import emit
from app.public_submit.models import Submission, SubmissionFile, SubmissionToken
from app.sharing.models import CollectionShare, GroupMember, share_active
from app.upload_sniff import sniff_content_type  # noqa: F401  (liste blanche partagée, L8)

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "gss_"
# Jeton = "gss_" + 12 hex (préfixe public, 16 car.) + "_" + secret urlsafe 256 bits.
_PREFIX_LEN = len(TOKEN_PREFIX) + 12
MAX_LIFETIME_DAYS = 365
MAX_PAYLOAD_BYTES = 64 * 1024
# L8 : plafonds d'une soumission publique (fichiers).
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024


class HourlyLimiter:
    """Fenêtre glissante d'une heure par clé (IP). En mémoire de process, comme le
    limiteur SP-26 (même limite assumée : pas de partage entre répliques, cf. ARC-32).
    Dédié : le limiteur du middleware est à fenêtre de 60 s."""

    def __init__(self, limit: int, window_seconds: float = 3600.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._calls = 0

    def has_room(self, key: str) -> bool:
        """Sans décompter (revue SP-L2 I4) : une requête refusée ne consomme rien."""
        now = time.monotonic()
        bucket = self._hits.get(key)
        return bucket is None or sum(now - t <= self.window for t in bucket) < self.limit

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        allowed = len(bucket) < self.limit
        if allowed:
            bucket.append(now)
        self._calls += 1
        if self._calls % 200 == 0:  # balayage : borne la croissance du dict
            for k in [k for k, b in self._hits.items() if not b or now - b[-1] > self.window]:
                del self._hits[k]
        return allowed

    def reset(self) -> None:
        self._hits.clear()


# 100 requêtes/h/IP : la 101e est refusée (429). Compte TOUTES les requêtes vers la
# route publique (jeton invalide compris), sinon le brute-force du jeton serait gratuit.
ip_limiter = HourlyLimiter(100)
# AUD-154 : aussi par jeton, quel que soit le nombre d'IP. Revue SP-L2 I4 : ne
# décompte que les soumissions ACCEPTÉES (sinon des requêtes invalides épuisent le
# formulaire d'autrui) ; seuil CORE_PUBLIC_SUBMIT_TOKEN_HOURLY_LIMIT (défaut 1000).
# ponytail: compteurs horaires par process ; le budget par minute partagé entre
# répliques est celui de PgRateLimiter.
token_limiter = HourlyLimiter(int(os.environ.get("CORE_PUBLIC_SUBMIT_TOKEN_HOURLY_LIMIT") or 1000))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(
    session: Session,
    *,
    collection: Collection,
    user,
    name: str,
    expires_in_days: int,
    max_submissions: int,
) -> tuple[SubmissionToken, str]:
    """Renvoie (ligne, jeton en clair) ; le jeton n'existe nulle part ailleurs."""
    if not 1 <= expires_in_days <= MAX_LIFETIME_DAYS:
        raise ValueError(f"expires_in_days must be between 1 and {MAX_LIFETIME_DAYS}")
    if max_submissions < 1:
        raise ValueError("max_submissions must be >= 1")
    prefix = TOKEN_PREFIX + secrets.token_hex(6)
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    row = SubmissionToken(
        id=str(uuid.uuid4()),
        tenant_id=collection.tenant_id,
        collection_id=collection.id,
        created_by=user.id,
        name=name,
        token_prefix=prefix,
        token_hash=_hash(token),
        expires_at=_utcnow() + timedelta(days=expires_in_days),
        max_submissions=max_submissions,
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        tenant_id=collection.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="submission_token.create",
        object_type="submission_token",
        object_id=row.id,
        payload={"collection": collection.id, "prefix": prefix, "name": name},
    )
    return row, token


def find_token(session: Session, token: str) -> SubmissionToken | None:
    """Jeton existant (valide au sens du condensat), quel que soit son état."""
    if not token.startswith(TOKEN_PREFIX) or len(token) <= _PREFIX_LEN:
        return None
    row = session.scalar(
        select(SubmissionToken).where(SubmissionToken.token_prefix == token[:_PREFIX_LEN])
    )
    if row is None or not hmac.compare_digest(row.token_hash, _hash(token)):
        return None
    return row


def token_is_usable(row: SubmissionToken) -> bool:
    return row.revoked_at is None and row.expires_at > _utcnow()


def reserve_slot(session: Session, row: SubmissionToken) -> bool:
    """Quota global du jeton, atomique (une seule requête UPDATE conditionnelle)."""
    result = session.execute(
        update(SubmissionToken)
        .where(
            SubmissionToken.id == row.id,
            SubmissionToken.revoked_at.is_(None),
            SubmissionToken.submission_count < SubmissionToken.max_submissions,
        )
        .values(submission_count=SubmissionToken.submission_count + 1)
    )
    return result.rowcount == 1


def create_submission(
    session: Session,
    *,
    token: SubmissionToken,
    payload: dict,
    attachment: dict | None = None,
    attachment_key: str | None = None,
    files: list[tuple[dict, str]] | None = None,
    client_op_id: str | None = None,
) -> Submission:
    sub = Submission(
        id=str(uuid.uuid4()),
        tenant_id=token.tenant_id,
        collection_id=token.collection_id,
        token_id=token.id,
        status="pending",
        payload=payload,
        attachment=attachment,
        attachment_key=attachment_key,
        client_op_id=client_op_id,
    )
    session.add(sub)
    session.flush()
    for meta, key in files or []:
        session.add(
            SubmissionFile(
                id=str(uuid.uuid4()),
                tenant_id=token.tenant_id,
                submission_id=sub.id,
                field_key=meta["fieldKey"],
                attachment=meta,
                attachment_key=key,
            )
        )
    session.flush()
    emit(  # F6 : identifiants seulement, jamais le contenu de la soumission (ADR 0017/0027)
        session,
        tenant_id=token.tenant_id,
        event_type="submission.pending",
        payload={"submissionId": sub.id, "collectionId": token.collection_id},
    )
    write_audit(
        session,
        tenant_id=token.tenant_id,
        actor_id=None,
        actor_kind="guest",
        action="submission.create",
        object_type="submission",
        object_id=sub.id,
        payload={"collection": token.collection_id, "token": token.token_prefix},
    )
    return sub


def moderator_ids(session: Session, col: Collection) -> set[str]:
    """Propriétaire + membres des groupes éditeurs/gestionnaires de la collection."""
    ids = {col.owner_id}
    rows = session.scalars(
        select(GroupMember.user_id)
        .join(CollectionShare, CollectionShare.group_id == GroupMember.group_id)
        .where(
            CollectionShare.collection_id == col.id,
            CollectionShare.role.in_(("editor", "manager")),
            share_active(CollectionShare),
        )
    )
    ids.update(rows)
    return ids


def notify_moderators(session: Session, col: Collection) -> None:
    """Best-effort : une panne de notification ne doit jamais perdre la soumission
    (SAVEPOINT, patron SP-39)."""
    try:
        with session.begin_nested():
            for uid in moderator_ids(session, col):
                notifications_repo.create_notification(
                    session,
                    tenant_id=col.tenant_id,
                    recipient_user_id=uid,
                    kind="submission",
                    status="success",
                    item_id=None,
                    item_resource_type=None,
                    item_title=col.title,
                )
    except Exception:  # noqa: BLE001
        logger.warning("notification de soumission non écrite", exc_info=True)


def find_replay(session: Session, token: SubmissionToken, client_op_id: str | None) -> bool:
    """Vrai si ce `clientOpId` a déjà produit une soumission pour ce jeton (rejeu hors-ligne)."""
    if not client_op_id:
        return False
    return (
        session.scalar(
            select(Submission.id).where(
                Submission.token_id == token.id, Submission.client_op_id == client_op_id
            )
        )
        is not None
    )
