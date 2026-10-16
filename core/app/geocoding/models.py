# SPDX-License-Identifier: Apache-2.0
"""Job de géocodage par lot avec reprise (REV-367 j). `results` est complété
chunk par chunk : une reprise repart de `len(results)`, jamais de zéro."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GeocodeJob(Base):
    __tablename__ = "geocode_jobs"
    __table_args__ = (Index("ix_geocode_jobs_tenant_id", "tenant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    addresses: Mapped[list] = mapped_column(JSON, nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
