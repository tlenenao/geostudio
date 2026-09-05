# SPDX-License-Identifier: Apache-2.0
"""app.appexport (SP-18a) — export d'une app/dashboard en bundle
autoporté. Mode "static" seul supporté pour l'instant ; "connected" et
"standalone" (SP-18b/c) réutiliseront la même table (colonne `mode`
existe déjà, pas de migration à refaire)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AppExportJob(Base):
    __tablename__ = "app_export_jobs"
    # cf. 0027_app_export_jobs.py — jamais déclaré côté modèle avant SP-43
    # Tâche 5 (trouvaille du comparateur de la Tâche 1, hors table du brief
    # initial mais mécanique et sûre : additive, correspond exactement à
    # l'index déjà posé par la migration).
    __table_args__ = (Index("ix_app_export_jobs_tenant_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
