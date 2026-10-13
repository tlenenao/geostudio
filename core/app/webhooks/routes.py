# SPDX-License-Identifier: Apache-2.0
"""Administration des webhooks sortants et des déclencheurs fichier (ARC4-F6, ADR 0027).
Tout est gardé par le privilège `automation.manage` ; un déclencheur exige en plus
l'écriture sur le pipeline visé. Le secret de signature n'est jamais renvoyé."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, assert_egress_allowed
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.outbox.emit import EVENT_TYPES
from app.outbox.models import FileTrigger, OutboundWebhook, OutboxEvent
from app.pipelines.service import require_pipeline_access, require_pipeline_config
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.secrets import repository as secrets_repo
from app.users.models import User
from app.webhooks import triggers

router = APIRouter()

EventType = Literal["item.created", "item.updated", "pipeline.run.finished", "submission.pending"]
assert set(EventType.__args__) == set(EVENT_TYPES)  # type: ignore[attr-defined]


def _guard(session: Session, user: User) -> None:
    require_privilege(session, user, Privilege.AUTOMATION_MANAGE.value)


def _iso(d: datetime | None) -> str | None:
    return d.replace(tzinfo=UTC).isoformat() if d else None


class WebhookCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    eventTypes: list[EventType] = Field(min_length=1)
    secretName: str = Field(min_length=1)  # secret `bearer_token` du coffre : clé HMAC


class WebhookUpdate(BaseModel):
    eventTypes: list[EventType] | None = Field(default=None, min_length=1)
    enabled: bool | None = None  # true = réactivation (remet le compteur d'échecs à zéro)


class WebhookRead(BaseModel):
    id: str
    url: str
    eventTypes: list[str]
    secretName: str
    enabled: bool
    consecutiveFailures: int
    disabledReason: str | None
    createdAt: str | None


class DeliveryRead(BaseModel):
    id: str
    eventType: str
    status: str
    attempts: int
    lastError: str | None
    nextAttemptAt: str | None
    createdAt: str | None
    deliveredAt: str | None


def _read(h: OutboundWebhook) -> WebhookRead:
    return WebhookRead(
        id=h.id,
        url=h.url,
        eventTypes=list(h.event_types),
        secretName=h.secret_name,
        enabled=h.enabled,
        consecutiveFailures=h.consecutive_failures,
        disabledReason=h.disabled_reason,
        createdAt=_iso(h.created_at),
    )


def _get(session: Session, user: User, webhook_id: str) -> OutboundWebhook:
    hook = session.scalar(
        select(OutboundWebhook).where(
            OutboundWebhook.id == webhook_id, OutboundWebhook.tenant_id == user.tenant_id
        )
    )
    if hook is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    return hook


def _require_secret(session: Session, user: User, name: str, kind: str) -> None:
    payload = secrets_repo.get_secret_payload(
        session, tenant_id=user.tenant_id, name=name, user=user
    )
    if payload is None:
        raise HTTPException(status_code=422, detail=f"secret '{name}' introuvable")
    if payload.kind != kind:
        raise HTTPException(status_code=422, detail=f"le secret doit être de type {kind}")


@router.get("/webhooks", response_model=list[WebhookRead])
def list_webhooks(
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[WebhookRead]:
    _guard(session, user)
    rows = session.scalars(
        select(OutboundWebhook)
        .where(OutboundWebhook.tenant_id == user.tenant_id)
        .order_by(OutboundWebhook.created_at)
    )
    return [_read(h) for h in rows]


@router.post("/webhooks", response_model=WebhookRead, status_code=201)
def create_webhook(
    body: WebhookCreate,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> WebhookRead:
    _guard(session, user)
    try:
        assert_egress_allowed(body.url)  # destination privée/RFC1918 refusée dès la création
    except EgressBlockedError as exc:
        raise HTTPException(status_code=422, detail=f"URL refusée : {exc}") from exc
    _require_secret(session, user, body.secretName, "bearer_token")
    hook = OutboundWebhook(
        id=uuid.uuid4().hex,
        tenant_id=user.tenant_id,
        url=body.url,
        event_types=sorted(set(body.eventTypes)),
        secret_name=body.secretName,
        created_by=user.id,
    )
    session.add(hook)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="webhook.create",
        object_type="outbound_webhook",
        object_id=hook.id,
        payload={"url": hook.url, "eventTypes": hook.event_types},
    )
    session.commit()
    return _read(hook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookRead)
def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> WebhookRead:
    _guard(session, user)
    hook = _get(session, user, webhook_id)
    if body.eventTypes is not None:
        hook.event_types = sorted(set(body.eventTypes))
    if body.enabled is not None:
        hook.enabled = body.enabled
        if body.enabled:
            hook.consecutive_failures = 0
            hook.disabled_reason = None
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="webhook.update",
        object_type="outbound_webhook",
        object_id=hook.id,
        payload={"enabled": hook.enabled, "eventTypes": hook.event_types},
    )
    session.commit()
    return _read(hook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(
    webhook_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    _guard(session, user)
    hook = _get(session, user, webhook_id)
    session.execute(sa_delete(OutboxEvent).where(OutboxEvent.webhook_id == hook.id))
    session.execute(sa_delete(OutboundWebhook).where(OutboundWebhook.id == hook.id))
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="webhook.delete",
        object_type="outbound_webhook",
        object_id=webhook_id,
    )
    session.commit()


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[DeliveryRead])
def list_deliveries(
    webhook_id: str,
    limit: int = 100,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[DeliveryRead]:
    _guard(session, user)
    hook = _get(session, user, webhook_id)
    rows = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.webhook_id == hook.id)
        .order_by(OutboxEvent.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    return [
        DeliveryRead(
            id=e.id,
            eventType=e.event_type,
            status=e.status,
            attempts=e.attempts,
            lastError=e.last_error,
            nextAttemptAt=_iso(e.next_attempt_at),
            createdAt=_iso(e.created_at),
            deliveredAt=_iso(e.delivered_at),
        )
        for e in rows
    ]


@router.post("/webhooks/{webhook_id}/deliveries/{event_id}/replay", status_code=202)
def replay_delivery(
    webhook_id: str,
    event_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> dict:
    """Remet l'événement en file (livré par le balayage suivant) ; la destination doit
    être active — la réactiver d'abord (PATCH enabled=true) si elle a été désactivée."""
    _guard(session, user)
    hook = _get(session, user, webhook_id)
    ev = session.scalar(
        select(OutboxEvent).where(OutboxEvent.id == event_id, OutboxEvent.webhook_id == hook.id)
    )
    if ev is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    ev.status = "pending"
    ev.attempts = 0
    ev.last_error = None
    ev.next_attempt_at = datetime.now(UTC).replace(tzinfo=None)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="webhook.replay",
        object_type="outbox_event",
        object_id=ev.id,
    )
    session.commit()
    return {"status": "pending"}


# --- déclencheurs fichier S3 ---


class FileTriggerCreate(BaseModel):
    pipelineItemId: str
    secretName: str = Field(min_length=1)  # s3_credentials lié à un bucket
    prefix: str = Field(min_length=1)  # s3://bucket/préfixe/


class FileTriggerRead(BaseModel):
    id: str
    pipelineItemId: str
    secretName: str
    prefix: str
    enabled: bool
    lastError: str | None
    createdAt: str | None


def _trigger_read(t: FileTrigger) -> FileTriggerRead:
    return FileTriggerRead(
        id=t.id,
        pipelineItemId=t.pipeline_item_id,
        secretName=t.secret_name,
        prefix=t.prefix,
        enabled=t.enabled,
        lastError=t.last_error,
        createdAt=_iso(t.created_at),
    )


@router.get("/file-triggers", response_model=list[FileTriggerRead])
def list_file_triggers(
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[FileTriggerRead]:
    _guard(session, user)
    rows = session.scalars(
        select(FileTrigger)
        .where(FileTrigger.tenant_id == user.tenant_id)
        .order_by(FileTrigger.created_at)
    )
    return [_trigger_read(t) for t in rows]


@router.post("/file-triggers", response_model=FileTriggerRead, status_code=201)
def create_file_trigger(
    body: FileTriggerCreate,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> FileTriggerRead:
    _guard(session, user)
    require_pipeline_access(session, user=user, item_id=body.pipelineItemId, action="write")
    require_pipeline_config(session, body.pipelineItemId)
    _require_secret(session, user, body.secretName, "s3_credentials")
    secret = secrets_repo.get_secret_payload(
        session, tenant_id=user.tenant_id, name=body.secretName, user=user
    )
    try:
        triggers.check_scope(secret, body.prefix)
    except (triggers.TriggerConfigError, EgressBlockedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    trigger = FileTrigger(
        id=uuid.uuid4().hex,
        tenant_id=user.tenant_id,
        pipeline_item_id=body.pipelineItemId,
        secret_name=body.secretName,
        prefix=body.prefix,
        created_by=user.id,
    )
    session.add(trigger)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="file_trigger.create",
        object_type="file_trigger",
        object_id=trigger.id,
        payload={"pipelineItemId": body.pipelineItemId, "prefix": body.prefix},
    )
    session.commit()
    return _trigger_read(trigger)


@router.delete("/file-triggers/{trigger_id}", status_code=204)
def delete_file_trigger(
    trigger_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    _guard(session, user)
    trigger = session.scalar(
        select(FileTrigger).where(
            FileTrigger.id == trigger_id, FileTrigger.tenant_id == user.tenant_id
        )
    )
    if trigger is None:
        raise HTTPException(status_code=404, detail="file trigger not found")
    require_pipeline_access(session, user=user, item_id=trigger.pipeline_item_id, action="write")
    session.delete(trigger)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="file_trigger.delete",
        object_type="file_trigger",
        object_id=trigger_id,
    )
    session.commit()
