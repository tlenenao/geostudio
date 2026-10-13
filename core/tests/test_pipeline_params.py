# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F3 : paramètres de run publiés."""

import duckdb
import pytest
from pydantic import ValidationError

from app.configs.pipeline_params import PipelineParamError, apply_params, resolve_params
from app.configs.schemas import PipelinePayload


def _payload(parameters, params, op="transform.filter"):
    return PipelinePayload.model_validate(
        {
            "parameters": parameters,
            "nodes": [
                {
                    "id": "r",
                    "kind": "reader",
                    "op": "reader.collection",
                    "params": {"collectionId": "c"},
                },
                {"id": "t", "kind": "transform", "op": op, "params": params},
                {
                    "id": "w",
                    "kind": "writer",
                    "op": "writer.collection",
                    "params": {"collectionId": "d"},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r", "to": "t"},
                {"id": "e2", "from": "t", "to": "w"},
            ],
        }
    )


def test_required_missing_raises():
    p = _payload(
        [{"name": "n", "type": "integer", "required": True}], {"expr": "pop > {{param.n}}"}
    )
    with pytest.raises(PipelineParamError, match="requis"):
        resolve_params(p.parameters, {})


def test_default_and_type_coercion():
    p = _payload([{"name": "n", "type": "integer", "default": 5}], {"expr": "pop > {{param.n}}"})
    assert resolve_params(p.parameters, {}) == {"n": 5}
    assert resolve_params(p.parameters, {"n": "7"}) == {"n": 7}
    with pytest.raises(PipelineParamError):
        resolve_params(p.parameters, {"n": "abc"})
    with pytest.raises(PipelineParamError, match="non déclaré"):
        resolve_params(p.parameters, {"zzz": 1})


def test_unknown_reference_rejected_at_schema():
    with pytest.raises(ValidationError, match="unknown parameter"):
        _payload([], {"expr": "pop > {{param.n}}"})


def test_injection_stays_a_literal_in_real_duckdb():
    value = "x'; DROP TABLE t; --"
    p = _payload(
        [{"name": "s", "type": "string", "required": True}], {"expr": "name = {{param.s}}"}
    )
    applied = apply_params(p, resolve_params(p.parameters, {"s": value}))
    expr = applied.nodes[1].params["expr"]
    assert expr == "name = 'x''; DROP TABLE t; --'"
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t(name VARCHAR)")
    conn.execute("INSERT INTO t VALUES (?), ('ok')", [value])
    assert conn.execute(f"SELECT count(*) FROM t WHERE {expr}").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 2  # table intacte


def test_whole_string_ref_keeps_type_and_embedded_is_text():
    p = _payload(
        [{"name": "d", "type": "number", "default": 2.5}],
        {"distance": "{{param.d}}", "label": "buf-{{param.d}}"},
        op="transform.buffer",
    )
    applied = apply_params(p, resolve_params(p.parameters, {}))
    assert applied.nodes[1].params == {"distance": 2.5, "label": "buf-2.5"}


def test_no_parameters_returns_payload_unchanged():
    p = _payload([], {"expr": "true"})
    assert apply_params(p, {}) is p
