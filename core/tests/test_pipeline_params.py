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


_EVIL = "1 OR 1=1; --"


@pytest.mark.parametrize(
    "op",
    [
        "reader.connector.postgres",
        "reader.connector.snowflake",
        "reader.connector.bigquery",
        "reader.connector.mssql",
        "reader.connector.oracle",
        "reader.connector.databricks",
    ],
)
def test_param_in_native_connector_query_is_refused_at_validation(op):
    """Injection : la requête native d'un connecteur n'est jamais paramétrable."""
    with pytest.raises(ValidationError, match="interdit"):
        PipelinePayload.model_validate(
            {
                "parameters": [{"name": "x", "type": "string", "default": _EVIL}],
                "nodes": [
                    {
                        "id": "r",
                        "kind": "reader",
                        "op": op,
                        "params": {
                            "secretName": "s",
                            "query": "SELECT * FROM t WHERE a = {{param.x}}",
                        },
                    },
                    {
                        "id": "w",
                        "kind": "writer",
                        "op": "writer.collection",
                        "params": {"collectionId": "d"},
                    },
                ],
                "edges": [{"id": "e", "from": "r", "to": "w"}],
            }
        )


@pytest.mark.parametrize("key", ["valueExpr", "urlExpr", "headersExpr", "bodyExpr"])
def test_param_in_http_call_expression_keys_is_an_escaped_literal(key):
    value = _EVIL + "' OR 'a'='a"
    p = _payload(
        [{"name": "x", "type": "string", "default": value}],
        {key: "concat('v=', {{param.x}})"},
        op="transform.httpCall",
    )
    applied = apply_params(p, resolve_params(p.parameters, {}))
    out = applied.nodes[1].params[key]
    # la valeur reste UN littéral : guillemets doublés, rien ne sort de la chaîne
    assert out == "concat('v=', '1 OR 1=1; --'' OR ''a''=''a')"
    assert duckdb.connect().execute(f"SELECT {out}").fetchone() == ("v=" + value,)


def _node_payload(op, params):
    kind = "reader" if op.startswith("reader") else "writer"
    nodes = [
        {"id": "r", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "c"}},
        {"id": "w", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "d"}},
    ]
    nodes[0 if kind == "reader" else 1] = {"id": "n", "kind": kind, "op": op, "params": params}
    return PipelinePayload.model_validate(
        {
            "parameters": [{"name": "p", "type": "string", "default": "/etc/passwd"}],
            "nodes": nodes,
            "edges": [{"id": "e", "from": nodes[0]["id"], "to": nodes[1]["id"]}],
        }
    )


@pytest.mark.parametrize("op", ["reader.file", "writer.file"])
def test_param_in_file_path_is_refused(op):
    """Un paramètre de run ne pilote jamais un chemin du disque du worker."""
    with pytest.raises(ValidationError, match="interdit"):
        _node_payload(op, {"path": "{{param.p}}"})


def test_param_in_blob_path_is_still_allowed():
    p = _node_payload("reader.connector.blob", {"secretName": "s", "path": "{{param.p}}"})
    applied = apply_params(p, resolve_params(p.parameters, {"p": "data/a.csv"}))
    assert applied.nodes[0].params["path"] == "data/a.csv"


def test_defense_in_depth_refuses_file_path_substitution_at_runtime():
    p = _payload([{"name": "p", "type": "string", "default": "/etc/passwd"}], {"x": 1})
    # contourne la validation : le nœud est modifié après coup
    p.nodes[1] = p.nodes[1].model_copy(
        update={"op": "reader.file", "params": {"path": "{{param.p}}"}}
    )
    with pytest.raises(PipelineParamError):
        apply_params(p, resolve_params(p.parameters, {}))


def test_injected_collection_id_is_a_plain_value_resolved_by_lookup():
    """collectionId paramétré : valeur injectée jamais interprétée (recherche par id)."""
    from app.db import init_db, make_engine, make_session_factory
    from app.pipelines import runtime
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    evil = "villes'; DROP TABLE villes; --"
    p = _node_payload("reader.collection", {"collectionId": "{{param.p}}"})
    applied = apply_params(p, resolve_params(p.parameters, {"p": evil}))
    assert applied.nodes[0].params["collectionId"] == evil
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="u",
            username="u",
            email=None,
            first_name="",
            last_name="",
        )
        with pytest.raises(runtime.PipelineRuntimeError, match="not found"):
            runtime._require_readable_collection_id(
                session, tenant_id=tenant.id, user=user, collection_id=evil
            )


@pytest.mark.parametrize(
    "params",
    [
        {"collectionId": "d", "mode": "{{param.p}}"},
        {"collectionId": "d", "mode": "upsert", "keyColumns": ["{{param.p}}"]},
        {"collectionId": "d", "keyColumns": ["id"], "statusColumn": "{{param.p}}"},
        {"collectionId": "d", "rejectWhenFalse": ["{{param.p}}"]},
        {"collectionId": "d", "onInvalid": "{{param.p}}"},
    ],
)
def test_param_in_writer_collection_mode_keys_is_refused(params):
    """K1×K2 (intégration vague 4) : les paramètres F1/F2 de writer.collection (mode,
    clés, colonne de statut, rejets) sont des identifiants/contrôles, jamais paramétrables."""
    with pytest.raises(ValidationError, match="interdit"):
        _node_payload("writer.collection", params)


def test_param_in_non_whitelisted_key_is_refused():
    with pytest.raises(ValidationError, match="interdit"):
        _payload([{"name": "x", "type": "string", "default": "a"}], {"anything": "{{param.x}}"})
