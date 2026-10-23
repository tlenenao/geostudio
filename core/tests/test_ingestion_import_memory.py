# SPDX-License-Identifier: Apache-2.0
"""AUD-014 : l'import ne matérialise plus le fichier (json.loads + deux listes complètes
+ liste de paramètres : pic mesuré 2,9 Go pour 281 Mo)."""

import json
import tracemalloc

from app.ingestion.importer import _CsvKinds, _open_rows


def test_geojson_import_streams_instead_of_materializing_the_file():
    features = [
        {
            "type": "Feature",
            "properties": {"nom": f"n{i}", "pop": i, "note": "x" * 20},
            "geometry": {"type": "Point", "coordinates": [2.0 + i * 1e-6, 48.0]},
        }
        for i in range(50_000)
    ]
    content = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    del features
    tracemalloc.start()
    try:
        scan, typed_rows = _open_rows(
            "big.geojson",
            content,
            lat_field=None,
            lon_field=None,
            layer_name=None,
            wkt_field=None,
            geometry_mode=None,
        )
        n = sum(1 for _ in typed_rows())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert scan.count == n == 50_000
    assert scan.columns == {"nom": "text", "pop": "bigint", "note": "text"}
    assert peak < 3 * len(content), f"pic {peak} o pour un fichier de {len(content)} o"


def test_ogr_and_geoparquet_read_by_windows(tmp_path, monkeypatch):
    """AUD-014 : OGR et GeoParquet lus par fenêtres ; l'ordre et les numéros d'entité tiennent
    d'une fenêtre à l'autre (fenêtre = 2 lignes, 5 entités : 2+2+1)."""
    import geopandas as gpd
    import shapely

    from app.ingestion import parsers

    monkeypatch.setattr(parsers, "_BATCH_ROWS", 2)
    gdf = gpd.GeoDataFrame(
        {"n": [0, 1, 2, 3, 4]},
        geometry=shapely.points([(i, 1.0) for i in range(5)]),
        crs="EPSG:4326",
    )
    gpkg = tmp_path / "w.gpkg"
    gdf.to_file(gpkg, layer="l", driver="GPKG")
    gp = tmp_path / "w.parquet"
    gdf.to_parquet(gp)
    for rows in (
        list(parsers.parse_gpkg(gpkg.read_bytes(), "l")),
        list(parsers.parse_geoparquet(gp.read_bytes())),
    ):
        assert [p["n"] for _g, p in rows] == [0, 1, 2, 3, 4]
        assert [g.x for g, _p in rows] == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_xml_generic_streams_the_same_records_as_the_dom(monkeypatch):
    """AUD-014 : le XML est lu en flux ; le parent retenu reste le premier du document en
    largeur d'abord, même quand un parent plus profond précède et que des frères sont ignorés."""
    from app.ingestion.parsers import GeometryMode, parse_xml_generic

    content = (
        b"<r><meta><k>1</k></meta><deep><x><i><a>9</a></i><i><a>8</a></i></x></deep>"
        b"<list><it id='1'><n>A</n><s><z>1</z></s></it><it id='2'><n>B</n></it>"
        b"<it id='3'><n>C</n></it></list></r>"
    )
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    # <deep> et <list> sont à la même profondeur ; <x> (profondeur 2) répète <i> mais <list>
    # (profondeur 1) répète <it> : le plus superficiel gagne, comme l'ancien BFS.
    assert [p["n"] for _g, p in rows] == ["A", "B", "C"]
    assert rows[0][1]["xml_id"] == "1"
    assert "z" not in rows[0][1]


def test_csv_kinds_tracks_each_column_in_one_pass():
    kinds = _CsvKinds(decimal_comma=True)
    for props in (
        {"a": "1", "b": "1,5", "c": "2026-01-02", "d": "x", "e": ""},
        {"a": " 2 ", "b": "2", "c": "2026-02-03", "d": "1", "e": None},
    ):
        kinds.add(props)
    assert kinds.kinds() == {"a": "int", "b": "float", "c": "date"}


def test_csv_column_order_matches_first_non_empty_value_of_typed_columns():
    """Ordre des colonnes identique à l'ancien calcul (après conversion des types CSV) :
    une colonne typée dont la 1re valeur est vide se place à sa 1re valeur non vide."""
    content = b"lat,lon,n,t\n1,2,,a\n3,4,5,b\n"
    scan, _rows = _open_rows(
        "x.csv",
        content,
        lat_field="lat",
        lon_field="lon",
        layer_name=None,
        wkt_field=None,
        geometry_mode=None,
    )
    assert list(scan.columns.items()) == [("t", "text"), ("n", "bigint")]
