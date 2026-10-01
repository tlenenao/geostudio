# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import BuilderConfig


def test_message_id_survives_round_trip():
    # P10.01 : sans champ `id`, pydantic le jetait et deux actions devenaient indiscernables.
    cfg = BuilderConfig.model_validate(
        {
            "kind": "app",
            "layout": {"type": "grid", "items": []},
            "messages": [
                {"id": "a", "from": "f", "event": "changed", "to": "var:v1", "action": "set"},
                {"id": "b", "from": "f", "event": "changed", "to": "var:v2", "action": "set"},
            ],
        }
    )
    data = cfg.model_dump(by_alias=True)
    assert [m["id"] for m in data["messages"]] == ["a", "b"]
