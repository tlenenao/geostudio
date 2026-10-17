# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

from app.mcp.tools import identity


def test_resolve_actor_applies_oidc_group_claims(monkeypatch):
    # AUD-096 : le MCP synchronise les groupes OIDC comme get_current_user.
    seen = {}
    user = SimpleNamespace(id="u1", tenant_id="t1")
    monkeypatch.setattr(
        identity, "get_or_create_default_tenant", lambda s: SimpleNamespace(id="t1")
    )
    monkeypatch.setattr(identity, "get_or_create_user", lambda s, **kw: user)
    monkeypatch.setattr(identity, "apply_from_token_claims", lambda s, **kw: seen.update(kw))
    token = SimpleNamespace(subject="sub", claims={"groups": ["/sig"], "preferred_username": "u"})
    assert identity.resolve_actor(object(), token) is user
    assert seen == {"tenant_id": "t1", "user_id": "u1", "claims": token.claims}
