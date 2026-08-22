# SPDX-License-Identifier: Apache-2.0
"""Round-trip du popup dans une config de carte (spec SP-24 §3.3). Pydantic
ignore les champs inconnus par défaut : sans ces champs sur MapLayer, un popup
sauvegardé serait perdu en silence — c'est le défaut que SP-17a avait trouvé
sur printLayout."""

from app.configs.schemas import BuilderConfig

BASE = {
    "kind": "map",
    "map": {
        "basemap": {"style": "s"},
        "view": {"center": [2.0, 46.0], "zoom": 5},
        "layers": [],
    },
}


def _layer(**extra):
    payload = {
        **BASE,
        "map": {
            **BASE["map"],
            "layers": [
                {
                    "id": "l1",
                    "title": "Communes",
                    "visible": True,
                    "kind": "vector",
                    "tilesUrl": "http://core/collections/communes/tiles/{z}/{x}/{y}.mvt",
                    "sourceLayer": "communes",
                    **extra,
                }
            ],
        },
    }
    return BuilderConfig.model_validate(payload).map.layers[0]


def test_a_field_list_popup_round_trips():
    layer = _layer(
        popup={
            "titleField": "nom",
            "fields": [{"name": "code_insee", "label": "Code INSEE"}, {"name": "population"}],
        }
    )
    assert layer.popup.titleField == "nom"
    assert [f.name for f in layer.popup.fields] == ["code_insee", "population"]
    assert layer.popup.fields[0].label == "Code INSEE"
    assert layer.popup.fields[1].label is None


def test_a_template_popup_round_trips():
    layer = _layer(popup={"template": "## ${nom}\n\n${population} habitants"})
    assert layer.popup.template == "## ${nom}\n\n${population} habitants"


def test_the_collection_binding_round_trips():
    layer = _layer(collectionId="communes", geometryKind="polygon", pkColumn="id")
    assert (layer.collectionId, layer.geometryKind, layer.pkColumn) == (
        "communes",
        "polygon",
        "id",
    )


def test_an_unknown_geometry_kind_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _layer(geometryKind="raster")


def test_a_layer_without_popup_stays_valid():
    assert _layer().popup is None
