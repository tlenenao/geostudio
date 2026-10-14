# SPDX-License-Identifier: Apache-2.0
"""Émission transactionnelle (ADR 0027) : à appeler DANS la transaction de l'écriture
émettrice, sans commit ni flush propre — l'événement n'existe que si l'écriture est
validée (aucune perte au crash, aucun événement fantôme au rollback). La livraison est
faite plus tard par `app.webhooks.jobs` (balayage périodique = reprise, piège n°14).

Le payload ne porte que des identifiants (jamais de valeur de champ : GAP-22, ni de
ligne `pending`, ADR 0017)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.outbox.models import OutboundWebhook, OutboxEvent

EVENT_TYPES = (
    "item.created",
    "item.updated",
    "pipeline.run.finished",
    "submission.pending",
)


def emit(session: Session, *, tenant_id: str, event_type: str, payload: dict) -> int:
    """Retourne le nombre de destinations abonnées (une ligne d'outbox chacune)."""
    hooks = session.scalars(
        select(OutboundWebhook).where(
            OutboundWebhook.tenant_id == tenant_id, OutboundWebhook.enabled.is_(True)
        )
    ).all()
    body = {
        "event": event_type,
        "tenantId": tenant_id,
        "occurredAt": datetime.now(UTC).isoformat(),
        **payload,
    }
    n = 0
    for hook in hooks:
        if event_type in hook.event_types:
            session.add(
                OutboxEvent(
                    id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    webhook_id=hook.id,
                    event_type=event_type,
                    payload=body,
                )
            )
            n += 1
    return n
