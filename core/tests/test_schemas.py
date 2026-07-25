# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


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


from app.configs.schemas import LayoutItem


def test_layout_item_accepts_optional_id():
    item = LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2, props={"text": "Hi"})
    assert item.id == "w1"
    dumped = item.model_dump()
    assert dumped["id"] == "w1"


def test_layout_item_id_defaults_to_none():
    item = LayoutItem(widget="text", x=0, y=0, w=4, h=2)
    assert item.id is None


def test_layout_item_layouts_round_trip():
    payload = _valid_payload("app")
    payload["layout"]["items"][0]["layouts"] = {"sm": {"x": 1, "y": 2, "w": 6, "h": 3}}
    config = BuilderConfig.model_validate(payload)
    assert config.layout.items[0].layouts == {"sm": {"x": 1, "y": 2, "w": 6, "h": 3}}
    dumped = config.model_dump(by_alias=True)
    assert dumped["layout"]["items"][0]["layouts"]["sm"]["x"] == 1


def test_layout_item_layouts_optional():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.layout.items[0].layouts is None


def test_pages_round_trip():
    payload = _valid_payload("app")
    payload["pages"] = [
        {"id": "p1", "name": "Accueil", "layout": payload["layout"]},
        {"id": "p2", "name": "Détails", "layout": {"type": "grid", "breakpoints": {}, "items": []}},
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.pages) == 2
    assert config.pages[0].name == "Accueil"
    dumped = config.model_dump(by_alias=True)
    assert dumped["pages"][1]["name"] == "Détails"


def test_pages_optional_defaults_empty():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.pages == []


def test_variables_round_trip():
    payload = _valid_payload("app")
    payload["variables"] = [
        {"id": "v1", "name": "message", "initialValue": "salut"},
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.variables) == 1
    assert config.variables[0].name == "message"
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == "salut"


def test_variables_optional_defaults_empty():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.variables == []


def test_layout_item_visible_when_round_trip():
    payload = _valid_payload("app")
    payload["layout"]["items"][0]["visibleWhen"] = "vars.x == 'a'"
    config = BuilderConfig.model_validate(payload)
    assert config.layout.items[0].visibleWhen == "vars.x == 'a'"
    dumped = config.model_dump(by_alias=True)
    assert dumped["layout"]["items"][0]["visibleWhen"] == "vars.x == 'a'"


def test_layout_item_visible_when_optional():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.layout.items[0].visibleWhen is None


def test_message_when_round_trip():
    payload = _valid_payload("app")
    payload["messages"][0]["when"] = "record.nom == 'A'"
    config = BuilderConfig.model_validate(payload)
    assert config.messages[0].when == "record.nom == 'A'"
    dumped = config.model_dump(by_alias=True)
    assert dumped["messages"][0]["when"] == "record.nom == 'A'"


def test_message_when_optional():
    config = BuilderConfig.model_validate(_valid_payload())
    assert config.messages[0].when is None


def test_variable_type_defaults_to_string():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "message", "initialValue": "salut"}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].type == "string"
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["type"] == "string"


def test_variable_type_number_round_trips_non_string_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "count", "type": "number", "initialValue": 42}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == 42
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == 42


def test_variable_type_bool_round_trips_bool_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "gate", "type": "bool", "initialValue": True}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue is True


def test_variable_type_record_round_trips_dict_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "selected", "type": "record", "initialValue": {"nom": "A"}}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == {"nom": "A"}
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == {"nom": "A"}


def test_variable_type_list_round_trips_list_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "items", "type": "list", "initialValue": [1, 2, 3]}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == [1, 2, 3]


def test_navigation_mode_round_trips():
    payload = _valid_payload("app")
    payload["navigationMode"] = "story"
    config = BuilderConfig.model_validate(payload)
    assert config.navigationMode == "story"
    dumped = config.model_dump(by_alias=True)
    assert dumped["navigationMode"] == "story"


def test_navigation_mode_defaults_to_tabs():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.navigationMode == "tabs"


def test_navigation_mode_rejects_unknown_value():
    payload = _valid_payload("app")
    payload["navigationMode"] = "carousel"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_page_on_enter_round_trips_with_payload():
    payload = _valid_payload("app")
    payload["pages"] = [
        {
            "id": "p1",
            "name": "Chapitre 1",
            "layout": payload["layout"],
            "onEnter": [
                {
                    "id": "oe1",
                    "from": "p1",
                    "event": "enter",
                    "to": "map",
                    "action": "flyTo",
                    "payload": {"center": [2.35, 48.85]},
                    "when": None,
                }
            ],
        }
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.pages[0].onEnter) == 1
    assert config.pages[0].onEnter[0].payload == {"center": [2.35, 48.85]}
    dumped = config.model_dump(by_alias=True)
    assert dumped["pages"][0]["onEnter"][0]["payload"] == {"center": [2.35, 48.85]}
    # from est bien re-sérialisé sous son alias, comme les messages de wiring
    assert dumped["pages"][0]["onEnter"][0]["from"] == "p1"


def test_page_on_enter_defaults_empty():
    payload = _valid_payload("app")
    payload["pages"] = [{"id": "p1", "name": "Chapitre 1", "layout": payload["layout"]}]
    config = BuilderConfig.model_validate(payload)
    assert config.pages[0].onEnter == []


def test_interactions_round_trips():
    payload = _valid_payload("app")
    payload["interactions"] = "auto"
    config = BuilderConfig.model_validate(payload)
    assert config.interactions == "auto"
    dumped = config.model_dump(by_alias=True)
    assert dumped["interactions"] == "auto"


def test_interactions_defaults_to_none():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.interactions is None


def test_interactions_rejects_unknown_value():
    payload = _valid_payload("app")
    payload["interactions"] = "sometimes"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)
