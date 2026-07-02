import pytest
from pydantic import ValidationError

from app.schemas import BuilderConfig


def _valid_payload(kind: str = "app") -> dict:
    return {
        "version": 1,
        "kind": kind,
        "dataSources": [
            {"id": "ds1", "type": "feature", "service": "martin",
             "layer": "communes", "query": {}}
        ],
        "layout": {
            "type": "grid",
            "breakpoints": {"lg": 12},
            "items": [
                {"widget": "map", "x": 0, "y": 0, "w": 8, "h": 6, "props": {}},
                {"widget": "table", "x": 8, "y": 0, "w": 4, "h": 6, "props": {}},
            ],
        },
        "messages": [
            {"from": "map", "event": "select", "to": "table", "action": "filter"}
        ],
    }


def test_valid_app_config_parses():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.kind == "app"
    assert config.layout.items[0].widget == "map"
    assert config.messages[0].from_ == "map"


def test_valid_dashboard_config_parses():
    config = BuilderConfig.model_validate(_valid_payload("dashboard"))
    assert config.kind == "dashboard"


def test_invalid_kind_rejected():
    payload = _valid_payload()
    payload["kind"] = "website"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_layout_required():
    payload = _valid_payload()
    del payload["layout"]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_message_from_alias_round_trips():
    config = BuilderConfig.model_validate(_valid_payload())
    dumped = config.model_dump(by_alias=True)
    assert dumped["messages"][0]["from"] == "map"


def _valid_map_payload() -> dict:
    return {
        "version": 1,
        "kind": "map",
        "map": {
            "basemap": {"style": "https://demotiles.maplibre.org/style.json"},
            "view": {"center": [2.35, 48.85], "zoom": 5},
            "layers": [
                {"id": "l1", "title": "Communes", "visible": True,
                 "kind": "vector", "tilesUrl": "https://martin/communes/{z}/{x}/{y}",
                 "sourceLayer": "communes"},
            ],
        },
    }


def test_valid_map_config_parses():
    config = BuilderConfig.model_validate(_valid_map_payload())
    assert config.kind == "map"
    assert config.layout is None
    assert config.map is not None
    assert config.map.layers[0].kind == "vector"
    assert config.map.view.center == (2.35, 48.85)


def test_map_config_requires_map_field():
    payload = _valid_map_payload()
    del payload["map"]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_app_config_still_requires_layout():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"kind": "app"})


from app.schemas import LayoutItem


def test_layout_item_accepts_optional_id():
    item = LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2, props={"text": "Hi"})
    assert item.id == "w1"
    dumped = item.model_dump()
    assert dumped["id"] == "w1"


def test_layout_item_id_defaults_to_none():
    item = LayoutItem(widget="text", x=0, y=0, w=4, h=2)
    assert item.id is None
