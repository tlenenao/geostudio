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
from shapely.geometry import MultiPoint


def _qi(name: str) -> str:
    # Duplication délibérée (patron déjà établi par compiler.py/runtime.py) — helper de 2
    # lignes, pas un import inter-module d'un nom `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


def _read_geometry_rows(conn, input_view: str) -> pd.DataFrame:
    """Lit toutes les colonnes de `input_view`, la géométrie sérialisée en WKB (bytearray,
    consommable par shapely.wkb.loads)."""
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    select_list = ", ".join(
        f"ST_AsWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    return conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}").fetchdf()


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


def _execute_triangulate(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformTriangulateParams

    TransformTriangulateParams.model_validate(params)  # forme seulement, aucun champ
    df = _read_geometry_rows(conn, input_view)
    points = [shapely.wkb.loads(bytes(wkb)) for wkb in df["geometry"]]
    triangles = shapely.ops.triangulate(MultiPoint([p.coords[0] for p in points]))
    other_cols = [c for c in df.columns if c != "geometry"]
    out = pd.DataFrame(
        {
            **{c: [df[c].iloc[0]] * len(triangles) for c in other_cols},
            "geometry": [shapely.wkb.dumps(t) for t in triangles],
        }
    )
    _write_geometry_rows(conn, out, view_name=view_name)


def _execute_densify(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformDensifyParams

    p = TransformDensifyParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    df = df.assign(
        geometry=[
            shapely.wkb.dumps(shapely.segmentize(shapely.wkb.loads(bytes(g)), p.maxSegmentLength))
            for g in df["geometry"]
        ]
    )
    _write_geometry_rows(conn, df, view_name=view_name)
