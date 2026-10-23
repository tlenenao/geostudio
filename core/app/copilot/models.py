# SPDX-License-Identifier: Apache-2.0
"""Consommation LLM par appel (AUD-106) et fournisseur LLM propre à un tenant (AUD-149)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # datetimes naïfs UTC (convention du dépôt)


class LlmUsage(Base):
    """Une ligne par appel au fournisseur (jetons lus sur la réponse). Sert au quota
    journalier du tenant et au panneau de consommation."""

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    surface: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128), default="", server_default="")
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TenantLlmSettings(Base):
    """Surcharge par tenant du fournisseur OpenAI-compatible. Colonne NULL = valeur
    d'instance (`CORE_LLM_*`). La clé est chiffrée AES-GCM comme le coffre de secrets."""

    __tablename__ = "tenant_llm_settings"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    daily_token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
