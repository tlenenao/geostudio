"""Génération d'AppConfig pour create_form_app (SP-7 Task 10) — pure, sans
DB. Sert aussi de test de non-régression structurel pour le mapping
schéma->champs, dupliqué côté TS dans
shell/src/builder/widgets/form.tsx::fieldsFromSchema (même risque de dérive
que CEL, arbitrage A8 — voir spec §Architecture MCP v1)."""
from app.mcp.form_app import build_config, form_fields_from_schema

SCHEMA = {
    "collection": "incidents", "pk": "id",
    "geometry": {"column": "geom", "type": "Point", "srid": 4326},
    "fields": [
        {"name": "titre", "type": "string", "required": True, "maxLength": 200},
        {"name": "gravite", "type": "enum", "required": False, "values": ["faible", "haute"]},
    ],
}


def test_form_fields_from_schema_maps_every_field_visible_and_unordered_by_default():
    fields = form_fields_from_schema(SCHEMA)
    assert fields == [
        {"name": "titre", "type": "string", "label": "titre", "order": 0,
         "hidden": False, "required": True, "maxLength": 200},
        {"name": "gravite", "type": "enum", "label": "gravite", "order": 1,
         "hidden": False, "required": False, "values": ["faible", "haute"]},
    ]


def test_build_config_with_form_includes_form_map_table_and_message():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=True)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["form", "map", "table"]
    assert len(config.messages) == 1
    assert config.messages[0].event == "itemSelected"
    assert config.messages[0].action == "loadRecord"
    table_item = next(i for i in config.layout.items if i.widget == "table")
    assert table_item.props["columns"] == ["titre", "gravite"]


def test_build_config_without_form_has_only_map_and_table():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=False)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["map", "table"]
    assert config.messages == []
