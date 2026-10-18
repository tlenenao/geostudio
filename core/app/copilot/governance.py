# SPDX-License-Identifier: Apache-2.0
"""Gouvernance de l'appel LLM (AUD-106, AUD-149) : fournisseur propre au tenant,
quota quotidien de jetons, trace de consommation. Point unique partagé par le copilote
(`/copilot/turn`) et les générateurs MCP (jumelles : tout appel LLM passe ici)."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.copilot.llm_provider import LLMProvider, LLMTurn, OpenAICompatibleLLMProvider
from app.copilot.models import LlmUsage, TenantLlmSettings
from app.secrets.crypto import decrypt, encrypt

# Générateurs : déterministes et courts (le brouillon est relu, pas une conversation).
GENERATOR_TEMPERATURE = 0.0
GENERATOR_MAX_TOKENS = 2_000


class LlmQuotaExceeded(Exception):
    pass


def get_settings(session: Session, tenant_id: str) -> TenantLlmSettings | None:
    return session.get(TenantLlmSettings, tenant_id)


def save_settings(
    session: Session,
    tenant_id: str,
    *,
    model: str | None,
    api_url: str | None,
    api_key: str | None,
    daily_token_limit: int | None,
) -> TenantLlmSettings:
    row = get_settings(session, tenant_id) or TenantLlmSettings(tenant_id=tenant_id)
    row.model = model or None
    row.api_url = api_url or None
    row.daily_token_limit = daily_token_limit
    if api_key:  # clé absente = conserver l'existante
        row.key_ciphertext, row.key_nonce = encrypt({"apiKey": api_key})
    session.add(row)
    session.flush()
    return row


def delete_settings(session: Session, tenant_id: str) -> bool:
    row = get_settings(session, tenant_id)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def resolve_provider(
    session: Session,
    tenant_id: str,
    base_factory: Callable[[], LLMProvider],
    *,
    generator: bool = False,
) -> LLMProvider:
    """Fournisseur effectif : surcharge du tenant (URL + clé chiffrée, modèle) sinon
    fournisseur d'instance. `base_factory` est passé par l'appelant (et non importé ici)
    pour que ses tests puissent le remplacer. `generator` : température 0, réponse courte."""
    row = get_settings(session, tenant_id)
    provider: LLMProvider
    if row is not None and row.api_url and row.key_ciphertext and row.key_nonce:
        key = str(decrypt(row.key_ciphertext, row.key_nonce)["apiKey"])
        provider = OpenAICompatibleLLMProvider(
            api_url=row.api_url,
            api_key=key,
            model=row.model or os.environ.get("CORE_LLM_MODEL", "gpt-4o-mini"),
        )
    else:
        provider = base_factory()
        if row is not None and row.model and isinstance(provider, OpenAICompatibleLLMProvider):
            provider = provider.with_model(row.model)
    if generator and isinstance(provider, OpenAICompatibleLLMProvider):
        provider = provider.with_params(
            temperature=GENERATOR_TEMPERATURE, max_tokens=GENERATOR_MAX_TOKENS
        )
    return provider


def daily_limit(session: Session, tenant_id: str) -> int | None:
    row = get_settings(session, tenant_id)
    if row is not None and row.daily_token_limit is not None:
        return row.daily_token_limit
    raw = os.environ.get("CORE_LLM_DAILY_TOKENS", "").strip()
    return int(raw) if raw.isdigit() else None


def _day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def tokens_used_today(session: Session, tenant_id: str) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(LlmUsage.prompt_tokens + LlmUsage.completion_tokens), 0))
        .where(LlmUsage.tenant_id == tenant_id)
        .where(LlmUsage.created_at >= _day_start())
    )
    return int(total or 0)


def check_quota(session: Session, tenant_id: str) -> None:
    """Refuse avant l'appel si le plafond du jour est atteint (un tour peut le dépasser)."""
    limit = daily_limit(session, tenant_id)
    if limit is not None and tokens_used_today(session, tenant_id) >= limit:
        raise LlmQuotaExceeded("quota quotidien de jetons LLM atteint")


def record_usage(
    session: Session, tenant_id: str, user_id: str | None, surface: str, turn: LLMTurn
) -> None:
    session.add(
        LlmUsage(
            tenant_id=tenant_id,
            user_id=user_id,
            surface=surface[:32],
            model=turn.model[:128],
            prompt_tokens=turn.prompt_tokens,
            completion_tokens=turn.completion_tokens,
        )
    )
    session.flush()


def usage_summary(session: Session, tenant_id: str, days: int = 30) -> dict[str, Any]:
    rows = session.execute(
        select(
            func.date(LlmUsage.created_at),
            func.count(),
            func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
        )
        .where(LlmUsage.tenant_id == tenant_id)
        .group_by(func.date(LlmUsage.created_at))
        .order_by(func.date(LlmUsage.created_at).desc())
        .limit(days)
    ).all()
    return {
        "dailyLimit": daily_limit(session, tenant_id),
        "usedToday": tokens_used_today(session, tenant_id),
        "days": [
            {"day": str(d), "calls": int(c), "promptTokens": int(p), "completionTokens": int(q)}
            for d, c, p, q in rows
        ],
    }
