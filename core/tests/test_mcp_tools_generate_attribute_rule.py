# SPDX-License-Identifier: Apache-2.0
"""generate_attribute_rule (ARC-14) — brouillon de règle CEL relu par un humain, jamais
écrit par l'outil (même patron que generate_cel_expression)."""

import json

import pytest

from app.collections import repository as collections_repo
from app.copilot.llm_provider import LLMTurn
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)

pytestmark = pytest.mark.postgis

GOOD = {
    "id": "titre-non-vide",
    "field": "titre",
    "expression": "size(titre) > 0",
    "message": "Le titre est obligatoire.",
}


class _Stub:
    def __init__(self, payload):
        self._text = payload if isinstance(payload, str) else json.dumps(payload)
        self.prompts: list[str] = []

    async def chat(self, messages, tools):
        self.prompts.append(messages[0]["content"])
        return LLMTurn(text=self._text)


def _call(app_client, monkeypatch, payload, **over):  # noqa: F811
    stub = _Stub(payload)
    monkeypatch.setattr("app.mcp.tools.query_generation.get_llm_provider", lambda: stub)
    cid = _register_incidents_collection(app_client)
    args = {"collectionId": cid, "question": "le titre ne doit pas être vide", **over}
    return cid, stub, args


def test_returns_a_reviewable_draft_and_writes_nothing(app_client, monkeypatch):  # noqa: F811
    cid, stub, args = _call(app_client, monkeypatch, f"```json\n{json.dumps(GOOD)}\n```")
    with app_client:
        result = call_tool(app_client, "generate_attribute_rule", args)
    assert result["rule"]["expression"] == "size(titre) > 0"
    assert result["rule"]["kind"] == "constraint"
    assert "titre" in stub.prompts[0]
    with app_client.session_factory() as session:  # jamais d'écriture automatique
        col = collections_repo.get_collection(
            session, tenant_id=app_client.tenant.id, collection_id=cid
        )
        assert col.attribute_rules == []


@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        ({**GOOD, "expression": "size(inconnu) > 0"}, "champs inconnus"),
        ({**GOOD, "expression": "size(titre) >"}, "invalid CEL"),
        ({**GOOD, "field": "nope"}, "unknown field"),
        ({**GOOD, "message": ""}, "mal formée"),
        ("pas du json", "non-JSON"),
    ],
)
def test_rejects_a_bad_draft(app_client, monkeypatch, payload, needle):  # noqa: F811
    _cid, _stub, args = _call(app_client, monkeypatch, payload)
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_attribute_rule", args)
    assert needle in error
