# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

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
