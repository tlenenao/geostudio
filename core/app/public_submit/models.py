# SPDX-License-Identifier: Apache-2.0
"""Soumission publique modérée (ARC-10, ADR 0017).

Choix de conception : une soumission en attente vit dans la table d'attente
`submissions` (table du cœur, jamais accordée à gis_rls), PAS dans la table de la
collection avec un statut. Elle est donc invisible de TOUT chemin de lecture des
features (REST, MVT, STAC, DCAT, exports, MCP, DuckDB/lac, CDC, moissonnage) par
construction — aucune jumelle de garde à tenir. L'approbation insère la ligne dans
la collection par l'écriture normale (validation + RLS + journal)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class SubmissionToken(Base):
    """Jeton public de soumission d'une collection. Seul le SHA-256 du jeton est stocké
    (patron ADR 0016) ; `token_prefix` (public) sert à la recherche et à l'affichage."""

    __tablename__ = "submission_tokens"
    __table_args__ = (Index("ix_submission_tokens_collection", "tenant_id", "collection_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    max_submissions: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Submission(Base):
    """`payload` = {"properties", "geometry"} tant que `pending` ; vidé à l'approbation
    (la donnée est alors dans la collection) et au rejet (donnée personnelle inutile)."""

    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_queue", "tenant_id", "collection_id", "status", "created_at"),
        Index("ix_submissions_attachment_key", "attachment_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    token_id: Mapped[str] = mapped_column(
        ForeignKey("submission_tokens.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)  # pending|approved|rejected
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    attachment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachment_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    moderated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    feature_id: Mapped[str | None] = mapped_column(String, nullable=True)
