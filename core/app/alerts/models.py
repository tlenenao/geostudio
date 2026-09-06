# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AlertEvaluation(Base):
    __tablename__ = "alert_evaluations"
    # cf. 0035_alert_pipeline_run_indexes.py (GAP-63, SP-49) : couvre le
    # filtre (tenant_id, alert_rule_item_id) ET le tri created_at DESC de
    # get_latest_evaluation/list_evaluations, ET le WHERE
    # alert_rule_item_id IN (...) SANS tenant_id de
    # get_latest_evaluations_for_items (cross-tenant par construction) —
    # alert_rule_item_id EN TÊTE (pas tenant_id), même correction que
    # pipeline_runs, cf. le docstring de la migration 0035 pour la mesure
    # EXPLAIN qui motive cet ordre.
    __table_args__ = (
        Index("ix_alert_evaluations_rule", "alert_rule_item_id", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    alert_rule_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String, nullable=False)
    transitioned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
