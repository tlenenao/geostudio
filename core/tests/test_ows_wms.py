# SPDX-License-Identifier: Apache-2.0
"""ARC-20 : WMS 1.3.0 + WMTS 1.0.0 rendus par le cœur (ADR 0020). PostGIS réel, vraie
RLS. Critères : capacités conformes aux XSD OGC, axes 1.3.0, CRS 4326/3857/2154, droits et
masquage identiques à l'API Features (test croisé), plafonds, perf 256x256 mesurée."""

import functools
import io
import statistics
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pyproj
import pytest
import xmlschema
from PIL import Image
from sqlalchemy import text

from app.sharing import geo_limits as gl
from app.styles.model import DEFAULT_COLOR
from tests.test_ows_wfs import _build, _cleanup  # noqa: F401  (fixture autouse)

pytestmark = pytest.mark.postgis

WMS = "/v1/ows/wms"
WMTS = "/v1/ows/wmts"
SCHEMAS = Path(__file__).parent / "fixtures" / "ogc_schemas" / "schemas.opengis.net"
FILL = tuple(int(DEFAULT_COLOR[i : i + 2], 16) for i in (1, 3, 5)) + (255,)


def _q(**kw):
    return {"service": "WMS", "version": "1.3.0", **kw}


def _map(**kw):
    base = {
        "request": "GetMap",
        "layers": "demo_ows",
        "styles": "",
        "format": "image/png",
        "crs": "EPSG:4326",
        "bbox": "44,0,48,4",  # lat,lon (1.3.0)
        "width": 400,
        "height": 400,
        "transparent": "TRUE",
    }
    return _q(**{**base, **kw})


def _img(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


@pytest.fixture()
def env(pg_engine, monkeypatch):
    monkeypatch.setenv("CORE_OWS_ENABLED", "true")
    monkeypatch.setenv("CORE_OWS_WMS_ENABLED", "true")
    return _build(pg_engine)


def _enable(c, **extra):
    r = c.patch(
        "/v1/collections/demo_ows",
        json={"owsEnabled": True, "isPublic": True, "sensitiveFields": ["secret"], **extra},
    )
    assert r.status_code == 200, r.text


@functools.cache
def _schema(xsd: str, **loc):
    return xmlschema.XMLSchema(
        str(SCHEMAS / xsd),
        locations={k: str(SCHEMAS / v) for k, v in loc.items()},
        allow="local",
        validation="lax",
    )


def test_flag_off_capability_is_absent(pg_engine, monkeypatch):
    monkeypatch.setenv("CORE_OWS_ENABLED", "true")
    monkeypatch.delenv("CORE_OWS_WMS_ENABLED", raising=False)
    c, _login, _admin = _build(pg_engine)
    assert c.get(WMS, params=_q(request="GetCapabilities")).status_code == 404
    assert c.get(WMTS, params={"request": "GetCapabilities"}).status_code == 404


def test_wms_capabilities_valid_xsd_and_per_collection(env):
    c, _login, _admin = env
    xsd = _schema("wms/1.3.0/capabilities_1_3_0.xsd")
    first = c.get(WMS, params=_q(request="GetCapabilities"))
    xsd.validate(first.text)
    assert "<Name>demo_ows</Name>" not in first.text  # activation par collection
    _enable(c)
    r = c.get(WMS, params=_q(request="GetCapabilities"))
    xsd.validate(r.text)
    assert "<Name>demo_ows</Name>" in r.text and "EPSG:2154" in r.text


def test_getmap_axis_order_and_default_style(env):
    c, login, _admin = env
    _enable(c)
    login(None)  # anonyme sur collection publique : même porte que l'API Features
    img = _img(c.get(WMS, params=_map()))
    assert img.size == (400, 400)
    # alpha (lon 1, lat 45) : x = 1/4*400, y = (48-45)/4*400
    assert img.getpixel((100, 300)) == FILL
    assert img.getpixel((10, 10))[3] == 0  # transparent ailleurs
    # bbox lon,lat (ordre CRS:84) : même image qu'en lat,lon sous EPSG:4326
    same = _img(c.get(WMS, params=_map(crs="CRS:84", bbox="0,44,4,48")))
    assert same.tobytes() == img.tobytes()
    # ordre non inversé sous EPSG:4326 = autre zone (lon 44..48) : rien d'affiché
    assert _img(c.get(WMS, params=_map(bbox="0,44,4,48"))).getbbox() is None
    opaque = _img(c.get(WMS, params=_map(transparent="FALSE", bgcolor="0xFF0000")))
    assert opaque.getpixel((10, 10)) == (255, 0, 0, 255)


@pytest.mark.parametrize("epsg", [3857, 2154])
def test_getmap_projected_crs(env, epsg):
    c, _login, admin = env
    _enable(c)
    tr = pyproj.Transformer.from_crs(4326, epsg, always_xy=True)
    x0, y0 = tr.transform(0.5, 44.5)
    x1, y1 = tr.transform(1.5, 45.5)  # encadre alpha (1, 45) au centre
    r = c.get(
        WMS,
        params=_map(crs=f"EPSG:{epsg}", bbox=f"{x0},{y0},{x1},{y1}", width=100, height=100),
    )
    img = _img(r)
    px, py = tr.transform(1.0, 45.0)
    ix = (px - x0) / (x1 - x0) * 100
    iy = (y1 - py) / (y1 - y0) * 100
    assert img.getpixel((round(ix), round(iy))) == FILL


def test_getfeatureinfo_masks_sensitive_like_features_api(env):
    c, login, admin = env
    _enable(c)
    q = _map(
        request="GetFeatureInfo",
        query_layers="demo_ows",
        info_format="application/json",
        i=100,
        j=300,
    )
    login(None)
    anon = c.get(WMS, params=q).json()["features"]
    assert [f["properties"]["nom"] for f in anon] == ["alpha"]
    assert "secret" not in anon[0]["properties"]
    features_api = c.get("/v1/collections/demo_ows/items").json()["features"][0]["properties"]
    assert set(anon[0]["properties"]) == set(features_api)  # mêmes propriétés que l'API Features
    login(admin)
    assert "secret" in c.get(WMS, params=q).json()["features"][0]["properties"]
    plain = c.get(WMS, params={**q, "info_format": "text/plain"})
    assert "nom = alpha" in plain.text
    assert c.get(WMS, params={**q, "i": 9999}).status_code == 400  # InvalidPoint


def test_private_collection_same_rights_as_features_api(env):
    c, login, _admin = env
    assert c.patch("/v1/collections/demo_ows", json={"owsEnabled": True}).status_code == 200
    login(None)
    r = c.get(WMS, params=_map())
    assert r.status_code == 404 and "ServiceException" in r.text
    assert c.get("/v1/collections/demo_ows/items").status_code == r.status_code
    tile = c.get(f"{WMTS}/1.0.0/demo_ows/default/WebMercatorQuad/0/0/0.png")
    assert tile.status_code == 404
    caps = c.get(WMS, params=_q(request="GetCapabilities")).text
    assert "<Name>demo_ows</Name>" not in caps


def test_geographic_limit_applies_to_render_like_features_api(env, pg_engine):
    """Test croisé RLS : un utilisateur sous limite géographique voit au rendu EXACTEMENT les
    entités que l'API Features lui renvoie."""
    from app.auth.dependency import get_current_user, get_current_user_optional
    from app.db import make_session_factory
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    c, login, admin = env
    _enable(c)
    S = make_session_factory(pg_engine)
    with S() as s:
        t = get_or_create_default_tenant(s)
        bob = get_or_create_user(
            s,
            tenant_id=t.id,
            oidc_sub="bob",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        # limite = boîte lon 0..1.5, lat 44..45.5 : ne contient que alpha (1, 45)
        box = {
            "type": "Polygon",
            "coordinates": [[[0, 44], [1.5, 44], [1.5, 45.5], [0, 45.5], [0, 44]]],
        }
        gl.upsert_limit(
            s, tenant_id=t.id, collection_id="demo_ows", target_type="role",
            target_id=bob.role_id, geometry=box, actor_id=admin.id,
        )  # fmt: skip
        s.commit()
        app = c.app
        app.dependency_overrides[get_current_user] = lambda: bob
        app.dependency_overrides[get_current_user_optional] = lambda: bob
    api = c.get("/v1/collections/demo_ows/items").json()["features"]
    assert [f["properties"]["nom"] for f in api] == ["alpha"]
    img = _img(c.get(WMS, params=_map()))
    assert img.getpixel((100, 300)) == FILL  # alpha visible
    assert img.getpixel((200, 200))[3] == 0  # bravo (2, 46) hors limite : non rendu
    assert img.getpixel((300, 100))[3] == 0  # charlie (3, 47)
    login(admin)
    assert _img(c.get(WMS, params=_map())).getpixel((200, 200)) == FILL


@pytest.mark.parametrize(
    "bad",
    [
        {"request": "GetMap", "layers": ""},
        {"layers": "nope"},
        {"layers": ",".join(["demo_ows"] * 9)},
        {"crs": "EPSG:9999"},
        {"bbox": "1,2,3"},
        {"bbox": "nan,0,4,48"},
        {"bbox": "48,0,44,4"},
        {"width": 4096},
        {"width": 2048, "height": 2048},
        {"width": 0},
        {"format": "image/gif"},
        {"styles": "map:x:y"},
        {"styles": "a,b"},
        {"bgcolor": "red", "transparent": "FALSE"},
        {"request": "Nope"},
        {"version": "1.1.1"},
    ],
)
def test_bad_getmap_is_service_exception(env, bad):
    c, _login, _admin = env
    _enable(c)
    r = c.get(WMS, params=_map(**bad))
    assert 400 <= r.status_code < 500, (bad, r.status_code)
    root = ET.fromstring(r.text)  # XML bien formé
    assert root.tag.endswith("ServiceExceptionReport")


def test_extreme_bbox_is_not_a_500(env):
    c, _login, _admin = env
    _enable(c)
    for crs, bbox in (
        ("EPSG:3857", "-1e12,-1e12,1e12,1e12"),
        ("EPSG:2154", "-1e12,-1e12,1e12,1e12"),
        ("CRS:84", "-1000,-1000,1000,1000"),
    ):
        r = c.get(WMS, params=_map(crs=crs, bbox=bbox, width=64, height=64))
        assert r.status_code in (200, 400), (crs, r.status_code, r.text[:200])


def test_style_reference_uses_symbology_and_can(env):
    c, login, admin = env
    _enable(c)
    sym = {
        "color": {
            "field": "nom",
            "mode": "categorical",
            "palette": "categorical-a",
            "domain": {"kind": "categorical", "values": ["alpha", "bravo", "charlie"]},
            "computedAt": "2026-01-01",
        },
        "opacity": 100,
    }
    cfg = {
        "kind": "map",
        "map": {
            "basemap": {"style": "s"},
            "view": {"center": [2, 46], "zoom": 5},
            "layers": [
                {
                    "id": "lay1", "title": "t", "visible": True, "kind": "vector",
                    "tilesUrl": "http://core/x/{z}/{x}/{y}", "sourceLayer": "demo_ows",
                    "collectionId": "demo_ows", "geometryKind": "point", "symbology": sym,
                }
            ],
        },
    }  # fmt: skip
    created = c.post("/v1/configs", json={"title": "Carte", "config": cfg})
    assert created.status_code in (200, 201), created.text
    item = created.json()["itemId"]
    style = f"map:{item}:lay1"
    img = _img(c.get(WMS, params=_map(styles=style)))
    assert img.getpixel((100, 300))[:3] == (0x25, 0x63, 0xEB)  # alpha : 1re couleur
    assert img.getpixel((200, 200))[:3] == (0xDC, 0x26, 0x26)  # bravo : 2e couleur
    # anonyme : la carte (privée) n'est pas lisible -> StyleNotDefined, rien ne fuit
    login(None)
    r = c.get(WMS, params=_map(styles=style))
    assert r.status_code == 400 and "StyleNotDefined" in r.text
    assert c.get(WMS, params=_map(styles="map:inconnu:lay1")).text == r.text.replace(
        item, "inconnu"
    )


def test_wmts_capabilities_valid_xsd_and_tile_kvp_rest_identical(env):
    c, _login, _admin = env
    _enable(c)
    xsd = _schema("wmts/1.0/wmtsGetCapabilities_response.xsd")
    kvp_caps = c.get(WMTS, params={"service": "WMTS", "request": "GetCapabilities"})
    xsd.validate(kvp_caps.text)
    rest_caps = c.get(f"{WMTS}/1.0.0/WMTSCapabilities.xml")
    assert rest_caps.text == kvp_caps.text and "<ows:Identifier>demo_ows" in rest_caps.text
    # zoom 6 : alpha (1, 45) -> tuile col 32, row 22 (WebMercatorQuad)
    kvp = c.get(
        WMTS,
        params={
            "service": "WMTS", "request": "GetTile", "version": "1.0.0", "layer": "demo_ows",
            "style": "default", "tilematrixset": "WebMercatorQuad", "tilematrix": 6,
            "tilerow": 22, "tilecol": 32, "format": "image/png",
        },
    )  # fmt: skip
    rest = c.get(f"{WMTS}/1.0.0/demo_ows/default/WebMercatorQuad/6/22/32.png")
    assert kvp.content == rest.content
    img = _img(kvp)
    assert img.size == (256, 256) and img.getbbox() is not None
    assert _img(c.get(f"{WMTS}/1.0.0/demo_ows/default/WebMercatorQuad/6/0/0.png")).getbbox() is None


@pytest.mark.parametrize(
    "path",
    [
        "demo_ows/default/WebMercatorQuad/6/64/0.png",  # ligne hors matrice
        "demo_ows/default/WebMercatorQuad/6/0/64.png",
        "demo_ows/default/WebMercatorQuad/99/0/0.png",
        "demo_ows/default/Autre/0/0/0.png",
        "inconnu/default/WebMercatorQuad/0/0/0.png",
        "demo_ows/pasdestyle/WebMercatorQuad/0/0/0.png",
    ],
)
def test_wmts_bad_tile_is_ows_exception(env, path):
    c, _login, _admin = env
    _enable(c)
    r = c.get(f"{WMTS}/1.0.0/{path}")
    assert 400 <= r.status_code < 500, path
    assert ET.fromstring(r.text).tag.endswith("ExceptionReport")


def test_render_truncates_at_cap_and_flags_it(env, pg_engine, monkeypatch):
    from app.ows import wms_routes

    c, _login, _admin = env
    _enable(c)
    monkeypatch.setattr(wms_routes, "MAX_FEATURES_PER_LAYER", 2)
    r = c.get(WMS, params=_map())
    assert r.status_code == 200 and r.headers.get("X-GeoStudio-Truncated") == "true"
    img = _img(r)
    assert img.getpixel((100, 300)) == FILL and img.getpixel((200, 200)) == FILL
    assert img.getpixel((300, 100))[3] == 0  # 3e entité au-delà du plafond


def test_tile_p95_under_300ms_on_nominal_layer(pg_engine, monkeypatch):
    """Mesure (et non simple assertion de durée sur un cas trivial) : couche nominale de
    2000 polygones, 80 tuiles distinctes zoom 7-9 sur l'emprise, requêtes HTTP complètes."""
    monkeypatch.setenv("CORE_OWS_ENABLED", "true")
    monkeypatch.setenv("CORE_OWS_WMS_ENABLED", "true")
    c, _login, _admin = _build(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS perf_ows"))
        conn.execute(
            text(
                "CREATE TABLE perf_ows (id serial PRIMARY KEY, nom text, "
                "geom geometry(Polygon, 4326))"
            )
        )
        conn.execute(text("CREATE INDEX ON perf_ows USING gist (geom)"))
    assert c.post("/v1/collections", json={"tableName": "perf_ows"}).status_code == 201
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO perf_ows (nom, geom) SELECT 'n' || g, ST_Buffer(ST_SetSRID("
                "ST_MakePoint(-2 + (g % 50) * 0.16, 43 + (g / 50) * 0.2), 4326), 0.05, 8) "
                "FROM generate_series(1, 2000) g"
            )
        )
    assert (
        c.patch("/v1/collections/perf_ows", json={"owsEnabled": True, "isPublic": True}).status_code
        == 200
    )
    try:
        tr = pyproj.Transformer.from_crs(4326, 3857, always_xy=True)
        cx, cy = tr.transform(2.0, 46.0)
        timings, n_features = [], 0
        for z in (7, 8, 9):
            n = 2**z
            size = 2 * 20037508.342789244 / n
            col0 = int((cx + 20037508.342789244) // size)
            row0 = int((20037508.342789244 - cy) // size)
            for dc in range(-4, 4):
                for dr in range(-4, 4):
                    if z == 9 and (dc + dr) % 2:
                        continue
                    url = (
                        f"{WMTS}/1.0.0/perf_ows/default/WebMercatorQuad/"
                        f"{z}/{row0 + dr}/{col0 + dc}.png"
                    )
                    t0 = time.perf_counter()
                    r = c.get(url)
                    timings.append((time.perf_counter() - t0) * 1000)
                    assert r.status_code == 200
                    n_features += (
                        Image.open(io.BytesIO(r.content)).convert("RGBA").getbbox() is not None
                    )
        timings.sort()
        p95 = timings[int(len(timings) * 0.95) - 1]
        print(
            f"\n[perf WMTS 256x256] n={len(timings)} non-vides={n_features} "
            f"p50={statistics.median(timings):.0f}ms p95={p95:.0f}ms max={timings[-1]:.0f}ms"
        )
        assert n_features > 20  # le jeu de mesure rend bien des entités
        assert p95 < 300, f"p95={p95:.0f}ms"
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS perf_ows"))
