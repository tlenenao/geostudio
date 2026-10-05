# SPDX-License-Identifier: Apache-2.0
"""Export asynchrone d'une collection (REV-283e). Table distincte d'`ExportJob`
(PDF/PNG) : celui-ci a un `item_id` non nul, une collection n'est pas un item."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _default_expiry() -> datetime:
    return _now() + timedelta(hours=24)


class CollectionExportJob(Base):
    __tablename__ = "collection_export_jobs"
    __table_args__ = (
        Index("ix_collection_export_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_collection_export_jobs_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    # Filtres de la requête d'origine : {"bbox": [..]|None, "geomIntersects": str|None,
    # "filters": {col: valeur}} — sans eux l'export asynchrone dépasserait la route sync.
    query: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    # Verdict GAP-22 figé à la création (data.view_sensitive du demandeur).
    masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_default_expiry)
