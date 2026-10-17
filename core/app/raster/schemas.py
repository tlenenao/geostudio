# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.raster.zonal import MAX_POLYGONS

Stat = Literal["count", "min", "max", "mean", "sum", "std"]


def _safe_filename(v: str) -> str:
    """Le nom entre dans la clé S3 : ni sous-chemin, ni `..`, ni caractère de contrôle."""
    if "/" in v or "\\" in v or ".." in v or any(ord(c) < 32 for c in v):
        raise ValueError("invalid filename")
    return v


class RasterPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)

    _check_filename = field_validator("filename")(_safe_filename)
    contentType: str = Field(default="image/tiff", min_length=1, max_length=100)
    # AUD-090 : taille annoncée, signée dans l'URL (S3 refuse tout autre Content-Length).
    size: int = Field(ge=1)


class RasterPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class RasterUploadCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)

    _check_filename = field_validator("filename")(_safe_filename)
    title: str = Field(min_length=1)
    # Collection dont les limites géographiques s'appliquent à ce raster (optionnel).
    limitCollectionId: str | None = None


class RasterUploadCreated(BaseModel):
    jobId: str


class RasterJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    itemId: str | None


class RasterBand(BaseModel):
    index: int
    min: float | None
    max: float | None
    mean: float | None
    std: float | None


class RasterInfo(BaseModel):
    itemId: str
    srid: int
    bounds: list[float]  # [west, south, east, north] EPSG:4326
    width: int
    height: int
    dtype: str
    nodata: float | None
    bands: list[RasterBand]
    sizeBytes: int
    limitCollectionId: str | None


class ZonalStatsRequest(BaseModel):
    # GeoJSON FeatureCollection / Feature / Polygon / MultiPolygon, OU une collection
    # (ses polygones lisibles par l'appelant) — exactement l'un des deux.
    geojson: dict | None = None
    collectionId: str | None = None
    band: int = Field(default=1, ge=1)
    stats: list[Stat] = Field(
        default_factory=lambda: ["count", "min", "max", "mean", "sum"], min_length=1
    )

    @model_validator(mode="after")
    def _one_source(self) -> "ZonalStatsRequest":
        if (self.geojson is None) == (self.collectionId is None):
            raise ValueError("fournir exactement un de geojson ou collectionId")
        return self


class ZonalStatsItem(BaseModel):
    id: str | int | None
    stats: dict[str, float | int | None]


class ZonalStatsResponse(BaseModel):
    count: int = Field(description=f"nombre de polygones traités (max {MAX_POLYGONS})")
    results: list[ZonalStatsItem]
