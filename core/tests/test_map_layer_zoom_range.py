# SPDX-License-Identifier: Apache-2.0
"""AUD-051 : plage d'échelle par couche."""

import pytest
from pydantic import ValidationError

from app.configs.schemas import MapLayer


def _layer(**extra) -> dict:
    return {"id": "l", "title": "L", "kind": "vector", **extra}


def test_zoom_range_round_trips_and_is_optional():
    assert MapLayer.model_validate(_layer()).minZoom is None
    layer = MapLayer.model_validate(_layer(minZoom=6, maxZoom=12.5))
    assert (layer.minZoom, layer.maxZoom) == (6, 12.5)


@pytest.mark.parametrize(
    "extra", [{"minZoom": 12, "maxZoom": 6}, {"minZoom": -1}, {"maxZoom": 25}], ids=str
)
def test_invalid_zoom_range_is_rejected(extra):
    with pytest.raises(ValidationError):
        MapLayer.model_validate(_layer(**extra))


def test_layer_filter_round_trips_and_validates_value_shape():
    f = [{"field": "pop", "op": "gte", "value": 10}, {"field": "t", "op": "in", "value": ["a"]}]
    assert MapLayer.model_validate(_layer(filter=f)).model_dump()["filter"][1]["op"] == "in"
    for bad in ({"field": "t", "op": "in", "value": "a"}, {"field": "t", "op": "eq", "value": [1]}):
        with pytest.raises(ValidationError):
            MapLayer.model_validate(_layer(filter=[bad]))
