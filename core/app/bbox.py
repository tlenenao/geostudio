# SPDX-License-Identifier: Apache-2.0
"""Parsing d'un paramètre `bbox` « minx,miny,maxx,maxy » (REV-367 f).

Module bas niveau, sans dépendance `app.*` (même statut que `app.sql_ident`) :
les routes REST, STAC, moissonnage, MCP et le mini-serveur d'export autoporté
le partagent, chacun gardant son propre canal d'erreur (il convertit la
`ValueError`). Sans ce garde, NaN/inf ou des bornes hors EPSG:4326 atteignaient
`ST_MakeEnvelope` et finissaient en 500.

`minx > maxx` est légitime : rectangle à cheval sur l'antiméridien (REV-364 a),
géré par les requêtes, pas refusé ici."""

import math


def parse_bbox_floats(
    raw: str | None, *, check_bounds: bool = True
) -> tuple[float, float, float, float] | None:
    """`None` si absent ; `ValueError` si malformé, non fini, ou (avec
    `check_bounds`) hors lon ±180 / lat ±90."""
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError(raw)
    minx, miny, maxx, maxy = (float(p) for p in parts)
    vals = (minx, miny, maxx, maxy)
    if not all(math.isfinite(v) for v in vals):
        raise ValueError(raw)
    if check_bounds and (max(abs(minx), abs(maxx)) > 180 or max(abs(miny), abs(maxy)) > 90):
        raise ValueError(raw)
    return vals
