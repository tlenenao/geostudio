# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class RasterJob(Base):
    """Job d'ingestion d'un raster (validation COG / conversion). cf. 0067."""

    __tablename__ = "raster_jobs"
    __table_args__ = (Index("ix_raster_jobs_tenant_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="uploaded", server_default="uploaded"
    )  # "uploaded" | "converting" | "done" | "error"
    source_key: Mapped[str] = mapped_column(String, nullable=False)  # brut, purgé en fin de job
    converted_key: Mapped[str | None] = mapped_column(String, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Collection dont les limites géographiques s'appliquent à ce raster (fail-closed).
    limit_collection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RasterAsset(Base):
    """Métadonnées d'un raster COG, 1:1 avec l'item `raster` (ADR 0024)."""

    __tablename__ = "raster_assets"
    __table_args__ = (Index("ix_raster_assets_tenant_id", "tenant_id"),)

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    source_key: Mapped[str] = mapped_column(String, nullable=False)  # COG dans le bucket raster
    srid: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds: Mapped[list] = mapped_column(JSON, nullable=False)  # [w, s, e, n] en EPSG:4326
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    dtype: Mapped[str] = mapped_column(String, nullable=False)
    nodata: Mapped[float | None] = mapped_column(Float, nullable=True)
    bands: Mapped[list] = mapped_column(JSON, nullable=False)  # [{index,min,max,mean,std}]
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    limit_collection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
