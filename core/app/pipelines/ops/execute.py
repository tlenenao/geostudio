# SPDX-License-Identifier: Apache-2.0
"""Op de pipeline dont le résultat est calculé en Python (Shapely), pas en SQL — mécanisme
générique introduit pour retirer le sidecar QGIS (design docs/superpowers/specs/
2026-09-20-vague2-transformers-duckdb-design.md §7.2). Chaque fonction `_execute_xxx` a la
signature `(conn, *, input_view, view_name, params) -> None` : elle lit `input_view`, calcule
en process, matérialise `view_name` — même contrat de sortie qu'un nœud `compile` (une TEMP
TABLE/VIEW nommée `view_name`, lisible par le nœud suivant), `runtime.py` ne voit aucune
différence."""

import pandas as pd
import shapely.ops
import shapely.wkb
from shapely.geometry import GeometryCollection, MultiPoint

from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi


def _read_geometry_rows(conn, input_view: str) -> pd.DataFrame:
    """Lit toutes les colonnes de `input_view`, la géométrie sérialisée en WKB (bytearray,
    consommable par shapely.wkb.loads). Les lignes à géométrie NULL sont écartées en SQL
    (REV-196) : aucune op de ce module n'a de sens sur une géométrie absente, et un NULL
    ferait lever `TypeError` à `bytes(...)`."""
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"input has no 'geometry' column (columns: {cols})")
    select_list = ", ".join(
        f"ST_AsWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    return conn.execute(
        f"SELECT {select_list} FROM {_qi(input_view)} WHERE {_qi('geometry')} IS NOT NULL"
    ).fetchdf()


def _write_geometry_rows(conn, df: pd.DataFrame, *, view_name: str) -> None:
    """Matérialise `df` (colonne `geometry` en WKB shapely.wkb.dumps) en TEMP TABLE
    `view_name`."""
    conn.register("_execute_tmp_df", df)
    cols = list(df.columns)
    select_list = ", ".join(
        f"ST_GeomFromWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {select_list} FROM _execute_tmp_df")
    conn.unregister("_execute_tmp_df")


def _group_frames(df: pd.DataFrame, group_by: list[str]) -> list[pd.DataFrame]:
    """Découpe `df` en un sous-DataFrame par combinaison distincte des colonnes `group_by`
    (REV-195). `group_by` vide = un seul groupe (tout `df`) — le comportement global
    historique. NaN/NULL forme son propre groupe (`dropna=False`), l'ordre d'apparition est
    conservé (`sort=False`)."""
    if not group_by:
        return [df]
    if "geometry" in group_by:
        raise PipelineRuntimeError("groupBy cannot contain the 'geometry' column")
    missing = [c for c in group_by if c not in df.columns]
    if missing:
        raise PipelineRuntimeError(f"groupBy column(s) not found in input: {missing}")
    return [frame for _, frame in df.groupby(group_by, dropna=False, sort=False)]


def _apply_per_group(df: pd.DataFrame, group_by: list[str], one, columns: list[str]):
    """Applique `one(frame) -> DataFrame` à chaque groupe de `df` et concatène. Entrée vide
    (ou aucun groupe ne produisant de ligne) -> 0 ligne, colonnes `columns` typées comme
    en entrée (REV-196 : jamais de ligne fantôme ni d'IndexError)."""
    groups = _group_frames(df, group_by)  # valide groupBy même sur entrée vide
    frames = [one(f) for f in groups] if not df.empty else []
    out = pd.concat(frames, ignore_index=True) if frames else df[columns].iloc[0:0]
    return out if not out.empty else df[columns].iloc[0:0]


def _execute_triangulate(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformTriangulateParams

    p = TransformTriangulateParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    other_cols = [c for c in df.columns if c != "geometry"]

    def _one(frame: pd.DataFrame) -> pd.DataFrame:
        points = [shapely.wkb.loads(bytes(wkb)) for wkb in frame["geometry"]]
        bad = sorted({g.geom_type for g in points if g.geom_type != "Point"})
        if bad:
            raise PipelineRuntimeError(
                f"transform.triangulate expects Point geometries, got {', '.join(bad)}"
            )
        if any(g.is_empty for g in points):  # REV-300 M3 : `POINT EMPTY` n'a pas de coordonnée
            raise PipelineRuntimeError("transform.triangulate: empty Point geometry in input")
        triangles = shapely.ops.triangulate(MultiPoint([g.coords[0] for g in points]))
        return pd.DataFrame(
            {
                **{c: [frame[c].iloc[0]] * len(triangles) for c in other_cols},
                "geometry": [shapely.wkb.dumps(t) for t in triangles],
            }
        )

    out = _apply_per_group(df, p.groupBy, _one, list(df.columns))
    _write_geometry_rows(conn, out, view_name=view_name)


def _execute_densify(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformDensifyParams

    p = TransformDensifyParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    if not df.empty:  # `assign(geometry=[])` fabriquerait une colonne float64 illisible par DuckDB
        df = df.assign(
            geometry=[
                shapely.wkb.dumps(
                    shapely.segmentize(shapely.wkb.loads(bytes(g)), p.maxSegmentLength)
                )
                for g in df["geometry"]
            ]
        )
    _write_geometry_rows(conn, df, view_name=view_name)


def _execute_minimum_bounding_circle(
    conn, *, input_view: str, view_name: str, params: dict
) -> None:
    from app.pipelines.ops.schemas import TransformMinimumBoundingCircleParams

    p = TransformMinimumBoundingCircleParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    columns = [*p.groupBy, "geometry"]

    def _one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = [shapely.wkb.loads(bytes(g)) for g in frame["geometry"]]
        circle = shapely.minimum_bounding_circle(GeometryCollection(geoms))
        return pd.DataFrame(
            [{**{c: frame[c].iloc[0] for c in p.groupBy}, "geometry": shapely.wkb.dumps(circle)}]
        )

    out = _apply_per_group(df, p.groupBy, _one, columns)
    _write_geometry_rows(conn, out, view_name=view_name)
