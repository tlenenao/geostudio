# SPDX-License-Identifier: Apache-2.0
"""AUD-131 / D7 : rafraîchissement planifié d'une source, borné à [5 s, 1 h]."""

import pytest
from pydantic import ValidationError

from app.configs.schemas import DataSource


def _source(**extra):
    return DataSource(id="d1", type="features", service="core", layer="c", **extra)


def test_refresh_seconds_is_optional_and_round_trips():
    assert _source().refreshSeconds is None
    assert _source(refreshSeconds=30).model_dump()["refreshSeconds"] == 30


@pytest.mark.parametrize("value", [0, 4, 3601, -1])
def test_refresh_seconds_is_bounded(value):
    with pytest.raises(ValidationError):
        _source(refreshSeconds=value)
