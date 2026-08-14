# SPDX-License-Identifier: Apache-2.0
"""Conversion d'un GeoTIFF brut en Cloud Optimized GeoTIFF, requise pour que
TiTiler serve des tuiles à coût constant (design §3). Le profil "deflate"
est sans perte : un profil "webp"/"jpeg" (courant pour de l'imagerie
classique) corromprait les valeurs d'élévation, contrairement à une image
RGB où une perte de qualité visuelle est acceptable — cf. Global
Constraints.

`timeout_seconds` borne uniquement l'appel GDAL potentiellement long
(cog_translate) via signal.alarm — un worker procrastinate exécute ses
tâches de façon synchrone dans le thread principal du process, donc
SIGALRM est sûr ici (Linux uniquement, comme tout ce conteneur)."""
import signal

import rasterio
from rasterio.errors import RasterioIOError
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles


class Terrain3DConversionError(ValueError):
    pass


class _ConversionTimeout(Exception):
    pass


def _raise_timeout(signum, frame):  # noqa: ARG001
    raise _ConversionTimeout()


def convert_to_cog(src_path: str, dest_path: str, *, timeout_seconds: int | None = None) -> None:
    try:
        with rasterio.open(src_path) as src:
            if src.crs is None:
                raise Terrain3DConversionError("le raster n'a pas de CRS défini")
    except RasterioIOError as exc:
        raise Terrain3DConversionError(f"fichier non lisible comme raster : {exc}") from exc

    profile = cog_profiles.get("deflate")
    previous_handler = None
    if timeout_seconds is not None:
        previous_handler = signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(timeout_seconds)
    try:
        cog_translate(
            src_path, dest_path, profile,
            in_memory=False, quiet=True,
            config={"GDAL_NUM_THREADS": "ALL_CPUS", "GDAL_TIFF_INTERNAL_MASK": True},
        )
    except _ConversionTimeout as exc:
        raise Terrain3DConversionError(f"conversion COG interrompue après {timeout_seconds}s") from exc
    except Exception as exc:  # rio_cogeo/GDAL peuvent lever divers types selon la cause
        raise Terrain3DConversionError(f"échec de la conversion COG : {exc}") from exc
    finally:
        if timeout_seconds is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    is_valid, errors, _warnings = cog_validate(dest_path, strict=True)
    if not is_valid:
        raise Terrain3DConversionError(f"COG produit invalide : {'; '.join(errors)}")
