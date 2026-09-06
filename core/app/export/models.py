# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ExportJob(Base):
    __tablename__ = "export_jobs"
    # cf. 0021_export_jobs.py — jamais déclaré côté modèle avant SP-43
    # Tâche 5 (trouvaille du comparateur de la Tâche 1, hors table du brief
    # initial mais mécanique et sûre : additive, correspond exactement à
    # l'index déjà posé par la migration).
    __table_args__ = (Index("ix_export_jobs_tenant_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    # Nullable, additive (SP-17b) : None préserve le comportement actuel du
    # bouton d'export manuel (pas de page/contexte particulier) ; renseignés
    # uniquement par le sweep de app.reports.jobs.
    page_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ctx: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Additive, nullable (SP-58 Tâche 2, migration 0035) : les jobs terminés
    # avant cette migration restent NULL, traités comme 0 par la somme de
    # app.quotas.service::job_output_storage_bytes (limitation assumée,
    # documentée en tête de la migration).
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
