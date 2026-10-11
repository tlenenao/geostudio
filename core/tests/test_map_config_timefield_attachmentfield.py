# SPDX-License-Identifier: Apache-2.0
"""REV-356 / ARC-09a : `MapLayer.timeField` et `PopupConfig.attachmentField`, émis
par le shell (REV-304, SP-40), sont acceptés à l'écriture et round-trippent."""

from app.configs.schemas import BuilderConfig, MapLayer, PopupConfig


def _config(layer: dict) -> dict:
    return {
        "kind": "map",
        "map": {
            "basemap": {"style": "s"},
            "view": {"center": [2.0, 46.0], "zoom": 5},
            "layers": [layer],
        },
    }


def test_maplayer_accepts_timefield():
    MapLayer.model_validate({"id": "l", "title": "t", "kind": "vector", "timeField": "d"})


def test_popupconfig_accepts_attachmentfield():
    PopupConfig.model_validate({"attachmentField": "f"})


def test_timefield_and_attachmentfield_round_trip_through_builderconfig():
    layer = {
        "id": "l1",
        "title": "Communes",
        "visible": True,
        "kind": "vector",
        "tilesUrl": "http://core/t/{z}/{x}/{y}.mvt",
        "sourceLayer": "communes",
        "timeField": "date_creation",
        "popup": {"titleField": "nom", "attachmentField": "photos"},
    }
    cfg = BuilderConfig.model_validate(_config(layer))
    dumped = cfg.model_dump(mode="json", exclude_none=True)["map"]["layers"][0]
    assert dumped["timeField"] == "date_creation"
    assert dumped["popup"]["attachmentField"] == "photos"
    # Relecture identique : re-valider la sortie donne la même config.
    again = BuilderConfig.model_validate(_config(dumped)).model_dump(mode="json", exclude_none=True)
    assert again["map"]["layers"][0] == dumped


def test_put_map_with_timefield_cluster_and_attachmentfield_is_200_and_reads_back(
    monkeypatch, tmp_path
):
    """Critère ARC-09a/ARC-01 : PUT carte -> 200, relecture identique (pas de 422)."""
    from fastapi.testclient import TestClient

    from app.db import init_db, make_engine
    from app.main import create_app

    url = f"sqlite+pysqlite:///{tmp_path / 'map_fields.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    client = TestClient(create_app())
    client.headers["Authorization"] = "Bearer mock:alice"
    layers = [
        {
            "id": "v",
            "title": "V",
            "visible": True,
            "kind": "vector",
            "tilesUrl": "https://core.test/t/{z}/{x}/{y}.mvt",
            "sourceLayer": "s",
            "timeField": "d",
            "popup": {"attachmentField": "photos"},
        },
        {
            "id": "f",
            "title": "F",
            "visible": True,
            "kind": "feature",
            "url": "https://fs.test/u.geojson",
            "renderAs": "circle",
            "cluster": {"radius": 70, "maxZoom": 11, "label": False},
        },
    ]
    cfg = _config(layers[0])
    cfg["map"]["layers"] = layers
    r = client.post("/v1/configs", json={"title": "Carte", "config": cfg})
    assert r.status_code == 201, r.text
    created = r.json()
    put = client.put(f"/v1/configs/by-item/{created['itemId']}", json=cfg)
    assert put.status_code == 200, put.text
    got = client.get(f"/v1/configs/by-item/{created['itemId']}").json()["config"]["map"]["layers"]
    assert got[0]["timeField"] == "d"
    assert got[0]["popup"]["attachmentField"] == "photos"
    assert got[1]["cluster"] == {"radius": 70, "maxZoom": 11, "label": False}
