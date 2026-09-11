# SPDX-License-Identifier: Apache-2.0
"""generate_visual_query (GAP-17) — génère filtres/jointure/résumé
structurés, jamais de SQL à redécompiler (spec §1.5/§2.7 : les ponts
compileFilterRowsToSql/decompileMetrics existants sont best-effort et
couplés à leur propre émetteur, pas réutilisés pour le LLM)."""

import json

import pytest

from app.copilot.llm_provider import LLMTurn
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)

pytestmark = pytest.mark.postgis

# Contrairement à generate_sql_query (Task 2), generate_visual_query n'exige
# aucun privilège au-delà de la lecture de la collection (spec §1.9) — pas
# de _grant_sql_lab_access ici, le mock user par défaut (rôle Lecteur, zéro
# privilège) doit déjà pouvoir appeler cet outil sur une collection publique.


class _StubLLMProvider:
    def __init__(self, text):
        self._text = text

    async def chat(self, messages, tools):
        return LLMTurn(text=self._text)


def test_generates_filters_only(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    payload = json.dumps(
        {
            "filters": [{"column": "titre", "operator": "eq", "value": "Nid de poule"}],
            "join": None,
            "summary": None,
        }
    )
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        result = call_tool(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "les nids de poule"},
        )
    assert result == {
        "filters": [{"column": "titre", "operator": "eq", "value": "Nid de poule"}],
        "join": None,
        "summary": None,
    }


def test_strips_markdown_code_fences(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    payload = '```json\n{"filters": [], "join": null, "summary": null}\n```'
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        result = call_tool(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "tout"},
        )
    assert result == {"filters": [], "join": None, "summary": None}


def test_generates_a_summary_with_a_valid_metric(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    payload = json.dumps(
        {
            "filters": [],
            "join": None,
            "summary": {
                "groupBy": ["titre"],
                "metrics": [
                    {"alias": "total", "function": "count", "sourceColumn": None, "p": None}
                ],
            },
        }
    )
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        result = call_tool(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "compte par titre"},
        )
    assert result["summary"] == {
        "groupBy": ["titre"],
        "metrics": [{"alias": "total", "function": "count", "sourceColumn": None, "p": None}],
    }


def test_errors_on_non_json_response(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider("ceci n'est pas du JSON"),
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "x"},
        )
    assert "JSON" in error_text


def test_errors_on_invalid_operator(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    payload = json.dumps(
        {
            "filters": [{"column": "titre", "operator": "startswith", "value": "N"}],
            "join": None,
            "summary": None,
        }
    )
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "x"},
        )
    assert error_text  # message Pydantic court, contenu non figé au caractère près


def test_errors_on_unknown_column(app_client, monkeypatch):  # noqa: F811
    collection_id = _register_incidents_collection(app_client)
    payload = json.dumps(
        {
            "filters": [{"column": "colonne_inexistante", "operator": "eq", "value": "x"}],
            "join": None,
            "summary": None,
        }
    )
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "x"},
        )
    assert "colonne_inexistante" in error_text


def test_never_creates_a_pipeline_or_collection(app_client, monkeypatch):  # noqa: F811
    """Critère d'acceptation : génération pure, jamais de création.

    Note d'exécution (piège CLAUDE.md n°3) : le brief de tâche visait
    `app.pipelines.service.create_pipeline_item`, qui n'existe pas dans ce
    dépôt (`grep` vide) — le chokepoint réel de création d'un item/config
    (pipeline compris, REST comme MCP `create_item`) est
    `app.configs.service.create_config_service`. C'est lui qu'il faut
    garder pour prouver l'absence de création.
    """
    import app.configs.service as configs_service

    monkeypatch.setattr(
        configs_service,
        "create_config_service",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("create_config_service must never be called")
        ),
    )
    collection_id = _register_incidents_collection(app_client)
    payload = json.dumps({"filters": [], "join": None, "summary": None})
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider(payload)
    )
    with app_client:
        call_tool(
            app_client,
            "generate_visual_query",
            {"baseCollectionId": collection_id, "question": "x"},
        )
