# SPDX-License-Identifier: Apache-2.0
"""Validation COG, conversion si besoin, extraction des métadonnées (ADR 0024).

La conversion réutilise `app.terrain3d.conversion` (profil deflate sans perte,
process fils borné par un délai) : un COG est un COG, qu'il porte un MNT ou une
ortho. Un raster déjà COG valide n'est pas réécrit."""

import shutil
from dataclasses import dataclass

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_validate

from app.terrain3d.conversion import Terrain3DConversionError, convert_to_cog

RasterIngestError = Terrain3DConversionError


@dataclass(frozen=True)
class RasterMetadata:
    srid: int
    bounds: list[float]  # [w, s, e, n] EPSG:4326
    width: int
    height: int
    dtype: str
    nodata: float | None
    bands: list[dict]


# GeoTIFF classique, BigTIFF, little/big endian. Tout autre contenu (VRT, formats GDAL à
# références externes comme /vsicurl/ ou fichiers locaux) est refusé AVANT toute ouverture GDAL
# (même classe que REV-333).
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def require_tiff(path: str) -> None:
    with open(path, "rb") as f:
        if f.read(4) not in _TIFF_MAGIC:
            raise RasterIngestError("seuls les GeoTIFF/COG sont acceptés")


def to_cog(raw_path: str, cog_path: str, *, timeout_seconds: int | None = None) -> bool:
    """Produit `cog_path`. Renvoie True si une conversion a eu lieu, False si la source
    était déjà un COG valide (simple copie)."""
    require_tiff(raw_path)
    try:
        with rasterio.open(raw_path, driver="GTiff") as src:
            has_crs = src.crs is not None
    except RasterioIOError as exc:
        raise RasterIngestError(f"fichier non lisible comme raster : {exc}") from exc
    if not has_crs:
        raise RasterIngestError("le raster n'a pas de CRS défini")
    is_valid, _errors, _warnings = cog_validate(raw_path, strict=True)
    if is_valid:
        shutil.copyfile(raw_path, cog_path)
        return False
    convert_to_cog(raw_path, cog_path, timeout_seconds=timeout_seconds)
    return True


def read_metadata(path: str) -> RasterMetadata:
    require_tiff(path)
    try:
        with rasterio.open(path, driver="GTiff") as src:
            srid = src.crs.to_epsg() if src.crs else None
            if srid is None:
                raise RasterIngestError("le raster n'a pas de code EPSG identifiable")
            w, s, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            bands = []
            for i in src.indexes:
                st = src.stats(indexes=i, approx=True)[0]
                bands.append(
                    {"index": i, "min": st.min, "max": st.max, "mean": st.mean, "std": st.std}
                )
            return RasterMetadata(
                srid=srid,
                bounds=[w, s, e, n],
                width=src.width,
                height=src.height,
                dtype=src.dtypes[0],
                nodata=None if src.nodata is None else float(src.nodata),
                bands=bands,
            )
    except RasterioIOError as exc:
        raise RasterIngestError(f"fichier non lisible comme raster : {exc}") from exc
