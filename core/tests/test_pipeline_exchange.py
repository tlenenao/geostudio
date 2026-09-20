# SPDX-License-Identifier: Apache-2.0
import json

import duckdb
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


def test_srid_is_coerced_to_int_before_sql_interpolation():
    # Revue finale de branche (Minor #2) : le module n'expose que
    # PipelineRuntimeError à ses appelants (cf. la conversion de
    # CatalogException plus bas) — _coerce_srid doit tenir la même
    # promesse pour un srid non convertible en int, pas laisser fuiter un
    # TypeError/ValueError brut.
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    with pytest.raises(PipelineRuntimeError):
        to_arrow_stream(rel, srid="abc")


def test_srid_zero_or_negative_is_rejected_consistently(tmp_path):
    # Vérifié empiriquement avant ce test : srid=0 produit "EPSG:0" (bidon)
    # sur le chemin Arrow mais crs=None sur le chemin GeoParquet (falsy
    # court-circuite `if srid` dans build_geodataframe_from_relation) ;
    # srid=-1 produit "EPSG:-1" (bidon) sur le chemin Arrow mais une
    # pyproj.exceptions.CRSError non contrôlée sur le chemin GeoParquet.
    # Les deux chemins doivent désormais lever la même PipelineRuntimeError.
    conn = open_spatial_connection()
    for bad_srid in (0, -1):
        rel = conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
        with pytest.raises(PipelineRuntimeError):
            to_arrow_stream(rel, srid=bad_srid)

        rel2 = conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
        with pytest.raises(PipelineRuntimeError):
            to_geoparquet_file(rel2, srid=bad_srid, path=str(tmp_path / f"x_{bad_srid}.parquet"))


class _ConnRaisingUnrelatedCatalogException:
    """Délègue à une vraie connexion DuckDB, sauf le CREATE TEMP TABLE de
    from_arrow_stream, où elle simule un CatalogException SANS RAPPORT avec
    une collision de nom (ex. fonction scalaire inconnue) — reproduit le
    message réel observé empiriquement ("Catalog Error: Scalar Function
    with name no_such_func does not exist!") sans dépendre d'un SELECT qui
    échouerait dès .arrow(), avant même d'atteindre from_arrow_stream."""

    def __init__(self, real_conn):
        self._real = real_conn

    def register(self, name, reader):
        return self._real.register(name, reader)

    def unregister(self, name):
        return self._real.unregister(name)

    def execute(self, sql, *args, **kwargs):
        if "CREATE TEMP TABLE" in sql:
            raise duckdb.CatalogException(
                "Catalog Error: Scalar Function with name no_such_func does not exist!"
            )
        return self._real.execute(sql, *args, **kwargs)


def test_from_arrow_stream_unrelated_catalog_exception_is_not_reported_as_name_collision():
    # Revue finale de branche (Minor #1) : le except duckdb.CatalogException
    # actuel réutilise le message "existe déjà" pour N'IMPORTE QUELLE
    # CatalogException (ex. une fonction/un type inconnu), pas seulement une
    # collision de nom — vérifié empiriquement (cf. docstring de
    # _ConnRaisingUnrelatedCatalogException) : ce message réel n'a rien à
    # voir avec un nom déjà pris.
    real_conn = open_spatial_connection()
    conn = _ConnRaisingUnrelatedCatalogException(real_conn)
    other_conn = open_spatial_connection()
    rel = other_conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    reader = to_arrow_stream(rel, srid=4326)
    with pytest.raises(PipelineRuntimeError) as excinfo:
        from_arrow_stream(conn, reader, view_name="whatever_never_used_before")
    assert "existe déjà" not in str(excinfo.value)


def test_view_name_collision_raises_pipeline_runtime_error():
    # Vérifié empiriquement avant ce test : un view_name déjà pris lève
    # aujourd'hui un duckdb.CatalogException brut ("Table with name ... already
    # exists!"), jamais une PipelineRuntimeError — incohérent avec le reste
    # du module, qui n'expose que PipelineRuntimeError à ses appelants.
    conn = open_spatial_connection()
    other_conn = open_spatial_connection()
    rel = other_conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    reader = to_arrow_stream(rel, srid=4326)
    from_arrow_stream(conn, reader, view_name="dup")

    rel2 = other_conn.sql("SELECT 2 AS id, ST_Point(3, 4) AS geom")
    reader2 = to_arrow_stream(rel2, srid=4326)
    with pytest.raises(PipelineRuntimeError):
        from_arrow_stream(conn, reader2, view_name="dup")
