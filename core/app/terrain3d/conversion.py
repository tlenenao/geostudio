# SPDX-License-Identifier: Apache-2.0
"""Conversion d'un GeoTIFF brut en Cloud Optimized GeoTIFF, requise pour que
TiTiler serve des tuiles à coût constant (design §3). Le profil "deflate"
est sans perte : un profil "webp"/"jpeg" (courant pour de l'imagerie
classique) corromprait les valeurs d'élévation, contrairement à une image
RGB où une perte de qualité visuelle est acceptable — cf. Global
Constraints.

`timeout_seconds` borne l'appel GDAL potentiellement long (cog_translate)
en l'exécutant dans un **process fils** joint avec un délai, jamais via
signal.alarm : procrastinate exécute une tâche synchrone via
asgiref.sync.sync_to_async(..., thread_sensitive=False), donc dans un
thread de worker — et signal.signal() lève
`ValueError: signal only works in main thread of the main interpreter`
hors du thread principal. Toute conversion réelle plantait donc à cette
ligne (revue finale de branche, C1). Bénéfice secondaire : la mémoire
allouée par GDAL est bornée au fils, et un fils bloqué est tué pour de
vrai (terminate puis kill).

Le contexte multiprocessing est explicitement "fork" : c'est le seul qui
hérite de l'état déjà importé/monkeypatché du parent (Python 3.14 est
passé à "forkserver" par défaut sur Linux), ce dont dépend le test de
timeout — et le seul qui n'exige pas que la cible soit picklable."""
import multiprocessing
import warnings

import rasterio
from rasterio.errors import RasterioIOError
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

_TERMINATE_GRACE_SECONDS = 5


class Terrain3DConversionError(ValueError):
    pass


def _cog_translate_child(src_path: str, dest_path: str, profile_name: str, conn) -> None:
    """Corps exécuté dans le process fils. Fonction de module (jamais une
    closure/partial) pour rester compatible avec un contexte picklant sa
    cible si le contexte devait changer un jour. Le profil est passé par
    *nom* et résolu ici : cog_profiles.get() rend un dict de driver GDAL
    qu'on ne veut pas transporter."""
    try:
        cog_translate(
            src_path, dest_path, cog_profiles.get(profile_name),
            in_memory=False, quiet=True,
            config={"GDAL_NUM_THREADS": "ALL_CPUS", "GDAL_TIFF_INTERNAL_MASK": True},
        )
    except Exception as exc:  # rio_cogeo/GDAL peuvent lever divers types selon la cause
        conn.send(str(exc) or exc.__class__.__name__)
    else:
        conn.send(None)
    finally:
        conn.close()


def _run_cog_translate(src_path: str, dest_path: str, *, timeout_seconds: int | None) -> None:
    ctx = multiprocessing.get_context("fork")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_cog_translate_child, args=(src_path, dest_path, "deflate", child_conn),
    )
    with warnings.catch_warnings():
        # Python ≥3.12 avertit quand fork() part d'un process multi-threadé
        # (c'est le cas d'un worker procrastinate). Le risque réel — un lock
        # tenu par un autre thread au moment du fork — est couvert par les
        # handlers os.register_at_fork de la stdlib (logging, threading) ;
        # le fils ne fait que du calcul GDAL puis sort. On ne laisse pas cet
        # avertissement casser une conversion sous `filterwarnings = error`.
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        proc.start()
    child_conn.close()
    try:
        proc.join(timeout_seconds)
        if proc.is_alive():
            proc.terminate()
            proc.join(_TERMINATE_GRACE_SECONDS)
            if proc.is_alive():  # SIGTERM ignoré/bloqué : kill dur
                proc.kill()
                proc.join()
            raise Terrain3DConversionError(
                f"conversion COG interrompue après {timeout_seconds}s"
            )
        error = parent_conn.recv() if parent_conn.poll() else None
    finally:
        parent_conn.close()

    if error is not None:
        raise Terrain3DConversionError(f"échec de la conversion COG : {error}")
    if proc.exitcode != 0:
        # Le fils est mort sans rien envoyer (segfault GDAL, OOM killer…).
        raise Terrain3DConversionError(
            f"échec de la conversion COG : processus interrompu (code {proc.exitcode})"
        )


def convert_to_cog(src_path: str, dest_path: str, *, timeout_seconds: int | None = None) -> None:
    try:
        with rasterio.open(src_path) as src:
            if src.crs is None:
                raise Terrain3DConversionError("le raster n'a pas de CRS défini")
    except RasterioIOError as exc:
        raise Terrain3DConversionError(f"fichier non lisible comme raster : {exc}") from exc

    _run_cog_translate(src_path, dest_path, timeout_seconds=timeout_seconds)

    is_valid, errors, _warnings = cog_validate(dest_path, strict=True)
    if not is_valid:
        raise Terrain3DConversionError(f"COG produit invalide : {'; '.join(errors)}")
