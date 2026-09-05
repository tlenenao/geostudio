# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class HarvestSource(Base):
    __tablename__ = "harvest_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(
        String, nullable=False, default="reference", server_default="reference"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=sa.true()
    )
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class HarvestRecord(Base):
    __tablename__ = "harvest_records"
    # Index(unique=True), pas UniqueConstraint : 0016_harvest.py crée cette
    # unicité via op.create_index(..., unique=True), jamais
    # op.create_unique_constraint(...). Avant SP-43 Tâche 5, le modèle
    # déclarait un UniqueConstraint de même nom — physiquement équivalent
    # (Postgres implémente aussi une UniqueConstraint via un index unique),
    # mais compare_metadata() les traite comme deux objets distincts et
    # produisait donc un faux positif ('remove_index' + 'add_constraint'
    # pour le même nom, jamais un vrai écart de schéma). Représenter le
    # modèle exactement comme la migration l'a physiquement créé fait
    # disparaître les deux entrées du diff sans toucher à la migration.
    __table_args__ = (
        Index(
            "uq_harvest_records_tenant_source_external",
            "tenant_id",
            "source_id",
            "external_id",
            unique=True,
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
    is_stale: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa.false()
    )
    external_url: Mapped[str | None] = mapped_column(String, nullable=True)
    tiles_url: Mapped[str | None] = mapped_column(String, nullable=True)
    layer_kind: Mapped[str | None] = mapped_column(String, nullable=True)
