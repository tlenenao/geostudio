# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HarvestSource(Base):
    __tablename__ = "harvest_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="reference")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class HarvestRecord(Base):
    __tablename__ = "harvest_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", "external_id",
            name="uq_harvest_records_tenant_source_external",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("harvest_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collections.id"), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
