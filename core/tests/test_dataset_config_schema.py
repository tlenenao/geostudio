# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _dataset_body(collection_id: str = "parcs") -> dict:
    return {
        "version": 1,
        "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": collection_id, "columns": {}},
    }


def test_dataset_config_valide():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.kind == "dataset"
    assert config.dataset.collectionId == "parcs"


def test_dataset_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "dataset"})


def test_dataset_config_colonnes_optionnelles():
    body = _dataset_body()
    body["dataset"]["columns"] = {"nom": {"label": "Nom", "format": "text"}}
    config = BuilderConfig.model_validate(body)
    assert config.dataset.columns["nom"].label == "Nom"
    assert config.dataset.columns["nom"].format == "text"


def test_dataset_config_time_field_and_reacts_to_extent_optional():
    body = _dataset_body()
    body["dataset"]["timeField"] = "date_releve"
    body["dataset"]["reactsToExtent"] = True
    config = BuilderConfig.model_validate(body)
    assert config.dataset.timeField == "date_releve"
    assert config.dataset.reactsToExtent is True


def test_dataset_config_time_field_and_reacts_to_extent_default():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.dataset.timeField is None
    assert config.dataset.reactsToExtent is False


def test_dataset_config_arcgis_source_valide():
    body = {
        "version": 1,
        "kind": "dataset",
        "dataset": {"source": "arcgis", "arcgisItemId": "item-1", "columns": {}},
    }
    config = BuilderConfig.model_validate(body)
    assert config.dataset.source == "arcgis"
    assert config.dataset.arcgisItemId == "item-1"
    assert config.dataset.collectionId is None


def test_dataset_config_collection_source_sans_collection_id_rejete():
    body = {"version": 1, "kind": "dataset", "dataset": {"source": "collection", "columns": {}}}
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_dataset_config_arcgis_source_sans_arcgis_item_id_rejete():
    body = {"version": 1, "kind": "dataset", "dataset": {"source": "arcgis", "columns": {}}}
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_dataset_config_arcgis_source_avec_collection_id_rejete():
    body = {
        "version": 1,
        "kind": "dataset",
        "dataset": {
            "source": "arcgis",
            "arcgisItemId": "item-1",
            "collectionId": "parcs",
            "columns": {},
        },
    }
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_dataset_config_cross_filter_links_default_empty():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.dataset.crossFilterLinks == []


def test_dataset_config_attribute_cross_filter_link():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {
            "mode": "attribute",
            "targetDatasetId": "ds-2",
            "sourceField": "commune",
            "targetField": "nom_commune",
        },
    ]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "attribute"
    assert link.targetDatasetId == "ds-2"
    assert link.sourceField == "commune"
    assert link.targetField == "nom_commune"


def test_dataset_config_spatial_cross_filter_link_defaults_to_bbox_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "spatial", "targetDatasetId": "ds-2"}]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "spatial"
    assert link.precision == "bbox"


def test_dataset_config_spatial_cross_filter_link_exact_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {"mode": "spatial", "targetDatasetId": "ds-2", "precision": "exact"},
    ]
    config = BuilderConfig.model_validate(body)
    assert config.dataset.crossFilterLinks[0].precision == "exact"


def test_dataset_config_cross_filter_link_unknown_mode_rejected():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "join", "targetDatasetId": "ds-2"}]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
