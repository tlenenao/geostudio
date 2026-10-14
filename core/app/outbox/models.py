# SPDX-License-Identifier: Apache-2.0
"""Webhooks sortants, outbox transactionnelle et déclencheurs fichier S3
(ARC4-F6, ADR 0027). Les tables vivent ici : `app.outbox` est une couche BASSE
(importable par les écrivains (items, pipelines, soumissions) pour `emit`), la livraison et les
routes sont dans `app.webhooks` (couche haute)."""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class OutboundWebhook(Base):
    __tablename__ = "outbound_webhooks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    event_types: Mapped[list] = mapped_column(sa.JSON, nullable=False)
    # Nom d'un secret `bearer_token` du coffre (clé HMAC) ; lu au nom de created_by.
    secret_name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    disabled_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class OutboxEvent(Base):
    """Une ligne par (événement, destination) — éventail créé à l'émission, dans la
    transaction de l'écriture émettrice."""

    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_due", "status", "next_attempt_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    webhook_id: Mapped[str] = mapped_column(
        ForeignKey("outbound_webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    # pending | delivered | failed (abandonné : destination désactivée)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FileTrigger(Base):
    """Déclenche un pipeline à l'arrivée d'un fichier sous `prefix` (sondage borné)."""

    __tablename__ = "file_triggers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    pipeline_item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    # secret `s3_credentials` lié à un bucket (ADR 0012) ; `prefix` doit être sous son bucketUrl.
    secret_name: Mapped[str] = mapped_column(String, nullable=False)
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class FileTriggerSeen(Base):
    """Clé d'idempotence (déclencheur, objet, etag) : un fichier = exactement un run."""

    __tablename__ = "file_trigger_seen"
    __table_args__ = (UniqueConstraint("trigger_id", "object_key", "etag", name="uq_fts"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    trigger_id: Mapped[str] = mapped_column(
        ForeignKey("file_triggers.id", ondelete="CASCADE"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String, nullable=False)
    etag: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
