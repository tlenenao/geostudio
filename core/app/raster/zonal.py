# SPDX-License-Identifier: Apache-2.0
"""Statistiques par zone (ADR 0024) : rasterio.mask polygone par polygone, en WGS84
reprojeté dans le CRS du raster. Lecture fenêtrée : jamais le raster entier en mémoire."""

import time
from collections.abc import Sequence
from typing import Any

import numpy as np
from rasterio.errors import WindowError
from rasterio.features import geometry_window
from rasterio.mask import mask
from rasterio.warp import transform_geom

MAX_POLYGONS = 1_000
# Fenêtre maximale lue par polygone (pixels) : borne mémoire/temps d'un polygone géant.
MAX_WINDOW_PIXELS = 50_000_000
# Budget cumulé par requête (pixels lus, durée) : 1000 polygones x 50 M px ne doivent pas
# immobiliser un thread de requête.
MAX_TOTAL_PIXELS = 200_000_000
MAX_SECONDS = 20.0
STATS = ("count", "min", "max", "mean", "sum", "std")


class ZonalError(ValueError):
    pass


def _summarize(values: np.ndarray, stats: Sequence[str]) -> dict[str, float | int | None]:
    n = int(values.size)
    out: dict[str, float | int | None] = {}
    for s in stats:
        if s == "count":
            out[s] = n
        elif n == 0:
            out[s] = None
        elif s == "min":
            out[s] = float(values.min())
        elif s == "max":
            out[s] = float(values.max())
        elif s == "mean":
            out[s] = float(values.mean(dtype=np.float64))
        elif s == "sum":
            out[s] = float(values.sum(dtype=np.float64))
        elif s == "std":
            out[s] = float(values.std(dtype=np.float64))
    return out


def zonal_stats(
    ds: Any,
    geometries: Sequence[dict],
    *,
    band: int = 1,
    stats: Sequence[str] = STATS,
    src_crs: str = "EPSG:4326",
) -> list[dict[str, float | int | None]]:
    """Une entrée par géométrie (GeoJSON dans `src_crs`, EPSG:4326 par défaut), dans l'ordre.
    Zone hors raster ou sans pixel valide : count = 0, autres statistiques None."""
    bad = [s for s in stats if s not in STATS]
    if bad:
        raise ZonalError(f"statistique inconnue : {bad[0]}")
    if band not in ds.indexes:
        raise ZonalError(f"bande {band} absente (le raster a {ds.count} bande(s))")
    if len(geometries) > MAX_POLYGONS:
        raise ZonalError(f"trop de polygones ({len(geometries)} > {MAX_POLYGONS})")
    results: list[dict[str, float | int | None]] = []
    total_pixels = 0
    deadline = time.monotonic() + MAX_SECONDS
    for geom in geometries:
        if time.monotonic() > deadline:
            raise ZonalError(
                f"délai dépassé ({MAX_SECONDS:.0f} s) : réduisez le nombre de polygones"
            )
        g = transform_geom(src_crs, ds.crs, geom)
        try:
            win = geometry_window(ds, [g])
            if win.width * win.height > MAX_WINDOW_PIXELS:
                raise ZonalError("polygone trop étendu pour ce raster (fenêtre > 50 M pixels)")
            total_pixels += win.width * win.height
            if total_pixels > MAX_TOTAL_PIXELS:
                raise ZonalError("budget de pixels dépassé (200 M) : réduisez les zones")
            data, _ = mask(ds, [g], crop=True, filled=False, indexes=band)
        except (ValueError, WindowError) as exc:  # zone disjointe du raster
            if isinstance(exc, ZonalError):
                raise
            results.append(_summarize(np.array([]), stats))
            continue
        results.append(_summarize(np.ma.compressed(data), stats))
    return results
