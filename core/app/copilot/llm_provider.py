# SPDX-License-Identifier: Apache-2.0
"""Fournisseur LLM enfichable pour le copilote (SP-20), même convention que
app.search.providers.EmbeddingProvider (SP-7) : un provider HTTP compatible
OpenAI pour la production, un provider déterministe sans réseau pour
dev/test/mock (CORE_LLM_PROVIDER=fake, ou absent)."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.copilot.egress import build_guarded_async_client

# Plafond par appel, sous le budget global du tour (app.copilot.routes).
LLM_CALL_TIMEOUT_SECONDS = 30.0


class LLMNotConfiguredError(ValueError):
    """CORE_LLM_PROVIDER défini mais vide (valeur du compose par défaut)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # AUD-106 : consommation lue sur la réponse fournisseur (0 = non fournie).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


class LLMProvider(Protocol):
    # Asynchrone par contrat : un `chat` bloquant gèlerait la boucle
    # d'événements de tout le process (la stack tourne sans `--workers`) et
    # ne serait pas annulable, donc l'échéance du tour ne ferait que cesser
    # de l'attendre au lieu de l'interrompre.
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMTurn: ...


class FakeLLMProvider:
    """Réponses scriptées, consommées dans l'ordre ; la dernière est
    réutilisée si l'appelant en demande plus qu'il n'y en a — permet de
    scripter une boucle multi-tours (ex. un tool_call puis une réponse
    texte) sans dépendre du contenu réel des messages."""

    def __init__(self, responses: list[LLMTurn] | None = None):
        self._responses = responses or [LLMTurn(text="(réponse simulée)")]
        self._i = 0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        turn = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return turn


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model: str,
        http_client: httpx.AsyncClient | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        # Client injectable (même couture que McpLoopbackSession) : sinon un
        # client éphémère par appel — la réutilisation de connexion pèse
        # peu face à la latence d'un aller-retour LLM.
        self._client = http_client

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        # Les outils arrivent en forme MCP/shell ({name, description,
        # inputSchema}) ; l'API chat-completions attend {name, description,
        # parameters}. Sans cette conversion, un vrai fournisseur rejette la
        # requête en 400 à chaque tour.
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]
        payload: dict[str, Any] = {"model": self._model, "messages": messages}
        if openai_tools:  # `tools: []` est refusé par certains fournisseurs compatibles
            payload["tools"] = openai_tools
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is not None:
            response = await self._client.post(self._api_url, headers=headers, json=payload)
        else:
            async with build_guarded_async_client(timeout=LLM_CALL_TIMEOUT_SECONDS) as client:
                response = await client.post(self._api_url, headers=headers, json=payload)
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
        usage = response.json().get("usage") or {}
        return LLMTurn(
            text=choice.get("content") or "",
            tool_calls=tool_calls,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            model=self._model,
        )

    def with_params(
        self, *, temperature: float | None, max_tokens: int | None
    ) -> "OpenAICompatibleLLMProvider":
        """Copie bornée pour les générateurs (déterministes, réponses courtes)."""
        return OpenAICompatibleLLMProvider(
            api_url=self._api_url,
            api_key=self._api_key,
            model=self._model,
            http_client=self._client,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def with_model(self, model: str) -> "OpenAICompatibleLLMProvider":
        return OpenAICompatibleLLMProvider(
            api_url=self._api_url,
            api_key=self._api_key,
            model=model,
            http_client=self._client,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )


def get_llm_provider() -> LLMProvider:
    kind = os.environ.get("CORE_LLM_PROVIDER")
    if kind == "":
        raise LLMNotConfiguredError(
            "fournisseur LLM non configuré : un administrateur doit définir "
            "CORE_LLM_PROVIDER (ex. openai) puis redémarrer le cœur"
        )
    if kind is None or kind == "fake":
        return FakeLLMProvider()
    if kind == "openai":
        return OpenAICompatibleLLMProvider(
            api_url=os.environ["CORE_LLM_API_URL"],
            api_key=os.environ["CORE_LLM_API_KEY"],
            model=os.environ.get("CORE_LLM_MODEL", "gpt-4o-mini"),
        )
    raise ValueError(f"unknown CORE_LLM_PROVIDER: {kind}")
