# SPDX-License-Identifier: Apache-2.0
"""Sérialisation WMS 1.3.0 / WMTS 1.0.0 (ARC-20, ADR 0020). Écriture seule : aucun
XML entrant n'est parsé (KVP uniquement) ; toute valeur sortante est échappée."""

import math

from app.ogc_crs import FRANCE_EPSG
from app.ows.render import LEGEND_ROW, LEGEND_WIDTH
from app.ows.wfs import NCNAME, _a, _t  # noqa: F401  (NCNAME ré-exporté)

NS_WMS = "http://www.opengis.net/wms"
NS_OGC = "http://www.opengis.net/ogc"
NS_WMTS = "http://www.opengis.net/wmts/1.0"
NS_OWS = "http://www.opengis.net/ows/1.1"
XLINK = "http://www.w3.org/1999/xlink"

# CRS servis : (identifiant WMS, EPSG, ordre lat/lon en 1.3.0 ?). Seul EPSG:4326 est
# inversé ; CRS:84 = lon/lat. EPSG:2154 est est/nord (x,y).
CRS_TABLE = {
    "EPSG:4326": (4326, True),
    "CRS:84": (4326, False),
    "EPSG:3857": (3857, False),
    "EPSG:2154": (2154, False),
}
CRS_TABLE.update({f"EPSG:{c}": (c, False) for c in FRANCE_EPSG})  # AUD-127
GETMAP_FORMATS = ("image/png",)
INFO_FORMATS = ("application/json", "text/plain")
TMS = "WebMercatorQuad"
TMS_ORIGIN = 20037508.342789244  # demi-circonférence de la sphère Web Mercator (m)
MAX_ZOOM = 22
_SCALE0 = 559082264.0287178  # dénominateur d'échelle au zoom 0 (pixel de 0,28 mm)


def service_exception(code: str, message: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ServiceExceptionReport version="1.3.0" xmlns="{NS_OGC}">'
        f"<ServiceException code={_a(code)}>{_t(message)}</ServiceException>"
        "</ServiceExceptionReport>"
    )


def _dcp(base: str) -> str:
    return (
        f'<DCPType><HTTP><Get><OnlineResource xmlns:xlink="{XLINK}" xlink:type="simple" '
        f"xlink:href={_a(base + '?')}/></Get></HTTP></DCPType>"
    )


def _legend_url(base: str, layer: str) -> str:
    """LegendURL d'un style (AUD-045) ; `_a` échappe `&` (quoteattr)."""
    href = (
        f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&LAYER={layer}&FORMAT=image/png"
    )
    return (
        f'<LegendURL width="{LEGEND_WIDTH}" height="{LEGEND_ROW}"><Format>image/png</Format>'
        f'<OnlineResource xlink:type="simple" xlink:href={_a(href)}/></LegendURL>'
    )


def wms_capabilities(base: str, title: str, collections: list) -> str:
    def op(name: str, formats: tuple[str, ...]) -> str:
        fmts = "".join(f"<Format>{_t(f)}</Format>" for f in formats)
        return f"<{name}>{fmts}{_dcp(base)}</{name}>"

    crs = "".join(f"<CRS>{c}</CRS>" for c in CRS_TABLE)
    bbox = (
        "<EX_GeographicBoundingBox><westBoundLongitude>-180</westBoundLongitude>"
        "<eastBoundLongitude>180</eastBoundLongitude><southBoundLatitude>-90</southBoundLatitude>"
        "<northBoundLatitude>90</northBoundLatitude></EX_GeographicBoundingBox>"
    )
    layers = "".join(
        f'<Layer queryable="1" opaque="0"><Name>{_t(c.id)}</Name><Title>{_t(c.title)}</Title>'
        f"<Abstract>{_t(c.description or '')}</Abstract>{crs}{bbox}"
        "<Style><Name>default</Name><Title>default</Title>"
        f"{_legend_url(base, c.id)}</Style></Layer>"
        for c in collections
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<WMS_Capabilities version="1.3.0" xmlns="{NS_WMS}" xmlns:xlink="{XLINK}">'
        f"<Service><Name>WMS</Name><Title>{_t(title)}</Title>"
        f'<OnlineResource xlink:type="simple" xlink:href={_a(base)}/>'
        "<MaxWidth>2048</MaxWidth><MaxHeight>2048</MaxHeight></Service>"
        "<Capability><Request>"
        f"{op('GetCapabilities', ('text/xml',))}{op('GetMap', GETMAP_FORMATS)}"
        f"{op('GetFeatureInfo', INFO_FORMATS)}</Request>"
        "<Exception><Format>XML</Format></Exception>"
        f"<Layer><Title>{_t(title)}</Title>{crs}{bbox}{layers}</Layer>"
        "</Capability></WMS_Capabilities>"
    )


def tile_matrix(z: int) -> tuple[float, int]:
    """(taille d'une tuile en mètres, nombre de tuiles par axe) au zoom z."""
    n = 2**z
    return 2 * TMS_ORIGIN / n, n


def tile_bbox(z: int, col: int, row: int) -> tuple[float, float, float, float]:
    """Emprise EPSG:3857 (minx, miny, maxx, maxy) d'une tuile WebMercatorQuad."""
    size, _ = tile_matrix(z)
    minx = -TMS_ORIGIN + col * size
    maxy = TMS_ORIGIN - row * size
    return minx, maxy - size, minx + size, maxy


def tile_matrix_set_json() -> dict:
    """WebMercatorQuad au format TMS 2.0 JSON (AUD-042)."""
    matrices = []
    for z in range(MAX_ZOOM + 1):
        size, n = tile_matrix(z)
        matrices.append(
            {
                "id": str(z),
                "scaleDenominator": _SCALE0 / n,
                "cellSize": size / 256,
                "cornerOfOrigin": "topLeft",
                "pointOfOrigin": [-TMS_ORIGIN, TMS_ORIGIN],
                "tileWidth": 256,
                "tileHeight": 256,
                "matrixWidth": n,
                "matrixHeight": n,
            }
        )
    return {
        "id": TMS,
        "title": "Google Maps Compatible for the World",
        "uri": "http://www.opengis.net/def/tilematrixset/OGC/1.0/WebMercatorQuad",
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "orderedAxes": ["E", "N"],
        "wellKnownScaleSet": "http://www.opengis.net/def/wkss/OGC/1.0/GoogleMapsCompatible",
        "tileMatrices": matrices,
    }


def wmts_capabilities(base: str, title: str, collections: list) -> str:
    def op(name: str) -> str:
        return (
            f'<ows:Operation name="{name}"><ows:DCP><ows:HTTP>'
            f'<ows:Get xlink:href={_a(base + "?")}><ows:Constraint name="GetEncoding">'
            "<ows:AllowedValues><ows:Value>KVP</ows:Value></ows:AllowedValues>"
            "</ows:Constraint></ows:Get></ows:HTTP></ows:DCP></ows:Operation>"
        )

    layers = ""
    for c in collections:
        tail = "{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"
        tmpl = f"{base}/1.0.0/{c.id}/{tail}"
        layers += (
            f"<Layer><ows:Title>{_t(c.title)}</ows:Title>"
            f"<ows:Abstract>{_t(c.description or '')}</ows:Abstract>"
            "<ows:WGS84BoundingBox><ows:LowerCorner>-180 -90</ows:LowerCorner>"
            "<ows:UpperCorner>180 90</ows:UpperCorner></ows:WGS84BoundingBox>"
            f"<ows:Identifier>{_t(c.id)}</ows:Identifier>"
            '<Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>'
            "<Format>image/png</Format>"
            f"<TileMatrixSetLink><TileMatrixSet>{TMS}</TileMatrixSet></TileMatrixSetLink>"
            f'<ResourceURL format="image/png" resourceType="tile" template={_a(tmpl)}/></Layer>'
        )
    matrices = ""
    for z in range(MAX_ZOOM + 1):
        _, n = tile_matrix(z)
        matrices += (
            f"<TileMatrix><ows:Identifier>{z}</ows:Identifier>"
            f"<ScaleDenominator>{_SCALE0 / n!r}</ScaleDenominator>"
            f"<TopLeftCorner>{-TMS_ORIGIN!r} {TMS_ORIGIN!r}</TopLeftCorner>"
            f"<TileWidth>256</TileWidth><TileHeight>256</TileHeight>"
            f"<MatrixWidth>{n}</MatrixWidth><MatrixHeight>{n}</MatrixHeight></TileMatrix>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Capabilities xmlns="{NS_WMTS}" xmlns:ows="{NS_OWS}" '
        f'xmlns:xlink="{XLINK}" version="1.0.0">'
        f"<ows:ServiceIdentification><ows:Title>{_t(title)}</ows:Title>"
        "<ows:ServiceType>OGC WMTS</ows:ServiceType>"
        "<ows:ServiceTypeVersion>1.0.0</ows:ServiceTypeVersion>"
        "</ows:ServiceIdentification>"
        f"<ows:OperationsMetadata>{op('GetCapabilities')}{op('GetTile')}</ows:OperationsMetadata>"
        f"<Contents>{layers}<TileMatrixSet><ows:Identifier>{TMS}</ows:Identifier>"
        "<ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>"
        f"{matrices}</TileMatrixSet></Contents>"
        f"<ServiceMetadataURL xlink:href={_a(base + '/1.0.0/WMTSCapabilities.xml')}/>"
        "</Capabilities>"
    )


def finite(*v: float) -> bool:
    return all(math.isfinite(x) for x in v)
