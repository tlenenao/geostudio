# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Terrain3DJob(Base):
    __tablename__ = "terrain3d_jobs"
    # cf. 0026_terrain3d_jobs.py — jamais déclaré côté modèle avant SP-43
    # Tâche 5 (trouvaille du comparateur de la Tâche 1, hors table du brief
    # initial mais mécanique et sûre : additive, correspond exactement à
    # l'index déjà posé par la migration).
    __table_args__ = (Index("ix_terrain3d_jobs_tenant_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="uploaded", server_default="uploaded"
    )
    # "uploaded" | "converting" | "done" | "error"
    source_key: Mapped[str] = mapped_column(
        String, nullable=False
    )  # raw upload, purged after conversion
    converted_key: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # set once the COG is uploaded
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
