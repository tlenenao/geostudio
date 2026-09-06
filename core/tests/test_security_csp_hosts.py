# SPDX-License-Identifier: Apache-2.0
from app.security.csp_hosts import (
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
