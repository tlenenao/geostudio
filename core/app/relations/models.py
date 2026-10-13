# SPDX-License-Identifier: Apache-2.0
"""Relation déclarée entre deux collections (ARC-21, ADR 0021).

Clé étrangère LOGIQUE : aucune contrainte SQL entre les tables métier, validée par le
cœur à l'écriture. 1-1 / 1-N : `child_key` (colonne de l'enfant) référence `parent_key`
(colonne du parent, la PK par défaut). N-N : une collection d'association porte
`link_parent_key` (-> `parent_key`) et `link_child_key` (-> `child_key` de l'enfant)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CollectionRelation(Base):
    __tablename__ = "collection_relations"
    __table_args__ = (
        UniqueConstraint("parent_collection_id", "name", name="uq_collection_relations_name"),
        Index("ix_collection_relations_tenant", "tenant_id"),
        Index("ix_collection_relations_parent", "parent_collection_id"),
        Index("ix_collection_relations_child", "child_collection_id"),
        Index("ix_collection_relations_link", "link_collection_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cardinality: Mapped[str] = mapped_column(
        String, nullable=False
    )  # one_to_one|one_to_many|many_to_many
    parent_collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    child_collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    parent_key: Mapped[str] = mapped_column(String, nullable=False)
    child_key: Mapped[str] = mapped_column(String, nullable=False)
    link_collection_id: Mapped[str | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=True
    )
    link_parent_key: Mapped[str | None] = mapped_column(String, nullable=True)
    link_child_key: Mapped[str | None] = mapped_column(String, nullable=True)
    on_delete: Mapped[str] = mapped_column(
        String, nullable=False, default="restrict", server_default="restrict"
    )  # restrict|cascade
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
