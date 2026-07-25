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
