# SPDX-License-Identifier: Apache-2.0
"""symbology (SP-25) round-trips through MapConfig exactly like paint/popup
(SP-24) — an untyped dict on MapLayer, same precedent."""

from app.configs.schemas import BuilderConfig

BASE = {
    "kind": "map",
    "map": {
        "basemap": {"style": "s"},
        "view": {"center": [2.0, 46.0], "zoom": 5},
        "layers": [],
    },
}


def _layer(**extra):
    payload = {
        **BASE,
        "map": {
            **BASE["map"],
            "layers": [
                {
                    "id": "l1",
                    "title": "Communes",
                    "visible": True,
                    "kind": "vector",
                    "tilesUrl": "http://core/collections/communes/tiles/{z}/{x}/{y}.mvt",
                    "sourceLayer": "communes",
                    **extra,
                }
            ],
        },
    }
    return BuilderConfig.model_validate(payload).map.layers[0]


def test_symbology_dict_round_trips():
    """Symbology is an untyped dict, same as paint — it round-trips through
    BuilderConfig without being stripped."""
    layer = _layer(
        symbology={
            "color": {
                "field": "population",
                "mode": "numeric",
                "classification": {"method": "quantile", "classes": 5},
                "palette": "sequential-blue",
                "domain": {"kind": "numeric-classed", "breaks": [0, 10, 20, 30, 40, 50]},
                "computedAt": "2026-08-23T00:00:00Z",
            }
        }
    )
    assert layer.symbology == {
        "color": {
            "field": "population",
            "mode": "numeric",
            "classification": {"method": "quantile", "classes": 5},
            "palette": "sequential-blue",
            "domain": {"kind": "numeric-classed", "breaks": [0, 10, 20, 30, 40, 50]},
            "computedAt": "2026-08-23T00:00:00Z",
        }
    }


def test_a_layer_without_symbology_stays_valid():
    """A layer without symbology is still valid."""
    assert _layer().symbology is None
