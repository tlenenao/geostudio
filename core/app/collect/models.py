# SPDX-License-Identifier: Apache-2.0
"""Idempotence des écritures de collecte (L8, AUD-004). Une ligne = une opération client
déjà appliquée : un rejeu (file hors-ligne après coupure) retrouve le résultat sans réécrire.
Pas de FK vers `users` : l'acteur reste lisible après anonymisation (RGPD)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CollectClientOp(Base):
    __tablename__ = "collect_client_ops"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "collection_id",
            "actor_id",
            "kind",
            "client_op_id",
            name="uq_collect_client_ops_op",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    client_op_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # feature | attachment
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
