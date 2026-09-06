# SPDX-License-Identifier: Apache-2.0
"""share_links.py — jeton HMAC des liens de partage à échéance (GAP-12).
Patron calqué sur test_export_tokens.py (SP-17a), adapté : TTL long
(jours), claim share_link_id (pas user_id — un lien de partage n'authentifie
pas un utilisateur donné)."""

import pytest

from app.sharing.share_links import (
    ShareLinkTokenError,
    decode_share_link_token,
    mint_share_link_token,
)

# >=32 bytes : évite l'InsecureKeyLengthWarning de PyJWT pour HS256, promue
# en échec dur par ce dépôt (filterwarnings = ["error", ...], pyproject.toml)
# — même contrainte que test_export_tokens.py::_SECRET.
_SECRET_A = "test-share-link-secret-padding-0123456789"
_SECRET_B = "a-different-share-link-secret-padding-999"


def test_mint_and_decode_round_trip(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_A)
    token = mint_share_link_token(
        share_link_id="sl1", tenant_id="t1", item_id="i1", ttl_seconds=86400
    )
    claims = decode_share_link_token(token)
    assert claims.share_link_id == "sl1"
    assert claims.tenant_id == "t1"
    assert claims.item_id == "i1"


def test_decode_without_secret_raises_not_crashes(monkeypatch):
    monkeypatch.delenv("CORE_SHARE_LINK_TOKEN_SECRET", raising=False)
    with pytest.raises(ShareLinkTokenError):
        decode_share_link_token("whatever")


def test_decode_garbage_token_raises(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_A)
    with pytest.raises(ShareLinkTokenError):
        decode_share_link_token("not-a-jwt-at-all")


def test_decode_wrong_secret_raises(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_A)
    token = mint_share_link_token(
        share_link_id="sl1", tenant_id="t1", item_id="i1", ttl_seconds=86400
    )
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_B)
    with pytest.raises(ShareLinkTokenError):
        decode_share_link_token(token)


def test_decode_expired_token_raises(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_A)
    token = mint_share_link_token(share_link_id="sl1", tenant_id="t1", item_id="i1", ttl_seconds=-1)
    with pytest.raises(ShareLinkTokenError):
        decode_share_link_token(token)


def test_mint_refuses_ttl_above_max(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET_A)
    with pytest.raises(ValueError):
        mint_share_link_token(
            share_link_id="sl1", tenant_id="t1", item_id="i1", ttl_seconds=31 * 86400
        )
