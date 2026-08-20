# SPDX-License-Identifier: Apache-2.0
import base64
import json

from app.configs.schemas import BookmarkPayload
from app.reports.ctx import encode_analytics_context


def _decode(raw: str) -> dict:
    # Mirrors shell/src/lib/analyticsContextUrl.ts::decodeAnalyticsContext's
    # base64url handling exactly (- -> +, _ -> /, re-pad to a multiple of 4).
    padded = raw.replace("-", "+").replace("_", "/")
    padded += "=" * ((4 - len(padded) % 4) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


def test_encode_round_trips_full_context():
    bookmark = BookmarkPayload.model_validate(
        {
            "appId": "app-1",
            "pageId": "page-1",
            "timeRange": {"from": "2026-01-01", "to": "2026-12-31"},
            "extent": [1.0, 2.0, 3.0, 4.0],
            "crossFilter": {
                "dataset-1": {
                    "field": "score",
                    "value": {"from": "10", "to": "90"},
                    "originSourceId": "src-1",
                },
            },
        }
    )

    encoded = encode_analytics_context(bookmark)
    decoded = _decode(encoded)

    assert decoded["timeRange"] == {"from": "2026-01-01", "to": "2026-12-31"}
    assert decoded["extent"] == [1.0, 2.0, 3.0, 4.0]
    assert decoded["crossFilter"] == {
        "dataset-1": {
            "field": "score",
            "value": {"from": "10", "to": "90"},
            "originSourceId": "src-1",
        },
    }


def test_encode_handles_empty_context():
    bookmark = BookmarkPayload.model_validate({"appId": "app-1", "pageId": "page-1"})

    decoded = _decode(encode_analytics_context(bookmark))

    assert decoded == {"timeRange": None, "extent": None, "crossFilter": {}}


def test_encode_is_url_safe():
    bookmark = BookmarkPayload.model_validate(
        {
            "appId": "app-1",
            "pageId": "page-1",
            "crossFilter": {
                "f": {"field": "libellé", "value": ["a", "b", "c???/+++"], "originSourceId": "s"}
            },
        }
    )

    encoded = encode_analytics_context(bookmark)

    assert "+" not in encoded
    assert "/" not in encoded
    assert "=" not in encoded
