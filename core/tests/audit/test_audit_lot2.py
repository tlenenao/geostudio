# SPDX-License-Identifier: Apache-2.0
"""Reproducteurs de bugs confirmés (audit lot 2). xfail strict : le test
passe en xfail tant que le bug existe, et casse (XPASS) une fois corrigé."""

import inspect

import duckdb
import pytest

from tests.test_compliance_purge_routes import _as_user_id, env  # noqa: F401

_MAP = {
    "kind": "map",
    "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
}


def test_s3_secret_not_readable_after_lock_down():
    from app.analytics.duckdb_conn import open_connection
    from app.analytics.sql_sandbox import _lock_down

    conn = open_connection(
        endpoint_url="http://minio:9000", access_key="AKID", secret_key="SUPERSECRET"
    )
    _lock_down(conn)
    try:
        leaked = conn.execute("select current_setting('s3_secret_access_key')").fetchone()[0]
    except duckdb.Error:
        return  # refusé : correct
    assert leaked != "SUPERSECRET"


@pytest.mark.xfail(strict=True, reason="REV-audit: rollback_config sans verrou de ligne")
def test_rollback_config_locks_the_row(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.configs.repository import rollback_config
    from app.db import init_db, make_engine, make_session_factory
    from app.main import create_app

    url = f"sqlite+pysqlite:///{tmp_path / 'rb.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine(url)
    init_db(engine)
    c = TestClient(create_app())
    c.headers["Authorization"] = "Bearer mock:alice"
    created = c.post("/v1/configs", json={"title": "C", "config": _MAP}).json()
    with make_session_factory(engine)() as s:
        seen = []
        real_get = s.get

        def spy(entity, ident, **kw):
            seen.append(kw.get("with_for_update"))
            return real_get(entity, ident, **kw)

        monkeypatch.setattr(s, "get", spy)
        rollback_config(s, created["id"], 1, tenant_id="default")
        assert seen and seen[0], "rollback doit lire la config avec with_for_update"


@pytest.mark.xfail(strict=True, reason="REV-audit: double purge de tenant acceptée")
def test_second_purge_request_while_first_pending_is_rejected(env):  # noqa: F811
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    url = f"/v1/compliance/tenants/{env['tenant_id']}/purge"
    body = {"confirmSlug": env["tenant_slug"]}
    assert env["client"].post(url, json=body).status_code == 202
    assert env["client"].post(url, json=body).status_code == 409
    assert len(env["deferred"]) == 1


def test_terrain3d_has_periodic_reclaim():
    import app.terrain3d.jobs as m

    assert "periodic" in inspect.getsource(m)


def test_tileset3d_has_periodic_reclaim():
    import app.tileset3d.jobs as m

    assert "periodic" in inspect.getsource(m)


@pytest.mark.xfail(strict=True, reason="REV-audit: purge_tenant_task sans trace d'échec")
def test_purge_task_failure_is_recorded_not_just_raised(monkeypatch):
    import app.compliance.jobs as jobs

    def boom(*a, **k):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(jobs, "purge_tenant", boom)
    monkeypatch.setattr(jobs, "s3_client_from_env", lambda: object())
    monkeypatch.setattr(jobs, "_session_factory", lambda: None)
    monkeypatch.setattr(jobs, "request_scoped_session", _fake_scope)
    # attendu : l'échec est capturé/tracé (statut, notification) au lieu de se propager nu
    jobs.purge_tenant_task(purge_id="p1", tenant_id="t1", requested_by_user_id="u1")


import contextlib  # noqa: E402


@contextlib.contextmanager
def _fake_scope(_factory):
    yield object()


def test_s3_secret_not_readable_via_settings_nor_secrets_view():
    """REV-332 : ni duckdb_settings(), ni duckdb_secrets() (même redact=false)."""
    from app.analytics.duckdb_conn import open_connection
    from app.analytics.sql_sandbox import _lock_down

    conn = open_connection(
        endpoint_url="http://minio:9000", access_key="AKID", secret_key="SUPERSECRET"
    )
    _lock_down(conn)
    rows = conn.execute(
        "select name, value from duckdb_settings() where name like 's3_%'"
    ).fetchall()
    assert "SUPERSECRET" not in repr(rows)
    assert "SUPERSECRET" not in repr(conn.execute("select * from duckdb_secrets()").fetchall())
    with pytest.raises(duckdb.Error):
        conn.execute("select * from duckdb_secrets(redact=false)")
