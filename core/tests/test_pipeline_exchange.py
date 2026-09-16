# SPDX-License-Identifier: Apache-2.0
import json

import geopandas as gpd
import pyarrow
import pytest
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_spatial_connection
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.exchange import from_arrow_stream, to_arrow_stream, to_geoparquet_file


def test_to_arrow_stream_embeds_projjson_crs_metadata():
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, ST_Point(700000, 6600000) AS geom")
    reader = to_arrow_stream(rel, srid=2154)
    table = reader.read_all()
    field = table.schema.field("geom")
    assert field.metadata[b"ARROW:extension:name"] == b"geoarrow.wkb"
    crs_meta = json.loads(field.metadata[b"ARROW:extension:metadata"])
    assert crs_meta["crs"]["id"] == {"authority": "EPSG", "code": 2154}


def test_to_arrow_stream_raises_on_relation_without_geometry_column():
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, 'a' AS name")
    with pytest.raises(PipelineRuntimeError, match="aucune colonne géométrie"):
        to_arrow_stream(rel, srid=4326)


def test_to_geoparquet_file_raises_on_relation_without_geometry_column(tmp_path):
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, 'a' AS name")
    with pytest.raises(PipelineRuntimeError, match="aucune colonne géométrie"):
        to_geoparquet_file(rel, srid=4326, path=str(tmp_path / "x.parquet"))


def test_arrow_round_trip_preserves_schema_crs_and_values():
    source_conn = open_spatial_connection()
    rel = source_conn.sql(
        "SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name "
        "UNION ALL SELECT 2, ST_Point(700100, 6600100), 'b'"
    )
    reader = to_arrow_stream(rel, srid=2154)

    target_conn = open_spatial_connection()
    from_arrow_stream(target_conn, reader, view_name="rt")

    rows = target_conn.sql("SELECT id, ST_AsText(geom) AS wkt, name FROM rt ORDER BY id").fetchall()
    assert rows == [
        (1, "POINT (700000 6600000)", "a"),
        (2, "POINT (700100 6600100)", "b"),
    ]
    desc = {d[0]: d[1] for d in target_conn.sql("SELECT * FROM rt LIMIT 0").description}
    assert str(desc["geom"]) == "GEOMETRY('EPSG:2154')"


def test_geoparquet_file_round_trip_preserves_schema_crs_and_values(tmp_path):
    conn = open_spatial_connection()
    rel = conn.sql(
        "SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name "
        "UNION ALL SELECT 2, ST_Point(700100, 6600100), 'b'"
    )
    path = str(tmp_path / "roundtrip.parquet")
    to_geoparquet_file(rel, srid=2154, path=path)

    gdf = gpd.read_parquet(path)
    assert list(gdf["id"]) == [1, 2]
    assert list(gdf["name"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 2154
    assert gdf.geometry.iloc[0].equals(Point(700000, 6600000))
    assert gdf.geometry.iloc[1].equals(Point(700100, 6600100))


def test_from_arrow_stream_unregisters_its_internal_arrow_source():
    # from_arrow_stream doit unregister son nom temporaire interne même en
    # cas de succès — sinon un register() ultérieur sur ce même nom
    # échouerait en "already registered". Important : la relation source et
    # from_arrow_stream() utilisent ici DEUX connexions distinctes
    # (other_conn / conn) — jamais la même (cf. plan, section "Risque
    # supplémentaire trouvé en vérifiant" : réutiliser la même connexion
    # pour la relation source ET l'appel from_arrow_stream deadlocke
    # conn.execute(), vérifié empiriquement).
    conn = open_spatial_connection()
    other_conn = open_spatial_connection()
    rel = other_conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    reader = to_arrow_stream(rel, srid=4326)
    from_arrow_stream(conn, reader, view_name="rt1")
    assert conn.sql("SELECT id FROM rt1").fetchone() == (1,)

    conn.register("__exchange_arrow_src_rt1", pyarrow.table({"x": [1]}))
    conn.unregister("__exchange_arrow_src_rt1")
