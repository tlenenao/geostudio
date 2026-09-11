# SPDX-License-Identifier: Apache-2.0
"""generate_sql_query (GAP-17) — génère un brouillon SQL en lecture seule,
n'exécute jamais rien. Réutilise le patron app_client PostGIS de
test_mcp_tools_query_features.py (introspection réelle de collection)."""

import httpx
import pytest

from app.copilot.egress import EgressBlockedError
from app.copilot.llm_provider import LLMTurn
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.users.repository import set_user_role
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)

pytestmark = pytest.mark.postgis


def _grant_sql_lab_access(app_client):  # noqa: F811
    with app_client.session_factory() as session:
        role = create_role(
            session,
            tenant_id=app_client.tenant.id,
            name="Analyste SQL",
            privileges=[Privilege.ANALYTICS_SQL_LAB_ACCESS.value],
        )
        set_user_role(
            session,
            tenant_id=app_client.tenant.id,
            user_id=app_client.mock_user.id,
            role_id=role.id,
            role_slug=role.slug,
        )
        session.commit()


class _StubLLMProvider:
    def __init__(self, text):
        self._text = text

    async def chat(self, messages, tools):
        return LLMTurn(text=self._text)


class _FailingLLMProvider:
    def __init__(self, exc):
        self._exc = exc

    async def chat(self, messages, tools):
        raise self._exc


def test_generates_sql_scoped_to_the_named_collection(app_client, monkeypatch):  # noqa: F811
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider(f'SELECT titre FROM "{collection_id}"'),
    )
    with app_client:
        result = call_tool(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert result == {"sql": f'SELECT titre FROM "{collection_id}"'}


def test_strips_markdown_code_fences(app_client, monkeypatch):  # noqa: F811
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider(f'```sql\nSELECT titre FROM "{collection_id}"\n```'),
    )
    with app_client:
        result = call_tool(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert result == {"sql": f'SELECT titre FROM "{collection_id}"'}


def test_errors_when_the_llm_returns_nothing(app_client, monkeypatch):  # noqa: F811
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider", lambda: _StubLLMProvider("   ")
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert "aucun SQL" in error_text


def test_requires_analytics_sql_lab_access_privilege(app_client, monkeypatch):  # noqa: F811
    # Pas de _grant_sql_lab_access ici : le mock user par défaut n'a que le
    # rôle Lecteur (aucun privilège), ANALYTICS_SQL_LAB_ACCESS lui manque.
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider("SELECT 1"),
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert "analytics.sql_lab.access" in error_text


def test_errors_on_unknown_collection(app_client, monkeypatch):  # noqa: F811
    _grant_sql_lab_access(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider("SELECT 1"),
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "generate_sql_query", {"collectionId": "does-not-exist", "question": "x"}
        )
    assert "not found" in error_text


def test_wraps_egress_blocked_error_into_a_clean_value_error(app_client, monkeypatch):  # noqa: F811
    """Important #2 de la revue de la Tâche 2 : le message brut de
    EgressBlockedError peut révéler des détails réseau internes (IP
    bloquée, hôte résolu) — l'appelant MCP ne doit voir qu'un message
    générique, comme app.copilot.routes le fait déjà pour le même appel."""
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _FailingLLMProvider(
            EgressBlockedError("cible réseau interne bloquée : 'internal-llm' → 10.0.0.5")
        ),
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert "10.0.0.5" not in error_text
    assert "internal-llm" not in error_text
    assert "indisponible" in error_text


def test_wraps_httpx_error_into_a_clean_value_error(app_client, monkeypatch):  # noqa: F811
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _FailingLLMProvider(httpx.ConnectTimeout("connect timed out")),
    )
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert "indisponible" in error_text


def test_never_calls_run_analyst_sql(app_client, monkeypatch):  # noqa: F811
    """Critère d'acceptation #1 de la spec : génération pure, jamais
    d'exécution — espionne run_analyst_sql et vérifie qu'il n'est jamais
    appelé pendant tout le tool call."""
    import app.analytics.sql_sandbox as sql_sandbox

    called = []
    monkeypatch.setattr(
        sql_sandbox,
        "run_analyst_sql",
        lambda *a, **k: (
            called.append(1)
            or (_ for _ in ()).throw(
                AssertionError("run_analyst_sql must never be called by generate_sql_query")
            )
        ),
    )
    _grant_sql_lab_access(app_client)
    collection_id = _register_incidents_collection(app_client)
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: _StubLLMProvider(f'SELECT titre FROM "{collection_id}"'),
    )
    with app_client:
        call_tool(
            app_client,
            "generate_sql_query",
            {"collectionId": collection_id, "question": "liste les titres"},
        )
    assert called == []
