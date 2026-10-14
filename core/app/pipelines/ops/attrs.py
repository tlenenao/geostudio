# SPDX-License-Identifier: Apache-2.0
"""Module de voie A — attributs, filtres, SCR, texte, logique (transformers FME).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Déclare ses ops ici (modèles `*Params` + `OperationContract`), agrégées par
app.pipelines.ops.contracts.LANE_MODULES et app.pipelines.registries — gabarit :
docs/superpowers/plans/_fme-lane-template.md. Ne jamais importer contracts/runtime/
registries au niveau module (cycle d'import).

Le modèle de pipeline n'a pas de ports de sortie nommés : un « routeur » FME devient une op
à paramètre `output` (passed/failed) — deux nœuds aux mêmes paramètres partitionnent l'entrée
(patron `transform.testFilter`). Les ops à logique Python (MGRS, texte, HTML, planéité) sont
des fonctions utilisateur DuckDB (UDF) : null-safe, une erreur par ligne donne NULL, aucune
ligne n'est jamais écartée ni aucun type de colonne réécrit."""

import codecs
import hashlib
import html.parser
from collections.abc import Callable
from typing import Literal

import numpy as np
import shapely.wkb
from pydantic import BaseModel, Field, model_validator

from app.pipelines.compiler import _output_srid_reconcile_join
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.expr_validation import validate_bounded_expr
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_DUCKDB = "MIT (DuckDB)"
_MAX_CELL = 1_000_000  # octets/caractères lus par cellule pour les UDF texte/HTML


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _columns(conn, view: str) -> list[str]:
    return [d[0] for d in conn.execute(f"DESCRIBE {_qi(view)}").fetchall()]


def _need_columns(op: str, have: list[str], *wanted: str) -> None:
    missing = [c for c in wanted if c not in have]
    if missing:
        raise PipelineRuntimeError(f"{op}: colonne(s) introuvable(s) : {missing}")


def _create_view(conn, view_name: str, sql: str) -> None:
    conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")


def _udf(conn, view_name: str, tag: str, fn, args: list[str], ret: str) -> str:
    """Enregistre `fn` comme UDF DuckDB, nommée de façon unique par nœud (`view_name`)."""
    name = f"gs_{tag}_{hashlib.sha1(view_name.encode()).hexdigest()[:10]}"
    try:
        conn.remove_function(name)
    except Exception:  # noqa: BLE001 — absente au premier appel
        pass

    def call(*a):
        if any(x is None for x in a):
            return None
        try:
            return fn(*a)
        except Exception:  # noqa: BLE001 — une erreur par ligne donne NULL, jamais un run cassé
            return None

    # DuckDB lit l'arité de la signature : une enveloppe à arité fixe (1 ou 2 arguments).
    safe = (lambda x: call(x)) if len(args) == 1 else (lambda x, y: call(x, y))
    conn.create_function(name, safe, args, ret, null_handling="special")
    return name


# --------------------------------------------------------------------------- attributeManager


class TransformAttributeManagerParams(BaseModel):
    """Ajoute/calcule, renomme, supprime et réordonne des attributs en un seul nœud. Les
    expressions `derive` lisent toutes les colonnes d'entrée (avant renommage) ; une colonne
    existante du même nom est remplacée. Ordre d'application : derive, rename, remove, order."""

    derive: dict[str, str] = Field(default_factory=dict, max_length=50)
    rename: dict[str, str] = Field(default_factory=dict, max_length=50)
    remove: list[str] = Field(default_factory=list, max_length=100)
    order: list[str] = Field(default_factory=list, max_length=200)


def execute_attribute_manager(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformAttributeManagerParams.model_validate(params)
    exprs: dict[str, str] = {c: _qi(c) for c in _columns(conn, input_view)}
    for name, expr in p.derive.items():
        validate_bounded_expr(conn, expr)
        exprs[name] = f"({expr})"
    op = "transform.attributeManager"
    _need_columns(op, list(exprs), *p.rename, *p.remove)
    if "geometry" in p.remove or "geometry" in p.rename:
        raise PipelineRuntimeError(
            f"{op}: la colonne 'geometry' ne peut être ni retirée ni renommée"
        )
    for old, new in p.rename.items():
        if new != old and new in exprs and new not in p.rename:
            raise PipelineRuntimeError(f"{op}: le renommage vers {new!r} écraserait une colonne")
    renamed = {p.rename.get(c, c): e for c, e in exprs.items() if c not in p.remove}
    if len(renamed) != len([c for c in exprs if c not in p.remove]):
        raise PipelineRuntimeError(f"{op}: deux colonnes porteraient le même nom")
    _need_columns(op, list(renamed), *p.order)
    final = [*p.order, *(c for c in renamed if c not in p.order)]
    select = ", ".join(f"{renamed[c]} AS {_qi(c)}" for c in dict.fromkeys(final))
    _create_view(conn, view_name, f"SELECT {select} FROM {_qi(input_view)}")


# --------------------------------------------------------------------------- aggregateFilter


class TransformAggregateFilterParams(BaseModel):
    """Garde (`passed`) ou écarte (`failed`) les lignes dont le groupe (`groupBy`, vide = tout
    le flux) satisfait la condition `having`, écrite sur les métriques (agrégats SQL nommés,
    ex. `{"n": "count(*)"}` et `n >= 2`). Les lignes ne sont pas fusionnées : chacune reçoit
    les colonnes de métrique de son groupe (équivalent d'un HAVING qui conserve le détail)."""

    groupBy: list[str] = Field(default_factory=list, max_length=20)
    metrics: dict[str, str] = Field(..., min_length=1, max_length=20)
    having: str
    output: Literal["passed", "failed"] = "passed"


def execute_aggregate_filter(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformAggregateFilterParams.model_validate(params)
    have = _columns(conn, input_view)
    op = "transform.aggregateFilter"
    _need_columns(op, have, *p.groupBy)
    clash = [m for m in p.metrics if m in have]
    if clash:
        raise PipelineRuntimeError(f"{op}: nom(s) de métrique déjà utilisé(s) : {clash}")
    for expr in [*p.metrics.values(), p.having]:
        validate_bounded_expr(conn, expr)
    q = [_qi(c) for c in p.groupBy]
    cols = ", ".join(f"({e}) AS {_qi(m)}" for m, e in p.metrics.items())
    agg = f"SELECT {', '.join([*q, cols])} FROM {_qi(input_view)}" + (
        f" GROUP BY {', '.join(q)}" if q else ""
    )
    on = " AND ".join(f"s.{c} IS NOT DISTINCT FROM a.{c}" for c in q) or "true"
    mcols = ", ".join(f"a.{_qi(m)}" for m in p.metrics)
    cond = f"coalesce(({p.having}), false)"
    where = cond if p.output == "passed" else f"NOT {cond}"
    _create_view(
        conn,
        view_name,
        f"SELECT * FROM (SELECT s.*, {mcols} FROM {_qi(input_view)} s JOIN ({agg}) a ON {on}) "
        f"WHERE {where}",
    )


# --------------------------------------------------------------------------- matcher


class TransformMatcherParams(BaseModel):
    """Repère les doublons sans les supprimer : ajoute à chaque ligne l'effectif de son groupe
    de lignes identiques (`matchCountColumn`), un identifiant de groupe (`groupIdColumn`) et un
    indicateur `isDuplicateColumn` (vrai pour toute ligne après la première du groupe). Deux
    lignes sont identiques quand les colonnes `keyColumns` sont égales et, si `matchGeometry`,
    que leurs géométries sont strictement identiques (même WKB, pas d'égalité topologique)."""

    keyColumns: list[str] = Field(default_factory=list, max_length=20)
    matchGeometry: bool = False
    matchCountColumn: str = "match_count"
    groupIdColumn: str = "match_group"
    isDuplicateColumn: str = "is_duplicate"

    @model_validator(mode="after")
    def _has_criterion(self) -> "TransformMatcherParams":
        if not self.keyColumns and not self.matchGeometry:
            raise ValueError("keyColumns ou matchGeometry est requis")
        return self


def compile_matcher(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformMatcherParams.model_validate(params)
    keys = [_qi(c) for c in p.keyColumns] + (["ST_AsWKB(geometry)"] if p.matchGeometry else [])
    k = ", ".join(keys)
    return (
        f'SELECT * EXCLUDE ("__i"), '
        f"count(*) OVER (PARTITION BY {k}) AS {_qi(p.matchCountColumn)}, "
        f"dense_rank() OVER (ORDER BY {k}) AS {_qi(p.groupIdColumn)}, "
        f'(row_number() OVER (PARTITION BY {k} ORDER BY "__i") > 1) AS {_qi(p.isDuplicateColumn)} '
        f'FROM (SELECT *, row_number() OVER () AS "__i" FROM {_qi(input_view)})'
    )


# --------------------------------------------------------------------------- geometryFilter

_GEOM_TYPES = {
    "point": ["POINT"],
    "line": ["LINESTRING"],
    "polygon": ["POLYGON"],
    "aggregate": ["MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION"],
}


class TransformGeometryFilterParams(BaseModel):
    """Garde (`passed`) ou écarte (`failed`) les lignes selon le type de leur géométrie :
    point, ligne, polygone, agrégat (multi-géométries et collections) ou nulle (`null`).
    Une même liste `types` avec `passed` puis `failed` partitionne l'entrée."""

    types: list[Literal["point", "line", "polygon", "aggregate", "null"]] = Field(
        ..., min_length=1, max_length=5
    )
    output: Literal["passed", "failed"] = "passed"


def compile_geometry_filter(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformGeometryFilterParams.model_validate(params)
    names = [n for t in p.types if t != "null" for n in _GEOM_TYPES[t]]
    parts = []
    if names:
        parts.append(f"ST_GeometryType(geometry)::VARCHAR IN ({', '.join(map(_lit, names))})")
    if "null" in p.types:
        parts.append("geometry IS NULL")
    cond = f"coalesce(({' OR '.join(parts)}), false)"
    where = cond if p.output == "passed" else f"NOT {cond}"
    return f"SELECT * FROM {_qi(input_view)} WHERE {where}"


# --------------------------------------------------------------------------- attributeRangeFilter


class _Range(BaseModel):
    min: float | None = None  # borne basse incluse
    max: float | None = None  # borne haute exclue

    @model_validator(mode="after")
    def _ok(self) -> "_Range":
        if self.min is None and self.max is None:
            raise ValueError("une plage exige min et/ou max")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("min doit être strictement inférieur à max")
        return self


class TransformAttributeRangeFilterParams(BaseModel):
    """Route les lignes selon la plage numérique [min, max[ où tombe la valeur de `column`.
    `passed` garde celles qui tombent dans au moins une plage, `failed` les autres (valeur
    hors plage, NULL ou non numérique) ; `annotate` garde tout et ajoute `rangeColumn` = rang
    (base 0) de la PREMIÈRE plage correspondante dans l'ordre de la liste (NULL si aucune) —
    la priorité de FME en cas de chevauchement."""

    column: str
    ranges: list[_Range] = Field(..., min_length=1, max_length=50)
    output: Literal["passed", "failed", "annotate"] = "passed"
    rangeColumn: str = "range_index"


def compile_attribute_range_filter(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformAttributeRangeFilterParams.model_validate(params)
    v = f"TRY_CAST({_qi(p.column)} AS DOUBLE)"
    conds = []
    for r in p.ranges:
        sub = ([f"{v} >= {float(r.min)!r}"] if r.min is not None else []) + (
            [f"{v} < {float(r.max)!r}"] if r.max is not None else []
        )
        conds.append(" AND ".join(sub))
    src = _qi(input_view)
    if p.output == "annotate":
        case = " ".join(f"WHEN {c} THEN {i}" for i, c in enumerate(conds))
        return f"SELECT *, (CASE {case} END)::INTEGER AS {_qi(p.rangeColumn)} FROM {src}"
    cond = f"coalesce(({' OR '.join(f'({c})' for c in conds)}), false)"
    return f"SELECT * FROM {src} WHERE {cond if p.output == 'passed' else f'NOT {cond}'}"


# --------------------------------------------------------------------------- planarityFilter


class TransformPlanarityFilterParams(BaseModel):
    """Route selon la planéité des surfaces 3D : `planar` (tous les sommets de chaque polygone
    sont coplanaires, à `tolerance` près — écart RMS au plan d'ajustement, en unités du CRS),
    `notPlanar`, ou `rejected` (géométrie nulle, vide ou non surfacique). Une géométrie sans
    coordonnée Z est plane."""

    output: Literal["planar", "notPlanar", "rejected"] = "planar"
    tolerance: float = Field(1e-9, ge=0)


def _classify_planarity(wkb: bytes, tolerance: float) -> str:
    try:
        g = shapely.wkb.loads(bytes(wkb))
    except Exception:  # noqa: BLE001 — WKB illisible = rejeté
        return "rejected"
    if g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
        return "rejected"
    for poly in getattr(g, "geoms", [g]):
        if not poly.has_z:
            continue
        pts = np.array([c for ring in [poly.exterior, *poly.interiors] for c in ring.coords])
        centered = pts - pts.mean(axis=0)
        # plus petite valeur singulière = écart au meilleur plan ; RMS = s / sqrt(n)
        s = np.linalg.svd(centered, compute_uv=False)[-1] if len(pts) >= 3 else 0.0
        if s / np.sqrt(len(pts)) > tolerance:
            return "notPlanar"
    return "planar"


def execute_planarity_filter(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformPlanarityFilterParams.model_validate(params)
    tol = p.tolerance
    fn = _udf(conn, view_name, "planar", lambda b: _classify_planarity(b, tol), ["BLOB"], "VARCHAR")
    _create_view(
        conn,
        view_name,
        f"SELECT * FROM {_qi(input_view)} "
        f"WHERE coalesce({fn}(ST_AsWKB(geometry)), 'rejected') = {_lit(p.output)}",
    )


# --------------------------------------------------------------------------- spatialRelator


class TransformSpatialRelatorParams(BaseModel):
    """Compare chaque ligne (Requestor) aux entités de la seconde entrée (Supplier) selon un
    prédicat OGC (`predicate`, du Requestor vers le Supplier : `contains` = le Requestor
    contient le Supplier) et ajoute `countColumn` = nombre d'entités en relation. `output` :
    `all` (tout, avec le compte), `related` (au moins une relation) ou `unrelated`. Les
    Suppliers ne sont jamais réémis ; leurs attributs ne sont pas copiés."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    predicate: Literal[
        "intersects", "equals", "touches", "contains", "within", "crosses", "overlaps", "disjoint"
    ] = "intersects"
    output: Literal["all", "related", "unrelated"] = "all"
    countColumn: str = "match_count"


def compile_spatial_relator(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformSpatialRelatorParams.model_validate(params)
    assert join_view is not None, "transform.spatialRelator requires join_view"
    cnt = _qi(p.countColumn)
    inner = (
        f"SELECT t.* EXCLUDE (geometry), t.geometry, COUNT(o.geometry) AS {cnt} "
        f"FROM {_qi(input_view)} t LEFT JOIN {_qi(join_view)} o "
        f"ON ST_{p.predicate.capitalize()}(t.geometry, o.geometry) GROUP BY ALL"
    )
    if p.output == "all":
        return inner
    return f"SELECT * FROM ({inner}) WHERE {cnt} {'>' if p.output == 'related' else '='} 0"


# --------------------------------------------------------------------------- featureTypeFilter


class TransformFeatureTypeFilterParams(BaseModel):
    """Garde (`passed`) ou écarte (`failed`) les lignes d'un flux hétérogène dont la colonne
    `typeColumn` (type d'entité d'origine) figure dans `types`. Chaque source étant déjà un
    nœud reader homogène, ce filtre ne sert que pour un flux mixte portant son type en
    colonne."""

    typeColumn: str = "feature_type"
    types: list[str] = Field(..., min_length=1, max_length=100)
    output: Literal["passed", "failed"] = "passed"


def compile_feature_type_filter(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformFeatureTypeFilterParams.model_validate(params)
    in_list = ", ".join(map(_lit, p.types))
    cond = f"coalesce(CAST({_qi(p.typeColumn)} AS VARCHAR) IN ({in_list}), false)"
    where = cond if p.output == "passed" else f"NOT {cond}"
    return f"SELECT * FROM {_qi(input_view)} WHERE {where}"


# --------------------------------------------------------------------------- MGRS

_PREC = Field(5, ge=0, le=5, description="Précision : 5 = 1 m, 0 = 100 km")


class TransformLatLongToMgrsParams(BaseModel):
    """Calcule la référence MGRS (grille militaire) de chaque point (centroïde pour une
    autre géométrie) et l'écrit dans `column`. Exige un flux en EPSG:4326 ; une géométrie
    nulle ou hors du domaine MGRS (latitude invalide) donne NULL. `precision` : 5 = 1 m,
    4 = 10 m … 0 = 100 km."""

    column: str = "mgrs"
    precision: int = _PREC


class TransformMgrsToLatLongParams(BaseModel):
    """Convertit la référence MGRS de la colonne `column` en géométrie Point EPSG:4326 (coin
    sud-ouest de la cellule désignée), qui remplace/crée la colonne `geometry`. Une référence
    invalide ou NULL donne une géométrie NULL."""

    column: str = "mgrs"


def _to_mgrs(lat, lon, precision: int):
    import mgrs

    try:
        return mgrs.MGRS().toMGRS(lat, lon, MGRSPrecision=precision)
    except Exception:  # noqa: BLE001 — hors domaine -> NULL par ligne
        return None


def _from_mgrs(ref, axis: int):
    import mgrs

    try:
        return float(mgrs.MGRS().toLatLon(ref.strip())[axis])
    except Exception:  # noqa: BLE001
        return None


def execute_lat_long_to_mgrs(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
) -> None:
    p = TransformLatLongToMgrsParams.model_validate(params)
    if input_srid != 4326:
        raise PipelineRuntimeError(
            f"transform.latLongToMgrs exige EPSG:4326 (reçu EPSG:{input_srid}) — "
            "insérer transform.reproject avant"
        )
    prec = p.precision
    fn = _udf(
        conn,
        view_name,
        "tomgrs",
        lambda la, lo: _to_mgrs(la, lo, prec),
        ["DOUBLE", "DOUBLE"],
        "VARCHAR",
    )
    sql = (
        f"SELECT * EXCLUDE ({_qi(p.column)}), "
        if p.column in _columns(conn, input_view)
        else "SELECT *, "
    ) + (
        f"{fn}(ST_Y(ST_Centroid(geometry)), ST_X(ST_Centroid(geometry))) AS {_qi(p.column)} "
        f"FROM {_qi(input_view)}"
    )
    _create_view(conn, view_name, sql)


def execute_mgrs_to_lat_long(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformMgrsToLatLongParams.model_validate(params)
    have = _columns(conn, input_view)
    _need_columns("transform.mgrsToLatLong", have, p.column)
    lat = _udf(conn, view_name, "mgrslat", lambda r: _from_mgrs(r, 0), ["VARCHAR"], "DOUBLE")
    lon = _udf(conn, view_name, "mgrslon", lambda r: _from_mgrs(r, 1), ["VARCHAR"], "DOUBLE")
    col = _qi(p.column)
    geom = f"ST_Point({lon}(CAST({col} AS VARCHAR)), {lat}(CAST({col} AS VARCHAR)))"
    head = "SELECT * EXCLUDE (geometry), " if "geometry" in have else "SELECT *, "
    _create_view(conn, view_name, f"{head}{geom} AS geometry FROM {_qi(input_view)}")


def _srid_4326(params: dict, *, op: str, input_srid: int, join_srid: int | None = None) -> int:
    return 4326


# --------------------------------------------------------------------------- texte


def _text_codec(name: str) -> str:
    try:
        info = codecs.lookup(name)
    except LookupError as exc:
        raise ValueError(f"encodage inconnu : {name!r}") from exc
    if not getattr(info, "_is_text_encoding", True):  # exclut hex, base64, rot13, zlib…
        raise ValueError(f"{name!r} n'est pas un jeu de caractères")
    return info.name


class TransformTextEncoderParams(BaseModel):
    """Encode la colonne texte `column` vers le jeu de caractères `encoding` (latin-1,
    utf-16, cp1252, …) dans la colonne binaire `outputColumn`. Un caractère non
    représentable donne NULL (`errors="strict"`) ou `?` (`"replace"`) ; NULL reste NULL."""

    column: str
    encoding: str
    outputColumn: str
    errors: Literal["strict", "replace"] = "strict"

    @model_validator(mode="after")
    def _codec(self) -> "TransformTextEncoderParams":
        self.encoding = _text_codec(self.encoding)
        return self


class TransformTextDecoderParams(BaseModel):
    """Décode la colonne binaire `column` depuis le jeu de caractères `encoding` vers du
    texte UTF-8 dans `outputColumn`. Un octet invalide donne NULL (`errors="strict"`) ou le
    caractère de remplacement (`"replace"`) ; NULL reste NULL."""

    column: str
    encoding: str
    outputColumn: str
    errors: Literal["strict", "replace"] = "strict"

    @model_validator(mode="after")
    def _codec(self) -> "TransformTextDecoderParams":
        self.encoding = _text_codec(self.encoding)
        return self


def _with_column(conn, input_view: str, out: str, expr: str) -> str:
    head = f"SELECT * EXCLUDE ({_qi(out)}), " if out in _columns(conn, input_view) else "SELECT *, "
    return f"{head}{expr} AS {_qi(out)} FROM {_qi(input_view)}"


def execute_text_encoder(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformTextEncoderParams.model_validate(params)
    _need_columns("transform.textEncoder", _columns(conn, input_view), p.column)
    enc, err = p.encoding, ("replace" if p.errors == "replace" else "strict")

    def f(s: str):
        try:
            return s[:_MAX_CELL].encode(enc, err)
        except (UnicodeError, LookupError):
            return None

    fn = _udf(conn, view_name, "enc", f, ["VARCHAR"], "BLOB")
    _create_view(
        conn,
        view_name,
        _with_column(conn, input_view, p.outputColumn, f"{fn}(CAST({_qi(p.column)} AS VARCHAR))"),
    )


def execute_text_decoder(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformTextDecoderParams.model_validate(params)
    _need_columns("transform.textDecoder", _columns(conn, input_view), p.column)
    enc, err = p.encoding, ("replace" if p.errors == "replace" else "strict")

    def f(b: bytes):
        try:
            return bytes(b)[:_MAX_CELL].decode(enc, err)
        except (UnicodeError, LookupError):
            return None

    fn = _udf(conn, view_name, "dec", f, ["BLOB"], "VARCHAR")
    _create_view(
        conn,
        view_name,
        _with_column(conn, input_view, p.outputColumn, f"{fn}(CAST({_qi(p.column)} AS BLOB))"),
    )


# --------------------------------------------------------------------------- HTMLExtractor

_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "wbr",
}


class TransformHtmlExtractorParams(BaseModel):
    """Extrait d'un contenu HTML (colonne `column`) : `text` = tout le texte visible ;
    `elementText` = le texte de chaque élément `tag` (filtrable par `className`) ;
    `attribute` = la valeur de `attribute` sur chaque élément `tag` (ex. a/href, img/src).
    Les résultats multiples sont joints par `separator`. Analyse tolérante (parseur HTML de
    la bibliothèque standard), sans sélecteurs CSS ni exécution de script."""

    column: str
    outputColumn: str
    mode: Literal["text", "elementText", "attribute"] = "text"
    tag: str | None = Field(None, pattern=r"^[A-Za-z][A-Za-z0-9]*$")
    attribute: str | None = Field(None, pattern=r"^[A-Za-z_:][-A-Za-z0-9_:.]*$")
    className: str | None = None
    separator: str = Field("\n", max_length=10)

    @model_validator(mode="after")
    def _needs(self) -> "TransformHtmlExtractorParams":
        if self.mode != "text" and not self.tag:
            raise ValueError("tag est requis pour elementText et attribute")
        if self.mode == "attribute" and not self.attribute:
            raise ValueError("attribute est requis pour le mode attribute")
        return self


class _Extractor(html.parser.HTMLParser):
    def __init__(self, p: TransformHtmlExtractorParams) -> None:
        super().__init__(convert_charrefs=True)
        self.p, self.out = p, []
        self.skip = 0  # profondeur script/style
        self.open: list[list[str]] = []  # éléments `tag` ouverts : fragments de texte

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if self.p.mode == "text" or tag != (self.p.tag or "").lower():
            return
        a = dict(attrs)
        if self.p.mode == "attribute":
            if a.get(self.p.attribute) is not None:
                self.out.append(a[self.p.attribute])
        elif tag not in _VOID and (
            not self.p.className or self.p.className in (a.get("class") or "").split()
        ):
            self.open.append([])

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if self.p.mode == "elementText" and tag == (self.p.tag or "").lower() and self.open:
            self.out.append(" ".join("".join(self.open.pop()).split()))

    def handle_data(self, data):
        if self.skip:
            return
        if self.p.mode == "text":
            self.out.append(data)
        for frag in self.open:
            frag.append(data)

    def close(self):
        super().close()
        while self.open:  # élément jamais refermé : on garde ce qu'il contient
            self.out.append(" ".join("".join(self.open.pop()).split()))


def _extract_html(s: str, p: TransformHtmlExtractorParams):
    x = _Extractor(p)
    try:
        x.feed(s[:_MAX_CELL])
        x.close()
    except Exception:  # noqa: BLE001 — HTML pathologique -> NULL par ligne
        return None
    if p.mode == "text":
        return " ".join(" ".join(x.out).split())
    return p.separator.join(t for t in x.out if t)


def execute_html_extractor(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformHtmlExtractorParams.model_validate(params)
    _need_columns("transform.htmlExtractor", _columns(conn, input_view), p.column)
    fn = _udf(conn, view_name, "html", lambda s: _extract_html(s, p), ["VARCHAR"], "VARCHAR")
    _create_view(
        conn,
        view_name,
        _with_column(conn, input_view, p.outputColumn, f"{fn}(CAST({_qi(p.column)} AS VARCHAR))"),
    )


# --------------------------------------------------------------------------- Terminator


class TransformTerminatorParams(BaseModel):
    """Arrête le run en erreur dès qu'une ligne satisfait la condition SQL `condition`
    (la ligne « invalide »), avec `message` ; sinon le flux passe tel quel. Pour router les
    lignes invalides sans interrompre l'exécution, utiliser `transform.testFilter`."""

    condition: str
    message: str = Field("Ligne invalide détectée", min_length=1, max_length=300)


def execute_terminator(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformTerminatorParams.model_validate(params)
    validate_bounded_expr(conn, p.condition)
    n = conn.execute(
        f"SELECT count(*) FROM {_qi(input_view)} WHERE coalesce(({p.condition}), false)"
    ).fetchone()[0]
    if n:
        raise PipelineRuntimeError(f"{p.message} ({n} ligne(s) concernée(s))")
    _create_view(conn, view_name, f"SELECT * FROM {_qi(input_view)}")


# --------------------------------------------------------------------------- contrats


def _c(op, schema, **kw) -> OperationContract:
    return OperationContract(
        op=f"transform.{op}",
        kind="transform",
        params_schema=schema,
        engine=kw.pop("engine", "duckdb"),
        engine_license=kw.pop("engine_license", _DUCKDB),
        **kw,
    )


CONTRACTS.extend(
    [
        _c("attributeManager", TransformAttributeManagerParams, execute=execute_attribute_manager),
        _c("aggregateFilter", TransformAggregateFilterParams, execute=execute_aggregate_filter),
        _c("matcher", TransformMatcherParams, compile=compile_matcher),
        _c("geometryFilter", TransformGeometryFilterParams, compile=compile_geometry_filter),
        _c(
            "attributeRangeFilter",
            TransformAttributeRangeFilterParams,
            compile=compile_attribute_range_filter,
        ),
        _c(
            "planarityFilter",
            TransformPlanarityFilterParams,
            engine="python",
            engine_license="BSD-3-Clause (Shapely) / BSD-3-Clause (NumPy)",
            execute=execute_planarity_filter,
        ),
        _c(
            "spatialRelator",
            TransformSpatialRelatorParams,
            accepts_secondary_input=True,
            compile=compile_spatial_relator,
            output_srid=_output_srid_reconcile_join,
        ),
        _c(
            "featureTypeFilter",
            TransformFeatureTypeFilterParams,
            compile=compile_feature_type_filter,
        ),
        _c(
            "latLongToMgrs",
            TransformLatLongToMgrsParams,
            engine="python",
            engine_license="MIT (mgrs)",
            execute=execute_lat_long_to_mgrs,
            needs_runtime_context=True,
        ),
        _c(
            "mgrsToLatLong",
            TransformMgrsToLatLongParams,
            engine="python",
            engine_license="MIT (mgrs)",
            execute=execute_mgrs_to_lat_long,
            output_srid=_srid_4326,
        ),
        _c(
            "textEncoder",
            TransformTextEncoderParams,
            engine="python",
            engine_license="PSF-2.0 (Python codecs)",
            execute=execute_text_encoder,
        ),
        _c(
            "textDecoder",
            TransformTextDecoderParams,
            engine="python",
            engine_license="PSF-2.0 (Python codecs)",
            execute=execute_text_decoder,
        ),
        _c(
            "htmlExtractor",
            TransformHtmlExtractorParams,
            engine="python",
            engine_license="PSF-2.0 (Python html.parser)",
            execute=execute_html_extractor,
        ),
        _c("terminator", TransformTerminatorParams, execute=execute_terminator),
    ]
)
