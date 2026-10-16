# SPDX-License-Identifier: Apache-2.0
"""Lot 9 : op expérimentales (flag CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED)."""

import pytest

from app.configs.schemas import PipelinePayload
from app.pipelines.ops.contracts import EXPERIMENTAL_OPS, OPERATIONS, ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, _prepare

FLAG = "CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED"


def test_contract_flag_matches_registry():
    assert EXPERIMENTAL_OPS <= OPERATIONS.keys()
    assert {op for op, c in OPERATIONS.items() if c.experimental} == EXPERIMENTAL_OPS
    # Les op simples et celles testées contre un vrai service restent stables.
    for op in ("transform.filter", "reader.connector.postgres", "reader.connector.rest"):
        assert not OPERATIONS[op].experimental


def test_catalog_hides_experimental_ops_by_default(monkeypatch):
    monkeypatch.setenv(FLAG, "false")
    catalog = ops_catalog()
    assert not EXPERIMENTAL_OPS & catalog.keys()
    assert catalog["transform.filter"]["experimental"] is False


def test_catalog_exposes_experimental_ops_when_enabled(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    catalog = ops_catalog()
    assert catalog["writer.slack"]["experimental"] is True
    assert catalog["transform.filter"]["experimental"] is False


def test_flag_defaults_to_false_when_unset(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert "writer.slack" not in ops_catalog()


def _payload(op: str) -> PipelinePayload:
    return PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.collection",
                    "params": {"collectionId": "c"},
                },
                {"id": "w1", "kind": "writer", "op": op, "params": {}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )


def test_execution_refuses_stored_experimental_node_when_flag_off(monkeypatch):
    monkeypatch.setenv(FLAG, "false")
    with pytest.raises(PipelineRuntimeError, match="Opération expérimentale désactivée"):
        _prepare(None, None, _payload("writer.slack"), tenant_id="t", user=None, base_uri="")  # type: ignore[arg-type]
