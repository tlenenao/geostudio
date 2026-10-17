# SPDX-License-Identifier: Apache-2.0
"""TenantLimits : plafonds propres à un tenant (AUD-098). Colonne NULL = limite d'instance."""

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TenantLimits(Base):
    __tablename__ = "tenant_limits"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    max_items: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_collections: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_storage_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_users: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_active_runs: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
