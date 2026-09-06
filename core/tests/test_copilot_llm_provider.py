# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.copilot.llm_provider import (
    FakeLLMProvider,
    LLMTurn,
    OpenAICompatibleLLMProvider,
    ToolCall,
    get_llm_provider,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _provider_on(handler) -> OpenAICompatibleLLMProvider:
    """Fournisseur câblé sur un transport factice : `chat` est asynchrone
    (l'échéance du tour doit pouvoir l'annuler, cf.
    test_copilot_routes.py), donc plus de `httpx.post` module-level à
    remplacer — on injecte le client, même couture que McpLoopbackSession."""
    return OpenAICompatibleLLMProvider(
        api_url="https://example/v1/chat",
        api_key="test-key",
        model="gpt-4o-mini",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.anyio
async def test_fake_provider_returns_scripted_responses_in_order():
    provider = FakeLLMProvider(
        responses=[
            LLMTurn(
                text="", tool_calls=[ToolCall(id="1", name="search_catalog", arguments={"q": "x"})]
            ),
            LLMTurn(text="Voici le résultat."),
        ]
    )
    first = await provider.chat(messages=[], tools=[])
    assert first.tool_calls[0].name == "search_catalog"
    second = await provider.chat(messages=[], tools=[])
    assert second.text == "Voici le résultat."


@pytest.mark.anyio
async def test_fake_provider_repeats_last_response_once_exhausted():
    provider = FakeLLMProvider(responses=[LLMTurn(text="unique")])
    await provider.chat(messages=[], tools=[])
    again = await provider.chat(messages=[], tools=[])
    assert again.text == "unique"


def test_get_llm_provider_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


def test_get_llm_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValueError, match="unknown CORE_LLM_PROVIDER"):
        get_llm_provider()


@pytest.mark.anyio
async def test_openai_compatible_provider_parses_tool_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        import json as json_module

        assert json_module.loads(request.content)["model"] == "gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "search_catalog",
                                        "arguments": '{"q": "incidents"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    turn = await _provider_on(handler).chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert turn.tool_calls == [
        ToolCall(id="call_1", name="search_catalog", arguments={"q": "incidents"})
    ]


@pytest.mark.anyio
async def test_openai_compatible_provider_sends_tools_in_openai_shape():
    """Les outils sont déclarés côté MCP/shell en forme {name, description,
    inputSchema} ; l'API chat-completions attend {name, description,
    parameters}. Un `inputSchema` laissé tel quel fait rejeter la requête
    (400) par un vrai fournisseur, à chaque tour (il y a toujours au moins
    les 6 outils MCP de l'allowlist)."""
    import json as json_module

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json_module.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    input_schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    await _provider_on(handler).chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "search_catalog", "description": "Cherche.", "inputSchema": input_schema}],
    )

    tool = captured["payload"]["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "search_catalog"
    assert tool["function"]["description"] == "Cherche."
    assert tool["function"]["parameters"] == input_schema
    assert "inputSchema" not in json_module.dumps(captured["payload"])


@pytest.mark.anyio
async def test_openai_compatible_provider_blocks_ssrf_target_when_unguarded():
    # http_client=None : chemin réellement emprunté en production, celui
    # que get_llm_provider() construit.
    provider = OpenAICompatibleLLMProvider(
        api_url="http://169.254.169.254/latest/meta-data/",
        api_key="test-key",
        model="gpt-4o-mini",
    )
    from app.copilot.egress import EgressBlockedError

    with pytest.raises(EgressBlockedError):
        await provider.chat(messages=[], tools=[])


@pytest.mark.anyio
async def test_openai_compatible_provider_tolerates_tools_without_description_or_schema():
    import json as json_module

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json_module.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    await _provider_on(handler).chat(messages=[], tools=[{"name": "addWidget"}])

    tool = captured["payload"]["tools"][0]["function"]
    assert tool == {
        "name": "addWidget",
        "description": "",
        "parameters": {"type": "object", "properties": {}},
    }
