# SPDX-License-Identifier: Apache-2.0
"""Livraison de l'outbox (ARC4-F6, ADR 0027) : signature HMAC-SHA256, egress gardé (la
session et la garde SSRF d'`app.alerts.egress` — redirections et épinglage DNS
compris), retries exponentiels, 5 échecs consécutifs d'une destination = désactivation
+ notification de son créateur. Appelée par le balayage périodique (`app.webhooks.jobs`)."""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, build_guarded_session
from app.notifications import repository as notifications_repo
from app.outbox.models import OutboundWebhook, OutboxEvent
from app.secrets import repository as secrets_repo
from app.users.models import User

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
BATCH_SIZE = 20
_BACKOFF_BASE_S = 30
_BACKOFF_CAP_S = 3600
_TIMEOUT_S = 10

Poster = Callable[[str, bytes, dict], None]


class DeliveryError(Exception):
    """Livraison impossible (jamais propagée : transformée en échec d'outbox)."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sign(body: bytes, key: str) -> str:
    return "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _http_post(url: str, body: bytes, headers: dict) -> None:
    try:
        resp = build_guarded_session().post(url, data=body, headers=headers, timeout=_TIMEOUT_S)
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
    except DeliveryError as exc:
        event.attempts += 1
        event.last_error = str(exc)[:500]
        event.next_attempt_at = _now() + timedelta(
            seconds=min(_BACKOFF_BASE_S * 2 ** (event.attempts - 1), _BACKOFF_CAP_S)
        )
        hook.consecutive_failures += 1
        if hook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            _disable(session, hook, reason=str(exc)[:500])
        session.flush()
        return False
    event.status = "delivered"
    event.attempts += 1
    event.last_error = None
    event.delivered_at = _now()
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
    logger.warning("webhook %s désactivé après %s échecs", hook.id, hook.consecutive_failures)


def deliver_due(session: Session, *, post: Poster = _http_post, limit: int = BATCH_SIZE) -> int:
    """Livre jusqu'à `limit` événements dus (SKIP LOCKED : plusieurs workers sans
    double livraison) ; commit après chacun. Retourne le nombre livré."""
    delivered = 0
    due = session.scalars(
        select(OutboxEvent)
        .join(OutboundWebhook, OutboundWebhook.id == OutboxEvent.webhook_id)
        .where(
            OutboxEvent.status == "pending",
            OutboxEvent.next_attempt_at <= _now(),
            OutboundWebhook.enabled.is_(True),
        )
        .order_by(OutboxEvent.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True, of=OutboxEvent)
    ).all()
    for event in due:
        hook = session.get(OutboundWebhook, event.webhook_id)
        assert hook is not None
        if deliver_one(session, event, hook, post=post):
            delivered += 1
        session.commit()
    return delivered
