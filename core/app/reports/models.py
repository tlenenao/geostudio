# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    report_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    # Pas de FK SQL vers export_jobs.id : app.export est sous app.reports
    # dans le contrat de couches, mais les lignes export_jobs sont
    # recherchées par id via export_repo.get_job à la lecture (§2 du
    # design), jamais jointes en SQL — même discipline que
    # pipeline_runs/get_latest_run.
    export_job_id: Mapped[str] = mapped_column(String, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
