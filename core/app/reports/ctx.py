# SPDX-License-Identifier: Apache-2.0
"""Mirrors shell/src/lib/analyticsContextUrl.ts::encodeAnalyticsContext byte
for byte: base64url (RFC 4648 §5) of the UTF-8 JSON encoding of
{timeRange, extent, crossFilter} — the exact three fields AppRuntimePage's
decodeAnalyticsContext reads back out of ?ctx=. Kept as its own tiny module
(not inlined in jobs.py) so it can be unit-tested against the JS
implementation's exact wire format without needing a running sweep."""
import base64
import json

from app.configs.schemas import BookmarkPayload


def encode_analytics_context(bookmark: BookmarkPayload) -> str:
    state = {
        "timeRange": bookmark.timeRange.model_dump(by_alias=True) if bookmark.timeRange else None,
        "extent": list(bookmark.extent) if bookmark.extent else None,
        "crossFilter": {key: entry.model_dump(by_alias=True) for key, entry in bookmark.crossFilter.items()},
    }
    json_bytes = json.dumps(state).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")
