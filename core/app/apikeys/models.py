# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ApiKey(Base):
    """Clé d'API de service (ARC-06, ADR 0016). Seul le SHA-256 du jeton est
    stocké ; `key_prefix` (public) sert à la recherche et à l'affichage."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_created_by", "tenant_id", "created_by"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # AUD-091 : None = plafond du rôle du créateur (historique) ; sinon sous-ensemble.
    scopes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    read_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
