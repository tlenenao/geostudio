# SPDX-License-Identifier: Apache-2.0
"""AUD-060 : la géométrie du cross-filter spatial survit à l'enregistrement du signet."""

import base64
import json

import pytest
from pydantic import ValidationError

from app.configs.schemas import BookmarkPayload
from app.reports.ctx import encode_analytics_context

_POLY = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


def _payload(entries: dict) -> BookmarkPayload:
    return BookmarkPayload.model_validate({"appId": "a", "pageId": "p", "crossFilter": entries})


def _entry(**extra) -> dict:
    return {"field": "g", "value": "x", "originSourceId": "s", **extra}


def test_bookmark_keeps_the_spatial_cross_filter_geometry():
    bookmark = _payload({"d1": _entry(geometry=_POLY)})
    assert bookmark.crossFilter["d1"].geometry == _POLY
    assert bookmark.model_dump()["crossFilter"]["d1"]["geometry"] == _POLY


def test_bookmark_rejects_an_oversized_geometry():
    huge = {"type": "LineString", "coordinates": [[0.123456, 0.654321]] * 10_000}
    with pytest.raises(ValidationError, match="too large"):
        _payload({"d1": _entry(geometry=huge)})


def test_scheduled_report_context_carries_the_geometry_but_omits_an_absent_one():
    encoded = encode_analytics_context(_payload({"d1": _entry(geometry=_POLY), "d2": _entry()}))
    decoded = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert decoded["crossFilter"]["d1"]["geometry"] == _POLY
    assert "geometry" not in decoded["crossFilter"]["d2"]
