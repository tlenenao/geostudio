# SPDX-License-Identifier: Apache-2.0
"""Module de voie F2 — lecteurs raster/vecteur GDAL (NetCDF, GRIB, ERDAS IMAGINE, JPEG 2000,
Sentinel-2 SAFE, Landsat-8, OSM, WMS, WCS) + CityJSON (Python pur : aucun pilote GDAL).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md (décision D5 : pilote
GDAL absent de l'image => ligne `out_of_scope`, pas de build GDAL maison).

Sécurité (leçons des revues précédentes) :
- Lecteurs de fichiers : même garde-fou que `reader.file` (CORE_PIPELINE_FILE_IO_ENABLED,
  chemin absolu local). Jamais de /vsi*, d'URL, de VRT : le pilote est FORCÉ (`driver=`) et la
  signature magique du fichier est vérifiée avant toute ouverture GDAL.
- Plafonds : taille de fichier, pixels déclarés de la source (bombes de décompression
  NetCDF/GRIB/JP2/PBF), cellules en sortie, délai, mémoire (RLIMIT_AS) — la lecture GDAL
  s'exécute dans un process fils tué au dépassement.
- WMS/WCS : requête émise par la session gardée de `app.pipelines.egress` (SSRF, épinglage DNS,
  redirections revérifiées), flux plafonné en octets et en temps, image plafonnée en pixels.
  Pas de secret (services publics, comme `reader.wfs`).
- Un reader n'a aucun effet de bord.

Les rasters sortent en tabulaire (une ligne par cellule valide : x, y, value|band_N, geometry),
comme `reader.raster`. Ne jamais importer contracts/runtime/registries au niveau module."""

import json
import multiprocessing
import os
import re
import resource
import time
import warnings
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
import pandas as pd
import rasterio
import rasterio.transform
import requests
import shapely
import shapely.errors
import shapely.geometry
from pydantic import BaseModel, Field, model_validator
from rasterio.enums import Resampling
from rasterio.io import MemoryFile

from app.auth.dependency import is_pipeline_file_io_enabled
from app.pipelines.egress import EgressBlockedError, build_guarded_session
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi
from app.terrain3d.conversion import LOCAL_ONLY_GDAL

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_PIXELS = 100_000_000  # pixels déclarés de la source (bombe de décompression)
MAX_CELLS = 2_000_000
MAX_WEB_BYTES = 50 * 1024 * 1024
MAX_WEB_PIXELS = 4_000_000
WEB_DEADLINE_S = 60.0
READ_TIMEOUT_S = 60.0
READ_EXTRA_MEMORY = 1536 * 1024 * 1024  # marge d'espace d'adressage du process fils
_CHUNK = 64 * 1024
_NOT_ABS = "chemin absolu local requis"

# --------------------------------------------------------------------------- garde fichier


def _magic_netcdf(head: bytes) -> bool:
    return head[:3] == b"CDF" or head[:8] == b"\x89HDF\r\n\x1a\n"


def _magic_hfa(head: bytes) -> bool:
    return head.startswith(b"EHFA_HEADER_TAG")


def _magic_jp2(head: bytes) -> bool:
    return head.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n") or head.startswith(
        b"\xff\x4f\xff\x51"
    )


def _magic_grib(head: bytes) -> bool:
    return b"GRIB" in head[:1024]


def _magic_tiff(head: bytes) -> bool:
    return head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


_OSM_XML = re.compile(rb"\A(\xef\xbb\xbf)?\s*(<\?xml[^>]*\?>\s*)?<osm[\s>]")
_OSM_FORBIDDEN = (b"vrt", b"/vsi")  # pilotes à références externes (OGR VRT) / chemins virtuels


def _magic_osm(head: bytes) -> bool:
    """Signature STRICTE : premier élément XML réel = <osm> (pas de commentaire, DOCTYPE ni autre
    racine devant) ou en-tête PBF (longueur + BlobHeader 'OSMHeader') ; et aucune trace de VRT.
    GDAL identifie le format par le contenu et pyogrio n'accepte pas de pilote forcé : un
    polyglotte `<osm>`+`<OGRVRTDataSource>` est donc refusé ici ET, après ouverture, par le
    contrôle du pilote réellement choisi (`_read_osm`)."""
    low = head.lower()
    if any(f in low for f in _OSM_FORBIDDEN):
        return False
    return bool(_OSM_XML.match(head)) or head[4:15] == b"\x0a\x09OSMHeader"


def _check_path(op: str, path: str) -> str:
    """Chemin absolu, local, sans /vsi* ni NUL ; résolu (liens symboliques suivis)."""
    if "\x00" in path or not path.startswith("/") or path.lower().startswith("/vsi"):
        raise PipelineRuntimeError(f"{op}: {_NOT_ABS}")
    if '"' in path:
        raise PipelineRuntimeError(f"{op}: caractère interdit dans le chemin")
    return os.path.realpath(path)


def _require_file_io(op: str) -> None:
    if not is_pipeline_file_io_enabled():
        raise PipelineRuntimeError(f"{op} requires CORE_PIPELINE_FILE_IO_ENABLED=true")


def _local_file(op: str, path: str, magic: Callable[[bytes], bool]) -> str:
    _require_file_io(op)
    real = _check_path(op, path)
    if not os.path.isfile(real):
        raise PipelineRuntimeError(f"{op}: fichier introuvable")
    if os.path.getsize(real) > MAX_FILE_BYTES:
        raise PipelineRuntimeError(f"{op}: file too large (max {MAX_FILE_BYTES} bytes)")
    with open(real, "rb") as f:
        if not magic(f.read(4096)):
            raise PipelineRuntimeError(f"{op}: le contenu ne correspond pas au format attendu")
    return real


def _find_in_dir(op: str, root: str, pattern: re.Pattern, magic) -> str:
    """Premier fichier (ordre alphabétique) du dossier produit dont le nom correspond ;
    liens symboliques et échappements hors du dossier ignorés."""
    _require_file_io(op)
    real_root = _check_path(op, root)
    if not os.path.isdir(real_root):
        raise PipelineRuntimeError(f"{op}: dossier introuvable")
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(real_root, followlinks=False):
        if dirpath[len(real_root) :].count(os.sep) >= 6:
            dirnames[:] = []
        hits += [
            os.path.join(dirpath, n)
            for n in filenames
            if pattern.search(os.path.join(dirpath, n)[len(real_root) :])
        ]
        if len(hits) > 10_000:
            break
    for h in sorted(hits):
        if not os.path.islink(h) and os.path.realpath(h).startswith(real_root + os.sep):
            return _local_file(op, h, magic)
    raise PipelineRuntimeError(f"{op}: aucune bande correspondante dans le produit")


# --------------------------------------------------------------------------- exécution bornée


def _bounded(op: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Exécute `fn(*args)` dans un process fils (fork) borné en mémoire (RLIMIT_AS) et en temps ;
    le résultat (DataFrame) revient par un pipe. Un pilote qui boucle ou explose ne touche pas
    le worker."""
    ctx = multiprocessing.get_context("fork")
    recv, send = ctx.Pipe(duplex=False)

    def child() -> None:
        try:
            with open("/proc/self/statm") as f:
                used = int(f.read().split()[0]) * resource.getpagesize()
            resource.setrlimit(resource.RLIMIT_AS, (used + READ_EXTRA_MEMORY,) * 2)
            send.send(("ok", fn(*args)))
        except BaseException as exc:  # noqa: BLE001 — tout échec du fils est rapporté
            send.send(("err", str(exc) or exc.__class__.__name__))
        finally:
            send.close()

    proc = ctx.Process(target=child, daemon=True)
    with warnings.catch_warnings():
        # Python >= 3.12 avertit si fork() part d'un process multi-threadé (worker) ; le fils ne
        # fait que du calcul puis sort (même choix que terrain3d/conversion.py).
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        proc.start()
    send.close()
    try:
        if not recv.poll(READ_TIMEOUT_S):
            raise PipelineRuntimeError(f"{op}: read exceeded the time limit")
        try:
            status, value = recv.recv()
        except EOFError as exc:
            raise PipelineRuntimeError(f"{op}: reader process died (memory limit?)") from exc
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(5)
        recv.close()
    if status == "err":
        raise PipelineRuntimeError(f"{op}: {value}")
    return value


# --------------------------------------------------------------------------- raster -> cellules


def _raster_frame(ds, bands: list[int], max_cells: int) -> pd.DataFrame:
    if ds.width * ds.height > MAX_SOURCE_PIXELS:
        raise PipelineRuntimeError(
            f"source raster too large ({ds.width}x{ds.height} px, max {MAX_SOURCE_PIXELS})"
        )
    for b in bands:
        if b not in ds.indexes:
            raise PipelineRuntimeError(f"band {b} not found")
    scale = max(1.0, (ds.width * ds.height / max_cells) ** 0.5)
    h, w = max(1, int(ds.height / scale)), max(1, int(ds.width / scale))
    transform = ds.transform * ds.transform.scale(ds.width / w, ds.height / h)
    valid = np.zeros((h, w), dtype=bool)
    arrays = []
    for b in bands:
        arr = ds.read(b, out_shape=(h, w), masked=True, resampling=Resampling.nearest)
        data = np.ma.getdata(arr)
        ok = ~np.ma.getmaskarray(arr)
        if data.dtype.kind == "f":
            ok &= np.isfinite(data)
        valid |= ok
        arrays.append(data)
    rows, cols = np.nonzero(valid)
    xs, ys = rasterio.transform.xy(transform, rows, cols)
    frame = {"x": xs, "y": ys}
    for b, data in zip(bands, arrays, strict=True):
        frame["value" if len(bands) == 1 else f"band_{b}"] = data[rows, cols]
    return pd.DataFrame(frame)


def _srid_of(ds, fallback: int | None) -> int:
    epsg = ds.crs.to_epsg() if ds.crs else None
    srid = epsg or fallback
    if srid is None:
        raise PipelineRuntimeError("le raster n'a pas de CRS EPSG ; renseignez `srid`")
    return srid


def _read_raster_file(path: str, driver: str, open_path: str | None, bands, max_cells, srid):
    """Corps exécuté dans le process fils : retourne (DataFrame, srid)."""
    with rasterio.Env(GDAL_CACHEMAX=128, **LOCAL_ONLY_GDAL):
        with rasterio.open(open_path or path, driver=driver) as ds:
            if ds.subdatasets and open_path is None:
                names = [s.rsplit(":", 1)[-1] for s in ds.subdatasets[:20]]
                raise PipelineRuntimeError(f"plusieurs variables, précisez `variable` : {names}")
            return _raster_frame(ds, bands, max_cells), _srid_of(ds, srid)


MAX_ITEM_PIXELS = 4_000_000  # = raster2.MAX_PIXELS (plafond des ops raster F1)
MAX_ITEM_BANDS = 16


def _to_geotiff(path: str, driver: str, open_path: str | None, srid: int | None, out: str):
    """Process fils : copie le raster (toutes bandes, par bande) en GeoTIFF local."""
    with rasterio.Env(GDAL_CACHEMAX=128, **LOCAL_ONLY_GDAL):
        with rasterio.open(open_path or path, driver=driver) as ds:
            if ds.subdatasets and open_path is None:
                raise ValueError("plusieurs variables, précisez `variable`")
            if ds.width * ds.height > MAX_ITEM_PIXELS:
                raise ValueError(
                    f"raster trop grand pour output=rasterItem ({ds.width}x{ds.height} > "
                    f"{MAX_ITEM_PIXELS} pixels) ; utilisez output=table (décimé)"
                )
            if ds.count > MAX_ITEM_BANDS:
                raise ValueError(f"plus de {MAX_ITEM_BANDS} bandes")
            epsg = _srid_of(ds, srid)
            profile = {
                "driver": "GTiff", "width": ds.width, "height": ds.height, "count": ds.count,
                "dtype": ds.dtypes[0], "transform": ds.transform, "nodata": ds.nodata,
                "crs": f"EPSG:{epsg}",
            }  # fmt: skip
            with rasterio.open(out, "w", **profile) as dst:
                for i in ds.indexes:
                    dst.write(ds.read(i), i)
            return ds.width, ds.height, ds.count, epsg


def _read_raster_item(op, conn, session, user, view_name, p, real, driver, open_path) -> int:
    """output=rasterItem : publie via app.raster.publish (mêmes gardes que les ops F1)."""
    import tempfile

    from fastapi import HTTPException

    from app.auth.dependency import is_raster_enabled
    from app.pipelines.ops.operation_contract import IN_PREVIEW
    from app.raster import publish

    if not is_raster_enabled():
        raise PipelineRuntimeError(f"{op} requires CORE_RASTER_ENABLED=true")
    if session is None or user is None:
        raise PipelineRuntimeError(f"{op}: aucun acteur pour publier le raster")
    if not publish.can_publish(session, user):
        raise PipelineRuntimeError(f"{op}: privilege 'catalog.manage' required")
    with tempfile.TemporaryDirectory(prefix="gs-readers2-") as tmp:
        tif = os.path.join(tmp, "src.tif")
        w, h, n, srid = _bounded(op, _to_geotiff, real, driver, open_path, p.srid, tif)
        item_id, keys = None, []  # type: ignore[var-annotated]
        if not IN_PREVIEW.get():  # aperçu : métadonnées seules, rien n'est publié
            try:
                pub = publish.publish_raster(
                    session, user, tif_path=tif, cog_path=os.path.join(tmp, "cog.tif"),
                    title=p.title or os.path.basename(real)[:200], limit_collection_id=None,
                    filename=os.path.basename(real), keys=keys,
                )  # fmt: skip
                item_id = pub.item_id
            except publish.RasterPublishError as exc:
                raise PipelineRuntimeError(f"{op}: {exc}") from exc
            except HTTPException as exc:  # quota d'items / de stockage
                raise PipelineRuntimeError(f"{op}: {exc.detail}") from exc
        try:
            _materialize_item(conn, view_name, item_id, w, h, n, srid)
        except BaseException:
            for k in keys:
                publish.delete_key(k)
            raise
    return 4326


def _materialize_item(conn, view_name, item_id, w, h, n, srid) -> None:
    conn.execute(
        f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT CAST(? AS VARCHAR) AS item_id, "
        "CAST(? AS INTEGER) AS width, CAST(? AS INTEGER) AS height, "
        "CAST(? AS INTEGER) AS bands, CAST(? AS INTEGER) AS srid",
        [item_id, w, h, n, srid],
    )


def _materialize(conn, frame: pd.DataFrame, view_name: str, geom: Literal["xy", "wkb"]) -> None:
    conn.register("_readers2_tmp", frame)
    try:
        if geom == "xy":
            sel = "*, ST_Point(x, y) AS geometry"
        else:
            sel = ", ".join(
                "ST_GeomFromWKB(CAST(geometry AS BLOB)) AS geometry" if c == "geometry" else _qi(c)
                for c in frame.columns
            )
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {sel} FROM _readers2_tmp")
    finally:
        conn.unregister("_readers2_tmp")


class _FileRasterParams(BaseModel):
    path: str = Field(..., min_length=1)
    band: int = Field(1, ge=1, le=256)
    maxCells: int = Field(1_000_000, ge=1, le=MAX_CELLS)
    srid: int | None = Field(None, ge=1)
    # `table` : une ligne par cellule (décimée au-delà de maxCells). `rasterItem` : publie le
    # raster entier (toutes les bandes, <= 4 M pixels, 16 bandes) comme item raster hébergé
    # (droit catalog.manage, quotas, audit ; rien n'est publié en aperçu) et sort une ligne
    # (item_id, width, height, bands, srid) pour les transformers raster (comme reader.rasterItems).
    output: Literal["table", "rasterItem"] = "table"
    title: str | None = Field(None, min_length=1, max_length=200)


class ReaderNetcdfParams(_FileRasterParams):
    """Lit une variable d'un fichier NetCDF (classique ou NetCDF-4/HDF5) en une ligne par
    cellule valide (x, y, value). Un fichier à plusieurs variables exige `variable` ; lecture
    décimée au-delà de maxCells. Fichier local, mêmes conditions que reader.file."""

    variable: str | None = Field(None, pattern=r"^[A-Za-z0-9_]{1,64}$")


class ReaderErdasImagineParams(_FileRasterParams):
    """Lit une bande d'un raster ERDAS IMAGINE (.img, pilote HFA) en une ligne par cellule
    valide (x, y, value). Fichier local, mêmes conditions que reader.file."""


class ReaderJpeg2000Params(_FileRasterParams):
    """Lit une bande d'un raster JPEG 2000 géoréférencé (GeoJP2/GMLJP2, pilote OpenJPEG) en une
    ligne par cellule valide (x, y, value). Fichier local, mêmes conditions que reader.file."""


class ReaderGribParams(_FileRasterParams):
    """Lit un message (bande) d'un fichier météorologique GRIB en une ligne par cellule valide
    (x, y, value). Fichier local, mêmes conditions que reader.file."""


class ReaderSentinel2Params(BaseModel):
    """Lit une bande d'un produit Sentinel-2 SAFE déjà présent sur disque (dossier .SAFE) :
    bande JP2 (B02, B03, B04, B08, …) en une ligne par cellule valide (x, y, value).
    Aucun téléchargement catalogue ; résolution optionnelle pour les produits L2A."""

    path: str = Field(..., min_length=1)
    band: str = Field("B04", pattern=r"^(B\d{2}A?|TCI|AOT|WVP|SCL)$")
    resolution: Literal[10, 20, 60] | None = None
    maxCells: int = Field(1_000_000, ge=1, le=MAX_CELLS)
    srid: int | None = Field(None, ge=1)


class ReaderLandsat8Params(BaseModel):
    """Lit une bande (1 à 11) d'un produit Landsat-8 déjà présent sur disque (dossier de
    fichiers *_B<n>.TIF) en une ligne par cellule valide (x, y, value, valeurs brutes DN).
    Aucun téléchargement catalogue."""

    path: str = Field(..., min_length=1)
    band: int = Field(4, ge=1, le=11)
    maxCells: int = Field(1_000_000, ge=1, le=MAX_CELLS)
    srid: int | None = Field(None, ge=1)


def _finish(conn, view_name: str, result: tuple[pd.DataFrame, int]) -> int:
    frame, srid = result
    _materialize(conn, frame, view_name, "xy")
    return srid


def read_netcdf(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderNetcdfParams.model_validate(params)
    real = _local_file("reader.netcdf", p.path, _magic_netcdf)
    open_path = f'NETCDF:"{real}":{p.variable}' if p.variable else None
    if p.output == "rasterItem":
        return _read_raster_item(
            "reader.netcdf", conn, session, user, view_name, p, real, "netCDF", open_path
        )
    res = _bounded(
        "reader.netcdf", _read_raster_file, real, "netCDF", open_path, [p.band], p.maxCells, p.srid
    )
    return _finish(conn, view_name, res)


def _simple(op: str, driver: str, magic):
    def reader(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
        p = _FileRasterParams.model_validate(params)
        real = _local_file(op, p.path, magic)
        if p.output == "rasterItem":
            return _read_raster_item(op, conn, session, user, view_name, p, real, driver, None)
        res = _bounded(op, _read_raster_file, real, driver, None, [p.band], p.maxCells, p.srid)
        return _finish(conn, view_name, res)

    return reader


read_erdas = _simple("reader.erdasImagine", "HFA", _magic_hfa)
read_jp2 = _simple("reader.jpeg2000", "JP2OpenJPEG", _magic_jp2)
read_grib = _simple("reader.grib", "GRIB", _magic_grib)


def read_sentinel2(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderSentinel2Params.model_validate(params)
    # La résolution entre dans le motif AVANT le tri (L2A : R10m/R20m/R60m, suffixe _<res>m).
    suffix = rf"_{p.resolution}m" if p.resolution is not None else r"(_\d+m)?"
    pat = re.compile(rf"IMG_DATA.*_{p.band}{suffix}\.jp2$", re.IGNORECASE)
    real = _find_in_dir("reader.sentinel2", p.path, pat, _magic_jp2)
    res = _bounded(
        "reader.sentinel2", _read_raster_file, real, "JP2OpenJPEG", None, [1], p.maxCells, p.srid
    )
    return _finish(conn, view_name, res)


def read_landsat8(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderLandsat8Params.model_validate(params)
    pat = re.compile(rf"_B{p.band}\.tif$", re.IGNORECASE)
    real = _find_in_dir("reader.landsat8", p.path, pat, _magic_tiff)
    res = _bounded(
        "reader.landsat8", _read_raster_file, real, "GTiff", None, [1], p.maxCells, p.srid
    )
    return _finish(conn, view_name, res)


# --------------------------------------------------------------------------- OSM

_OSM_LAYERS = ("points", "lines", "multilinestrings", "multipolygons", "other_relations")


class ReaderOsmParams(BaseModel):
    """Lit une couche d'un fichier OpenStreetMap (XML .osm ou binaire .pbf) : points, lignes,
    multilignes, multipolygones ou autres relations ; balises restantes dans `other_tags`.
    Plafond d'entités. Fichier local, mêmes conditions que reader.file."""

    path: str = Field(..., min_length=1)
    layer: Literal["points", "lines", "multilinestrings", "multipolygons", "other_relations"] = (
        "points"
    )
    maxFeatures: int = Field(10_000, ge=1, le=100_000)


def _read_osm(real: str, layer: str, max_features: int) -> pd.DataFrame:
    import pyogrio

    pyogrio.set_gdal_config_options({"OSM_MAX_TMPFILE_SIZE": "100", **LOCAL_ONLY_GDAL})
    driver = pyogrio.read_info(real, layer=layer).get("driver")
    if driver != "OSM":  # ceinture et bretelles : le pilote choisi par GDAL doit être OSM
        raise PipelineRuntimeError(f"pilote inattendu '{driver}'")
    gdf = pyogrio.read_dataframe(real, layer=layer, max_features=max_features)
    out = pd.DataFrame(gdf.drop(columns="geometry"))
    out["geometry"] = gdf.geometry.map(lambda g: None if g is None else shapely.to_wkb(g))
    return out


def read_osm(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderOsmParams.model_validate(params)
    real = _local_file("reader.osm", p.path, _magic_osm)
    frame = _bounded("reader.osm", _read_osm, real, p.layer, p.maxFeatures)
    if any(c.lower() == "geometry" for c in frame.columns if c != "geometry"):
        raise PipelineRuntimeError("reader.osm: colonne 'geometry' en collision")
    _materialize(conn, frame, view_name, "wkb")
    return 4326


# --------------------------------------------------------------------------- CityJSON

MAX_CITYJSON_BYTES = 50 * 1024 * 1024


class ReaderCityjsonParams(BaseModel):
    """Lit un fichier CityJSON (modèle de ville 3D) en une ligne par objet (bâtiment, pont…) :
    id, type, lod, attributs (JSON), altitudes min/max et empreinte 2D (union des faces projetées
    à plat ; la 3D n'est pas conservée). `lod` filtre le niveau de détail (sinon le plus fin).
    Fichier local, mêmes conditions que reader.file."""

    path: str = Field(..., min_length=1)
    lod: str | None = Field(None, max_length=8)
    maxObjects: int = Field(10_000, ge=1, le=100_000)
    srid: int | None = Field(None, ge=1)


def _surfaces(geom: dict) -> list:
    t, b = geom.get("type"), geom.get("boundaries") or []
    if t in ("MultiSurface", "CompositeSurface"):
        return b
    if t == "Solid":
        return [s for shell in b for s in shell]
    if t in ("MultiSolid", "CompositeSolid"):
        return [s for solid in b for shell in solid for s in shell]
    return []


_CITY_COLS = ["id", "type", "lod", "attributes", "min_z", "max_z", "error", "geometry"]


def _city_object(obj: dict, verts: np.ndarray, lod: str | None) -> dict:
    """Une ligne par objet ; toute entrée dégénérée devient une erreur DE LIGNE (`error`)."""
    geoms = obj.get("geometry") or []
    if lod is not None:
        geoms = [g for g in geoms if str(g.get("lod")) == lod]
    elif geoms:  # niveau le plus fin
        best = max(str(g.get("lod", "")) for g in geoms)
        geoms = [g for g in geoms if str(g.get("lod", "")) == best]
    polys, zs = [], []
    try:
        for g in geoms:
            for surf in _surfaces(g):
                if not surf:
                    continue
                for ring in surf:
                    if len(ring) < 3:
                        raise ValueError("anneau de moins de 3 sommets")
                    if min(ring) < 0 or max(ring) >= len(verts):
                        raise ValueError("indice de sommet hors bornes")
                rings = [verts[np.asarray(r, dtype=int)] for r in surf]
                zs.append(rings[0][:, 2])
                poly = shapely.geometry.Polygon(rings[0][:, :2], [r[:, :2] for r in rings[1:]])
                if poly.area > 0:  # faces verticales : projection dégénérée, ignorée
                    polys.append(poly if poly.is_valid else poly.buffer(0))
        footprint = shapely.union_all(polys) if polys else None
        error = None
    except (ValueError, TypeError, shapely.errors.GEOSException) as exc:
        footprint, zs, error = None, [], f"géométrie invalide : {exc}"
    zall = np.concatenate(zs) if zs else None
    return {
        "type": obj.get("type"),
        "lod": str(geoms[0].get("lod")) if geoms else None,
        "attributes": json.dumps(obj.get("attributes") or {}),
        "min_z": float(zall.min()) if zall is not None else None,
        "max_z": float(zall.max()) if zall is not None else None,
        "error": error,
        "geometry": shapely.to_wkb(footprint) if footprint is not None else None,
    }


def _cityjson_frame(real: str, lod: str | None, max_objects: int, srid: int | None):
    """Corps exécuté dans le process fils borné (json.load d'un fichier jusqu'à 50 Mo = jusqu'à
    ~1 Go d'objets Python : hors du worker)."""
    try:
        with open(real, encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("type") != "CityJSON":
            raise ValueError("type != CityJSON")
        verts = np.asarray(doc["vertices"], dtype="float64").reshape(-1, 3)
        objects = doc.get("CityObjects") or {}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"fichier CityJSON invalide ({exc})") from exc
    tr = doc.get("transform") or {}
    verts = verts * np.asarray(tr.get("scale", [1, 1, 1]), dtype="float64") + np.asarray(
        tr.get("translate", [0, 0, 0]), dtype="float64"
    )
    if srid is None:
        crs = str((doc.get("metadata") or {}).get("referenceSystem"))
        m = re.search(r"EPSG[/:]+(?:\d+[/:]+)?(\d+)$", crs)
        srid = int(m.group(1)) if m else None
    if srid is None:
        raise ValueError("pas de CRS EPSG dans metadata ; renseignez `srid`")
    rows = []
    for oid, obj in list(objects.items())[:max_objects]:
        try:
            rows.append({"id": oid, **_city_object(obj, verts, lod)})
        except (AttributeError, TypeError, ValueError) as exc:  # objet mal formé
            rows.append({"id": oid, "error": f"objet invalide : {exc}"})
    return pd.DataFrame(rows, columns=_CITY_COLS), srid


def read_cityjson(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderCityjsonParams.model_validate(params)
    op = "reader.cityjson"
    real = _local_file(op, p.path, lambda h: b"CityJSON" in h or b"cityjson" in h.lower())
    if os.path.getsize(real) > MAX_CITYJSON_BYTES:
        raise PipelineRuntimeError(f"{op}: file too large (max {MAX_CITYJSON_BYTES} bytes)")
    frame, srid = _bounded(op, _cityjson_frame, real, p.lod, p.maxObjects, p.srid)
    _materialize(conn, frame, view_name, "wkb")
    return srid


# --------------------------------------------------------------------------- WMS / WCS


def _fetch_image(op: str, url: str, query: dict) -> bytes:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise PipelineRuntimeError(f"{op}: URL http(s) requise")
    deadline = time.monotonic() + WEB_DEADLINE_S
    response = None
    try:
        response = build_guarded_session().get(url, params=query, stream=True)
        response.raise_for_status()
        chunks, total = [], 0
        for chunk in response.iter_content(_CHUNK):
            total += len(chunk)
            if total > MAX_WEB_BYTES:
                raise PipelineRuntimeError(f"{op}: response too large")
            if time.monotonic() > deadline:
                raise PipelineRuntimeError(f"{op}: download exceeded the time limit")
            chunks.append(chunk)
        return b"".join(chunks)
    except EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, EgressBlockedError):
            raise PipelineRuntimeError(f"{op}: egress blocked: {cause}") from exc
        raise PipelineRuntimeError(f"{op}: request failed: {exc}") from exc
    finally:
        if response is not None:
            response.close()


def _image_frame(op: str, body: bytes, bbox, srid: int, width: int, height: int):
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        driver = "PNG"
    elif body[:3] == b"\xff\xd8\xff":
        driver = "JPEG"
    elif _magic_tiff(body[:4]):
        driver = "GTiff"
    else:
        raise PipelineRuntimeError(f"{op}: response is not an image (service exception?)")
    with (
        warnings.catch_warnings()
    ):  # PNG/JPEG non géoréférencés : attendu, emprise appliquée plus bas
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        return _image_frame_open(op, body, driver, bbox, srid, width, height)


def _image_frame_open(op, body, driver, bbox, srid, width, height):
    with MemoryFile(body) as mem, rasterio.Env(**LOCAL_ONLY_GDAL), mem.open(driver=driver) as ds:
        if ds.width * ds.height > MAX_WEB_PIXELS:
            raise PipelineRuntimeError(f"{op}: image too large")
        size = (ds.width, ds.height)  # taille REÇUE (le serveur peut ignorer WIDTH/HEIGHT)
        frame = _raster_frame(ds, list(range(1, min(ds.count, 8) + 1)), MAX_WEB_PIXELS)
        if driver == "GTiff" and ds.crs is not None:
            return frame, ds.crs.to_epsg() or srid
    if driver != "GTiff":  # PNG/JPEG non géoréférencés : on applique l'emprise demandée
        t = rasterio.transform.from_bounds(*bbox, size[0], size[1])
        cols = np.floor(frame["x"].to_numpy()).astype(int)
        rows = np.floor(frame["y"].to_numpy()).astype(int)
        frame["x"], frame["y"] = rasterio.transform.xy(t, rows, cols)
    return frame, srid


class _WebParams(BaseModel):
    url: str = Field(..., min_length=1)
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    srid: int = Field(4326, ge=1)
    width: int = Field(256, ge=1, le=2048)
    height: int = Field(256, ge=1, le=2048)

    @model_validator(mode="after")
    def _check(self):
        if self.width * self.height > MAX_WEB_PIXELS:
            raise ValueError(f"width*height > {MAX_WEB_PIXELS}")
        if not (self.bbox[0] < self.bbox[2] and self.bbox[1] < self.bbox[3]):
            raise ValueError("bbox doit être [minx, miny, maxx, maxy] non vide")
        return self


class ReaderWmsParams(_WebParams):
    """Lit une image d'un service WMS (GetMap, emprise et taille bornées) en une ligne par pixel
    (x, y, band_1..band_n : valeurs RGB[A] du rendu, pas des données brutes — pour des valeurs
    mesurées, utiliser un WCS). Requête via la garde d'egress, services publics sans secret."""

    layers: str = Field(..., min_length=1, max_length=500)
    version: Literal["1.1.1", "1.3.0"] = "1.3.0"
    styles: str = Field("", max_length=500)
    format: Literal["image/png", "image/jpeg"] = "image/png"


class ReaderWcsParams(_WebParams):
    """Lit une couverture d'un service WCS (GetCoverage en GeoTIFF, emprise et taille bornées) en
    une ligne par cellule valide (x, y, band_1..band_n : valeurs brutes). Requête via la garde
    d'egress, services publics sans secret. En 2.0.1 les noms d'axes (x/y) varient selon les
    serveurs."""

    coverage: str = Field(..., min_length=1, max_length=200)
    version: Literal["1.0.0", "2.0.1"] = "1.0.0"


def read_wms(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderWmsParams.model_validate(params)
    minx, miny, maxx, maxy = p.bbox
    # WMS 1.3.0 : l'axe de l'EPSG:4326 est lat/lon.
    bbox_q = (miny, minx, maxy, maxx) if p.version == "1.3.0" and p.srid == 4326 else p.bbox
    query = {
        "service": "WMS", "version": p.version, "request": "GetMap", "layers": p.layers,
        "styles": p.styles, "bbox": ",".join(map(str, bbox_q)), "width": p.width,
        "height": p.height, "format": p.format,
        ("crs" if p.version == "1.3.0" else "srs"): f"EPSG:{p.srid}",
    }  # fmt: skip
    body = _fetch_image("reader.wms", p.url, query)
    frame, srid = _image_frame("reader.wms", body, p.bbox, p.srid, p.width, p.height)
    _materialize(conn, frame, view_name, "xy")
    return srid


def read_wcs(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    p = ReaderWcsParams.model_validate(params)
    minx, miny, maxx, maxy = p.bbox
    if p.version == "1.0.0":
        query = {
            "service": "WCS", "version": "1.0.0", "request": "GetCoverage",
            "coverage": p.coverage, "crs": f"EPSG:{p.srid}", "bbox": ",".join(map(str, p.bbox)),
            "width": p.width, "height": p.height, "format": "GeoTIFF",
        }  # fmt: skip
    else:
        query = [
            ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
            ("coverageid", p.coverage), ("subset", f"x({minx},{maxx})"),
            ("subset", f"y({miny},{maxy})"), ("scalesize", f"x({p.width}),y({p.height})"),
            ("format", "image/tiff"),
        ]  # fmt: skip
    body = _fetch_image("reader.wcs", p.url, query)  # type: ignore[arg-type]
    if not _magic_tiff(body[:4]):
        raise PipelineRuntimeError("reader.wcs: response is not a GeoTIFF (service exception?)")
    frame, srid = _image_frame("reader.wcs", body, p.bbox, p.srid, p.width, p.height)
    _materialize(conn, frame, view_name, "xy")
    return srid


# --------------------------------------------------------------------------- contrats

_GDAL = "MIT/X (GDAL, pilote {}) via rasterio (BSD-3-Clause)"


def _c(op: str, model: type[BaseModel], engine: str, lic: str, enabled=None) -> OperationContract:
    return OperationContract(
        op=op, kind="reader", params_schema=model, engine=engine, engine_license=lic,
        enabled_when=enabled,
    )  # fmt: skip


_FIO = is_pipeline_file_io_enabled
_JP2 = _GDAL.format("JP2OpenJPEG")
_PY = "BSD-3-Clause (rasterio) ; GDAL (MIT)"
CONTRACTS: list[OperationContract] = [
    _c("reader.netcdf", ReaderNetcdfParams, "python", _GDAL.format("netCDF"), _FIO),
    _c("reader.erdasImagine", ReaderErdasImagineParams, "python", _GDAL.format("HFA"), _FIO),
    _c("reader.jpeg2000", ReaderJpeg2000Params, "python", _JP2 + " ; OpenJPEG BSD-2-Clause", _FIO),
    _c("reader.grib", ReaderGribParams, "python", _GDAL.format("GRIB"), _FIO),
    _c("reader.sentinel2", ReaderSentinel2Params, "python", _JP2, _FIO),
    _c("reader.landsat8", ReaderLandsat8Params, "python", _GDAL.format("GTiff"), _FIO),
    _c("reader.osm", ReaderOsmParams, "python", _GDAL.format("OSM"), _FIO),
    _c("reader.cityjson", ReaderCityjsonParams, "python", "stdlib json ; Shapely (BSD-3)", _FIO),
    _c("reader.wms", ReaderWmsParams, "python", _PY),
    _c("reader.wcs", ReaderWcsParams, "python", _PY),
]
READERS: dict[str, Callable] = {
    "reader.netcdf": read_netcdf,
    "reader.erdasImagine": read_erdas,
    "reader.jpeg2000": read_jp2,
    "reader.grib": read_grib,
    "reader.sentinel2": read_sentinel2,
    "reader.landsat8": read_landsat8,
    "reader.osm": read_osm,
    "reader.cityjson": read_cityjson,
    "reader.wms": read_wms,
    "reader.wcs": read_wcs,
}
WRITERS: dict[str, Callable] = {}
