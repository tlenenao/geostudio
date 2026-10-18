# SPDX-License-Identifier: Apache-2.0
"""Module de voie « qualité » (SP-L5, AUD-079/021) : validation/réparation de géométrie,
mesures planes ou géodésiques, jointure spatiale avec report d'attributs.

Agrégé par app.pipelines.ops.contracts.LANE_MODULES ; ne jamais importer contracts/runtime/
registries au niveau module (cycle d'import)."""

from collections.abc import Callable
from typing import Literal

import shapely.wkb
from pydantic import BaseModel, Field, model_validator
from shapely.validation import explain_validity

from app.pipelines.compiler import _output_srid_reconcile_join
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.attrs import _columns, _create_view, _no_clash, _udf
from app.pipelines.ops.operation_contract import OperationContract, OutputColumn
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_DUCKDB = "MIT (DuckDB)"
_RID = '"__gs_rid"'


# --------------------------------------------------------------------------- validateGeometry


class TransformValidateGeometryParams(BaseModel):
    """Contrôle OGC de chaque géométrie. `flag` : ajoute `validColumn` (booléen, NULL si
    géométrie absente) et, si `reasonColumn` est renseigné, la raison de l'invalidité.
    `repair` : remplace aussi la géométrie par `ST_MakeValid` (le drapeau décrit l'état
    AVANT réparation)."""

    mode: Literal["flag", "repair"] = "flag"
    validColumn: OutputColumn = "geometry_valid"
    reasonColumn: OutputColumn | None = None


def execute_validate_geometry(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformValidateGeometryParams.model_validate(params)
    have = _columns(conn, input_view)
    extra = [p.reasonColumn] if p.reasonColumn else []
    _no_clash("transform.validateGeometry", have, p.validColumn, *extra)
    sel = [f"ST_IsValid(geometry) AS {_qi(p.validColumn)}"]
    if p.reasonColumn:
        fn = _udf(
            conn,
            view_name,
            "why",
            lambda wkb: (
                None
                if (r := explain_validity(shapely.wkb.loads(bytes(wkb)))) == "Valid Geometry"
                else r
            ),
            ["BLOB"],
            "VARCHAR",
        )
        sel.append(f"{fn}(ST_AsWKB(geometry)) AS {_qi(p.reasonColumn)}")
    geom = "ST_MakeValid(geometry)" if p.mode == "repair" else "geometry"
    _create_view(
        conn,
        view_name,
        f"SELECT * EXCLUDE (geometry), {geom} AS geometry, {', '.join(sel)} FROM {_qi(input_view)}",
    )


# --------------------------------------------------------------------------- measure


class TransformMeasureParams(BaseModel):
    """Ajoute une mesure par géométrie. `planar` : unités du SCR (mètres pour un SCR
    projeté métrique). `geodesic` : mètres / m² sur l'ellipsoïde WGS84, quel que soit le
    SCR d'entrée (reprojection interne en EPSG:4326)."""

    measure: Literal["area", "length", "perimeter"]
    method: Literal["planar", "geodesic"] = "geodesic"
    column: OutputColumn


_PLANAR = {"area": "ST_Area", "length": "ST_Length", "perimeter": "ST_Perimeter"}
_SPHEROID = {
    "area": "ST_Area_Spheroid",
    "length": "ST_Length_Spheroid",
    "perimeter": "ST_Perimeter_Spheroid",
}


def execute_measure(
    conn, *, input_view: str, view_name: str, params: dict, input_srid: int | None = None, **_
) -> None:
    p = TransformMeasureParams.model_validate(params)
    _no_clash("transform.measure", _columns(conn, input_view), p.column)
    if p.method == "planar":
        expr = f"{_PLANAR[p.measure]}(geometry)"
    else:
        if not input_srid:
            raise PipelineRuntimeError(
                "transform.measure : SRID d'entrée inconnu — utiliser transform.setSrid"
            )
        g = "geometry"
        if input_srid != 4326:
            g = f"ST_Transform(geometry, 'EPSG:{input_srid}', 'EPSG:4326', true)"
        # *_Spheroid attend (lat, lon) : ST_FlipCoordinates (vérifié DuckDB 1.5.5).
        expr = f"{_SPHEROID[p.measure]}(ST_FlipCoordinates({g}))"
    _create_view(conn, view_name, f"SELECT *, {expr} AS {_qi(p.column)} FROM {_qi(input_view)}")


# --------------------------------------------------------------------------- spatialJoin


class TransformSpatialJoinParams(BaseModel):
    """Jointure spatiale avec report des attributs de la seconde entrée, préfixés par
    `prefix`. `match` : `all` (une ligne par correspondance), `first` (une seule, arbitraire
    mais stable), `largestOverlap` (celle de plus grande surface d'intersection — polygones).
    `how=left` garde les lignes sans correspondance (attributs NULL). La géométrie de sortie
    est celle de l'entrée principale, ou l'intersection."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    predicate: Literal["intersects", "within", "contains", "dwithin"] = "intersects"
    distance: float | None = Field(None, gt=0)
    how: Literal["inner", "left"] = "left"
    match: Literal["all", "first", "largestOverlap"] = "first"
    prefix: str = Field("join_", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")
    outputGeometry: Literal["left", "intersection"] = "left"

    @model_validator(mode="after")
    def _distance_for_dwithin(self) -> "TransformSpatialJoinParams":
        if (self.predicate == "dwithin") != (self.distance is not None):
            raise ValueError("distance est requis pour dwithin, et seulement pour lui")
        return self


def compile_spatial_join(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformSpatialJoinParams.model_validate(params)
    assert join_view is not None, "transform.spatialJoin requires join_view"
    right = [c for c in (join_columns or []) if c != "geometry"]
    out = [f"{p.prefix}{c}" for c in right]
    _no_clash("transform.spatialJoin", input_columns or [], *out, _RID.strip('"'))
    pred = {
        "intersects": "ST_Intersects(t.geometry, o.geometry)",
        "within": "ST_Within(t.geometry, o.geometry)",
        "contains": "ST_Contains(t.geometry, o.geometry)",
        "dwithin": f"ST_DWithin(t.geometry, o.geometry, {p.distance})",
    }[p.predicate]
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    right_sel = "".join(f", o.{_qi(c)} AS {_qi(n)}" for c, n in zip(right, out, strict=True))
    geom = (
        "t.geometry"
        if p.outputGeometry == "left"
        else (
            "coalesce(ST_Intersection(ST_MakeValid(t.geometry), ST_MakeValid(o.geometry)), "
            "t.geometry)"
        )
    )
    # Surface d'intersection calculée seulement quand elle départage (largestOverlap).
    overlap = (
        "ST_Area(ST_Intersection(ST_MakeValid(t.geometry), ST_MakeValid(o.geometry)))"
        if p.match == "largestOverlap"
        else "NULL::DOUBLE"
    )
    base = (
        f"SELECT t.* EXCLUDE (geometry), {geom} AS geometry{right_sel}, t.{_RID} AS {_RID}, "
        f"{overlap} AS __gs_overlap "
        f"FROM (SELECT *, row_number() OVER () AS {_RID} FROM {_qi(input_view)}) t "
        f"{join_kw} {_qi(join_view)} o ON {pred}"
    )
    if p.match == "all":
        return f"SELECT * EXCLUDE ({_RID}, __gs_overlap) FROM ({base})"
    order = "__gs_overlap DESC NULLS LAST" if p.match == "largestOverlap" else "1"
    return (
        f"SELECT * EXCLUDE ({_RID}, __gs_overlap) FROM ({base}) "
        f"QUALIFY row_number() OVER (PARTITION BY {_RID} ORDER BY {order}) = 1"
    )


def _c(op, schema, **kw) -> OperationContract:
    return OperationContract(
        op=f"transform.{op}",
        kind="transform",
        params_schema=schema,
        engine="duckdb",
        engine_license=_DUCKDB,
        **kw,
    )


CONTRACTS.extend(
    [
        _c(
            "validateGeometry",
            TransformValidateGeometryParams,
            execute=execute_validate_geometry,
        ),
        _c(
            "measure",
            TransformMeasureParams,
            execute=execute_measure,
            needs_runtime_context=True,
        ),
        _c(
            "spatialJoin",
            TransformSpatialJoinParams,
            accepts_secondary_input=True,
            needs_columns=True,
            compile=compile_spatial_join,
            output_srid=_output_srid_reconcile_join,
        ),
    ]
)
