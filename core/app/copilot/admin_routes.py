# SPDX-License-Identifier: Apache-2.0
"""Gouvernance du LLM par tenant (AUD-106, AUD-149) : consommation, plafond quotidien,
fournisseur propre au tenant (« apportez votre modèle »). Monté sans flag : les
générateurs MCP consomment du LLM même quand le copilote est éteint."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.copilot import governance
from app.copilot.egress import EgressBlockedError, assert_egress_allowed
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()


class UsageDay(BaseModel):
    day: str
    calls: int
    promptTokens: int
    completionTokens: int


class UsageSummary(BaseModel):
    dailyLimit: int | None
    usedToday: int
    days: list[UsageDay]


class LlmSettingsRead(BaseModel):
    configured: bool
    model: str | None = None
    apiUrl: str | None = None
    hasApiKey: bool = False  # la clé n'est jamais renvoyée
    dailyTokenLimit: int | None = None


class LlmSettingsWrite(BaseModel):
    model: str | None = Field(default=None, max_length=128)
    apiUrl: str | None = Field(default=None, max_length=512)
    apiKey: str | None = Field(default=None, max_length=512)  # absente = conserver
    dailyTokenLimit: int | None = Field(default=None, ge=0)


def _read(session: Session, tenant_id: str) -> LlmSettingsRead:
    row = governance.get_settings(session, tenant_id)
    if row is None:
        return LlmSettingsRead(configured=False)
    return LlmSettingsRead(
        configured=True,
        model=row.model,
        apiUrl=row.api_url,
        hasApiKey=bool(row.key_ciphertext),
        dailyTokenLimit=row.daily_token_limit,
    )


@router.get("/copilot/usage", response_model=UsageSummary)
def get_usage(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    return governance.usage_summary(session, user.tenant_id)


@router.get("/copilot/llm-settings", response_model=LlmSettingsRead)
def get_llm_settings(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> LlmSettingsRead:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    return _read(session, user.tenant_id)


@router.put("/copilot/llm-settings", response_model=LlmSettingsRead)
def put_llm_settings(
    body: LlmSettingsWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> LlmSettingsRead:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    if body.apiUrl:
        try:  # garde d'egress dès l'écriture (rejouée à chaque appel)
            assert_egress_allowed(body.apiUrl)
        except EgressBlockedError as exc:
            raise HTTPException(
                status_code=422, detail=f"URL du fournisseur refusée : {exc}"
            ) from exc
    existing = governance.get_settings(session, user.tenant_id)
    if body.apiUrl and not body.apiKey and not (existing and existing.key_ciphertext):
        raise HTTPException(status_code=422, detail="Une clé d'API est requise avec une URL.")
    governance.save_settings(
        session,
        user.tenant_id,
        model=body.model,
        api_url=body.apiUrl,
        api_key=body.apiKey,
        daily_token_limit=body.dailyTokenLimit,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="copilot.llm_settings.update",
        object_type="tenant",
        object_id=user.tenant_id,
        payload={"model": body.model, "apiUrl": body.apiUrl, "keyChanged": bool(body.apiKey)},
    )
    session.commit()
    return _read(session, user.tenant_id)


@router.delete("/copilot/llm-settings", status_code=204)
def delete_llm_settings(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> Response:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    if governance.delete_settings(session, user.tenant_id):
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="copilot.llm_settings.delete",
            object_type="tenant",
            object_id=user.tenant_id,
        )
    session.commit()
    return Response(status_code=204)
