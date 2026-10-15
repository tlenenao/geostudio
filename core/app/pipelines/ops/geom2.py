# SPDX-License-Identifier: Apache-2.0
"""Module de voie C — géométrie (15 transformers FME, Shapely/GEOS BSD-3-Clause).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Déclare ses ops ici (modèles `*Params` + `OperationContract`), agrégées par
app.pipelines.ops.contracts.LANE_MODULES et app.pipelines.registries — gabarit :
docs/superpowers/plans/_fme-lane-template.md. Ne jamais importer contracts/runtime/
registries au niveau module (cycle d'import).

Patron des 3 op Shapely de `ops/execute.py` (`execute(conn, *, input_view, view_name,
params)`, groupBy, lignes à géométrie NULL écartées en SQL — REV-196) ; masquage GAP-22 et
SRID inchangés (le runtime masque la vue d'entrée avant `execute`, l'op ne lit rien d'autre).

Bornes des ops topologiques (nombre de lignes, de sommets, délai) : `MAX_FEATURES`,
`MAX_VERTICES`, `TIMEOUT_S`. ponytail: le délai est coopératif (vérifié entre deux
géométries/groupes) — un unique appel GEOS pathologique n'est pas interruptible ; le plafond
de sommets en amont est la vraie borne. Upgrade : exécution en sous-process si besoin.
"""

import math
import time
from collections.abc import Callable
from typing import Literal

import numpy as np
import pandas as pd
import shapely
import shapely.ops
import shapely.wkb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.strtree import STRtree

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.execute import (
    _apply_per_group,
    _read_geometry_rows,
    _write_geometry_rows,
)
from app.pipelines.ops.operation_contract import OperationContract, OutputColumn
from app.sql_ident import quote_ident_duckdb as _qi

MAX_FEATURES = 20_000
MAX_VERTICES = 1_000_000
TIMEOUT_S = 60.0
MAX_OUTPUT_ROWS = 1_000_000  # plafond de lignes produites par une op (amplification)
MAX_CHOP_PIECES = 100_000  # morceaux par géométrie pour chop/maxLength
MAX_AREA_FEATURES = 2_000  # polygones par groupe pour l'Intersector (faces en O(n²))
RUBBER_CHUNK = 4_000_000  # sommets×contrôles par bloc (~100 Mo de temporaires)

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Budget:
    """Garde commune : plafond de lignes/sommets à l'entrée, délai coopératif."""

    def __init__(self, op: str) -> None:
        self.op = op
        self.deadline = time.monotonic() + TIMEOUT_S

    def check(self) -> None:
        if time.monotonic() > self.deadline:
            raise PipelineRuntimeError(f"{self.op}: délai dépassé ({TIMEOUT_S:g} s)")

    def out(self, n: int) -> None:
        if n > MAX_OUTPUT_ROWS:
            raise PipelineRuntimeError(
                f"{self.op}: sortie trop volumineuse ({n} > {MAX_OUTPUT_ROWS} géométries)"
            )

    def bound(self, geoms: list, *, topological: bool = True) -> None:
        if topological and len(geoms) > MAX_FEATURES:
            raise PipelineRuntimeError(
                f"{self.op}: trop d'entités ({len(geoms)} > {MAX_FEATURES}) pour une op topologique"
            )
        n = int(shapely.get_num_coordinates(np.asarray(geoms, dtype=object)).sum()) if geoms else 0
        if n > MAX_VERTICES:
            raise PipelineRuntimeError(f"{self.op}: trop de sommets ({n} > {MAX_VERTICES})")


def _loads(frame: pd.DataFrame) -> list:
    return [shapely.wkb.loads(bytes(w)) for w in frame["geometry"]]


def _dump(g) -> bytes:
    return shapely.wkb.dumps(g)


def _fam(g) -> str:
    return g.geom_type.removeprefix("Multi")


def _require(op: str, geoms: list, families: set[str]) -> None:
    bad = sorted({g.geom_type for g in geoms if _fam(g) not in families})
    if bad:
        raise PipelineRuntimeError(
            f"{op}: types de géométrie attendus {sorted(families)}, reçu {', '.join(bad)}"
        )


def _parts(g) -> list:
    return [p for p in shapely.get_parts(g) if not p.is_empty]


def _rowwise(conn, input_view, view_name, op, fn) -> None:
    """Applique `fn(geom) -> list[geom]` à chaque ligne : 0 sortie = ligne écartée, n sorties =
    n lignes aux attributs recopiés."""
    df = _read_geometry_rows(conn, input_view)
    b = _Budget(op)
    geoms = _loads(df) if not df.empty else []
    b.bound(geoms, topological=False)
    idx: list[int] = []
    out: list[bytes] = []
    for i, g in enumerate(geoms):
        b.check()
        for geom in fn(g):
            idx.append(i)
            out.append(_dump(geom))
        b.out(len(idx))
    res_df = df.iloc[idx].reset_index(drop=True)
    if idx:
        res_df["geometry"] = out
    _write_geometry_rows(conn, res_df, view_name=view_name)


# --------------------------------------------------------------------------------------
# Triangulator (polygones) — constrained Delaunay, une ligne par triangle
# --------------------------------------------------------------------------------------


class TransformTriangulatePolygonParams(_Strict):
    """Décompose chaque polygone en triangles (triangulation de Delaunay contrainte, trous
    respectés) : une ligne par triangle, attributs recopiés. Les géométries vides sont
    écartées ; seuls les polygones sont acceptés (pour trianguler un nuage de points, voir
    l'opération de triangulation de Delaunay)."""


def _exec_triangulate_polygon(conn, *, input_view, view_name, params) -> None:
    TransformTriangulatePolygonParams.model_validate(params)
    op = "transform.triangulatePolygon"

    def fn(g):
        _require(op, [g], {"Polygon"})
        if g.is_empty:
            return []
        try:
            return _parts(shapely.constrained_delaunay_triangles(g))
        except shapely.errors.GEOSException as exc:
            raise PipelineRuntimeError(f"{op}: polygone non triangulable ({exc})") from exc

    _rowwise(conn, input_view, view_name, op, fn)


# --------------------------------------------------------------------------------------
# VertexRemover / SpikeRemover — reconstruction par anneau/ligne
# --------------------------------------------------------------------------------------


def _reject_nonplanar_z(op: str, g) -> None:
    """Revue finale FME, I5 : une surface Z invalide en 2D (faces verticales, solide
    `reader.cityjson`) serait détruite par une réparation ou un filtre de surface planaire
    (make_valid, `area > 0`) : refus explicite plutôt que perte silencieuse."""
    if g.has_z and not g.is_empty and _fam(g) == "Polygon" and not g.is_valid:
        raise PipelineRuntimeError(
            f"{op}: surface 3D non planaire (faces verticales, solide) non prise en charge "
            "par cette op 2D — séparez les faces ou retirez Z avant"
        )


def _reject_z(op: str, geoms: list) -> None:
    """Op de couverture planaire (union/différence de surfaces) : aucune entrée Z acceptée."""
    if any(g.has_z for g in geoms):
        raise PipelineRuntimeError(
            f"{op}: géométries 3D (Z) non prises en charge (op planaire) — retirez Z avant"
        )


def _valid_area(g, op: str):
    """Résultat d'une reconstruction : un polygone devenu invalide est réparé (make_valid) et
    réduit à sa partie surfacique (vide si elle disparaît). Surface Z non planaire : refus."""
    if g.is_empty or g.is_valid or _fam(g) != "Polygon":
        return g
    _reject_nonplanar_z(op, g)
    ps = [q for q in _parts(shapely.make_valid(g)) if q.geom_type == "Polygon"]
    return shapely.union_all(ps) if ps else Polygon()


def _rebuild(g, f: Callable[[np.ndarray, bool], np.ndarray]):
    """Reconstruit `g` en passant la liste de sommets de chaque ligne/anneau (anneau sans son
    sommet de fermeture) à `f`. Résultat dégénéré (<2 sommets ligne, <3 anneau) → vide."""
    if g.is_empty or g.geom_type in ("Point", "MultiPoint"):
        return g
    t = g.geom_type
    if t in ("LineString", "LinearRing"):
        c = f(np.asarray(g.coords), False)
        return LineString(c) if len(c) >= 2 else LineString()
    if t == "Polygon":
        ext = f(np.asarray(g.exterior.coords)[:-1], True)
        if len(ext) < 3:
            return Polygon()
        holes = []
        for r in g.interiors:
            h = f(np.asarray(r.coords)[:-1], True)
            if len(h) >= 3:
                holes.append(h)
        return Polygon(ext, holes)
    parts = [r for r in (_rebuild(p, f) for p in g.geoms) if not r.is_empty]
    return type(g)(parts) if parts else type(g)()


class TransformRemoveVerticesParams(_Strict):
    """Supprime (mode `remove`) ou conserve seuls (mode `keep`) les sommets dont la position
    est dans `indices`. Position comptée à partir de 0 sur chaque ligne ou anneau (le sommet
    de fermeture d'un anneau n'est pas compté) ; les négatifs comptent depuis la fin. Un
    résultat dégénéré (moins de 2 sommets pour une ligne, 3 pour un anneau) donne une
    géométrie vide."""

    indices: list[int] = Field(..., min_length=1, max_length=1000)
    mode: Literal["remove", "keep"] = "remove"


def _exec_remove_vertices(conn, *, input_view, view_name, params) -> None:
    p = TransformRemoveVerticesParams.model_validate(params)

    def f(c: np.ndarray, closed: bool) -> np.ndarray:
        n = len(c)
        sel = {i if i >= 0 else n + i for i in p.indices} & set(range(n))
        mask = np.zeros(n, dtype=bool)
        mask[list(sel)] = True
        return c[~mask] if p.mode == "remove" else c[mask]

    _rowwise(
        conn,
        input_view,
        view_name,
        "transform.removeVertices",
        lambda g: [_valid_area(_rebuild(g, f), "transform.removeVertices")],
    )


class TransformRemoveSpikesParams(_Strict):
    """Supprime les pics : sommets dont l'angle entre les deux segments adjacents est inférieur
    à `angleThreshold` degrés, et les sommets consécutifs dupliqués. Les extrémités d'une
    ligne sont toujours conservées. Applicable aux points (inchangés), lignes et polygones."""

    angleThreshold: float = Field(5.0, gt=0, lt=180)


def _despike(c: np.ndarray, closed: bool, thr_deg: float) -> np.ndarray:
    # Toutes les dimensions (X, Y et Z si présent) : en XY seul, une arête verticale (même XY,
    # Z différent) passait pour un doublon ou un pic d'angle nul (revue finale FME, I5).
    keep = np.ones(len(c), dtype=bool)
    keep[1:] = np.any(np.diff(c, axis=0) != 0, axis=1)  # doublons consécutifs
    c = c[keep]
    for _ in range(50):
        n = len(c)
        if n < (4 if closed else 3):
            break
        prev = np.roll(c, 1, axis=0) - c
        nxt = np.roll(c, -1, axis=0) - c
        norm = np.linalg.norm(prev, axis=1) * np.linalg.norm(nxt, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = np.where(norm > 0, (prev * nxt).sum(axis=1) / norm, 1.0)
        ang = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        bad = ang < thr_deg
        if not closed:
            bad[0] = bad[-1] = False
        # deux voisins mauvais : on ne retire que le plus aigu, au tour suivant l'autre
        for i in np.flatnonzero(bad):
            if bad[(i + 1) % n] and ang[(i + 1) % n] < ang[i]:
                bad[i] = False
        if not bad.any():
            break
        c = c[~bad]
    return c


def _exec_remove_spikes(conn, *, input_view, view_name, params) -> None:
    p = TransformRemoveSpikesParams.model_validate(params)
    _rowwise(
        conn,
        input_view,
        view_name,
        "transform.removeSpikes",
        lambda g: [
            _valid_area(
                _rebuild(g, lambda c, closed: _despike(c, closed, p.angleThreshold)),
                "transform.removeSpikes",
            )
        ],
    )


# --------------------------------------------------------------------------------------
# AreaGapAndOverlapCleaner
# --------------------------------------------------------------------------------------


class TransformCleanAreaGapsOverlapsParams(_Strict):
    """Nettoie une couverture de polygones : un chevauchement est attribué au premier polygone
    (ordre d'entrée), les interstices de surface au plus `maxGapArea` sont comblés en les
    rattachant au voisin partageant la plus longue frontière. `gapTolerance` (> 0) ferme aussi
    les interstices ouverts plus étroits que cette distance. `groupBy` nettoie chaque groupe
    séparément."""

    maxGapArea: float = Field(..., gt=0)
    gapTolerance: float = Field(0.0, ge=0)
    groupBy: list[str] = Field(default_factory=list)


def _polygonal(g):
    g = shapely.make_valid(g) if not g.is_valid else g
    ps = [q for q in _parts(g) if q.geom_type == "Polygon" and q.area > 0]
    return shapely.union_all(ps) if ps else Polygon()


def _clean_coverage(geoms: list, p: TransformCleanAreaGapsOverlapsParams, b: _Budget) -> list:
    done: list = []
    tree_geoms: list = []
    for g in geoms:
        b.check()
        g = _polygonal(g)
        if tree_geoms and not g.is_empty:
            tree = STRtree(tree_geoms)
            near = [tree_geoms[i] for i in tree.query(g, predicate="intersects")]
            if near:
                g = _polygonal(g.difference(shapely.union_all(near)))
        done.append(g)
        tree_geoms.append(g)
    live = [g for g in done if not g.is_empty]
    if not live:
        return done
    u = shapely.union_all(live)
    shells = shapely.union_all([Polygon(q.exterior) for q in _parts(u)])
    closed = shells
    if p.gapTolerance > 0:
        t = p.gapTolerance / 2
        closed = u.buffer(t, join_style="mitre").buffer(-t, join_style="mitre").union(shells)
    gaps = [q for q in _parts(closed.difference(u)) if 0 < q.area <= p.maxGapArea]
    if not gaps:
        return done
    tree = STRtree(done)
    reach = p.gapTolerance + 1e-9 * max(1.0, max(abs(v) for v in u.bounds))
    for gap in gaps:
        b.check()
        cand = tree.query(gap.buffer(reach), predicate="intersects")
        best, best_len = None, 0.0
        for i in cand:
            if done[i].is_empty:
                continue
            ln = gap.boundary.intersection(done[i].buffer(reach)).length
            if ln > best_len:
                best, best_len = i, ln
        if best is not None:
            done[best] = _polygonal(done[best].union(gap))
            tree = STRtree(done)
    return done


def _exec_clean_gaps_overlaps(conn, *, input_view, view_name, params) -> None:
    p = TransformCleanAreaGapsOverlapsParams.model_validate(params)
    op = "transform.cleanAreaGapsOverlaps"
    df = _read_geometry_rows(conn, input_view)
    b = _Budget(op)

    def one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = _loads(frame)
        _require(op, geoms, {"Polygon"})
        _reject_z(op, geoms)
        b.bound(geoms)
        res = _clean_coverage(geoms, p, b)
        keep = [i for i, g in enumerate(res) if not g.is_empty]
        out = frame.iloc[keep].reset_index(drop=True)
        out["geometry"] = [_dump(res[i]) for i in keep]
        return out

    out = _apply_per_group(df, p.groupBy, one, list(df.columns))
    _write_geometry_rows(conn, out, view_name=view_name)


# --------------------------------------------------------------------------------------
# AreaAmalgamator / AreaBuilder / LineCombiner — agrégats par groupe
# --------------------------------------------------------------------------------------


def _group_op(conn, input_view, view_name, op, group_by, build, families, topological=True):
    """`build(geoms, budget) -> list[geom]` ; une ligne par géométrie, colonnes groupBy +
    geometry."""
    df = _read_geometry_rows(conn, input_view)
    b = _Budget(op)

    def one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = _loads(frame)
        _require(op, geoms, families)
        b.bound(geoms, topological=topological)
        res = [g for g in build([g for g in geoms if not g.is_empty], b) if not g.is_empty]
        b.out(len(res))
        return pd.DataFrame(
            {
                **{c: [frame[c].iloc[0]] * len(res) for c in group_by},
                "geometry": [_dump(g) for g in res],
            }
        )

    out = _apply_per_group(df, group_by, one, [*group_by, "geometry"])
    _write_geometry_rows(conn, out, view_name=view_name)


class TransformAmalgamateAreasParams(_Strict):
    """Généralise une couverture de polygones : relie les polygones distants d'au plus
    `distance`, fusionne les voisins et comble les trous de surface au plus `fillHolesBelowArea`.
    Une ligne par polygone résultant ; seules les colonnes `groupBy` sont conservées."""

    distance: float = Field(0.0, ge=0)
    fillHolesBelowArea: float | None = Field(None, gt=0)
    groupBy: list[str] = Field(default_factory=list)


def _exec_amalgamate_areas(conn, *, input_view, view_name, params) -> None:
    p = TransformAmalgamateAreasParams.model_validate(params)

    def build(geoms, b):
        if not geoms:
            return []
        _reject_z("transform.amalgamateAreas", geoms)
        u = shapely.union_all([_polygonal(g) for g in geoms])
        if p.distance > 0:
            r = p.distance / 2
            u = u.buffer(r, join_style="mitre").buffer(-r, join_style="mitre").union(u)
        res = []
        for q in _parts(u):
            if q.geom_type != "Polygon":
                continue
            if p.fillHolesBelowArea is not None:
                holes = [h for h in q.interiors if Polygon(h).area > p.fillHolesBelowArea]
                q = Polygon(q.exterior, holes)
            res.append(q)
        return res

    _group_op(
        conn,
        input_view,
        view_name,
        "transform.amalgamateAreas",
        p.groupBy,
        build,
        {"Polygon"},
    )


class TransformBuildAreasParams(_Strict):
    """Construit des polygones (avec leurs trous) à partir d'un réseau de lignes formant des
    boucles fermées : les lignes sont d'abord noeudées à leurs intersections. Une ligne
    ouverte ou pendante ne produit aucun polygone. Une ligne par polygone ; seules les
    colonnes `groupBy` sont conservées."""

    groupBy: list[str] = Field(default_factory=list)


def _exec_build_areas(conn, *, input_view, view_name, params) -> None:
    p = TransformBuildAreasParams.model_validate(params)
    _group_op(
        conn,
        input_view,
        view_name,
        "transform.buildAreas",
        p.groupBy,
        lambda geoms, b: _parts(shapely.polygonize([shapely.union_all(geoms)])) if geoms else [],
        {"LineString"},
    )


class TransformCombineLinesParams(_Strict):
    """Fusionne les segments de lignes qui partagent une extrémité en lignes continues (la
    fusion s'arrête aux nœuds où trois segments ou plus se rejoignent). Une ligne par ligne
    résultante ; seules les colonnes `groupBy` sont conservées."""

    groupBy: list[str] = Field(default_factory=list)


def _exec_combine_lines(conn, *, input_view, view_name, params) -> None:
    p = TransformCombineLinesParams.model_validate(params)
    _group_op(
        conn,
        input_view,
        view_name,
        "transform.combineLines",
        p.groupBy,
        lambda geoms, b: _parts(shapely.line_merge(shapely.union_all(geoms))) if geoms else [],
        {"LineString"},
        topological=False,
    )


# --------------------------------------------------------------------------------------
# DonutHoleExtractor
# --------------------------------------------------------------------------------------


class TransformExtractDonutHolesParams(_Strict):
    """Extrait les trous (anneaux intérieurs) des polygones comme polygones distincts, une
    ligne par trou, attributs de l'entité d'origine recopiés. Les polygones sans trou sont
    écartés."""


def _exec_extract_donut_holes(conn, *, input_view, view_name, params) -> None:
    TransformExtractDonutHolesParams.model_validate(params)
    op = "transform.extractDonutHoles"

    def fn(g):
        _require(op, [g], {"Polygon"})
        return [Polygon(r) for q in _parts(g) for r in q.interiors]

    _rowwise(conn, input_view, view_name, op, fn)


# --------------------------------------------------------------------------------------
# Chopper
# --------------------------------------------------------------------------------------


class TransformChopParams(_Strict):
    """Découpe les lignes et polygones en morceaux plus petits, attributs recopiés : au plus
    `maxVertices` sommets par morceau et/ou `maxLength` de longueur (lignes seulement). Les
    polygones sont découpés par bissection de leur emprise. Les points passent inchangés."""

    maxVertices: int | None = Field(None, ge=4, le=1_000_000)
    maxLength: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _one(self):
        if self.maxVertices is None and self.maxLength is None:
            raise ValueError("maxVertices ou maxLength requis")
        return self


def _chop_line(line: LineString, p: TransformChopParams) -> list:
    pieces = [line]
    if p.maxLength is not None and line.length > p.maxLength:
        n = math.ceil(line.length / p.maxLength)
        if n > MAX_CHOP_PIECES:
            raise PipelineRuntimeError(
                f"transform.chop: maxLength produirait {n} morceaux (> {MAX_CHOP_PIECES})"
            )
        step = line.length / n
        pieces = [shapely.ops.substring(line, i * step, (i + 1) * step) for i in range(n)]
    if p.maxVertices is not None:
        out = []
        for pc in pieces:
            c = list(pc.coords)
            if len(c) <= p.maxVertices:
                out.append(pc)
                continue
            step = p.maxVertices - 1
            out += [LineString(c[i : i + p.maxVertices]) for i in range(0, len(c) - 1, step)]
        pieces = [q for q in out if len(q.coords) >= 2]
    return pieces


def _chop_area(poly, max_v: int, depth: int = 0) -> list:
    if shapely.get_num_coordinates(poly) <= max_v:
        return [poly]
    if depth > 40:
        raise PipelineRuntimeError(f"transform.chop: impossible de descendre sous {max_v} sommets")
    x0, y0, x1, y1 = poly.bounds
    if x1 - x0 >= y1 - y0:
        m = (x0 + x1) / 2
        boxes = [(x0, y0, m, y1), (m, y0, x1, y1)]
    else:
        m = (y0 + y1) / 2
        boxes = [(x0, y0, x1, m), (x0, m, x1, y1)]
    out = []
    for bx in boxes:
        piece = shapely.clip_by_rect(poly, *bx)
        for q in _parts(piece):
            if q.geom_type == "Polygon" and q.area > 0:
                out += _chop_area(q, max_v, depth + 1)
    return out


def _exec_chop(conn, *, input_view, view_name, params) -> None:
    p = TransformChopParams.model_validate(params)
    op = "transform.chop"

    def fn(g):
        _require(op, [g], {"Point", "LineString", "Polygon"})
        if g.is_empty or _fam(g) == "Point":
            return [g]
        if _fam(g) == "LineString":
            return [pc for ln in _parts(g) for pc in _chop_line(ln, p)]
        if p.maxVertices is None:
            raise PipelineRuntimeError(f"{op}: maxLength ne s'applique pas aux polygones")
        _reject_nonplanar_z(op, g)  # `_chop_area` écarterait les faces verticales (aire 0)
        return [pc for q in _parts(g) for pc in _chop_area(q, p.maxVertices)]

    _rowwise(conn, input_view, view_name, op, fn)


# --------------------------------------------------------------------------------------
# GeometryCoercer
# --------------------------------------------------------------------------------------


class TransformCoerceGeometryParams(_Strict):
    """Convertit le type de géométrie : `point` (multipoint éclaté en points), `line` (polygone
    en ses contours, multiligne éclatée), `area` (ligne fermée en polygone), `multi`
    (regroupe les parties homogènes en une géométrie multi-parties). `onUnconvertible`
    `null` met la géométrie à NULL pour les lignes non convertibles, `error` échoue."""

    target: Literal["point", "line", "area", "multi"]
    onUnconvertible: Literal["error", "null"] = "error"


class _Unconvertible(Exception):
    pass


def _coerce(g, target: str) -> list:
    if g.is_empty:
        raise _Unconvertible("géométrie vide")
    fam = _fam(g) if g.geom_type != "GeometryCollection" else None
    if target == "point":
        if fam == "Point":
            return _parts(g)
        raise _Unconvertible(f"{g.geom_type} -> point")
    if target == "line":
        if fam == "LineString":
            return _parts(g)
        if fam == "Polygon":
            return [LineString(r) for q in _parts(g) for r in (q.exterior, *q.interiors)]
        raise _Unconvertible(f"{g.geom_type} -> line")
    if target == "area":
        if fam == "Polygon":
            return _parts(g)
        if fam == "LineString":
            res = []
            for ln in _parts(g):
                if not ln.is_closed or len(ln.coords) < 4:
                    raise _Unconvertible("ligne non fermée")
                res.append(Polygon(ln))
            return res
        raise _Unconvertible(f"{g.geom_type} -> area")
    parts = _parts(g)
    fams = {_fam(q) for q in parts}
    if len(fams) != 1:
        raise _Unconvertible("parties hétérogènes")
    cls = {"Point": shapely.MultiPoint, "LineString": MultiLineString}.get(
        next(iter(fams)), shapely.MultiPolygon
    )
    return [cls(parts)]


def _exec_coerce_geometry(conn, *, input_view, view_name, params) -> None:
    p = TransformCoerceGeometryParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    idx: list[int] = []
    out: list[bytes | None] = []
    b = _Budget("transform.coerceGeometry")
    for i, g in enumerate(_loads(df) if not df.empty else []):
        b.check()
        try:
            for r in _coerce(g, p.target):
                idx.append(i)
                out.append(_dump(r))
        except _Unconvertible as exc:
            if p.onUnconvertible == "error":
                raise PipelineRuntimeError(
                    f"transform.coerceGeometry: ligne {i} non convertible ({exc})"
                ) from exc
            idx.append(i)
            out.append(None)
    res = df.iloc[idx].reset_index(drop=True)
    if idx:
        res["geometry"] = out
    _write_geometry_rows(conn, res, view_name=view_name)


# --------------------------------------------------------------------------------------
# Intersector / LineOnAreaOverlayer
# --------------------------------------------------------------------------------------


class TransformIntersectorParams(_Strict):
    """Fragmente les lignes (ou les polygones) à chaque intersection entre entités du même
    groupe : une ligne de sortie par fragment, attributs de l'entité d'origine recopiés
    (un fragment commun à deux polygones est émis une fois par polygone). Un groupe ne mélange
    pas lignes et polygones. Le port des nœuds de FME n'est pas fourni."""

    groupBy: list[str] = Field(default_factory=list)


def _node_lines(geoms: list, b: _Budget) -> list[list]:
    tree = STRtree(geoms)
    scale = max(1.0, max(abs(v) for g in geoms for v in g.bounds))
    tol = 1e-9 * scale
    res: list[list] = []
    total = 0
    for i, g in enumerate(geoms):
        b.check()
        near = [geoms[j] for j in tree.query(g, predicate="intersects") if j != i]
        noded = shapely.node(MultiLineString([*_parts(g), *[q for n in near for q in _parts(n)]]))
        res.append(
            [
                q
                for q in _parts(noded)
                if q.length > 0
                and shapely.distance(shapely.line_interpolate_point(q, 0.5, normalized=True), g)
                <= tol
            ]
        )
        total += len(res[-1])
        b.out(total)
    return res


def _node_areas(geoms: list, b: _Budget) -> list[list]:
    if len(geoms) > MAX_AREA_FEATURES:
        raise PipelineRuntimeError(
            f"transform.intersector: trop de polygones par groupe ({len(geoms)} > "
            f"{MAX_AREA_FEATURES}) — faces en O(n²)"
        )
    faces = _parts(
        shapely.polygonize([shapely.union_all([shapely.boundary(g) for g in geoms])]),
    )
    b.out(len(faces))
    if not faces:
        return [[] for _ in geoms]
    tree = STRtree(faces)
    res: list[list] = []
    total = 0
    for g in geoms:
        b.check()
        res.append(
            [
                faces[k]
                for k in tree.query(g, predicate="intersects")
                if g.contains(faces[k].representative_point())
            ]
        )
        total += len(res[-1])
        b.out(total)
    return res


def _exec_intersector(conn, *, input_view, view_name, params) -> None:
    p = TransformIntersectorParams.model_validate(params)
    op = "transform.intersector"
    df = _read_geometry_rows(conn, input_view)
    b = _Budget(op)

    def one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = _loads(frame)
        _require(op, geoms, {"LineString", "Polygon"})
        keep = [i for i, g in enumerate(geoms) if not g.is_empty]
        geoms = [geoms[i] for i in keep]
        frame = frame.iloc[keep]
        b.bound(geoms)
        if not geoms:
            return frame.iloc[0:0]
        fams = {_fam(g) for g in geoms}
        if len(fams) > 1:
            raise PipelineRuntimeError(f"{op}: lignes et polygones ne se mélangent pas")
        pieces = _node_lines(geoms, b) if fams == {"LineString"} else _node_areas(geoms, b)
        idx = [i for i, ps in enumerate(pieces) for _ in ps]
        out = frame.iloc[idx].reset_index(drop=True)
        out["geometry"] = [_dump(q) for ps in pieces for q in ps]
        return out

    out = _apply_per_group(df, p.groupBy, one, list(df.columns))
    _write_geometry_rows(conn, out, view_name=view_name)


class TransformLineOnAreaOverlayerParams(_Strict):
    """Superpose, dans un même flux, des lignes et des polygones. Mode `splitLines` : les
    lignes sont coupées aux frontières des polygones (colonne `overlay_inside` : fragment à
    l'intérieur ou non) ; les polygones sont écartés. Mode `splitAreas` : les polygones sont
    subdivisés par les lignes ; les lignes sont écartées."""

    mode: Literal["splitLines", "splitAreas"] = "splitLines"
    groupBy: list[str] = Field(default_factory=list)


def _lines_only(g) -> list:
    return [q for q in _parts(g) if q.geom_type == "LineString" and q.length > 0]


def _exec_line_on_area_overlayer(conn, *, input_view, view_name, params) -> None:
    p = TransformLineOnAreaOverlayerParams.model_validate(params)
    op = "transform.lineOnAreaOverlayer"
    df = _read_geometry_rows(conn, input_view)
    columns = list(df.columns)
    if p.mode == "splitLines":
        df = df.assign(overlay_inside=pd.Series([False] * len(df), dtype="boolean"))
        columns.append("overlay_inside")
    b = _Budget(op)

    def one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = _loads(frame)
        _require(op, geoms, {"LineString", "Polygon"})
        b.bound(geoms)
        areas = [g for g in geoms if _fam(g) == "Polygon" and not g.is_empty]
        lines = [g for g in geoms if _fam(g) == "LineString" and not g.is_empty]
        idx: list[int] = []
        out: list[bytes] = []
        inside: list[bool] = []
        if p.mode == "splitLines":
            area_u = shapely.union_all(areas) if areas else Polygon()
            for i, g in enumerate(geoms):
                b.check()
                if _fam(g) != "LineString" or g.is_empty:
                    continue
                ins = _lines_only(g.intersection(area_u))
                outs = _lines_only(g.difference(area_u))
                for q, flag in [(q, True) for q in ins] + [(q, False) for q in outs]:
                    idx.append(i)
                    out.append(_dump(q))
                    inside.append(flag)
        else:
            line_u = shapely.union_all(lines) if lines else None
            for i, g in enumerate(geoms):
                b.check()
                if _fam(g) != "Polygon" or g.is_empty:
                    continue
                cut = line_u.intersection(g) if line_u is not None else None
                if cut is None or cut.is_empty:
                    faces = [g]
                else:
                    faces = [
                        f
                        for f in _parts(shapely.polygonize([shapely.union_all([g.boundary, cut])]))
                        if g.contains(f.representative_point())
                    ]
                for f in faces:
                    idx.append(i)
                    out.append(_dump(f))
        res = frame.iloc[idx].reset_index(drop=True)
        if idx:
            res["geometry"] = out
        if p.mode == "splitLines":
            res["overlay_inside"] = pd.Series(inside, dtype="boolean")
        return res

    out = _apply_per_group(df, p.groupBy, one, columns)
    _write_geometry_rows(conn, out, view_name=view_name)


# --------------------------------------------------------------------------------------
# AffineWarper / RubberSheeter
# --------------------------------------------------------------------------------------


class ControlVector(_Strict):
    """Vecteur de contrôle : `source` (position actuelle) et `target` (position souhaitée)."""

    source: tuple[float, float]
    target: tuple[float, float]

    @field_validator("source", "target")
    @classmethod
    def _finite(cls, v):
        if not all(math.isfinite(c) for c in v):
            raise ValueError("coordonnée non finie")
        return v


class TransformAffineWarpParams(_Strict):
    """Recale les coordonnées par la transformation affine (moindres carrés) qui amène au
    mieux chaque `source` sur sa `target` — au moins 3 vecteurs de contrôle non alignés.
    La coordonnée Z éventuelle est conservée."""

    controlVectors: list[ControlVector] = Field(..., min_length=3, max_length=1000)


class TransformRubberSheetParams(_Strict):
    """Déplace chaque sommet d'un déplacement interpolé (pondération par l'inverse de la
    distance à la puissance `power`) entre les vecteurs de contrôle : exact aux points de
    contrôle, dont l'influence décroît avec la distance. Au moins 1 vecteur ; la coordonnée
    Z éventuelle est conservée."""

    controlVectors: list[ControlVector] = Field(..., min_length=1, max_length=1000)
    power: float = Field(2.0, gt=0, le=10)


def _warp_rows(conn, input_view, view_name, op, move: Callable[[np.ndarray], np.ndarray]):
    def f(xy: np.ndarray) -> np.ndarray:
        return move(np.asarray(xy[:, :2], dtype=float))

    def fn(g):
        if g.is_empty:
            return [g]
        return [
            shapely.transform(g, lambda c: np.column_stack([f(c), c[:, 2:]]), include_z=g.has_z)
        ]

    _rowwise(conn, input_view, view_name, op, fn)


def _exec_affine_warp(conn, *, input_view, view_name, params) -> None:
    p = TransformAffineWarpParams.model_validate(params)
    src = np.array([v.source for v in p.controlVectors])
    dst = np.array([v.target for v in p.controlVectors])
    a = np.column_stack([src, np.ones(len(src))])
    if np.linalg.matrix_rank(a) < 3:
        raise PipelineRuntimeError(
            "transform.affineWarp: vecteurs de contrôle alignés ou confondus"
        )
    coef, *_ = np.linalg.lstsq(a, dst, rcond=None)
    _warp_rows(
        conn,
        input_view,
        view_name,
        "transform.affineWarp",
        lambda xy: np.column_stack([xy, np.ones(len(xy))]) @ coef,
    )


def _exec_rubber_sheet(conn, *, input_view, view_name, params) -> None:
    p = TransformRubberSheetParams.model_validate(params)
    src = np.array([v.source for v in p.controlVectors])
    disp = np.array([v.target for v in p.controlVectors]) - src

    step = max(1, RUBBER_CHUNK // len(src))

    def move(xy: np.ndarray) -> np.ndarray:
        # blocs de sommets : la mémoire reste bornée quel que soit sommets × contrôles
        return np.vstack([_move_block(xy[i : i + step]) for i in range(0, len(xy), step)])

    def _move_block(xy: np.ndarray) -> np.ndarray:
        d = np.linalg.norm(xy[:, None, :] - src[None, :, :], axis=2)
        exact = d < 1e-12
        with np.errstate(divide="ignore"):
            w = 1.0 / np.power(d, p.power)
        w = np.where(exact.any(axis=1, keepdims=True), exact.astype(float), w)
        return xy + (w @ disp) / w.sum(axis=1, keepdims=True)

    _warp_rows(conn, input_view, view_name, "transform.rubberSheet", move)


# --------------------------------------------------------------------------------------
# CoordinateSystemDescriptionConverter
# --------------------------------------------------------------------------------------

MAX_CRS_VALUES = 10_000
MAX_CRS_TEXT = 20_000


class TransformConvertCrsDescriptionParams(_Strict):
    """Convertit une description de système de coordonnées (code EPSG, WKT, PROJ.4, PROJJSON,
    nom) contenue dans la colonne `sourceColumn` vers le format `targetFormat`, écrit dans
    `outputColumn` (remplacée si elle existe). Une description illisible donne NULL."""

    sourceColumn: str
    outputColumn: OutputColumn = "crs_converted"
    targetFormat: Literal["epsg", "wkt", "projjson", "proj4", "name"] = "wkt"


def _convert_crs(text: str, fmt: str) -> str | None:
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    s = text.strip()
    if not s or len(s) > MAX_CRS_TEXT or "+init=" in s.lower():  # +init= lit des fichiers PROJ
        return None
    try:
        crs = CRS.from_user_input(int(s) if s.isdigit() else s)
        if fmt == "epsg":
            code = crs.to_epsg()
            return f"EPSG:{code}" if code else None
        if fmt == "wkt":
            return crs.to_wkt()
        if fmt == "projjson":
            return crs.to_json()
        if fmt == "proj4":
            return crs.to_proj4()
        return crs.name
    except (CRSError, ValueError):
        return None


def _exec_convert_crs_description(conn, *, input_view, view_name, params) -> None:
    p = TransformConvertCrsDescriptionParams.model_validate(params)
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    if p.sourceColumn not in cols:
        raise PipelineRuntimeError(
            f"transform.convertCrsDescription: colonne {p.sourceColumn!r} introuvable"
        )
    src = f"CAST({_qi(p.sourceColumn)} AS VARCHAR)"
    vals = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT {src} FROM {_qi(input_view)} WHERE {src} IS NOT NULL "
            f"LIMIT {MAX_CRS_VALUES + 1}"
        ).fetchall()
    ]
    if len(vals) > MAX_CRS_VALUES:
        raise PipelineRuntimeError(
            f"transform.convertCrsDescription: plus de {MAX_CRS_VALUES} valeurs distinctes"
        )
    mapping = pd.DataFrame(
        {"k": vals, "v": [_convert_crs(v, p.targetFormat) for v in vals]},
        dtype="object",
    )
    conn.register("_crs_map_tmp", mapping)
    out = _qi(p.outputColumn)
    star = f"i.* REPLACE (m.v AS {out})" if p.outputColumn in cols else f"i.*, m.v AS {out}"
    try:
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {star} FROM {_qi(input_view)} i "
            f"LEFT JOIN _crs_map_tmp m ON CAST(i.{_qi(p.sourceColumn)} AS VARCHAR) = m.k"
        )
    finally:
        conn.unregister("_crs_map_tmp")


# --------------------------------------------------------------------------------------
# Contrats
# --------------------------------------------------------------------------------------

_SHAPELY = {"engine": "shapely", "engine_license": "BSD-3-Clause (Shapely)"}

CONTRACTS += [
    OperationContract(op=op, kind="transform", params_schema=schema, execute=fn, **_SHAPELY)
    for op, schema, fn in [
        (
            "transform.triangulatePolygon",
            TransformTriangulatePolygonParams,
            _exec_triangulate_polygon,
        ),
        ("transform.removeVertices", TransformRemoveVerticesParams, _exec_remove_vertices),
        ("transform.removeSpikes", TransformRemoveSpikesParams, _exec_remove_spikes),
        (
            "transform.cleanAreaGapsOverlaps",
            TransformCleanAreaGapsOverlapsParams,
            _exec_clean_gaps_overlaps,
        ),
        ("transform.amalgamateAreas", TransformAmalgamateAreasParams, _exec_amalgamate_areas),
        ("transform.buildAreas", TransformBuildAreasParams, _exec_build_areas),
        ("transform.intersector", TransformIntersectorParams, _exec_intersector),
        (
            "transform.lineOnAreaOverlayer",
            TransformLineOnAreaOverlayerParams,
            _exec_line_on_area_overlayer,
        ),
        ("transform.combineLines", TransformCombineLinesParams, _exec_combine_lines),
        (
            "transform.extractDonutHoles",
            TransformExtractDonutHolesParams,
            _exec_extract_donut_holes,
        ),
        ("transform.chop", TransformChopParams, _exec_chop),
        ("transform.coerceGeometry", TransformCoerceGeometryParams, _exec_coerce_geometry),
        ("transform.affineWarp", TransformAffineWarpParams, _exec_affine_warp),
        ("transform.rubberSheet", TransformRubberSheetParams, _exec_rubber_sheet),
    ]
] + [
    # Pas de géométrie en jeu : pyproj (MIT), pas Shapely.
    OperationContract(
        op="transform.convertCrsDescription",
        kind="transform",
        params_schema=TransformConvertCrsDescriptionParams,
        execute=_exec_convert_crs_description,
        engine="python",
        engine_license="MIT (pyproj)",
    )
]
