# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""generate_cel_expression (REV-183) — brouillon CEL pour visibleWhen. Génération
pure : n'écrit ni n'exécute jamais rien (même patron que generate_sql_query)."""

import asyncio

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from app.copilot.egress import EgressBlockedError
from app.copilot.llm_provider import LLMTurn
from app.mcp.tools import register_tools
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import (  # noqa: F401
    _seed_item,
    app_client,
    call_tool,
    call_tool_expecting_error,
)

FIELDS = ["vars.statut", "user.name"]


class _StubLLMProvider:
    def __init__(self, text):
        self._text = text
        self.prompts: list[str] = []

    async def chat(self, messages, tools):
        self.prompts.append(messages[0]["content"])
        return LLMTurn(text=self._text)


class _FailingLLMProvider:
    def __init__(self, exc):
        self._exc = exc

    async def chat(self, messages, tools):
        raise self._exc


def _stub(monkeypatch, provider):
    monkeypatch.setattr("app.mcp.tools.query_generation.get_llm_provider", lambda: provider)


def _args(item_id, **over):
    base = {"itemId": item_id, "question": "visible si le statut est ouvert"}
    return {**base, "availableFields": FIELDS, **over}


def test_schema_declares_item_question_and_fields():
    server = FastMCP("schema")
    register_tools(server, None)
    tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "generate_cel_expression")
    schema = tool.inputSchema
    assert set(schema["required"]) == {"itemId", "question", "availableFields"}
    assert schema["properties"]["itemId"]["type"] == "string"
    assert schema["properties"]["question"]["type"] == "string"
    assert schema["properties"]["availableFields"]["type"] == "array"
    assert schema["properties"]["availableFields"]["items"] == {"type": "string"}


def test_generates_a_fenced_expression_and_lists_fields_in_the_prompt(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    provider = _StubLLMProvider('```cel\nvars.statut == "ouvert"\n```')
    _stub(monkeypatch, provider)
    with app_client:
        result = call_tool(app_client, "generate_cel_expression", _args(item_id))
    assert result == {"expression": 'vars.statut == "ouvert"'}
    assert "vars.statut" in provider.prompts[0] and "user.name" in provider.prompts[0]


def test_refuses_an_item_the_caller_cannot_see(app_client, monkeypatch):
    with app_client.session_factory() as session:
        other = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="other-sub",
            username="other",
            email=None,
            first_name="O",
            last_name="T",
        )
        session.commit()
        other_id = other.id
    item_id = _seed_item(app_client, owner_id=other_id)
    _stub(monkeypatch, _StubLLMProvider("true"))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "item not found" in error


def test_rejects_a_syntactically_broken_draft(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("vars.statut =="))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "expression CEL invalide" in error


def test_rejects_a_draft_referencing_an_unknown_field(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider('vars.inconnu == "x" && user.name == "a"'))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "champs inconnus dans l'expression : vars.inconnu" in error


@pytest.mark.parametrize(
    "draft",
    [
        'vars . inconnu == "x"',
        'vars\n.inconnu == "x"',
        'vars["inconnu"] == "x"',
        "record['inconnu'] == 1",
        'user ["inconnu"] == "a"',
    ],
)
def test_rejects_unknown_field_via_spaced_or_bracket_form(app_client, monkeypatch, draft):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "champs inconnus dans l'expression" in error
    assert ".inconnu" in error


@pytest.mark.parametrize("draft", ["vars[x] == 1", "user[vars.statut] == 1"])
def test_rejects_non_literal_index(app_client, monkeypatch, draft):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "champs inconnus dans l'expression" in error


def test_accepts_known_field_via_spaced_and_bracket_forms(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    draft = 'vars . statut == "a" && vars ["statut"] != "b"'
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        result = call_tool(app_client, "generate_cel_expression", _args(item_id))
    assert result == {"expression": draft}


def test_empty_llm_answer_is_an_error(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("   "))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "aucune expression" in error


def test_llm_egress_failures_become_a_generic_refusal(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    with app_client:  # un TestClient ne se réentre pas : un seul bloc, boucle dedans
        for exc in (EgressBlockedError("10.0.0.1"), httpx.ConnectError("boom")):
            _stub(monkeypatch, _FailingLLMProvider(exc))
            error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
            assert "le fournisseur LLM est indisponible" in error
            assert "10.0.0.1" not in error


def test_bounds_question_and_field_list(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("true"))
    with app_client:
        long_q = call_tool_expecting_error(
            app_client, "generate_cel_expression", _args(item_id, question="x" * 2001)
        )
        many = call_tool_expecting_error(
            app_client,
            "generate_cel_expression",
            _args(item_id, availableFields=[f"vars.v{i}" for i in range(201)]),
        )
    assert "question trop longue" in long_q
    assert "trop de champs" in many


def test_computed_column_context_accepts_record_field_and_refuses_unknown(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    args = _args(item_id, availableFields=["record.population"], context="computedColumn")
    _stub(monkeypatch, _StubLLMProvider("record.population * 2"))
    with app_client:
        assert call_tool(app_client, "generate_cel_expression", args) == {
            "expression": "record.population * 2"
        }
        _stub(monkeypatch, _StubLLMProvider("record.inconnu * 2"))
        error = call_tool_expecting_error(app_client, "generate_cel_expression", args)
    assert "record.inconnu" in error


def test_record_root_refused_outside_computed_column(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("record.population > 1"))
    with app_client:
        error = call_tool_expecting_error(
            app_client,
            "generate_cel_expression",
            _args(item_id, availableFields=["record.population"]),
        )
    assert "racine non autorisée" in error


def test_action_condition_allows_ctx_root(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("ctx.selected == 1"))
    with app_client:
        result = call_tool(
            app_client,
            "generate_cel_expression",
            _args(item_id, availableFields=["ctx.selected"], context="actionCondition"),
        )
    assert result == {"expression": "ctx.selected == 1"}


def test_string_literal_is_not_a_reference(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    draft = '"vars.inconnue" == vars.statut'
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        result = call_tool(app_client, "generate_cel_expression", _args(item_id))
    assert result == {"expression": draft}


@pytest.mark.parametrize(
    "draft", ['vars["inconnu"]["b"] == 1', "vars.statut[vars.x] == 1", 'vars["statut"][x] == 1']
)
def test_chained_access_is_fully_traversed(app_client, monkeypatch, draft):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "champs inconnus dans l'expression" in error


def test_chained_known_access_passes(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    draft = 'vars["statut"]["b"][0] == 1'
    _stub(monkeypatch, _StubLLMProvider(draft))
    with app_client:
        assert call_tool(app_client, "generate_cel_expression", _args(item_id)) == {
            "expression": draft
        }
