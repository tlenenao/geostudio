# SPDX-License-Identifier: Apache-2.0
"""Journal d'entité (ARC-15) : un instantané avant/après par écriture REST."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class EntityHistory(Base):
    """`before`/`after` = {"properties": {...}, "geometry": {...}|None}, complets
    (champs sensibles inclus) : le masquage GAP-22 s'applique à la LECTURE
    (app.history.service.mask_snapshot). `actor_id` est nullable : l'anonymisation
    d'un utilisateur (SP-58) le remet à NULL (aucun FK, comme audit_log)."""

    __tablename__ = "entity_history"
    __table_args__ = (
        Index("ix_entity_history_entity", "collection_id", "fid", "id"),
        Index("ix_entity_history_tenant_at", "tenant_id", "collection_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    fid: Mapped[str] = mapped_column(String, nullable=False)
    op: Mapped[str] = mapped_column(String, nullable=False)  # create|update|delete|restore
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
