# SPDX-License-Identifier: Apache-2.0
import pytest

from app.copilot.llm_provider import (
    FakeLLMProvider, LLMTurn, ToolCall, get_llm_provider,
)


def test_fake_provider_returns_scripted_responses_in_order():
    provider = FakeLLMProvider(responses=[
        LLMTurn(text="", tool_calls=[ToolCall(id="1", name="search_catalog", arguments={"q": "x"})]),
        LLMTurn(text="Voici le résultat."),
    ])
    first = provider.chat(messages=[], tools=[])
    assert first.tool_calls[0].name == "search_catalog"
    second = provider.chat(messages=[], tools=[])
    assert second.text == "Voici le résultat."


def test_fake_provider_repeats_last_response_once_exhausted():
    provider = FakeLLMProvider(responses=[LLMTurn(text="unique")])
    provider.chat(messages=[], tools=[])
    again = provider.chat(messages=[], tools=[])
    assert again.text == "unique"


def test_get_llm_provider_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


def test_get_llm_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValueError, match="unknown CORE_LLM_PROVIDER"):
        get_llm_provider()


def test_openai_compatible_provider_parses_tool_calls(monkeypatch):
    import httpx

    from app.copilot.llm_provider import OpenAICompatibleLLMProvider

    def fake_post(url, *, headers, json, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "function": {"name": "search_catalog", "arguments": '{"q": "incidents"}'},
                        }],
                    },
                }],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OpenAICompatibleLLMProvider(api_url="https://example/v1/chat", api_key="test-key", model="gpt-4o-mini")
    turn = provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert turn.tool_calls == [ToolCall(id="call_1", name="search_catalog", arguments={"q": "incidents"})]


def test_openai_compatible_provider_sends_tools_in_openai_shape(monkeypatch):
    """Les outils sont déclarés côté MCP/shell en forme {name, description,
    inputSchema} ; l'API chat-completions attend {name, description,
    parameters}. Un `inputSchema` laissé tel quel fait rejeter la requête
    (400) par un vrai fournisseur, à chaque tour (il y a toujours au moins
    les 6 outils MCP de l'allowlist)."""
    import json as json_module

    import httpx

    from app.copilot.llm_provider import OpenAICompatibleLLMProvider

    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured["payload"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    input_schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    provider = OpenAICompatibleLLMProvider(api_url="https://example/v1/chat", api_key="test-key", model="gpt-4o-mini")
    provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "search_catalog", "description": "Cherche.", "inputSchema": input_schema}],
    )

    tool = captured["payload"]["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "search_catalog"
    assert tool["function"]["description"] == "Cherche."
    assert tool["function"]["parameters"] == input_schema
    assert "inputSchema" not in json_module.dumps(captured["payload"])


def test_openai_compatible_provider_tolerates_tools_without_description_or_schema(monkeypatch):
    import httpx

    from app.copilot.llm_provider import OpenAICompatibleLLMProvider

    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured["payload"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OpenAICompatibleLLMProvider(api_url="https://example/v1/chat", api_key="test-key", model="gpt-4o-mini")
    provider.chat(messages=[], tools=[{"name": "addWidget"}])

    tool = captured["payload"]["tools"][0]["function"]
    assert tool == {"name": "addWidget", "description": "", "parameters": {"type": "object", "properties": {}}}
