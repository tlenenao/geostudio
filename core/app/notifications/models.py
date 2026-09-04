# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_created",
            "tenant_id",
            "recipient_user_id",
            "created_at",
        ),
        Index(
            "ix_notifications_recipient_unread",
            "tenant_id",
            "recipient_user_id",
            "read_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # "ingestion" | "pipeline" | "export" | "appexport" | "report"
    status: Mapped[str] = mapped_column(String, nullable=False)
    # "success" | "failure"
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    item_resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    item_title: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False, default="all")
    # "all" | "failures_only" | "none"
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
