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
