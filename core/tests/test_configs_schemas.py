# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig, PrintLayout


def test_print_layout_defaults():
    layout = PrintLayout()
    assert layout.pageSize == "a4"
    assert layout.orientation == "portrait"
    assert layout.showLegend is True
    assert layout.showScaleBar is True
    assert layout.showNorthArrow is False
    assert layout.title is None
    assert layout.cartouche is None


def test_print_layout_rejects_invalid_page_size():
    with pytest.raises(ValidationError):
        PrintLayout(pageSize="letter")


def test_builder_config_print_layout_optional_and_absent_by_default():
    config = BuilderConfig(
        kind="map",
        map={
            "basemap": {"style": "https://example.test/style.json"},
            "view": {"center": [0.0, 0.0], "zoom": 3.0},
        },
    )
    assert config.printLayout is None


def test_builder_config_accepts_print_layout_on_map_kind():
    config = BuilderConfig(
        kind="map",
        map={
            "basemap": {"style": "https://example.test/style.json"},
            "view": {"center": [0.0, 0.0], "zoom": 3.0},
        },
        printLayout={"pageSize": "a3", "orientation": "landscape", "title": "Carte des incidents"},
    )
    assert config.printLayout is not None
    assert config.printLayout.pageSize == "a3"
    assert config.printLayout.title == "Carte des incidents"


def test_builder_config_accepts_print_layout_on_app_kind():
    config = BuilderConfig(
        kind="app", layout={"type": "grid", "items": []}, printLayout={"cartouche": "GeoStudio"}
    )
    assert config.printLayout is not None
    assert config.printLayout.cartouche == "GeoStudio"
