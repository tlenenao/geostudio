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
