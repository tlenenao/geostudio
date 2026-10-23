# SPDX-License-Identifier: Apache-2.0
"""L8 T5 : preuve de travail de la soumission publique (défi HMAC, 60 s, usage unique)."""

import hashlib

import pytest

from app.collect import pow as pow_


@pytest.fixture(autouse=True)
def _fresh():
    pow_.reset()
    yield
    pow_.reset()


def solve(challenge: str, bits: int = pow_.BITS) -> str:
    n = 0
    while pow_.leading_zero_bits(hashlib.sha256(f"{challenge}:{n}".encode()).digest()) < bits:
        n += 1
    return str(n)


def test_valid_proof_is_accepted_with_the_production_difficulty():
    ch = pow_.issue("gss_aaaaaaaaaaaa")
    assert ch["bits"] == 18
    assert pow_.verify("gss_aaaaaaaaaaaa", ch["challenge"], solve(ch["challenge"]))


def test_challenge_is_single_use():
    ch = pow_.issue("gss_aaaaaaaaaaaa")["challenge"]
    nonce = solve(ch, 8)
    assert pow_.verify("gss_aaaaaaaaaaaa", ch, nonce, bits=8)
    assert not pow_.verify("gss_aaaaaaaaaaaa", ch, nonce, bits=8)


def test_expired_challenge_is_refused():
    ch = pow_.issue("gss_aaaaaaaaaaaa", now=1_000_000)["challenge"]
    assert not pow_.verify("gss_aaaaaaaaaaaa", ch, solve(ch, 8), now=1_000_000 + 61, bits=8)


def test_challenge_is_bound_to_its_token():
    ch = pow_.issue("gss_aaaaaaaaaaaa")["challenge"]
    assert not pow_.verify("gss_bbbbbbbbbbbb", ch, solve(ch, 8), bits=8)


def test_tampered_or_forged_challenge_is_refused():
    ch = pow_.issue("gss_aaaaaaaaaaaa")["challenge"]
    v, exp, rand, mac = ch.split(".")
    forged = ".".join([v, str(int(exp) + 3600), rand, mac])
    assert not pow_.verify("gss_aaaaaaaaaaaa", forged, solve(forged, 8), bits=8)
    assert not pow_.verify("gss_aaaaaaaaaaaa", "v1.1.2.3", "0", bits=8)
    assert not pow_.verify("gss_aaaaaaaaaaaa", "", "", bits=8)


def test_insufficient_work_is_refused_and_burns_the_challenge():
    ch = pow_.issue("gss_aaaaaaaaaaaa")["challenge"]
    nonce = solve(ch, 4)
    # difficulté 30 bits : quasi impossible à satisfaire par hasard avec un nonce trouvé à 4 bits
    assert not pow_.verify("gss_aaaaaaaaaaaa", ch, nonce, bits=30)
    assert not pow_.verify("gss_aaaaaaaaaaaa", ch, solve(ch, 8), bits=8)  # défi brûlé


def test_leading_zero_bits():
    assert pow_.leading_zero_bits(b"\x00\x01") == 15
    assert pow_.leading_zero_bits(b"\x80") == 0
