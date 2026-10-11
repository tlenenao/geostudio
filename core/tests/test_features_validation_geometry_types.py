# SPDX-License-Identifier: Apache-2.0
"""REV-352 : règle de compatibilité de type de géométrie."""

import pytest

from app.features.validation import geometry_type_accepted

POLY = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
MPOLY1 = {"type": "MultiPolygon", "coordinates": [POLY["coordinates"]]}
MPOLY2 = {"type": "MultiPolygon", "coordinates": [POLY["coordinates"], POLY["coordinates"]]}
PT = {"type": "Point", "coordinates": [0, 0]}


@pytest.mark.parametrize(
    ("layer", "geom", "ok"),
    [
        ("GEOMETRY", PT, True),
        ("GEOMETRY", MPOLY2, True),
        ("MultiPolygon", POLY, True),
        ("MultiPolygon", MPOLY2, True),
        ("Polygon", MPOLY1, True),
        ("Polygon", MPOLY2, False),  # perte d'information : refusé
        ("Polygon", PT, False),
        ("MultiPolygon", PT, False),
        ("Point", POLY, False),
    ],
)
def test_geometry_type_accepted(layer, geom, ok):
    assert geometry_type_accepted(layer, geom) is ok
