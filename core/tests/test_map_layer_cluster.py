# SPDX-License-Identifier: Apache-2.0
"""ARC-01 : `MapLayer.cluster` est accepté en écriture (sinon 422, REV-356)."""

import pytest
from pydantic import ValidationError

from app.configs.schemas import MapLayer


def _layer(**extra):
    return {"id": "l", "title": "t", "kind": "feature", "url": "u", **extra}


def test_maplayer_accepts_cluster():
    layer = MapLayer.model_validate(_layer(cluster={"radius": 60, "maxZoom": 12, "label": True}))
    assert layer.cluster is not None
    assert layer.model_dump(exclude_none=True)["cluster"] == {
        "radius": 60,
        "maxZoom": 12,
        "label": True,
    }


def test_maplayer_cluster_all_optional():
    assert MapLayer.model_validate(_layer(cluster={})).cluster is not None


def test_maplayer_cluster_rejects_unknown_key():
    with pytest.raises(ValidationError):
        MapLayer.model_validate(_layer(cluster={"radius": 50, "bogus": 1}))
