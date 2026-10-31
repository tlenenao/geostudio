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


def test_local_fallback_is_thread_safe_under_concurrent_requests():
    """Le repli mémoire tourne dans le threadpool : sans verrou, _sweep itère _hits pendant
    qu'un autre thread y insère (RuntimeError: dictionary changed size)."""
    import sys
    import threading

    dead = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/x")
    lim = PgRateLimiter(dead)
    lim.allow("warm", "sql")  # ouvre le disjoncteur : tout passe par le repli local
    errors: list[BaseException] = []

    def hammer(n: int) -> None:
        try:
            for i in range(3000):
                lim.allow(f"k{n}-{i}", "sql")
        except BaseException as exc:
            errors.append(exc)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=hammer, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert errors == []


def test_hourly_submit_limiter_is_shared_between_replicas(engine):
    # REV-396 : deux « process » liés au même moteur partagent le budget horaire.
    from app.public_submit.service import HourlyLimiter

    a, b = HourlyLimiter(3, group="t:long"), HourlyLimiter(3, group="t:long")
    a.bind(engine)
    b.bind(engine)
    assert [(a if i % 2 else b).allow("k") for i in range(5)] == [True] * 3 + [False] * 2
    assert not a.has_room("k") and not b.has_room("k")


def test_minute_purge_never_deletes_long_counters(engine):
    # Les compteurs `:long` (heure, seconde) ont des fenêtres d'une autre échelle : la purge à
    # fenêtre de 60 s ne doit pas les emporter (sinon le budget horaire se réinitialise).
    from app.public_submit.service import HourlyLimiter

    lim = HourlyLimiter(10**6, group="t:long")
    lim.bind(engine)
    lim.allow("k")
    pg = PgRateLimiter(engine)
    for i in range(1100):  # > 2 purges (toutes les 500 appels)
        pg.allow(f"c{i % 7}", "sql")
    lim2 = HourlyLimiter(1, group="t:long")
    lim2.bind(engine)
    assert not lim2.has_room("k")  # le compteur de `lim` a survécu : 1 >= limite 1


def test_geocode_pacer_caps_per_second_across_processes(engine, monkeypatch):
    from app.geocoding import batch

    monkeypatch.setattr(batch, "shared_engine", lambda: engine)
    monkeypatch.setattr(batch.time, "time", lambda: 1000.5)

    class _Slept(Exception):
        pass

    def sleep(_s):
        raise _Slept

    a = batch._Pacer(2, shared=True, sleep=sleep)
    b = batch._Pacer(2, shared=True, sleep=sleep)
    a._wait_shared()
    b._wait_shared()  # 2 appels/s au total, tous process confondus
    with pytest.raises(_Slept):  # le 3e doit attendre la seconde suivante
        a._wait_shared()


def test_geocode_job_results_are_appended_not_rewritten(pg_engine):
    import uuid

    from app.db import Base, make_session_factory
    from app.geocoding.jobs import _append_results
    from app.geocoding.models import GeocodeJob
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="g", username="g", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )  # fmt: skip
        job = GeocodeJob(
            id=uuid.uuid4().hex, tenant_id=tenant.id, created_by=user.id,
            status="running", addresses=["a", "b", "c"], results=[],
        )  # fmt: skip
        s.add(job)
        s.commit()
        _append_results(s, job.id, [{"address": "a"}])
        _append_results(s, job.id, [{"address": "b"}, {"address": "c"}])
        s.commit()
        s.refresh(job)
        assert [r["address"] for r in job.results] == ["a", "b", "c"]
        s.delete(job)
        s.commit()


def test_hourly_submit_limiter_falls_back_locally_when_db_is_down():
    from app.public_submit.service import HourlyLimiter

    lim = HourlyLimiter(2)
    lim.bind(create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x"))
    assert [lim.allow("k") for _ in range(3)] == [True, True, False]


def test_routing_budget_is_shared_between_processes(engine, test_db_url, monkeypatch):
    """Le budget routage (100/min/utilisateur) vaut pour core ET worker : deux _Window distincts
    (deux process) consomment le même compteur Postgres (repli du limiteur de la voie P)."""
    from app.routing import client as rc

    monkeypatch.setenv("CORE_RATELIMIT_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    rc._shared_limiter.cache_clear()
    try:
        core_proc, worker_proc = rc._Window(), rc._Window()
        for i in range(100):
            (core_proc if i % 2 else worker_proc).check("u1")
        with pytest.raises(rc.RateLimited):
            core_proc.check("u1")
        worker_proc.check("u2")  # autre utilisateur : budget propre
    finally:
        rc._shared_limiter.cache_clear()


def test_mcp_server_is_stateless_for_multi_replica_core(monkeypatch):
    """ARC-32 : une session MCP en mémoire casserait la bascule entre réplicas."""
    from app.mcp.server import create_mcp_server

    monkeypatch.setenv("CORE_MCP_STATELESS", "true")

    server = create_mcp_server("http://localhost:8200", lambda: None)
    assert server.settings.stateless_http is True


def test_stateless_mcp_serves_a_tool_call_without_any_session_id(monkeypatch):
    """Un appel autonome tombant sur l'AUTRE réplica doit réussir : pas d'id de session requis."""
    import json

    from fastapi.testclient import TestClient

    from app import db
    from app.db import init_db, make_engine, make_session_factory, request_scoped_session
    from app.main import create_app

    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_MCP_STATELESS", "true")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    headers = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer x"}
    init_params = {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    }
    with TestClient(app, base_url="http://localhost:8200") as client:
        init = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init_params},
            headers=headers,
        )
        assert init.status_code == 200 and "mcp-session-id" not in init.headers
        call = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "whoami", "arguments": {}},
            },
            headers=headers,
        )
        assert call.status_code == 200
        line = next(x for x in call.text.splitlines() if x.startswith("data: "))
        assert "mockuser" in json.loads(line.removeprefix("data: "))["result"]["content"][0]["text"]
    engine.dispose()
