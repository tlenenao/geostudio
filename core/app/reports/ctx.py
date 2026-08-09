# SPDX-License-Identifier: Apache-2.0
"""Reproduit octet pour octet shell/src/lib/analyticsContextUrl.ts::
encodeAnalyticsContext : base64url (RFC 4648 §5) de l'encodage JSON UTF-8 de
{timeRange, extent, crossFilter} — exactement les trois champs que
decodeAnalyticsContext d'AppRuntimePage relit depuis ?ctx=. Gardé dans son
propre petit module (pas inliné dans jobs.py) pour pouvoir le tester
unitairement contre le format de sérialisation exact de l'implémentation JS
sans avoir besoin d'un sweep en cours d'exécution."""
import base64
import json

from app.configs.schemas import BookmarkPayload


def encode_analytics_context(bookmark: BookmarkPayload) -> str:
    state = {
        "timeRange": bookmark.timeRange.model_dump(by_alias=True) if bookmark.timeRange else None,
        "extent": list(bookmark.extent) if bookmark.extent else None,
        # by_alias=True requis : BookmarkCrossFilterEntry.value peut nester une BookmarkTimeRange,
        # dont le champ Python from_ est aliasé vers la clé JSON "from". Sans by_alias=True,
        # la clé sortirait en "from_", cassant la compatibilité de format avec le décodeur JS du shell.
        "crossFilter": {key: entry.model_dump(by_alias=True) for key, entry in bookmark.crossFilter.items()},
    }
    json_bytes = json.dumps(state).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")
