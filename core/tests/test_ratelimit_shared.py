# SPDX-License-Identifier: Apache-2.0
"""Limiteur partagé Postgres (ARC-32) : budget cohérent entre 2 « réplicas »."""

import pytest
from sqlalchemy import create_engine, text

from app.ratelimit.limiter import PgRateLimiter


@pytest.fixture
def engine(test_db_url):
    eng = create_engine(test_db_url)
    with eng.begin() as c:
        c.execute(
            text(
                "CREATE UNLOGGED TABLE IF NOT EXISTS rate_limit_counters (key_hash varchar(64), "
                "grp varchar, window_start bigint, hits integer NOT NULL, "
                "PRIMARY KEY (key_hash, grp, window_start))"
            )
        )
        c.execute(text("DELETE FROM rate_limit_counters"))
    yield eng
    eng.dispose()


def test_budget_is_shared_between_two_replicas(engine):
    a, b = PgRateLimiter(engine), PgRateLimiter(engine)
    results = [(a if i % 2 else b).allow("Bearer tok", "sql") for i in range(12)]
    assert results == [True] * 10 + [False] * 2  # budget sql = 10, pas 10 par réplica


def test_keys_are_hashed_never_stored_raw(engine):
    PgRateLimiter(engine).allow("Bearer secret-token", "sql")
    with engine.connect() as c:
        keys = c.execute(text("SELECT key_hash FROM rate_limit_counters")).scalars().all()
    assert keys and all("secret-token" not in k and len(k) == 64 for k in keys)


def test_different_callers_independent(engine):
    lim = PgRateLimiter(engine)
    for _ in range(10):
        lim.allow("Bearer a", "sql")
    assert lim.allow("Bearer a", "sql") is False
    assert lim.allow("Bearer b", "sql") is True


def test_degrades_to_local_counter_when_db_unreachable():
    dead = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/x")
    lim = PgRateLimiter(dead)
    results = [lim.allow("Bearer k", "sql") for _ in range(12)]
    assert results == [True] * 10 + [False] * 2  # repli en mémoire, jamais d'exception
    assert lim.degraded is True


def test_circuit_breaker_skips_db_after_failure(monkeypatch):
    dead = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/x")
    lim = PgRateLimiter(dead)
    lim.allow("Bearer k", "sql")
    calls = []
    monkeypatch.setattr(lim, "_allow_pg", lambda *a: calls.append(a) or True)
    lim.allow("Bearer k", "sql")
    assert calls == []  # disjoncteur ouvert : pas de nouvel aller-retour pendant le délai
