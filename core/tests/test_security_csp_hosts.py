# SPDX-License-Identifier: Apache-2.0
import pytest

from app.security.csp_hosts import (
    _origin,
    extract_config_external_hosts,
    extract_extension_hosts,
    extract_harvest_hosts,
)


class _FakeHarvestSource:
    def __init__(self, type_: str, url: str) -> None:
        self.type = type_
        self.url = url


def test_extract_harvest_hosts_keeps_only_wms_and_wmts():
    sources = [
        _FakeHarvestSource("wms", "https://tiles.example.com/wms?service=WMS"),
        _FakeHarvestSource("wmts", "https://tiles2.example.org:8443/wmts"),
        _FakeHarvestSource("arcgis", "https://ignored.example.net/rest"),
        _FakeHarvestSource("stac", "https://ignored2.example.net/stac"),
    ]
    assert extract_harvest_hosts(sources) == {
        "https://tiles.example.com",
        "https://tiles2.example.org:8443",
    }


def test_extract_harvest_hosts_empty_list():
    assert extract_harvest_hosts([]) == set()


def test_extract_config_external_hosts_terrain_and_external_tiles3d():
    body = {
        "basemap": {"style": "https://basemap.example/style.json"},
        "view": {"center": [0, 0], "zoom": 1},
        "terrain": {"tilesUrl": "https://dem.example.com/{z}/{x}/{y}.png", "encoding": "terrarium"},
        "layers": [
            {
                "id": "a",
                "title": "A",
                "kind": "tiles3d",
                "url": "https://3d.example.com/tileset.json",
            },
            {
                "id": "b",
                "title": "B",
                "kind": "raster",
                "collectionId": "col-1",
                # tilesUrl présent malgré collectionId : ne doit jamais
                # apparaître dans le résultat — c'est précisément ce que
                # falsifie le test (retirer le filtre collectionId doit
                # faire échouer ce test, pas seulement rester vert par
                # absence de valeur à extraire).
                "tilesUrl": "https://internal-should-be-ignored.example.com/mvt",
            },
            {"id": "c", "title": "C", "kind": "vector", "collectionId": "col-2"},
        ],
    }
    assert extract_config_external_hosts(body) == {
        "https://dem.example.com",
        "https://3d.example.com",
    }


def test_extract_config_external_hosts_ignores_internal_proxy_paths():
    # tileset3d/terrain3d convertis : servis par le proxy authentifié du
    # cœur, jamais un hôte externe — une URL relative (ou absente) ne doit
    # jamais produire d'entrée.
    body = {
        "basemap": {"style": "x"},
        "view": {"center": [0, 0], "zoom": 1},
        "layers": [
            {"id": "a", "title": "A", "kind": "tiles3d", "url": "/tileset3d/item-1/tileset.json"},
        ],
    }
    assert extract_config_external_hosts(body) == set()


def test_extract_config_external_hosts_missing_terrain_and_layers():
    assert (
        extract_config_external_hosts(
            {"basemap": {"style": "x"}, "view": {"center": [0, 0], "zoom": 1}}
        )
        == set()
    )


class _FakeExtension:
    def __init__(self, module_url: str) -> None:
        self.module_url = module_url


def test_extract_extension_hosts():
    extensions = [
        _FakeExtension("https://cdn.example.com/widgets/gauge.js"),
        _FakeExtension("/extensions/local-widget.js"),  # même origine, ignoré
    ]
    assert extract_extension_hosts(extensions) == {"https://cdn.example.com"}


@pytest.mark.parametrize(
    "url",
    [
        'https://a"b.example/x',
        "https://x:abc/",
        "https://x:99999/",
        "https://a b.example/",
        "https://a;b.example/",
        "https://évil.example/",
    ],
)
def test_malformed_hosts_are_dropped_not_raised(url):
    # AUD-089 : un seul enregistrement piégé ne doit ni injecter de directive
    # ni faire lever le calcul (qui figeait la CSP de toute l'instance).
    assert _origin(url) is None


def test_valid_origin_keeps_port():
    assert (
        _origin("https://tiles.example.org:8443/{z}/{x}/{y}.png")
        == "https://tiles.example.org:8443"
    )


def test_one_bad_layer_does_not_hide_the_good_ones():
    body = {
        "layers": [
            {"kind": "raster", "url": "https://x:abc/{z}"},
            {"kind": "raster", "url": "https://ok.example/{z}"},
        ]
    }
    assert extract_config_external_hosts(body) == {"https://ok.example"}


class _FakeExt:
    def __init__(self, connect, img):
        self.connect_hosts = connect
        self.img_hosts = img


def test_extract_extension_declared_hosts_keeps_only_safe_origins():
    from app.security.csp_hosts import extract_extension_declared_hosts

    connect, img = extract_extension_declared_hosts(
        [
            _FakeExt(["https://api.example.org", "https://bad host"], ["https://cdn.example.org"]),
            _FakeExt([], ["javascript:alert(1)", "https://cdn2.example.org:8443/x"]),
        ]
    )
    assert connect == {"https://api.example.org"}
    assert img == {"https://cdn.example.org", "https://cdn2.example.org:8443"}
