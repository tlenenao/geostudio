# SPDX-License-Identifier: Apache-2.0
"""CRS offerts par OGC API Features Part 2 (REV-367 a). Module feuille : importé
par `app.features` (paramètre `crs`, en-tête `Content-Crs`) et `app.collections`
(`storageCrs`/`crs` de la description de collection)."""

# 4326 = lon/lat (CRS84) comme GeoJSON.
# AUD-127 : Lambert-93 + coniques conformes CC42..CC50 + UTM outre-mer (Guyane RGFG95/UTM22N,
# Réunion RGR92/UTM40S, Mayotte RGM04/UTM38S, Antilles RGAF09/UTM20N).
FRANCE_EPSG = (2972, 2975, 4471, 5490, *range(3942, 3951))
SUPPORTED_EPSG = (4326, 3857, 2154, *FRANCE_EPSG)
CRS84_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


def crs_uri(srid: int) -> str:
    # Part 2 : l'URI EPSG/0/4326 impose lat/lon ; nous servons lon/lat -> CRS84.
    return CRS84_URI if srid == 4326 else f"http://www.opengis.net/def/crs/EPSG/0/{srid}"


def collection_crs_fields(storage_srid: int | None) -> dict:
    """`crs` (liste des CRS servis, dont le CRS de stockage) et `storageCrs`."""
    if not storage_srid:
        return {}
    offered = [crs_uri(s) for s in SUPPORTED_EPSG]
    storage = crs_uri(storage_srid)
    if storage not in offered:
        offered.append(storage)
    return {"crs": offered, "storageCrs": storage}
