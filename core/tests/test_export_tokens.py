# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest

from app.auth.export_tokens import (
    ExportTokenError,
    decode_export_token,
    is_export_token,
    mint_export_token,
)


_SECRET = "test-export-secret-padding-01234"  # >=32 bytes: avoids PyJWT's
# InsecureKeyLengthWarning for HS256, which this repo's pytest config
# (filterwarnings = ["error", ...], pyproject.toml) promotes to a hard
# failure.


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", _SECRET)


def test_mint_and_decode_round_trip():
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    claims = decode_export_token(token)
    assert claims.tenant_id == "t1"
    assert claims.user_id == "u1"
    assert claims.job_id == "j1"


def test_is_export_token_true_for_export_token_false_for_rs256():
    export_token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    assert is_export_token(export_token) is True
    rs256_like = jwt.encode(
        {"sub": "x"},
        "irrelevant-padding-to-reach-64-bytes-for-hs512-signing-key-00000",
        algorithm="HS512",
    )
    assert is_export_token(rs256_like) is False
    assert is_export_token("not-even-a-jwt") is False


def test_decode_rejects_expired_token(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1", ttl_seconds=-1)
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_tampered_signature(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "a-different-secret-padding-01234")
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_wrong_typ_claim():
    bad = jwt.encode({"typ": "not-export", "tenant_id": "t1", "user_id": "u1", "job_id": "j1",
                       "iat": int(time.time()), "exp": int(time.time()) + 60}, _SECRET, algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)


def test_decode_rejects_missing_claim():
    bad = jwt.encode({"typ": "export", "tenant_id": "t1"}, _SECRET, algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)


def test_decode_raises_export_token_error_when_secret_unset(monkeypatch):
    # Régression : sur une instance qui n'a jamais déployé CORE_EXPORT_TOKEN_SECRET
    # (toute instance à ce jour, avant l'existence du worker d'export), un jeton
    # HS256 forgé par un attaquant avec un secret arbitraire ne doit jamais faire
    # planter decode_export_token en KeyError brut — il doit être rejeté proprement
    # en ExportTokenError, comme n'importe quel autre jeton invalide.
    monkeypatch.delenv("CORE_EXPORT_TOKEN_SECRET", raising=False)
    forged = jwt.encode(
        {"typ": "export", "tenant_id": "t1", "user_id": "u1", "job_id": "j1"},
        "attacker-controlled-secret-of-their-choosing",
        algorithm="HS256",
    )
    with pytest.raises(ExportTokenError):
        decode_export_token(forged)
