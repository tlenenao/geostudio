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
