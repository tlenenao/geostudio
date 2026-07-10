from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", name="uq_collections_tenant_table"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, défaut = table_name
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    pk_column: Mapped[str] = mapped_column(String, nullable=False)
    geometry_column: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String, nullable=True)
    srid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
