# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Item(Base):
    __tablename__ = "items"
    # Index unique partiel (slug IS NOT NULL) — cf. 0015_items_slug.py, créé
    # via op.create_index(unique=True, postgresql_where=...), jamais déclaré
    # côté modèle avant SP-43 Tâche 5 (trouvaille du comparateur de la
    # Tâche 1, hors table du brief initial).
    __table_args__ = (
        Index(
            "uq_items_tenant_slug",
            "tenant_id",
            "slug",
            unique=True,
            postgresql_where=sa.text("slug IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "app" | "dashboard" | "map"
    title: Mapped[str] = mapped_column(String, nullable=False)
    abstract: Mapped[str] = mapped_column(String, default="", server_default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
    # Métadonnées ouvertes (chantier 4.9, sous-ensemble réduit à license+
    # language — cf. spec §1.2). Même convention str/default="" que
    # Collection.
    license: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="fr", server_default="fr", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
