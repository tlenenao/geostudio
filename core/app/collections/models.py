# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", name="uq_collections_tenant_table"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, défaut = table_name
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    pk_column: Mapped[str] = mapped_column(String, nullable=False)
    geometry_column: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String, nullable=True)
    srid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # [{"key": str, "label": str}] — champs `attachment` déclarés (chantier
    # 4.12) ; pas de colonne SQL réelle par champ, cf.
    # docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md §3.1.
    attachment_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Métadonnées ouvertes (chantier 4.9, docs/superpowers/specs/
    # 2026-09-04-sp41-metadonnees-licence-design.md §1.1). Convention
    # str/default="" (pas None) : un PATCH ne peut jamais distinguer un champ
    # omis d'un champ explicitement remis à None, donc "" porte le sens
    # "non déclaré" partout ici, cohérent avec description ci-dessus.
    license: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    license_uri: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    producer: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    contact: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    update_frequency: Mapped[str] = mapped_column(
        String, default="", server_default="", nullable=False
    )
    lineage: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="fr", server_default="fr", nullable=False)
    version: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    temporal_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    temporal_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
