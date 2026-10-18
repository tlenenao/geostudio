# SPDX-License-Identifier: Apache-2.0
"""AUD-106/149 : quota quotidien, trace de consommation, fournisseur par tenant."""

import anyio
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.copilot import governance
from app.copilot.llm_provider import (
    FakeLLMProvider,
    LLMTurn,
    OpenAICompatibleLLMProvider,
)
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.mcp.tools import query_generation
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_LLM_DAILY_TOKENS", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="c",
            username="creator",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        ids = (tenant.id, admin.id, creator.id)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    return app, TestClient(app), Session, ids


def _as(app, Session, user_id):
    def override_user():
        with Session() as s:
            yield s.get(User, user_id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user


def _turn(prompt=10, completion=5):
    return LLMTurn(text="x", prompt_tokens=prompt, completion_tokens=completion, model="m")


def test_quota_refuses_once_daily_limit_reached(env, monkeypatch):
    _, _, Session, (tenant_id, admin_id, _) = env
    monkeypatch.setenv("CORE_LLM_DAILY_TOKENS", "20")
    with Session() as s:
        governance.check_quota(s, tenant_id)  # rien consommé
        governance.record_usage(s, tenant_id, admin_id, "copilot", _turn())
        governance.check_quota(s, tenant_id)  # 15 < 20
        governance.record_usage(s, tenant_id, admin_id, "copilot", _turn())
        with pytest.raises(governance.LlmQuotaExceeded):
            governance.check_quota(s, tenant_id)  # 30 >= 20


def test_tenant_limit_overrides_env(env, monkeypatch):
    _, _, Session, (tenant_id, admin_id, _) = env
    monkeypatch.setenv("CORE_LLM_DAILY_TOKENS", "1")
    with Session() as s:
        governance.save_settings(
            s, tenant_id, model=None, api_url=None, api_key=None, daily_token_limit=1000
        )
        governance.record_usage(s, tenant_id, admin_id, "copilot", _turn())
        governance.check_quota(s, tenant_id)  # plafond du tenant, pas celui de l'env


def test_resolve_provider_uses_tenant_override_with_decrypted_key(env):
    _, _, Session, (tenant_id, _, _) = env
    base = FakeLLMProvider()
    with Session() as s:
        assert governance.resolve_provider(s, tenant_id, lambda: base) is base
        governance.save_settings(
            s,
            tenant_id,
            model="mon-modele",
            api_url="https://llm.example.org/v1/chat",
            api_key="sk-secret",
            daily_token_limit=None,
        )
        provider = governance.resolve_provider(s, tenant_id, lambda: base, generator=True)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider._api_key == "sk-secret"
    assert provider._model == "mon-modele"
    assert provider._temperature == 0.0


def test_ask_llm_records_usage_and_enforces_quota(env, monkeypatch):
    _, _, Session, (tenant_id, admin_id, _) = env
    monkeypatch.setattr(
        query_generation, "get_llm_provider", lambda: FakeLLMProvider([_turn(7, 3)])
    )
    who = (tenant_id, admin_id)
    msgs = [{"role": "user", "content": "q"}]
    anyio.run(query_generation._ask_llm, msgs, Session, who)
    with Session() as s:
        assert governance.tokens_used_today(s, tenant_id) == 10
    monkeypatch.setenv("CORE_LLM_DAILY_TOKENS", "10")
    with pytest.raises(ValueError, match="quota"):
        anyio.run(query_generation._ask_llm, msgs, Session, who)


def test_settings_routes_never_return_key_and_need_privilege(env, monkeypatch):
    monkeypatch.setattr("app.copilot.admin_routes.assert_egress_allowed", lambda url: None)
    app, client, Session, (_, admin_id, creator_id) = env
    _as(app, Session, creator_id)
    assert client.get("/v1/copilot/llm-settings").status_code == 403
    assert client.get("/v1/copilot/usage").status_code == 403
    _as(app, Session, admin_id)
    assert client.get("/v1/copilot/llm-settings").json() == {
        "configured": False,
        "model": None,
        "apiUrl": None,
        "hasApiKey": False,
        "dailyTokenLimit": None,
    }
    resp = client.put(
        "/v1/copilot/llm-settings",
        json={
            "model": "m",
            "apiUrl": "https://llm.example.org/v1/chat",
            "apiKey": "sk-secret",
            "dailyTokenLimit": 500,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["hasApiKey"] is True
    assert "sk-secret" not in resp.text
    assert "sk-secret" not in client.get("/v1/copilot/llm-settings").text
    usage = client.get("/v1/copilot/usage").json()
    assert usage["dailyLimit"] == 500 and usage["usedToday"] == 0
    assert client.delete("/v1/copilot/llm-settings").status_code == 204
    assert client.get("/v1/copilot/llm-settings").json()["configured"] is False


def test_settings_routes_reject_internal_url_and_keyless_url(env):
    app, client, Session, (_, admin_id, _) = env
    _as(app, Session, admin_id)
    internal = client.put(
        "/v1/copilot/llm-settings", json={"apiUrl": "http://127.0.0.1:9/x", "apiKey": "k"}
    )
    assert internal.status_code == 422
    keyless = client.put("/v1/copilot/llm-settings", json={"apiUrl": "https://llm.example.org/x"})
    assert keyless.status_code == 422
