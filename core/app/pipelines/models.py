# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    # cf. 0035_alert_pipeline_run_indexes.py (GAP-63, SP-49) : couvre le
    # filtre (tenant_id, pipeline_item_id) ET le tri created_at DESC de
    # get_latest_run/list_runs, ET le WHERE pipeline_item_id IN (...) SANS
    # tenant_id de get_latest_runs_for_items (cross-tenant par construction)
    # — pipeline_item_id EN TÊTE (pas tenant_id), corrigé en revue finale de
    # branche : vérifié par EXPLAIN que l'ordre inverse fait ignorer l'index
    # par la requête batchée (Seq Scan complet), cf. le docstring de la
    # migration 0035 pour la mesure.
    __table_args__ = (
        Index("ix_pipeline_runs_pipeline", "pipeline_item_id", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    pipeline_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="queued", server_default="queued"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    # server_default="{}" en chaîne nue (comme la migration 0018) : cf.
    # collections/models.py sur attachment_fields — le contournement du
    # piège de comparaison PG pour un type json vit côté test
    # (tests/test_model_alembic_parity.py::_compare_server_default), pas ici.
    node_stats: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
