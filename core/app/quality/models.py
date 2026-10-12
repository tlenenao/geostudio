# SPDX-License-Identifier: Apache-2.0
"""Rapport de qualité d'une collection (ARC-14) : évaluation différée des règles d'attributs
`constraint` et `batch` sur les entités DÉJÀ écrites (jamais rétro-appliquées : rapport)."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    __table_args__ = (
        Index("ix_quality_reports_collection", "tenant_id", "collection_id", "created_at"),
        Index("ix_quality_reports_status", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    # "pending" | "running" | "done" | "failed"
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    # Verdict GAP-22 figé à la création (data.view_sensitive du demandeur).
    masked: Mapped[bool] = mapped_column(nullable=False, default=True)
    checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # {ruleId: {"message", "violations": n, "errors": n}} — comptes exacts sur toute la collection.
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Échantillon plafonné [{fid, ruleId, field, message}] : jamais de valeur d'attribut.
    violations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
