# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


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
    # Nullable depuis la revue finale SP-17b (I2) : un déclenchement qui
    # échoue (propriétaire ayant perdu l'accès au bookmark/à l'app, capacité
    # export coupée, erreur inattendue) crée quand même une ligne report_runs
    # — sans quoi list_due_reports, qui dérive la cadence de get_latest_run,
    # rejugeait le rapport « dû » à chaque balayage de 5 minutes au lieu de
    # respecter son cron. Une telle ligne n'a par construction aucun
    # export_jobs derrière elle.
    export_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
