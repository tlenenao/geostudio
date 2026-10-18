# SPDX-License-Identifier: Apache-2.0
"""AUD-150 (d02 §11) : paramètres de terrain bornés à l'écriture."""

import pytest
from pydantic import ValidationError

from app.configs.schemas import MapTerrain

OK = "https://dem.example.com/{z}/{x}/{y}.png"


@pytest.mark.parametrize("value", [None, 0, 1.5, 20])
def test_exaggeration_in_range_is_accepted(value):
    assert MapTerrain(tilesUrl=OK, exaggeration=value).exaggeration == value


@pytest.mark.parametrize("value", [-5, 1e9, 20.01, float("nan"), float("inf")])
def test_exaggeration_out_of_range_is_refused(value):
    with pytest.raises(ValidationError):
        MapTerrain(tilesUrl=OK, exaggeration=value)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "data:text/png,x"])
def test_tiles_url_scheme_is_restricted(url):
    with pytest.raises(ValidationError):
        MapTerrain(tilesUrl=url)


@pytest.mark.parametrize(
    "url", [OK, "http://localhost:8200/v1/terrain3d/x/tiles/{z}/{x}/{y}.png", "/v1/t/{z}/{x}/{y}"]
)
def test_tiles_url_http_and_relative_are_accepted(url):
    assert MapTerrain(tilesUrl=url).tilesUrl == url
