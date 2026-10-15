# SPDX-License-Identifier: Apache-2.0
"""Module de voie F1 — opérations raster (FME : Raster*, WebMapTiler, ImageFetcher,
VectorOnRasterOverlayer, SurfaceDraper).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Modèle de donnée raster dans un pipeline (le moteur DuckDB reste tabulaire, aucun changement du
modèle partagé) : un raster n'est jamais une valeur de ligne mais une RÉFÉRENCE vers un item
`raster` hébergé (ARC-33). Une op raster est un `transform` dont chaque ligne d'entrée porte
l'id d'un item dans la colonne `itemColumn` (source : `reader.rasterItems`, ou toute table). Elle
produit soit une sortie tabulaire (stats, GCP, valeurs draguées, tuiles/blobs PNG), soit un
NOUVEL item raster hébergé (colonne `raster_item_id`) publié via `app.raster.publish` : droit
`catalog.manage`, quotas, audit, `limit_collection_id` hérité de la source. Mêmes portes que
`reader.raster` : `can(read)` sur chaque source (404 indistinguable), refus fail-closed des
limites géographiques, flag `CORE_RASTER_ENABLED` revérifié à l'exécution.

Plafonds (le travail dans la boucle Python n'est pas borné par DuckDB) : MAX_PIXELS par raster
d'entrée, MAX_BANDS, MAX_ROWS rasters par nœud, MAX_OUT_ITEMS, MAX_SECONDS (timeout coopératif
vérifié à chaque bloc), lecture et écriture FENÊTRÉES par blocs de BLOCK px. En aperçu : le
calcul est exécuté (bornes identiques) mais RIEN n'est publié (`raster_item_id` NULL)."""

import json
import math
import os
import tempfile
import time
import warnings
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from typing import Any, Literal

import numpy as np
import pandas as pd
import rasterio
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import Affine, GroundControlPoint, from_gcps
from rasterio.warp import reproject, transform, transform_geom
from rasterio.windows import Window

from app.auth.dependency import is_raster_enabled
from app.pipelines.egress import EgressBlockedError, build_guarded_session
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.pipelines.ops.raster import _authorized_asset
from app.raster import publish as _publish
from app.raster.service import open_asset
from app.sql_ident import quote_ident_duckdb as _qi
from app.terrain3d.conversion import LOCAL_ONLY_GDAL

MAX_PIXELS = 4_000_000  # par raster d'entrée
MAX_OUT_PIXELS = 16_000_000  # mosaïque
MAX_BANDS = 16
MAX_ROWS = 10  # rasters (lignes) par nœud
MAX_OUT_ITEMS = 20  # items publiés par nœud
MAX_SECONDS = 120.0
BLOCK = 512
MAX_BLOB_PIXELS = 1_000_000
MAX_BLOB_BYTES = 16_000_000
MAX_TILES = 256
MAX_TILE_BYTES = 64_000_000
MAX_POINTS = 20_000
MAX_GEOMS = 10_000
MAX_IMAGE_BYTES = 20_000_000
_FETCH_CHUNK = 65_536
_NODATA = -9999.0
_ORIGIN = 20037508.342789244

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}


class _RowError(Exception):
    """Erreur attachée à UNE ligne (colonne `raster_error`) ; les autres lignes continuent."""


# --------------------------------------------------------------------------- infra


class _Run:
    def __init__(self, op: str, resolver, preview: bool) -> None:
        self.op, self.preview = op, preview
        self.session = getattr(resolver, "session", None)
        self.user = getattr(resolver, "user", None)
        if self.session is None or self.user is None:
            raise PipelineRuntimeError(f"{op}: aucun acteur pour lire le raster")
        self.deadline = time.monotonic() + MAX_SECONDS
        self.stack = ExitStack()
        self.tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="gs-raster2-"))
        self.published = 0
        self.keys: list[str] = []
        self._n = 0

    def __enter__(self) -> "_Run":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stack.close()
        if exc_type is not None:
            # run en échec : l'item publié sera annulé avec la session, pas l'objet S3
            for key in self.keys:
                _publish.delete_key(key)
            if isinstance(exc, _RowError):
                raise PipelineRuntimeError(f"{self.op}: {exc}") from exc

    def require_publish(self) -> None:
        """Droit de publication vérifié AVANT tout travail coûteux (appel réseau)."""
        if not _publish.can_publish(self.session, self.user):
            raise PipelineRuntimeError(f"{self.op}: privilege 'catalog.manage' required")

    def tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise PipelineRuntimeError(f"{self.op}: délai dépassé ({MAX_SECONDS:.0f} s)")

    def path(self, suffix: str = ".tif") -> str:
        self._n += 1
        return os.path.join(self.tmp, f"f{self._n}{suffix}")

    def open(self, item_id: str, *, max_pixels: int | None = None):
        """Asset autorisé + dataset borné. 404/403 -> PipelineRuntimeError (jamais ligne)."""
        if not is_raster_enabled():
            raise PipelineRuntimeError(f"{self.op} requires CORE_RASTER_ENABLED=true")
        asset = _authorized_asset(self.session, self.user.tenant_id, self.user, item_id, self.op)
        ds = self.stack.enter_context(open_asset(asset))
        max_pixels = MAX_PIXELS if max_pixels is None else max_pixels
        if ds.width * ds.height > max_pixels:
            raise PipelineRuntimeError(
                f"{self.op}: raster '{item_id}' trop grand "
                f"({ds.width}x{ds.height} > {max_pixels} pixels)"
            )
        if ds.count > MAX_BANDS:
            raise PipelineRuntimeError(f"{self.op}: plus de {MAX_BANDS} bandes")
        return ds, asset

    def publish(self, tif: str, title: str, limit_ids: list, filename: str = "pipeline.tif"):
        """Dict de colonnes de sortie. Aperçu : métadonnées seules, rien n'est publié."""
        with rasterio.open(tif) as o:
            w, h, n = o.width, o.height, o.count
        if self.preview:
            return {
                "raster_item_id": None,
                "raster_width": w,
                "raster_height": h,
                "raster_bands": n,
            }
        if self.published >= MAX_OUT_ITEMS:
            raise PipelineRuntimeError(f"{self.op}: plus de {MAX_OUT_ITEMS} rasters produits")
        limits = {x for x in limit_ids if x}
        if len(limits) > 1:
            raise _RowError("rasters sources liés à des collections de limites différentes")
        self.published += 1
        try:
            p = _publish.publish_raster(
                self.session,
                self.user,
                tif_path=tif,
                cog_path=self.path(".cog.tif"),
                title=title,
                limit_collection_id=next(iter(limits), None),
                filename=filename,
                timeout_seconds=max(1, int(self.deadline - time.monotonic())),
                keys=self.keys,
            )
        except _publish.RasterPublishError as exc:
            raise PipelineRuntimeError(f"{self.op}: {exc}") from exc
        except HTTPException as exc:  # QuotaExceededError (quota d'items/stockage)
            raise PipelineRuntimeError(f"{self.op}: {exc.detail}") from exc
        return {
            "raster_item_id": p.item_id,
            "raster_width": p.width,
            "raster_height": p.height,
            "raster_bands": p.bands,
        }


def _blocks(w: int, h: int) -> Iterator[Window]:
    for r in range(0, h, BLOCK):
        for c in range(0, w, BLOCK):
            yield Window(c, r, min(BLOCK, w - c), min(BLOCK, h - r))


def _columns(conn, view: str) -> list[str]:
    return [d[0] for d in conn.execute(f"DESCRIBE {_qi(view)}").fetchall()]


def _item_rows(
    conn, view: str, col: str, op: str
) -> tuple[list[str], list[tuple[int, str | None]]]:
    cols = _columns(conn, view)
    if col not in cols:
        raise PipelineRuntimeError(f"{op}: input has no '{col}' column")
    rows = conn.execute(
        f"SELECT row_number() OVER () AS rn, CAST({_qi(col)} AS VARCHAR) FROM {_qi(view)} "
        f"LIMIT {MAX_ROWS + 1}"
    ).fetchall()
    if len(rows) > MAX_ROWS:
        raise PipelineRuntimeError(f"{op}: more than {MAX_ROWS} rasters in input")
    return cols, [(rn, (v or "").strip() or None) for rn, v in rows]


def _require_srid(op: str, input_srid: int | None) -> None:
    """SRID 0 = « non défini » (transform.removeSrid) : jamais replié sur 4326 (`or 4326`)."""
    if input_srid == 0:
        raise PipelineRuntimeError(f"{op}: SRID non défini (0) en entrée — reprojection impossible")


def _no_clash(op: str, cols: list[str], new: list[str]) -> None:
    clash = [c for c in new if c in cols]
    if clash:
        raise PipelineRuntimeError(f"{op}: input already has column(s) {clash}")


def _emit_join(conn, view: str, name: str, types: dict[str, str], results: dict[int, dict]) -> None:
    """Colonnes d'entrée + colonnes de sortie typées (NULL pour les lignes sans résultat)."""
    frame = pd.DataFrame(
        [{"rn": rn, **r} for rn, r in results.items()], columns=["rn", *types]
    ).astype(object)
    conn.register("_r2_res", frame)
    try:
        sel = "".join(f", CAST(r.{_qi(c)} AS {t}) AS {_qi(c)}" for c, t in types.items())
        conn.execute(
            f"CREATE TEMP TABLE {_qi(name)} AS SELECT s.* EXCLUDE (_rn){sel} "
            f"FROM (SELECT *, row_number() OVER () AS _rn FROM {_qi(view)}) s "
            "LEFT JOIN _r2_res r ON r.rn = s._rn ORDER BY s._rn"
        )
    finally:
        conn.unregister("_r2_res")


def _emit_table(conn, name: str, rows: list[dict], types: dict[str, str]) -> None:
    frame = pd.DataFrame(rows, columns=list(types)).astype(object)
    conn.register("_r2_tab", frame)
    try:
        sel = ", ".join(f"CAST({_qi(c)} AS {t}) AS {_qi(c)}" for c, t in types.items())
        conn.execute(f"CREATE TEMP TABLE {_qi(name)} AS SELECT {sel} FROM _r2_tab")
    finally:
        conn.unregister("_r2_tab")


_OUT_TYPES = {
    "raster_item_id": "VARCHAR",
    "raster_width": "INTEGER",
    "raster_height": "INTEGER",
    "raster_bands": "INTEGER",
    "raster_error": "VARCHAR",
}


def _fits(value: float | None, dtype: str) -> bool:
    if value is None:
        return True
    dt = np.dtype(dtype)
    if np.issubdtype(dt, np.integer):
        i = np.iinfo(dt)
        return float(value).is_integer() and i.min <= value <= i.max
    return bool(np.isfinite(value)) and abs(value) <= float(np.finfo(dt).max)


def _same_grid(a, b) -> None:
    if (
        a.width != b.width
        or a.height != b.height
        or a.crs != b.crs
        or not all(
            abs(x - y) <= 1e-9 * max(1.0, abs(x))
            for x, y in zip(a.transform, b.transform, strict=True)
        )
    ):
        raise _RowError("les rasters n'ont pas la même grille (taille, CRS, géotransformée)")


def _write(
    path: str,
    ds,
    *,
    count: int,
    dtype: str,
    nodata: float | None,
    transform_: Affine | None = None,
    crs=None,
    width: int | None = None,
    height: int | None = None,
    tags: dict | None = None,
):
    out = rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width or ds.width,
        height=height or ds.height,
        count=count,
        dtype=dtype,
        crs=crs or ds.crs,
        transform=transform_ or ds.transform,
        nodata=nodata,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    )
    if tags:
        out.update_tags(**tags)
    return out


def _copy(
    run: _Run,
    ds,
    out_path: str,
    *,
    bands: list[int] | None = None,
    nodata: Any = "keep",
    transform_: Affine | None = None,
    crs=None,
    post: Callable | None = None,
    tags: dict | None = None,
) -> None:
    """Copie fenêtrée (bandes choisies), géoréférence/nodata surchargeables ; `post(arr, win)`
    peut modifier le bloc (masked array de forme (bandes, h, w)) avant écriture."""
    bands = bands or list(ds.indexes)
    nd = ds.nodata if nodata == "keep" else nodata
    if not _fits(nd, ds.dtypes[0]):
        raise _RowError(f"nodata {nd} incompatible avec le type {ds.dtypes[0]}")
    with _write(
        out_path,
        ds,
        count=len(bands),
        dtype=ds.dtypes[0],
        nodata=nd,
        transform_=transform_,
        crs=crs,
        tags=tags,
    ) as out:
        for win in _blocks(ds.width, ds.height):
            run.tick()
            arr = ds.read(bands, window=win, masked=False)
            if post is not None:
                arr = post(arr, win)
            out.write(arr, window=win)


def _finish_rows(conn, view, name, cols, results, extra: dict[str, str]) -> None:
    _emit_join(conn, view, name, {**_OUT_TYPES, **extra}, results)


class _ItemColumn(BaseModel):
    itemColumn: str = Field("item_id", min_length=1, description="Colonne portant l'id du raster")
    title: str = Field("Raster dérivé", min_length=1, max_length=200)


def _derive_per_row(
    conn,
    *,
    op: str,
    view: str,
    name: str,
    p: _ItemColumn,
    resolver,
    preview: bool,
    build: Callable[[_Run, Any, Any, str], None],
    title: str | None = None,
) -> None:
    """Une ligne = un raster source -> un raster dérivé (`build(run, ds, asset, out_path)`)."""
    cols, rows = _item_rows(conn, view, p.itemColumn, op)
    _no_clash(op, cols, list(_OUT_TYPES))
    results: dict[int, dict] = {}
    with _Run(op, resolver, preview) as run:
        for rn, item_id in rows:
            run.tick()
            if item_id is None:
                results[rn] = {"raster_error": "identifiant de raster absent"}
                continue
            ds, asset = run.open(item_id)
            out = run.path()
            try:
                build(run, ds, asset, out)
                results[rn] = run.publish(out, title or p.title, [asset.limit_collection_id])
            except _RowError as exc:
                results[rn] = {"raster_error": str(exc)}
    _finish_rows(conn, view, name, cols, results, {})


# ------------------------------------------------------------------ reader.rasterItems


class ReaderRasterItemsParams(BaseModel):
    """Référence des rasters hébergés (items `raster`) : une ligne par raster avec son id, sa
    taille, son nombre de bandes et son SRID — point d'entrée des ops raster du pipeline."""

    itemIds: list[str] = Field(..., min_length=1, max_length=MAX_ROWS)


def read_raster_items(
    conn, *, session, tenant_id, node_id, params, view_name, user, base_uri
) -> int:
    p = ReaderRasterItemsParams.model_validate(params)
    rows = []
    for item_id in dict.fromkeys(p.itemIds):
        a = _authorized_asset(session, tenant_id, user, item_id, "reader.rasterItems")
        rows.append(
            {
                "item_id": item_id,
                "width": a.width,
                "height": a.height,
                "bands": len(a.bands) or 1,
                "srid": a.srid,
            }
        )
    _emit_table(
        conn,
        view_name,
        rows,
        {
            "item_id": "VARCHAR",
            "width": "INTEGER",
            "height": "INTEGER",
            "bands": "INTEGER",
            "srid": "INTEGER",
        },
    )
    return 4326


READERS["reader.rasterItems"] = read_raster_items

# ------------------------------------------------------- RasterCellValueCalculator


class TransformRasterCalcParams(_ItemColumn):
    """Calcule cellule à cellule une opération (somme, différence, produit, quotient, minimum,
    maximum, moyenne) entre le raster de chaque ligne et un second raster : publie un raster
    flottant 32 bits (nodata -9999 si l'une des cellules est invalide ou si la division est par
    zéro). Les deux rasters doivent avoir exactement la même grille."""

    otherItemId: str = Field(..., min_length=1)
    operation: Literal["add", "subtract", "multiply", "divide", "min", "max", "mean"]
    band: int = Field(1, ge=1)
    otherBand: int = Field(1, ge=1)


_CALC = {
    "add": np.ma.add,
    "subtract": np.ma.subtract,
    "multiply": np.ma.multiply,
    "divide": np.ma.divide,
    "min": np.ma.minimum,
    "max": np.ma.maximum,
    "mean": lambda a, b: (a + b) / 2,
}


def execute_calc(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterCalcParams.model_validate(params)

    def build(run: _Run, a, asset_a, out_path: str) -> None:
        b, asset_b = run.open(p.otherItemId)
        _same_grid(a, b)
        if p.band > a.count or p.otherBand > b.count:
            raise _RowError("bande inexistante")
        if asset_a.limit_collection_id != asset_b.limit_collection_id:
            raise _RowError("rasters sources liés à des collections de limites différentes")
        with _write(out_path, a, count=1, dtype="float32", nodata=_NODATA) as out:
            for win in _blocks(a.width, a.height):
                run.tick()
                x = a.read(p.band, window=win, masked=True).astype("float64")
                y = b.read(p.otherBand, window=win, masked=True).astype("float64")
                with np.errstate(all="ignore"):
                    r = np.ma.masked_invalid(_CALC[p.operation](x, y))
                out.write(np.ma.filled(r, _NODATA).astype("float32"), 1, window=win)

    _derive_per_row(
        conn,
        op="transform.rasterCalc",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )


# ------------------------------------------------------------------ RasterConvolver


class TransformRasterConvolveParams(_ItemColumn):
    """Applique un noyau de convolution (au plus 7x7, dimensions impaires) à toutes les bandes
    du raster de chaque ligne : lissage, accentuation, contours. Les cellules invalides sont
    ignorées du voisinage (noyau renormalisé) et restent invalides ; le résultat est flottant
    32 bits. Noyau appliqué en corrélation (identique à une convolution pour un noyau
    symétrique)."""

    kernel: list[list[float]] = Field(..., min_length=1, max_length=7)
    normalize: bool = True

    @field_validator("kernel")
    @classmethod
    def _shape(cls, k):
        w = len(k[0]) if k else 0
        if w < 1 or w > 7 or w % 2 == 0 or len(k) % 2 == 0 or any(len(r) != w for r in k):
            raise ValueError("kernel must be a rectangle of odd dimensions, at most 7x7")
        if not all(math.isfinite(v) for r in k for v in r):
            raise ValueError("kernel must hold finite numbers")
        return k

    @model_validator(mode="after")
    def _sum(self):
        if self.normalize and abs(sum(map(sum, self.kernel))) < 1e-12:
            raise ValueError("kernel sums to zero: set normalize=false")
        return self


def execute_convolve(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterConvolveParams.model_validate(params)
    k = np.array(p.kernel, dtype="float64")
    if p.normalize:
        k = k / k.sum()
    ky, kx = k.shape[0] // 2, k.shape[1] // 2

    def build(run: _Run, ds, asset, out_path: str) -> None:
        with _write(out_path, ds, count=ds.count, dtype="float32", nodata=_NODATA) as out:
            for win in _blocks(ds.width, ds.height):
                run.tick()
                big = Window(
                    win.col_off - kx, win.row_off - ky, win.width + 2 * kx, win.height + 2 * ky
                )
                arr = ds.read(window=big, boundless=True, masked=True).astype("float64")
                h, w = win.height, win.width
                res = np.full((ds.count, h, w), _NODATA, dtype="float32")
                for b in range(ds.count):
                    valid = ~np.ma.getmaskarray(arr[b])
                    v = np.where(valid, np.ma.getdata(arr[b]), 0.0)
                    num = np.zeros((h, w))
                    den = np.zeros((h, w))
                    for i in range(k.shape[0]):
                        for j in range(k.shape[1]):
                            sl = (slice(i, i + h), slice(j, j + w))
                            num += k[i, j] * v[sl]
                            den += k[i, j] * valid[sl]
                    centre = valid[ky : ky + h, kx : kx + w]
                    if p.normalize:
                        with np.errstate(all="ignore"):
                            val = num / den
                        ok = centre & (np.abs(den) > 1e-12)
                    else:
                        val, ok = num, centre
                    res[b] = np.where(ok, val, _NODATA)
                out.write(res, window=win)

    _derive_per_row(
        conn,
        op="transform.rasterConvolve",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )


# ------------------------------------------------------------------ RasterMosaicker


class TransformRasterMosaicParams(_ItemColumn):
    """Fusionne en un seul raster les rasters de toutes les lignes (même CRS, même taille de
    cellule, grilles alignées, même nombre de bandes) : où ils se recouvrent, le premier
    raster valide l'emporte (`first`) ou le dernier (`last`). Publie un raster unique ; pas de
    rééchantillonnage (des grilles décalées sont refusées)."""

    onOverlap: Literal["first", "last"] = "first"
    nodata: float | None = Field(None, description="Obligatoire si le premier raster n'en a pas")


def execute_mosaic(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterMosaicParams.model_validate(params)
    op = "transform.rasterMosaic"
    cols, rows = _item_rows(conn, input_view, p.itemColumn, op)
    _no_clash(op, cols, list(_OUT_TYPES))
    ids = [i for _, i in rows if i]
    if len(ids) < 2:
        raise PipelineRuntimeError(f"{op}: au moins deux rasters sont nécessaires")
    with _Run(op, secret_resolver, preview) as run:
        opened = [run.open(i) for i in ids]
        dss = [d for d, _ in opened]
        first = dss[0]
        res = (first.transform.a, first.transform.e)
        for d in dss:
            t = d.transform
            if t.b or t.d or t.e >= 0 or t.a <= 0:
                raise PipelineRuntimeError(f"{op}: rasters orientés nord en haut uniquement")
            if d.crs != first.crs or d.count != first.count or d.dtypes[0] != first.dtypes[0]:
                raise PipelineRuntimeError(f"{op}: CRS, bandes ou type différents")
            if abs(t.a - res[0]) > 1e-9 * res[0] or abs(t.e - res[1]) > 1e-9 * abs(res[1]):
                raise PipelineRuntimeError(f"{op}: tailles de cellule différentes")
        left = min(d.transform.c for d in dss)
        top = max(d.transform.f for d in dss)
        right = max(d.transform.c + d.width * res[0] for d in dss)
        bottom = min(d.transform.f + d.height * res[1] for d in dss)
        w, h = round((right - left) / res[0]), round((top - bottom) / -res[1])
        if w * h > MAX_OUT_PIXELS:
            raise PipelineRuntimeError(f"{op}: mosaïque trop grande ({w}x{h} pixels)")
        offs = []
        for d in dss:
            dx, dy = (d.transform.c - left) / res[0], (top - d.transform.f) / -res[1]
            if abs(dx - round(dx)) > 1e-3 or abs(dy - round(dy)) > 1e-3:
                raise PipelineRuntimeError(f"{op}: grilles non alignées (pas de rééchantillonnage)")
            offs.append((round(dx), round(dy)))
        nd = p.nodata if p.nodata is not None else first.nodata
        if nd is None:
            raise PipelineRuntimeError(f"{op}: nodata requis (le premier raster n'en a pas)")
        if not _fits(nd, first.dtypes[0]):
            raise PipelineRuntimeError(f"{op}: nodata incompatible avec le type")
        out_path = run.path()
        with _write(
            out_path,
            first,
            count=first.count,
            dtype=first.dtypes[0],
            nodata=nd,
            transform_=Affine(res[0], 0, left, 0, res[1], top),
            width=w,
            height=h,
        ) as out:
            for win in _blocks(w, h):
                run.tick()
                acc = np.full((first.count, win.height, win.width), nd, dtype=first.dtypes[0])
                filled = np.zeros((win.height, win.width), dtype=bool)
                order = range(len(dss)) if p.onOverlap == "first" else range(len(dss) - 1, -1, -1)
                for i in order:
                    d, (dx, dy) = dss[i], offs[i]
                    c0, r0 = win.col_off - dx, win.row_off - dy
                    if (
                        c0 >= d.width
                        or r0 >= d.height
                        or c0 + win.width <= 0
                        or r0 + win.height <= 0
                    ):
                        continue
                    sw = Window(c0, r0, win.width, win.height)
                    m = d.read(window=sw, boundless=True, masked=True)
                    valid = ~np.ma.getmaskarray(m).all(axis=0)
                    inside = np.zeros_like(valid)
                    ys, xs = np.mgrid[0 : win.height, 0 : win.width]
                    inside = (
                        (c0 + xs >= 0) & (c0 + xs < d.width) & (r0 + ys >= 0) & (r0 + ys < d.height)
                    )
                    take = valid & inside & ~filled
                    acc[:, take] = np.ma.getdata(m)[:, take]
                    filled |= take
                out.write(acc, window=win)
        limits = [a.limit_collection_id for _, a in opened]
        try:
            res_cols = run.publish(out_path, p.title, limits)
        except _RowError as exc:
            raise PipelineRuntimeError(f"{op}: {exc}") from exc
    _emit_table(
        conn, view_name, [res_cols], {k: v for k, v in _OUT_TYPES.items() if k != "raster_error"}
    )


# ------------------------------------------------------------------ RasterPyramider


class TransformRasterPyramidParams(_ItemColumn):
    """Rééchantillonne le raster de chaque ligne en plusieurs résolutions (chaque niveau divise
    la taille par 2 ; au plus 4 niveaux) et publie un raster par niveau : une ligne de sortie
    par (raster, niveau) avec `raster_level`. Moyenne des cellules valides."""

    levels: int = Field(3, ge=1, le=4)
    resampling: Literal["average", "nearest"] = "average"


def execute_pyramid(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterPyramidParams.model_validate(params)
    op = "transform.rasterPyramid"
    _, rows = _item_rows(conn, input_view, p.itemColumn, op)
    out_rows: list[dict] = []
    with _Run(op, secret_resolver, preview) as run:
        for _, item_id in rows:
            if item_id is None:
                out_rows.append({"raster_error": "identifiant de raster absent"})
                continue
            ds, asset = run.open(item_id)
            for lvl in range(1, p.levels + 1):
                run.tick()
                f = 2**lvl
                w, h = max(1, ds.width // f), max(1, ds.height // f)
                path = run.path()
                data = ds.read(
                    out_shape=(ds.count, h, w),
                    masked=True,
                    resampling=Resampling[p.resampling],
                )
                nd = ds.nodata
                tr = ds.transform * Affine.scale(ds.width / w, ds.height / h)
                with _write(
                    path,
                    ds,
                    count=ds.count,
                    dtype=ds.dtypes[0],
                    nodata=nd,
                    transform_=tr,
                    width=w,
                    height=h,
                ) as out:
                    out.write(np.ma.filled(data, nd if nd is not None else 0))
                out_rows.append(
                    {
                        "source_item_id": item_id,
                        "raster_level": lvl,
                        **run.publish(path, f"{p.title} (1/{f})", [asset.limit_collection_id]),
                    }
                )
    _emit_table(
        conn,
        view_name,
        out_rows,
        {"source_item_id": "VARCHAR", "raster_level": "INTEGER", **_OUT_TYPES},
    )


# ------------------------------------------------------------ RasterStatisticsCalculator


class TransformRasterStatsParams(_ItemColumn):
    """Calcule les statistiques de bandes du raster de chaque ligne (nombre de cellules valides,
    minimum, maximum, moyenne, écart-type) et les ajoute en colonnes `raster_b<N>_<stat>`.
    Lecture par blocs : aucun raster entier en mémoire."""

    bands: list[int] = Field(default_factory=lambda: [1], min_length=1, max_length=MAX_BANDS)

    @field_validator("bands")
    @classmethod
    def _pos(cls, v):
        if any(b < 1 for b in v):
            raise ValueError("bands are 1-based")
        return list(dict.fromkeys(v))


def _band_stats(run: _Run, ds, band: int) -> dict[str, float | int | None]:
    n, mean, m2, lo, hi = 0, 0.0, 0.0, math.inf, -math.inf
    for win in _blocks(ds.width, ds.height):
        run.tick()
        v = np.ma.compressed(ds.read(band, window=win, masked=True)).astype("float64")
        if v.size == 0:
            continue
        bn, bm = v.size, float(v.mean())
        bm2 = float(((v - bm) ** 2).sum())
        d = bm - mean
        tot = n + bn
        m2 += bm2 + d * d * n * bn / tot
        mean += d * bn / tot
        n = tot
        lo, hi = min(lo, float(v.min())), max(hi, float(v.max()))
    if n == 0:
        return {"count": 0, "min": None, "max": None, "mean": None, "std": None}
    return {"count": n, "min": lo, "max": hi, "mean": mean, "std": math.sqrt(m2 / n)}


def execute_stats(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterStatsParams.model_validate(params)
    op = "transform.rasterStats"
    cols, rows = _item_rows(conn, input_view, p.itemColumn, op)
    types = {"raster_error": "VARCHAR"}
    for b in p.bands:
        types.update(
            {
                f"raster_b{b}_count": "BIGINT",
                **{f"raster_b{b}_{s}": "DOUBLE" for s in ("min", "max", "mean", "std")},
            }
        )
    _no_clash(op, cols, list(types))
    results: dict[int, dict] = {}
    with _Run(op, secret_resolver, preview) as run:
        for rn, item_id in rows:
            if item_id is None:
                results[rn] = {"raster_error": "identifiant de raster absent"}
                continue
            ds, _ = run.open(item_id)
            missing = [b for b in p.bands if b > ds.count]
            if missing:
                results[rn] = {"raster_error": f"bande(s) inexistante(s) : {missing}"}
                continue
            r: dict = {}
            for b in p.bands:
                for s, v in _band_stats(run, ds, b).items():
                    r[f"raster_b{b}_{s}"] = v
            results[rn] = r
    _emit_join(conn, input_view, view_name, types, results)


# ------------------------------------------------------------------ band operations


class TransformRasterBandCombineParams(_ItemColumn):
    """Empile en un seul raster multi-bandes les bandes des rasters de toutes les lignes
    (rasters coïncidents : même grille ; au plus 16 bandes au total ; type = le plus large)."""

    nodata: float | None = None


def execute_band_combine(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterBandCombineParams.model_validate(params)
    op = "transform.rasterBandCombine"
    cols, rows = _item_rows(conn, input_view, p.itemColumn, op)
    _no_clash(op, cols, list(_OUT_TYPES))
    ids = [i for _, i in rows if i]
    if len(ids) < 2:
        raise PipelineRuntimeError(f"{op}: au moins deux rasters sont nécessaires")
    with _Run(op, secret_resolver, preview) as run:
        opened = [run.open(i) for i in ids]
        dss = [d for d, _ in opened]
        try:
            for d in dss[1:]:
                _same_grid(dss[0], d)
        except _RowError as exc:
            raise PipelineRuntimeError(f"{op}: {exc}") from exc
        total = sum(d.count for d in dss)
        if total > MAX_BANDS:
            raise PipelineRuntimeError(f"{op}: plus de {MAX_BANDS} bandes au total")
        dtype = str(np.result_type(*[np.dtype(d.dtypes[0]) for d in dss]))
        nd = p.nodata if p.nodata is not None else dss[0].nodata
        if not _fits(nd, dtype):
            raise PipelineRuntimeError(f"{op}: nodata incompatible avec le type {dtype}")
        out_path = run.path()
        with _write(out_path, dss[0], count=total, dtype=dtype, nodata=nd) as out:
            for win in _blocks(dss[0].width, dss[0].height):
                run.tick()
                parts = [
                    np.ma.filled(
                        d.read(window=win, masked=True).astype(dtype), nd if nd is not None else 0
                    )
                    for d in dss
                ]
                out.write(np.concatenate(parts, axis=0), window=win)
        try:
            res = run.publish(out_path, p.title, [a.limit_collection_id for _, a in opened])
        except _RowError as exc:
            raise PipelineRuntimeError(f"{op}: {exc}") from exc
    _emit_table(
        conn, view_name, [res], {k: v for k, v in _OUT_TYPES.items() if k != "raster_error"}
    )


class TransformRasterBandSeparateParams(_ItemColumn):
    """Sépare le raster de chaque ligne en un raster mono-bande par bande : une ligne de sortie
    par (raster, bande) avec `raster_band`."""


def execute_band_separate(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterBandSeparateParams.model_validate(params)
    op = "transform.rasterBandSeparate"
    _, rows = _item_rows(conn, input_view, p.itemColumn, op)
    out_rows: list[dict] = []
    with _Run(op, secret_resolver, preview) as run:
        for _, item_id in rows:
            if item_id is None:
                out_rows.append({"raster_error": "identifiant de raster absent"})
                continue
            ds, asset = run.open(item_id)
            for b in ds.indexes:
                path = run.path()
                _copy(run, ds, path, bands=[b])
                out_rows.append(
                    {
                        "source_item_id": item_id,
                        "raster_band": b,
                        **run.publish(path, f"{p.title} (bande {b})", [asset.limit_collection_id]),
                    }
                )
    _emit_table(
        conn,
        view_name,
        out_rows,
        {"source_item_id": "VARCHAR", "raster_band": "INTEGER", **_OUT_TYPES},
    )


class TransformRasterBandRemoveParams(_ItemColumn):
    """Supprime des bandes (numérotées à partir de 1) du raster de chaque ligne et publie le
    raster restant. Refusé si aucune bande ne resterait."""

    removeBands: list[int] = Field(..., min_length=1, max_length=MAX_BANDS)

    @field_validator("removeBands")
    @classmethod
    def _pos(cls, v):
        if any(b < 1 for b in v):
            raise ValueError("bands are 1-based")
        return v


def execute_band_remove(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterBandRemoveParams.model_validate(params)

    def build(run: _Run, ds, asset, out_path: str) -> None:
        keep = [b for b in ds.indexes if b not in set(p.removeBands)]
        if len(keep) == ds.count and not set(p.removeBands) & set(ds.indexes):
            raise _RowError("aucune des bandes demandées n'existe")
        if not keep:
            raise _RowError("toutes les bandes seraient supprimées")
        _copy(run, ds, out_path, bands=keep)

    _derive_per_row(
        conn,
        op="transform.rasterBandRemove",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )


class TransformRasterBandNodataParams(_ItemColumn):
    """Définit (ou retire, si `nodata` est vide) la valeur nodata du raster de chaque ligne sans
    toucher aux valeurs de cellule. La valeur s'applique au raster entier (GeoTIFF : un seul
    nodata pour toutes les bandes)."""

    nodata: float | None = None


def execute_band_nodata(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterBandNodataParams.model_validate(params)

    def build(run: _Run, ds, asset, out_path: str) -> None:
        _copy(run, ds, out_path, nodata=p.nodata)

    _derive_per_row(
        conn,
        op="transform.rasterBandNodata",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )


# ------------------------------------------------------ georeferencing (3 ops)


class TransformRasterGeoreferenceParams(_ItemColumn):
    """Re-géoréférence le raster de chaque ligne sans modifier les cellules ni rééchantillonner :
    soit par coins (`ulx`/`uly` haut-gauche, `lrx`/`lry` bas-droite, raster nord en haut), soit
    par origine + taille de cellule + rotation (degrés, sens trigonométrique). `srid` = code
    EPSG du résultat. Un raster hébergé a toujours un CRS : l'op remplace sa géoréférence."""

    mode: Literal["corners", "origin"]
    srid: int = Field(..., ge=1)
    ulx: float | None = None
    uly: float | None = None
    lrx: float | None = None
    lry: float | None = None
    originX: float | None = None
    originY: float | None = None
    cellWidth: float | None = Field(None, gt=0)
    cellHeight: float | None = Field(None, gt=0)
    rotation: float = 0.0

    @model_validator(mode="after")
    def _need(self):
        need = (
            ("ulx", "uly", "lrx", "lry")
            if self.mode == "corners"
            else ("originX", "originY", "cellWidth", "cellHeight")
        )
        miss = [n for n in need if getattr(self, n) is None]
        if miss:
            raise ValueError(f"mode {self.mode}: missing {miss}")
        for n in need:
            if not math.isfinite(getattr(self, n)):
                raise ValueError(f"{n} must be finite")
        if self.mode == "corners" and (self.lrx <= self.ulx or self.lry >= self.uly):
            raise ValueError("corners must satisfy lrx > ulx and lry < uly")
        return self


def _crs(srid: int, op: str):
    try:
        return rasterio.crs.CRS.from_epsg(srid)
    except Exception as exc:
        raise _RowError(f"EPSG:{srid} inconnu") from exc


def execute_georeference(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterGeoreferenceParams.model_validate(params)

    def build(run: _Run, ds, asset, out_path: str) -> None:
        if p.mode == "corners":
            t = Affine((p.lrx - p.ulx) / ds.width, 0, p.ulx, 0, (p.lry - p.uly) / ds.height, p.uly)
        else:
            t = (
                Affine.translation(p.originX, p.originY)
                * Affine.rotation(p.rotation)
                * Affine.scale(p.cellWidth, -p.cellHeight)
            )
        _copy(run, ds, out_path, transform_=t, crs=_crs(p.srid, "geo"))

    _derive_per_row(
        conn,
        op="transform.rasterGeoreference",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )


class GcpModel(BaseModel):
    col: float = Field(..., description="Colonne pixel")
    row: float = Field(..., description="Ligne pixel")
    x: float
    y: float
    z: float = 0.0


class TransformRasterGcpSetParams(_ItemColumn):
    """Géoréférence le raster de chaque ligne à partir de points de contrôle au sol (au moins 3
    non alignés, au plus 100) : ajuste par moindres carrés une transformation affine (ordre 1 ;
    pas de polynôme d'ordre supérieur ni de spline), publie le raster géoréférencé (cellules
    inchangées, points conservés dans la balise `GS_GCPS`) et ajoute `raster_gcp_rmse`
    (erreur quadratique moyenne en unités du CRS). `srid` = EPSG des coordonnées x/y."""

    gcps: list[GcpModel] = Field(..., min_length=3, max_length=100)
    srid: int = Field(..., ge=1)


def _affine_rmse(gcps: list[GcpModel], t: Affine) -> float:
    err = 0.0
    for g in gcps:
        x, y = t * (g.col, g.row)
        err += (x - g.x) ** 2 + (y - g.y) ** 2
    return math.sqrt(err / len(gcps))


def execute_gcp_set(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterGcpSetParams.model_validate(params)
    cols, rows = _item_rows(conn, input_view, p.itemColumn, "transform.rasterGcpSet")
    _no_clash("transform.rasterGcpSet", cols, ["raster_gcp_rmse"])
    try:
        pts = [GroundControlPoint(g.row, g.col, g.x, g.y, g.z) for g in p.gcps]
        t = from_gcps(pts)
    except Exception as exc:
        raise PipelineRuntimeError(
            f"transform.rasterGcpSet: points de contrôle invalides : {exc}"
        ) from exc
    if abs(t.determinant) < 1e-18 or not all(math.isfinite(v) for v in t):
        raise PipelineRuntimeError(
            "transform.rasterGcpSet: points de contrôle alignés ou dégénérés"
        )
    rmse = _affine_rmse(p.gcps, t)
    tag = json.dumps([g.model_dump() for g in p.gcps])

    def build(run: _Run, ds, asset, out_path: str) -> None:
        _copy(run, ds, out_path, transform_=t, crs=_crs(p.srid, "gcp"), tags={"GS_GCPS": tag})

    _derive_per_row(
        conn,
        op="transform.rasterGcpSet",
        view=input_view,
        name=view_name,
        p=p,
        resolver=secret_resolver,
        preview=preview,
        build=build,
    )
    conn.execute(  # colonne d'erreur quadratique : constante de l'ajustement
        f"ALTER TABLE {_qi(view_name)} ADD COLUMN raster_gcp_rmse DOUBLE DEFAULT {rmse!r}"
    )


class TransformRasterGcpExtractParams(_ItemColumn):
    """Extrait les points de contrôle au sol attachés au raster de chaque ligne (GCP GDAL ou
    balise `GS_GCPS` posée par `transform.rasterGcpSet`) : une ligne par point (`gcp_col`,
    `gcp_row`, `gcp_x`, `gcp_y`, `gcp_z`). Un raster sans point ne produit aucune ligne."""


def execute_gcp_extract(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterGcpExtractParams.model_validate(params)
    op = "transform.rasterGcpExtract"
    _, rows = _item_rows(conn, input_view, p.itemColumn, op)
    out_rows: list[dict] = []
    with _Run(op, secret_resolver, preview) as run:
        for _, item_id in rows:
            if item_id is None:
                continue
            ds, _ = run.open(item_id)
            pts = [(g.col, g.row, g.x, g.y, g.z) for g in ds.gcps[0]][:100]
            tag = ds.tags().get("GS_GCPS")
            if not pts and tag:
                try:
                    pts = [
                        (g["col"], g["row"], g["x"], g["y"], g.get("z", 0.0))
                        for g in json.loads(tag)
                    ][:100]
                except (ValueError, KeyError, TypeError):
                    pts = []
            for c, r, x, y, z in pts:
                out_rows.append(
                    {
                        "source_item_id": item_id,
                        "gcp_col": c,
                        "gcp_row": r,
                        "gcp_x": x,
                        "gcp_y": y,
                        "gcp_z": z,
                    }
                )
    _emit_table(
        conn,
        view_name,
        out_rows,
        {
            "source_item_id": "VARCHAR",
            "gcp_col": "DOUBLE",
            "gcp_row": "DOUBLE",
            "gcp_x": "DOUBLE",
            "gcp_y": "DOUBLE",
            "gcp_z": "DOUBLE",
        },
    )


# ------------------------------------------------------- RasterExtractor / WebMapTiler


def _png_bytes(arr: np.ndarray) -> bytes:
    """arr : (bandes 1..4, h, w) uint8/uint16."""
    with MemoryFile() as mem, warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with mem.open(
            driver="PNG",
            width=arr.shape[2],
            height=arr.shape[1],
            count=arr.shape[0],
            dtype=arr.dtype,
        ) as o:
            o.write(arr)
        return mem.read()


class TransformRasterExtractParams(_ItemColumn):
    """Encode le raster de chaque ligne (au plus 1 million de pixels) en PNG ou GeoTIFF dans une
    colonne binaire `raster_blob` (avec `raster_format`, `raster_width`, `raster_height`). PNG :
    types 8/16 bits, 1 à 4 bandes."""

    format: Literal["png", "gtiff"] = "png"


def execute_extract(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformRasterExtractParams.model_validate(params)
    op = "transform.rasterExtract"
    cols, rows = _item_rows(conn, input_view, p.itemColumn, op)
    types = {
        "raster_blob": "BLOB",
        "raster_format": "VARCHAR",
        "raster_width": "INTEGER",
        "raster_height": "INTEGER",
        "raster_error": "VARCHAR",
    }
    _no_clash(op, cols, list(types))
    results: dict[int, dict] = {}
    with _Run(op, secret_resolver, preview) as run:
        for rn, item_id in rows:
            if item_id is None:
                results[rn] = {"raster_error": "identifiant de raster absent"}
                continue
            ds, _ = run.open(item_id, max_pixels=MAX_BLOB_PIXELS)
            try:
                if p.format == "png":
                    if ds.dtypes[0] not in ("uint8", "uint16") or ds.count > 4:
                        raise _RowError(
                            "PNG : types 8/16 bits et 4 bandes au plus (utiliser gtiff)"
                        )
                    data = ds.read()
                    blob = _png_bytes(data)
                else:
                    path = run.path()
                    _copy(run, ds, path)
                    with open(path, "rb") as f:
                        blob = f.read(MAX_BLOB_BYTES + 1)
                if len(blob) > MAX_BLOB_BYTES:
                    raise _RowError(f"image encodée trop volumineuse (> {MAX_BLOB_BYTES} octets)")
                results[rn] = {
                    "raster_blob": blob,
                    "raster_format": p.format,
                    "raster_width": ds.width,
                    "raster_height": ds.height,
                }
            except _RowError as exc:
                results[rn] = {"raster_error": str(exc)}
    _emit_join(conn, input_view, view_name, types, results)


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    size = 2 * _ORIGIN / 2**z
    return (
        -_ORIGIN + x * size,
        _ORIGIN - (y + 1) * size,
        -_ORIGIN + (x + 1) * size,
        _ORIGIN - y * size,
    )


def _tile_range(bounds: list[float], z: int) -> tuple[range, range]:
    n = 2**z
    w, s, e, nn = bounds
    lat = lambda v: max(-85.0511, min(85.0511, v))  # noqa: E731

    def xy(lon: float, la: float) -> tuple[float, float]:
        la_r = math.radians(lat(la))
        return (
            (lon + 180.0) / 360.0 * n,
            (1 - math.log(math.tan(la_r) + 1 / math.cos(la_r)) / math.pi) / 2 * n,
        )

    x0, y1 = xy(w, s)
    x1, y0 = xy(e, nn)
    cl = lambda v: max(0, min(n - 1, int(math.floor(v))))  # noqa: E731
    return range(cl(x0), cl(x1) + 1), range(cl(y0), cl(y1) + 1)


class TransformWebMapTilerParams(_ItemColumn):
    """Découpe le raster de chaque ligne en tuiles PNG 256x256 Web Mercator (schéma XYZ) pour
    les niveaux de zoom `minZoom` à `maxZoom` : une ligne par tuile (`z`, `x`, `y`, `tile`).
    Au plus 256 tuiles par nœud ; les tuiles entièrement vides sont omises. Données 8 bits
    utilisées telles quelles, sinon étirées entre `scale` (ou min/max de la bande 1)."""

    minZoom: int = Field(..., ge=0, le=22)
    maxZoom: int = Field(..., ge=0, le=22)
    bands: list[int] = Field(default_factory=lambda: [1], min_length=1, max_length=3)
    scale: list[float] | None = Field(None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def _chk(self):
        if self.maxZoom < self.minZoom:
            raise ValueError("maxZoom must be >= minZoom")
        if len(self.bands) not in (1, 3) or any(b < 1 for b in self.bands):
            raise ValueError("bands: 1 (gris) or 3 (RVB), 1-based")
        if self.scale and not (self.scale[1] > self.scale[0]):
            raise ValueError("scale must be [min, max] with max > min")
        return self


def execute_tiler(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformWebMapTilerParams.model_validate(params)
    op = "transform.webMapTiler"
    _, rows = _item_rows(conn, input_view, p.itemColumn, op)
    out_rows: list[dict] = []
    total_bytes = 0
    with _Run(op, secret_resolver, preview) as run:
        # plan complet AVANT tout calcul : le plafond de tuiles est un plafond de travail
        plan: list[tuple[str, Any, Any, int, int, int]] = []
        for _, item_id in rows:
            if item_id is None:
                continue
            ds, asset = run.open(item_id)
            if max(p.bands) > ds.count:
                raise PipelineRuntimeError(f"{op}: bande inexistante")
            for z in range(p.minZoom, p.maxZoom + 1):
                xs, ys = _tile_range(asset.bounds, z)
                if len(plan) + len(xs) * len(ys) > MAX_TILES:
                    raise PipelineRuntimeError(f"{op}: plus de {MAX_TILES} tuiles")
                plan += [(item_id, ds, asset, z, x, y) for x in xs for y in ys]
        for item_id, ds, asset, z, x, y in plan:
            run.tick()
            b = _tile_bounds(z, x, y)
            dst_t = Affine((b[2] - b[0]) / 256, 0, b[0], 0, -(b[3] - b[1]) / 256, b[3])
            chans = []
            for band in p.bands:
                dst = np.full((256, 256), np.nan, dtype="float32")
                reproject(
                    source=rasterio.band(ds, band),
                    destination=dst,
                    dst_transform=dst_t,
                    dst_crs="EPSG:3857",
                    src_nodata=ds.nodata,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                    init_dest_nodata=True,
                )
                chans.append(dst)
            valid = ~np.isnan(chans[0])
            if not valid.any():
                continue
            if ds.dtypes[0] == "uint8" and not p.scale:
                lo, hi = 0.0, 255.0
            else:
                st = asset.bands[p.bands[0] - 1] if len(asset.bands) >= p.bands[0] else {}
                lo, hi = p.scale or (st.get("min"), st.get("max"))
                if lo is None or hi is None or hi <= lo:
                    raise PipelineRuntimeError(f"{op}: `scale` requis pour ce raster")
            rgb = [np.clip(np.nan_to_num(c, nan=lo), lo, hi) for c in chans]
            arr = np.stack(
                [((c - lo) / (hi - lo) * 255).astype("uint8") for c in rgb]
                + [valid.astype("uint8") * 255]
            )
            blob = _png_bytes(arr)
            total_bytes += len(blob)
            if total_bytes > MAX_TILE_BYTES:
                raise PipelineRuntimeError(
                    f"{op}: tuiles trop volumineuses (> {MAX_TILE_BYTES} octets)"
                )
            out_rows.append({"source_item_id": item_id, "z": z, "x": x, "y": y, "tile": blob})
    _emit_table(
        conn,
        view_name,
        out_rows,
        {
            "source_item_id": "VARCHAR",
            "z": "INTEGER",
            "x": "INTEGER",
            "y": "INTEGER",
            "tile": "BLOB",
        },
    )


# ------------------------------------------------------------ VectorOnRasterOverlayer


class TransformVectorOnRasterParams(BaseModel):
    """Rasterise les géométries de l'entrée sur un raster EXISTANT (`itemId`) : les cellules
    couvertes prennent la valeur `burnValue` (ou celle de `valueColumn`) dans la bande `band`,
    les autres sont inchangées. Publie un nouveau raster (l'original n'est jamais modifié) ;
    `all_touched` brûle toute cellule touchée. Au plus 10 000 géométries."""

    itemId: str = Field(..., min_length=1)
    band: int = Field(1, ge=1)
    burnValue: float = 1.0
    valueColumn: str | None = None
    allTouched: bool = False
    title: str = Field("Raster dérivé", min_length=1, max_length=200)


def execute_vector_on_raster(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformVectorOnRasterParams.model_validate(params)
    op = "transform.vectorOnRaster"
    _require_srid(op, input_srid)
    cols = _columns(conn, input_view)
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"{op}: input has no 'geometry' column")
    if p.valueColumn and p.valueColumn not in cols:
        raise PipelineRuntimeError(f"{op}: input has no '{p.valueColumn}' column")
    val = f"TRY_CAST({_qi(p.valueColumn)} AS DOUBLE)" if p.valueColumn else "NULL"
    rows = conn.execute(
        f"SELECT ST_AsGeoJSON(geometry), {val} FROM {_qi(input_view)} "
        f"WHERE geometry IS NOT NULL AND NOT ST_IsEmpty(geometry) LIMIT {MAX_GEOMS + 1}"
    ).fetchall()
    if len(rows) > MAX_GEOMS:
        raise PipelineRuntimeError(f"{op}: more than {MAX_GEOMS} geometries")
    with _Run(op, secret_resolver, preview) as run:
        ds, asset = run.open(p.itemId)
        if p.band > ds.count:
            raise PipelineRuntimeError(f"{op}: bande {p.band} inexistante")
        src_crs = f"EPSG:{input_srid or 4326}"
        shapes = []
        for gj, v in rows:
            g = transform_geom(src_crs, ds.crs, json.loads(gj))
            burn = float(v) if v is not None else p.burnValue
            if not _fits(burn, ds.dtypes[0]):
                raise PipelineRuntimeError(
                    f"{op}: valeur {burn} incompatible avec le type {ds.dtypes[0]}"
                )
            shapes.append((g, burn))
        from rasterio.features import rasterize

        def post(arr: np.ndarray, win: Window) -> np.ndarray:
            if shapes:
                mask = rasterize(
                    [(g, 1) for g, _ in shapes],
                    out_shape=(win.height, win.width),
                    transform=ds.window_transform(win),
                    all_touched=p.allTouched,
                    dtype="uint8",
                )
                vals = rasterize(
                    shapes,
                    out_shape=(win.height, win.width),
                    transform=ds.window_transform(win),
                    all_touched=p.allTouched,
                    dtype="float64",
                    fill=0.0,
                )
                arr = arr.copy()
                b = p.band - 1
                arr[b] = np.where(mask == 1, vals.astype(arr.dtype), arr[b])
            return arr

        out = run.path()
        _copy(run, ds, out, post=post)
        res = run.publish(out, p.title, [asset.limit_collection_id])
    _emit_table(
        conn, view_name, [res], {k: v for k, v in _OUT_TYPES.items() if k != "raster_error"}
    )


# -------------------------------------------------------------------- SurfaceDraper


class TransformSurfaceDrapeParams(BaseModel):
    """Drape les points de l'entrée sur un raster d'élévation (MNT) : ajoute `drape_z` (valeur
    du raster sous le point), et `drape_slope` (pente en degrés) / `drape_aspect` (exposition,
    degrés depuis le nord, sens horaire) calculées sur le voisinage 3x3 (méthode de Horn). Points
    hors raster, sur cellule invalide ou géométries non ponctuelles : NULL. La géométrie d'entrée
    est conservée (2D). Pas de triangulation de nuage de points ni de breaklines (contrairement
    à FME). Au plus 20 000 points.

    `mode: geometry` : drape TOUTES les géométries (points, lignes, polygones, multi-parties) et
    remplace `geometry` par sa version 3D (Z = valeur du raster sous chaque sommet, dans le CRS
    d'entrée). `densify` insère des sommets au pas du pixel le long des lignes et des anneaux
    (échantillonnage du relief entre deux sommets) ; sinon seuls les sommets existants sont
    drapés. Un sommet hors raster ou sur cellule invalide prend `outsideZ` ; sans `outsideZ`, la
    ligne garde sa géométrie d'origine et `drape_error` explique pourquoi. Au plus 10 000
    géométries et 500 000 sommets drapés par nœud (densification comprise, estimée avant
    d'être calculée). Sortie 3D : l'écrire dans une collection typée 2D échoue à l'insertion."""

    itemId: str = Field(..., min_length=1)
    band: int = Field(1, ge=1)
    slopeAspect: bool = True
    mode: Literal["attributes", "geometry"] = "attributes"
    densify: bool = True
    outsideZ: float | None = None


def _horn(win: np.ma.MaskedArray, dx: float, dy: float) -> tuple[float | None, float | None]:
    if np.ma.getmaskarray(win).any() or win.shape != (3, 3):
        return None, None
    a = np.ma.getdata(win).astype("float64")
    dzdx = ((a[0, 2] + 2 * a[1, 2] + a[2, 2]) - (a[0, 0] + 2 * a[1, 0] + a[2, 0])) / (8 * dx)
    dzdy = ((a[2, 0] + 2 * a[2, 1] + a[2, 2]) - (a[0, 0] + 2 * a[0, 1] + a[0, 2])) / (8 * dy)
    slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    if dzdx == 0 and dzdy == 0:
        return slope, None  # plat : exposition indéfinie
    # dzdy positif = la valeur croît vers le sud (lignes vers le bas) -> pente descend au nord
    aspect = (math.degrees(math.atan2(dzdx, dzdy)) + 180.0) % 360.0
    return slope, aspect


def execute_drape(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformSurfaceDrapeParams.model_validate(params)
    op = "transform.surfaceDrape"
    _require_srid(op, input_srid)
    if p.mode == "geometry":
        return _drape_geometries(
            conn, input_view, view_name, p, secret_resolver, preview, input_srid
        )
    cols = _columns(conn, input_view)
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"{op}: input has no 'geometry' column")
    types = {"drape_z": "DOUBLE", "drape_slope": "DOUBLE", "drape_aspect": "DOUBLE"}
    _no_clash(op, cols, list(types))
    pts = conn.execute(
        f"SELECT row_number() OVER () AS rn, "
        f"CASE WHEN geometry IS NOT NULL AND ST_GeometryType(geometry) = 'POINT' "
        f"AND NOT ST_IsEmpty(geometry) THEN ST_X(geometry) END, "
        f"CASE WHEN geometry IS NOT NULL AND ST_GeometryType(geometry) = 'POINT' "
        f"AND NOT ST_IsEmpty(geometry) THEN ST_Y(geometry) END "
        f"FROM {_qi(input_view)} LIMIT {MAX_POINTS + 1}"
    ).fetchall()
    if len(pts) > MAX_POINTS:
        raise PipelineRuntimeError(f"{op}: more than {MAX_POINTS} points")
    results: dict[int, dict] = {}
    with _Run(op, secret_resolver, preview) as run:
        ds, _ = run.open(p.itemId)
        if p.band > ds.count:
            raise PipelineRuntimeError(f"{op}: bande {p.band} inexistante")
        todo = [(rn, x, y) for rn, x, y in pts if x is not None and y is not None]
        if todo and (input_srid or 4326) != ds.crs.to_epsg():
            xs, ys = transform(
                f"EPSG:{input_srid or 4326}", ds.crs, [t[1] for t in todo], [t[2] for t in todo]
            )
            todo = [(rn, x, y) for (rn, _, _), x, y in zip(todo, xs, ys, strict=True)]
        geographic = ds.crs.is_geographic
        for rn, x, y in todo:
            run.tick()
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            try:
                r, c = ds.index(x, y)
            except (ValueError, OverflowError):
                continue
            if not (0 <= r < ds.height and 0 <= c < ds.width):
                continue
            win = ds.read(p.band, window=Window(c - 1, r - 1, 3, 3), boundless=True, masked=True)
            if win.mask.shape and win.mask[1, 1]:
                continue
            res = {"drape_z": float(win[1, 1])}
            if p.slopeAspect:
                rx, ry = abs(ds.res[0]), abs(ds.res[1])
                if geographic:
                    rx, ry = rx * 111320.0 * max(math.cos(math.radians(y)), 1e-6), ry * 110540.0
                res["drape_slope"], res["drape_aspect"] = _horn(win, rx, ry)
            results[rn] = res
    _emit_join(conn, input_view, view_name, types, results)


MAX_DRAPE_VERTICES = 500_000


def _drape_geometries(conn, input_view, view_name, p, secret_resolver, preview, input_srid):
    """mode=geometry : géométries 3D drapées (cf. TransformSurfaceDrapeParams)."""
    import shapely

    op = "transform.surfaceDrape"
    cols = _columns(conn, input_view)
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"{op}: input has no 'geometry' column")
    _no_clash(op, cols, ["drape_error"])
    rows = conn.execute(
        f"SELECT row_number() OVER () AS rn, CASE WHEN geometry IS NOT NULL AND NOT "
        f"ST_IsEmpty(geometry) THEN ST_AsWKB(geometry) END FROM {_qi(input_view)} "
        f"LIMIT {MAX_GEOMS + 1}"
    ).fetchall()
    if len(rows) > MAX_GEOMS:
        raise PipelineRuntimeError(f"{op}: more than {MAX_GEOMS} geometries")
    results: dict[int, dict] = {}
    with _Run(op, secret_resolver, preview) as run:
        ds, _ = run.open(p.itemId)
        if p.band > ds.count:
            raise PipelineRuntimeError(f"{op}: bande {p.band} inexistante")
        band = ds.read(p.band, masked=True)  # borné par MAX_PIXELS (run.open)
        data, mask = np.ma.getdata(band).astype("float64"), np.ma.getmaskarray(band)
        inv = ~ds.transform
        src = f"EPSG:{input_srid or 4326}"
        reproj = (input_srid or 4326) != ds.crs.to_epsg()
        step = min(abs(ds.res[0]), abs(ds.res[1]))
        total = 0

        def to_raster(xy: np.ndarray) -> np.ndarray:
            xs, ys = transform(src, ds.crs, xy[:, 0].tolist(), xy[:, 1].tolist())
            return np.column_stack([xs, ys])

        def sample(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
            c, r = inv * (xs, ys)
            c, r = np.floor(c).astype("int64"), np.floor(r).astype("int64")
            ok = (c >= 0) & (c < ds.width) & (r >= 0) & (r < ds.height)
            z = np.full(xs.shape, np.nan)
            z[ok] = np.where(mask[r[ok], c[ok]], np.nan, data[r[ok], c[ok]])
            return z

        for rn, wkb in rows:
            run.tick()
            if wkb is None:
                continue
            g = shapely.force_2d(shapely.from_wkb(bytes(wkb)))
            gr = shapely.transform(g, to_raster) if reproj else g
            dense = p.densify and gr.geom_type not in ("Point", "MultiPoint")
            # Budget estimé AVANT segmentize : une ligne très longue densifiée au pas du pixel
            # allouerait ses sommets avant tout contrôle (sommets existants + longueur / pas).
            est = shapely.get_num_coordinates(gr) + (shapely.length(gr) / step if dense else 0)
            if not math.isfinite(est) or total + est > MAX_DRAPE_VERTICES:
                raise PipelineRuntimeError(f"{op}: more than {MAX_DRAPE_VERTICES} vertices")
            if dense:
                gr = shapely.segmentize(gr, step)
            total += shapely.get_num_coordinates(gr)
            if total > MAX_DRAPE_VERTICES:
                raise PipelineRuntimeError(f"{op}: more than {MAX_DRAPE_VERTICES} vertices")
            xy = shapely.get_coordinates(gr)
            z = sample(xy[:, 0], xy[:, 1])
            if np.isnan(z).any():
                if p.outsideZ is None:
                    results[rn] = {
                        "drape_error": "sommet(s) hors du raster ou sur cellule invalide"
                    }
                    continue
                z = np.where(np.isnan(z), p.outsideZ, z)
            if reproj:
                bx, by = transform(ds.crs, src, xy[:, 0].tolist(), xy[:, 1].tolist())
                xy = np.column_stack([bx, by])
            g3 = shapely.set_coordinates(shapely.force_3d(gr), np.column_stack([xy, z]))
            if not all(np.isfinite(shapely.get_coordinates(g3, include_z=True)).ravel()):
                results[rn] = {"drape_error": "reprojection hors domaine"}
                continue
            results[rn] = {"wkb": shapely.to_wkb(g3)}
    frame = pd.DataFrame(
        [{"rn": rn, "wkb": r.get("wkb"), "drape_error": r.get("drape_error")}
         for rn, r in results.items()],
        columns=["rn", "wkb", "drape_error"],
    ).astype(object)  # fmt: skip
    conn.register("_r2_drape", frame)
    try:
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT s.* EXCLUDE (_rn) REPLACE ("
            "CASE WHEN r.wkb IS NOT NULL THEN ST_GeomFromWKB(CAST(r.wkb AS BLOB)) "
            "ELSE s.geometry END AS geometry), CAST(r.drape_error AS VARCHAR) AS drape_error "
            f"FROM (SELECT *, row_number() OVER () AS _rn FROM {_qi(input_view)}) s "
            "LEFT JOIN _r2_drape r ON r.rn = s._rn ORDER BY s._rn"
        )
    finally:
        conn.unregister("_r2_drape")


# --------------------------------------------------------------------- ImageFetcher


class TransformImageFetchParams(BaseModel):
    """Télécharge l'image (PNG, JPEG ou GeoTIFF) dont l'URL figure dans la colonne `urlColumn`
    de chaque ligne et la publie comme raster hébergé (au plus 10 images, 20 Mo, 4 millions de
    pixels). Une image PNG/JPEG n'a pas de géoréférence : `bounds` [ouest, sud, est, nord] en
    EPSG `srid` est obligatoire ; un GeoTIFF garde la sienne. Appel réseau gardé par l'egress
    SSRF (hôtes internes refusés, IP épinglée) ; refusé en aperçu."""

    urlColumn: str = Field("url", min_length=1)
    bounds: list[float] | None = Field(None, min_length=4, max_length=4)
    srid: int = Field(4326, ge=1)
    title: str = Field("Image importée", min_length=1, max_length=200)

    @field_validator("bounds")
    @classmethod
    def _b(cls, v):
        if v is not None and (not all(math.isfinite(x) for x in v) or v[2] <= v[0] or v[3] <= v[1]):
            raise ValueError(
                "bounds must be [west, south, east, north] with east>west, north>south"
            )
        return v


_MAGIC = {b"\x89PNG": "PNG", b"\xff\xd8\xff": "JPEG", b"II*\x00": "GTiff", b"MM\x00*": "GTiff"}


def _fetch(url: str, run: _Run | None = None) -> bytes:
    """Téléchargement borné en octets ET en durée : `run.tick()` à chaque bloc (un serveur
    goutte-à-goutte ne contourne pas le délai du nœud)."""
    try:
        with build_guarded_session().get(url, stream=True, timeout=(10, 30)) as resp:
            resp.raise_for_status()
            try:
                declared = int(resp.headers.get("Content-Length") or 0)
            except ValueError:
                declared = 0
            if declared > MAX_IMAGE_BYTES:
                raise _RowError("image trop volumineuse")
            buf = bytearray()
            for chunk in resp.iter_content(_FETCH_CHUNK):
                if run is not None:
                    run.tick()
                buf += chunk
                if len(buf) > MAX_IMAGE_BYTES:
                    raise _RowError(f"image trop volumineuse (> {MAX_IMAGE_BYTES} octets)")
            return bytes(buf)
    except EgressBlockedError as exc:
        raise PipelineRuntimeError(f"transform.imageFetch: egress refusé : {exc}") from exc
    except Exception as exc:
        if isinstance(exc, _RowError | PipelineRuntimeError):
            raise
        if type(exc).__module__.startswith(("requests", "urllib3")):
            raise _RowError(f"téléchargement impossible : {type(exc).__name__}") from exc
        raise


def execute_image_fetch(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    p = TransformImageFetchParams.model_validate(params)
    op = "transform.imageFetch"
    if preview:
        raise PipelineRuntimeError(f"{op}: indisponible en aperçu (appel réseau et publication)")
    cols, rows = _item_rows(conn, input_view, p.urlColumn, op)
    _no_clash(op, cols, list(_OUT_TYPES))
    results: dict[int, dict] = {}
    with _Run(op, secret_resolver, preview) as run:
        run.require_publish()
        for rn, url in rows:
            run.tick()
            if url is None:
                results[rn] = {"raster_error": "URL absente"}
                continue
            try:
                raw = _fetch(url, run)
                kind = next((v for k, v in _MAGIC.items() if raw.startswith(k)), None)
                if kind is None:
                    raise _RowError("format d'image non pris en charge (PNG, JPEG, GeoTIFF)")
                out = run.path()
                with warnings.catch_warnings(), rasterio.Env(**LOCAL_ONLY_GDAL):
                    warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
                    mem_ctx = MemoryFile(raw)
                    with mem_ctx as mem, mem.open(driver=kind) as src:
                        if src.width * src.height > MAX_PIXELS:
                            raise _RowError(f"image trop grande (> {MAX_PIXELS} pixels)")
                        if src.count > 4:
                            raise _RowError("plus de 4 bandes")
                        if kind == "GTiff" and src.crs is not None:
                            _copy(run, src, out)
                        else:
                            if p.bounds is None:
                                raise _RowError("image non géoréférencée : `bounds` requis")
                            w, s, e, n = p.bounds
                            t = Affine((e - w) / src.width, 0, w, 0, (s - n) / src.height, n)
                            _copy(run, src, out, transform_=t, crs=_crs(p.srid, op), nodata=None)
                results[rn] = run.publish(out, p.title, [None], "image.tif")
            except _RowError as exc:
                results[rn] = {"raster_error": str(exc)}
    _emit_join(conn, input_view, view_name, _OUT_TYPES, results)


# ------------------------------------------------------------------------ registry

_LIC = "BSD-3-Clause (rasterio) ; GDAL (MIT)"


def _c(op: str, model: type[BaseModel], fn: Callable) -> OperationContract:
    return OperationContract(
        op=op,
        kind="transform",
        params_schema=model,
        engine="python",
        engine_license=_LIC,
        execute=fn,
        needs_runtime_context=True,
        enabled_when=is_raster_enabled,
    )


CONTRACTS.extend(
    [
        OperationContract(
            op="reader.rasterItems",
            kind="reader",
            params_schema=ReaderRasterItemsParams,
            engine="python",
            engine_license=_LIC,
            enabled_when=is_raster_enabled,
        ),
        _c("transform.rasterCalc", TransformRasterCalcParams, execute_calc),
        _c("transform.rasterConvolve", TransformRasterConvolveParams, execute_convolve),
        _c("transform.rasterMosaic", TransformRasterMosaicParams, execute_mosaic),
        _c("transform.rasterPyramid", TransformRasterPyramidParams, execute_pyramid),
        _c("transform.rasterStats", TransformRasterStatsParams, execute_stats),
        _c("transform.rasterBandCombine", TransformRasterBandCombineParams, execute_band_combine),
        _c(
            "transform.rasterBandSeparate", TransformRasterBandSeparateParams, execute_band_separate
        ),
        _c("transform.rasterBandRemove", TransformRasterBandRemoveParams, execute_band_remove),
        _c("transform.rasterBandNodata", TransformRasterBandNodataParams, execute_band_nodata),
        _c("transform.rasterExtract", TransformRasterExtractParams, execute_extract),
        _c("transform.vectorOnRaster", TransformVectorOnRasterParams, execute_vector_on_raster),
        _c("transform.webMapTiler", TransformWebMapTilerParams, execute_tiler),
        _c("transform.imageFetch", TransformImageFetchParams, execute_image_fetch),
        _c("transform.rasterGeoreference", TransformRasterGeoreferenceParams, execute_georeference),
        _c("transform.rasterGcpSet", TransformRasterGcpSetParams, execute_gcp_set),
        _c("transform.rasterGcpExtract", TransformRasterGcpExtractParams, execute_gcp_extract),
        _c("transform.surfaceDrape", TransformSurfaceDrapeParams, execute_drape),
    ]
)
