# SPDX-License-Identifier: Apache-2.0
"""Livraison de l'outbox (ARC4-F6, ADR 0027) : signature HMAC-SHA256, egress gardé (la
session et la garde SSRF d'`app.alerts.egress`, épinglage DNS compris ; une
redirection n'est jamais suivie et compte comme un échec, AUD-169), retries
exponentiels, 5 échecs consécutifs d'une destination = désactivation
+ notification de son créateur. Appelée par le balayage périodique (`app.webhooks.jobs`)."""

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, build_guarded_session
from app.audit.writer import write_audit
from app.notifications import repository as notifications_repo
from app.outbox.models import OutboundWebhook, OutboxEvent
from app.secrets import repository as secrets_repo
from app.users.models import User

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
_BACKOFF_BASE_S = 30
_BACKOFF_CAP_S = 3600
_TIMEOUT_S = 10
# Lot réservé à la fois ; le bail doit couvrir le pire cas du lot (BATCH_SIZE x _TIMEOUT_S).
BATCH_SIZE = 10
LEASE_S = 300
SWEEP_BUDGET_S = 45  # le balayage tourne chaque minute
OUTBOX_RETENTION_DAYS = 30

Poster = Callable[[str, bytes, dict], None]


class DeliveryError(Exception):
    """Livraison impossible (jamais propagée : transformée en échec d'outbox)."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sign(body: bytes, key: str) -> str:
    return "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _http_post(url: str, body: bytes, headers: dict) -> None:
    try:
        resp = build_guarded_session().post(
            url, data=body, headers=headers, timeout=_TIMEOUT_S, allow_redirects=False
        )
        if 300 <= resp.status_code < 400:  # AUD-169 : jamais suivie, jamais « delivered »
            raise requests.HTTPError(f"redirection refusée ({resp.status_code})", response=resp)
        resp.raise_for_status()
    except EgressBlockedError as exc:
        raise DeliveryError(f"egress bloqué : {exc}") from exc
    except requests.RequestException as exc:
        raise DeliveryError(f"livraison échouée : {exc}") from exc


def deliver_one(
    session: Session, event: OutboxEvent, hook: OutboundWebhook, *, post: Poster = _http_post
) -> bool:
    """Livre `event` ; met à jour l'outbox et le compteur d'échecs de `hook`."""
    try:
        owner = session.get(User, hook.created_by)
        secret = (
            secrets_repo.get_secret_payload(
                session, tenant_id=hook.tenant_id, name=hook.secret_name, user=owner
            )
            if owner is not None
            else None
        )
        if secret is None or secret.kind != "bearer_token":
            raise DeliveryError(f"secret de signature '{hook.secret_name}' inutilisable")
        body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode()
        post(
            hook.url,
            body,
            {
                "Content-Type": "application/json",
                "X-GeoStudio-Event": event.event_type,
                "X-GeoStudio-Delivery": event.id,
                "X-GeoStudio-Signature": sign(body, secret.token),
            },
        )
    except Exception as exc:  # noqa: BLE001 — DeliveryError ou imprévu (déchiffrement…) : l'échec reste sur CETTE destination
        if not isinstance(exc, DeliveryError):
            logger.exception("livraison %s : échec inattendu", event.id)
        event.attempts += 1
        event.last_error = str(exc)[:500]
        event.next_attempt_at = _now() + timedelta(
            seconds=min(_BACKOFF_BASE_S * 2 ** (event.attempts - 1), _BACKOFF_CAP_S)
        )
        # Verrou de ligne : deux balayages livrant la même destination ne perdent pas
        # d'incrément (lecture fraîche sous FOR UPDATE, relâché au commit de l'appelant).
        session.refresh(hook, with_for_update=True)
        if not hook.enabled:  # désactivée entre-temps par un autre balayage
            session.flush()
            return False
        hook.consecutive_failures += 1
        if hook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            _disable(session, hook, reason=str(exc)[:500])
        session.flush()
        return False
    event.status = "delivered"
    event.attempts += 1
    event.last_error = None
    event.delivered_at = _now()
    session.refresh(hook, with_for_update=True)
    hook.consecutive_failures = 0
    session.flush()
    return True


def _disable(session: Session, hook: OutboundWebhook, *, reason: str) -> None:
    hook.enabled = False
    hook.disabled_reason = reason
    for ev in session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.webhook_id == hook.id, OutboxEvent.status == "pending"
        )
    ):
        ev.status = "failed"
        ev.last_error = "destination désactivée après échecs répétés"
    notifications_repo.create_notification(
        session,
        tenant_id=hook.tenant_id,
        recipient_user_id=hook.created_by,
        kind="webhook_disabled",
        status="failure",
        item_id=None,
        item_resource_type=None,
        item_title=hook.url,
        error_message=reason,
    )
    write_audit(
        session,
        tenant_id=hook.tenant_id,
        actor_id=None,
        actor_kind="system",
        action="webhook.disabled",
        object_type="outbound_webhook",
        object_id=hook.id,
        payload={
            "url": hook.url,
            "consecutiveFailures": hook.consecutive_failures,
            "reason": reason,
        },
    )
    logger.warning("webhook %s désactivé après %s échecs", hook.id, hook.consecutive_failures)


def _claim(session: Session, limit: int) -> list[str]:
    """Réserve jusqu'à `limit` événements dus en repoussant leur échéance d'un bail
    (`UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED) RETURNING`), puis
    commit : un balayage concurrent ne les voit plus dus, sans qu'aucun verrou ne
    soit tenu pendant les appels HTTP. Tourniquet par tenant (rang dans le tenant
    d'abord) : un backlog d'un tenant n'affame pas les autres (I6)."""
    now = _now()
    due = (
        OutboxEvent.status == "pending",
        OutboxEvent.next_attempt_at <= now,
    )
    ranked = (
        select(
            OutboxEvent.id,
            func.row_number()
            .over(partition_by=OutboxEvent.tenant_id, order_by=OutboxEvent.next_attempt_at)
            .label("rn"),
        )
        .join(OutboundWebhook, OutboundWebhook.id == OutboxEvent.webhook_id)
        .where(*due, OutboundWebhook.enabled.is_(True))
        .subquery()
    )
    # Les conditions « dû » sont répétées sur la requête verrouillante : Postgres les
    # réévalue sur la version courante d'une ligne réservée entre-temps par un autre.
    locked = (
        select(OutboxEvent.id)
        .join(ranked, ranked.c.id == OutboxEvent.id)
        .where(*due)
        .order_by(ranked.c.rn, OutboxEvent.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True, of=OutboxEvent)
    )
    ids = list(
        session.scalars(
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(locked))
            .values(next_attempt_at=now + timedelta(seconds=LEASE_S))
            .returning(OutboxEvent.id)
            .execution_options(synchronize_session=False)
        )
    )
    session.commit()
    return ids


def deliver_due(
    session: Session,
    *,
    post: Poster = _http_post,
    limit: int = BATCH_SIZE,
    budget_s: float = SWEEP_BUDGET_S,
) -> int:
    """Livre les événements dus par lots réservés (`_claim`) jusqu'à épuisement ou
    jusqu'au budget de temps du balayage ; commit après chaque événement. Livraison
    « au moins une fois » : un worker mort en plein lot laisse ses réservations
    expirer (bail) et un balayage suivant les relivre. Retourne le nombre livré."""
    delivered = 0
    deadline = time.monotonic() + budget_s
    while True:
        ids = _claim(session, limit)
        for event_id in ids:
            event = session.get(OutboxEvent, event_id, populate_existing=True)
            # Destination désactivée en cours de lot : ses événements sont déjà `failed`.
            if event is None or event.status != "pending":
                continue
            hook = session.get(OutboundWebhook, event.webhook_id)
            if hook is None or not hook.enabled:  # désactivée à la main : bail laissé expirer
                continue
            if deliver_one(session, event, hook, post=post):
                delivered += 1
            session.commit()
        if len(ids) < limit or time.monotonic() >= deadline:
            return delivered


def purge_outbox(session: Session) -> int:
    """Rétention : supprime les lignes livrées/abandonnées de plus de
    OUTBOX_RETENTION_DAYS (les `pending` restent, quel que soit leur âge)."""
    res = session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.status.in_(("delivered", "failed")),
            OutboxEvent.created_at < _now() - timedelta(days=OUTBOX_RETENTION_DAYS),
        )
    )
    session.commit()
    return int(res.rowcount)  # type: ignore[attr-defined]
