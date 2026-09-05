# SPDX-License-Identifier: Apache-2.0
"""Pièces jointes sur une entité de collection (chantier 4.12,
docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md). `fid` est
toujours du texte (contrairement à app.features, qui coerce en int selon le
type de la PK introspectée) et n'a AUCUNE FK Postgres vers la table dynamique
de la collection — impossible génériquement, chaque collection est une vraie
table dont le nom varie (cf. spec §1). L'intégrité (collection_id, fid) est
gérée côté application, comme feature_count."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index(
            "ix_attachments_entity",
            "tenant_id",
            "collection_id",
            "fid",
            "field_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    # ondelete="CASCADE" (SP-42/F-securite-tenant-rls-03) : filet de sécurité
    # DB, en plus de la purge applicative explicite
    # (attachments_repo.delete_all_for_collection, appelée par
    # unregister_collection AVANT la suppression de la collection). Sans lui,
    # DELETE /collections/{id} échouait en 500 (IntegrityError) dès qu'une
    # pièce jointe existait — même patron que CollectionShare.collection_id
    # (app/sharing/models.py).
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    fid: Mapped[str] = mapped_column(String, nullable=False)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
