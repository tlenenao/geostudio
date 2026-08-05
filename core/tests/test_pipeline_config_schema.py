# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _pipeline_body() -> dict:
    return {
        "version": 1,
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection",
                 "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection",
                 "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }


def test_pipeline_config_valide():
    config = BuilderConfig.model_validate(_pipeline_body())
    assert config.kind == "pipeline"
    assert config.pipeline.nodes[0].op == "reader.collection"
    assert config.pipeline.edges[0].from_ == "r1"


def test_pipeline_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "pipeline"})


def test_pipeline_config_ids_dupliques_rejetes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][1]["id"] = "r1"
    with pytest.raises(ValidationError, match="unique"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_edge_vers_noeud_inconnu_rejetee():
    body = _pipeline_body()
    body["pipeline"]["edges"][0]["to"] = "does-not-exist"
    with pytest.raises(ValidationError, match="unknown node"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_reader_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][1]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="reader"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_writer_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][0]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="writer"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_x_y_when_acceptes_mais_inertes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][0]["x"] = 100
    body["pipeline"]["nodes"][0]["y"] = 40
    body["pipeline"]["edges"][0]["when"] = "true"
    config = BuilderConfig.model_validate(body)
    assert config.pipeline.nodes[0].x == 100
    assert config.pipeline.edges[0].when == "true"
