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
