# SPDX-License-Identifier: Apache-2.0
"""ETag par entité (ARC-04) : empreinte de la ligne sérialisée, pas de colonne de version
(aucune migration). L'empreinte porte sur la vue de l'appelant (colonnes masquées exclues,
géométrie découpée sous limite géographique) : c'est la même fonction côté GET et côté
écriture, donc un ETag lu est comparable à celui recalculé avant PUT/DELETE."""

import hashlib
import json


def feature_etag(feature: dict) -> str:
    body = {k: feature.get(k) for k in ("id", "geometry", "properties")}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return '"' + hashlib.sha256(raw.encode()).hexdigest()[:32] + '"'


def if_match_satisfied(if_match: str, etag: str) -> bool:
    """RFC 9110 §13.1.1 (comparaison forte) : `*` ou l'un des ETags listés."""
    tags = [t.strip() for t in if_match.split(",")]
    return "*" in tags or etag in tags
