# SPDX-License-Identifier: Apache-2.0
"""Fixtures raster minuscules générées (aucun binaire versionné)."""

import numpy as np
import rasterio
from rasterio.transform import from_origin


def write_tif(path: str, *, crs: str | None = "EPSG:4326", size: int = 64) -> np.ndarray:
    """GeoTIFF size×size non tuilé, 1 bande float32 = rampe (valeur = ligne*size+col), pixel
    0.01°, origine (2.0E, 49.0N). La ligne 0 vaut nodata (-9999). Au-delà de 512 px un TIFF
    non tuilé n'est plus un COG valide (utile pour tester la conversion)."""
    d = np.arange(size * size, dtype="float32").reshape(size, size)
    d[0, :] = -9999.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(2.0, 49.0, 0.01, 0.01),
        nodata=-9999.0,
    ) as dst:
        dst.write(d, 1)
    return d
