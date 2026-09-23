# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.pipelines.ops.execute import _read_geometry_rows, _write_geometry_rows


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE base (id INTEGER, geometry GEOMETRY)")
    c.execute("INSERT INTO base VALUES (1, ST_Point(3.0, 45.0)), (2, ST_Point(3.001, 45.0))")
    return c


def test_read_write_geometry_rows_round_trips(conn):
    df = _read_geometry_rows(conn, "base")
    assert list(df.columns) == ["id", "geometry"]
    import shapely.wkb

    geom = shapely.wkb.loads(bytes(df["geometry"][0]))
    assert geom.wkt == "POINT (3 45)"

    _write_geometry_rows(conn, df, view_name="roundtrip")
    row = conn.execute("SELECT id, ST_AsText(geometry) FROM roundtrip WHERE id = 1").fetchone()
    assert row == (1, "POINT (3 45)")


def test_execute_triangulate_produces_one_row_per_triangle(conn):
    conn.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts VALUES "
        "(1, ST_Point(0, 0)), (2, ST_Point(4, 0)), (3, ST_Point(2, 4)), (4, ST_Point(1, 1))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts", view_name="out", params={})
    count = conn.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count >= 2  # au moins 2 triangles pour 4 points non colinéaires
    geom_types = conn.execute("SELECT DISTINCT ST_GeometryType(geometry) FROM out").fetchall()
    assert geom_types == [("POLYGON",)]


def test_execute_triangulate_merges_distinct_groups_into_one_global_cloud(conn):
    """Addition B (brief Task 24) : `input_view` porte ici DEUX nuages de points distincts
    (id=1 et id=2), tels qu'un utilisateur no-code pourrait vouloir en triangulant chacun
    séparément (ex. deux parcelles distinctes). L'implémentation actuelle de
    `_execute_triangulate` ne fait AUCUN group-by par colonne non-géométrique : elle construit
    un unique `MultiPoint` sur la totalité de `df["geometry"]` (ligne
    `MultiPoint([p.coords[0] for p in points])`), donc les deux nuages sont fusionnés en une
    seule triangulation de Delaunay globale — des triangles peuvent relier un point du groupe
    1 à un point du groupe 2. Ce n'est pas un crash ni un résultat incohérent (toujours des
    POLYGON valides, un nombre de triangles cohérent avec 6 points), mais ce n'est PAS un
    « triangulé par groupe » : c'est un comportement de v1 à trancher côté produit si le
    besoin réel est du group-by (cf. rapport de tâche — non résolu ici, brief ne demande pas
    de group-by)."""
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(1, 0)), (1, ST_Point(0, 1)), "
        "(2, ST_Point(100, 100)), (2, ST_Point(101, 100)), (2, ST_Point(100, 101))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts_grouped", view_name="out_grouped", params={})

    # Toutes les colonnes non-géométriques de sortie valent `id`=1 (df["id"].iloc[0]) : la
    # valeur du 2e groupe est perdue, confirmant qu'il n'y a pas de group-by.
    ids = conn.execute("SELECT DISTINCT id FROM out_grouped").fetchall()
    assert ids == [(1,)]

    # Le triangulé produit couvre les DEUX nuages : au moins un triangle a un sommet dans
    # chaque nuage (donc un bord "pont" traversant l'espace vide entre (0,0)-(1,0)-(0,1) et
    # (100,100)-(101,100)-(100,101)) — preuve directe de la fusion en un seul nuage global.
    bounds = conn.execute(
        "SELECT min(ST_XMin(geometry)), max(ST_XMax(geometry)) FROM out_grouped"
    ).fetchone()
    assert bounds[0] < 50 and bounds[1] > 50  # une géométrie de sortie s'étend sur les 2 nuages


def test_execute_densify_adds_vertices_every_max_segment_length(conn):
    conn.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO line VALUES (1, ST_GeomFromText('LINESTRING (0 0, 10 0)'))")
    from app.pipelines.ops.execute import _execute_densify

    _execute_densify(conn, input_view="line", view_name="out", params={"maxSegmentLength": 2})
    row = conn.execute("SELECT ST_NPoints(geometry) FROM out WHERE id = 1").fetchone()
    assert row == (6,)
