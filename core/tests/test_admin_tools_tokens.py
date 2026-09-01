# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest

from app.admin_tools.tokens import (
    AdminToolsTokenError,
    decode_launch_token,
    decode_session_token,
    mint_launch_token,
    mint_session_token,
)

_SECRET = "test-admin-tools-secret-padding-0123456"  # >=32 bytes, cf.
# test_export_tokens.py (InsecureKeyLengthWarning promue en erreur, filterwarnings)


@pytest.fixture(autouse=True)
def admin_tools_secret(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", _SECRET)


def test_launch_token_round_trip():
    token = mint_launch_token(sub="u1", tool="martin")
    claims = decode_launch_token(token)
    assert claims.sub == "u1"
    assert claims.tool == "martin"


def test_session_token_round_trip():
    token = mint_session_token(sub="u1")
    claims = decode_session_token(token)
    assert claims.sub == "u1"


def test_decode_launch_token_rejects_expired(monkeypatch):
    now = int(time.time())
    expired = jwt.encode(
        {"typ": "admin_launch", "sub": "u1", "tool": "martin", "iat": now - 120, "exp": now - 60},
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(expired)


def test_decode_launch_token_rejects_tampered_signature(monkeypatch):
    token = mint_launch_token(sub="u1", tool="martin")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", "a-different-secret-padding-0123456")
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(token)


def test_decode_launch_token_rejects_wrong_typ():
    session_like = mint_session_token(sub="u1")
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(session_like)


def test_decode_session_token_rejects_wrong_typ():
    launch_like = mint_launch_token(sub="u1", tool="martin")
    with pytest.raises(AdminToolsTokenError):
        decode_session_token(launch_like)


def test_decode_launch_token_rejects_missing_claim():
    bad = jwt.encode(
        {"typ": "admin_launch", "sub": "u1"},  # 'tool' manquant
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(bad)


def test_decode_raises_clean_error_when_secret_unset(monkeypatch):
    # Même régression que test_export_tokens.py:
    # test_decode_raises_export_token_error_when_secret_unset : un jeton forgé
    # par un attaquant avec un secret arbitraire ne doit jamais faire planter
    # en KeyError brut quand CORE_ADMIN_TOOLS_TOKEN_SECRET est absente (instance
    # qui n'a jamais activé la capacité).
    monkeypatch.delenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", raising=False)
    forged = jwt.encode(
        {"typ": "admin_launch", "sub": "u1", "tool": "martin"},
        "attacker-controlled-secret-of-their-choosing",
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(forged)
