## Task 3: Core — `llm_provider.py`

**Files:**
- Create: `core/app/copilot/__init__.py` (empty)
- Create: `core/app/copilot/llm_provider.py`
- Create: `core/tests/test_copilot_llm_provider.py`

**Interfaces:**
- Produces: `LLMProvider` (Protocol), `LLMTurn`, `ToolCall`, `FakeLLMProvider`, `OpenAICompatibleLLMProvider`, `get_llm_provider() -> LLMProvider`, all in `app.copilot.llm_provider`. Consumed by Task 5's `routes.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_copilot_llm_provider.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.copilot'`.

- [ ] **Step 3: Implement**

Create `core/app/copilot/__init__.py` (empty file).

Create `core/app/copilot/llm_provider.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Fournisseur LLM enfichable pour le copilote (SP-20), même convention que
app.search.providers.EmbeddingProvider (SP-7) : un provider HTTP compatible
OpenAI pour la production, un provider déterministe sans réseau pour
dev/test/mock (CORE_LLM_PROVIDER=fake, ou absent)."""
import json
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn: ...


class FakeLLMProvider:
    """Réponses scriptées, consommées dans l'ordre ; la dernière est
    réutilisée si l'appelant en demande plus qu'il n'y en a — permet de
    scripter une boucle multi-tours (ex. un tool_call puis une réponse
    texte) sans dépendre du contenu réel des messages."""

    def __init__(self, responses: list[LLMTurn] | None = None):
        self._responses = responses or [LLMTurn(text="(réponse simulée)")]
        self._i = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        turn = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return turn


class OpenAICompatibleLLMProvider:
    def __init__(self, *, api_url: str, api_key: str, model: str):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        openai_tools = [{"type": "function", "function": t} for t in tools]
        response = httpx.post(
            self._api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": messages, "tools": openai_tools},
            timeout=30.0,
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"]["arguments"] or "{}"),
            )
            for tc in choice.get("tool_calls") or []
        ]
        return LLMTurn(text=choice.get("content") or "", tool_calls=tool_calls)


def get_llm_provider() -> LLMProvider:
    kind = os.environ.get("CORE_LLM_PROVIDER")
    if kind is None or kind == "fake":
        return FakeLLMProvider()
    if kind == "openai":
        return OpenAICompatibleLLMProvider(
            api_url=os.environ["CORE_LLM_API_URL"],
            api_key=os.environ["CORE_LLM_API_KEY"],
            model=os.environ.get("CORE_LLM_MODEL", "gpt-4o-mini"),
        )
    raise ValueError(f"unknown CORE_LLM_PROVIDER: {kind}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_llm_provider.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Commit**

```bash
git add core/app/copilot/__init__.py core/app/copilot/llm_provider.py core/tests/test_copilot_llm_provider.py
git commit -m "$(cat <<'EOF'
feat(core): fournisseur LLM enfichable pour le copilote (SP-20)

LLMProvider (Protocol) + FakeLLMProvider (scriptable, tests/mock) +
OpenAICompatibleLLMProvider (CORE_LLM_PROVIDER=openai), même patron que
app.search.providers.EmbeddingProvider (SP-7).
EOF
)"
```

---

