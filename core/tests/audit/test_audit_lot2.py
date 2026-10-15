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


@pytest.mark.xfail(strict=True, reason="REV-audit: secret S3 lisible via current_setting()")
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


def test_purge_task_failure_is_recorded_not_just_raised(tmp_path, monkeypatch):
    """REV-344 b : l'échec est consigné sur le reçu (`failed` + message), jamais un 202 éternel."""
    from datetime import UTC, datetime

    import app.compliance.jobs as jobs
    from app.compliance.models import PurgeReceipt
    from app.db import init_db, make_engine, make_session_factory

    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'purge.db'}")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        s.add(
            PurgeReceipt(
                id="p1",
                tenant_slug="t",
                requested_by_user_id="u1",
                requested_at=datetime.now(UTC),
                counts={},
                status="pending",
            )
        )
        s.commit()

    def boom(*a, **k):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(jobs, "purge_tenant", boom)
    monkeypatch.setattr(jobs, "s3_client_from_env", lambda: object())
    monkeypatch.setattr(jobs, "_session_factory", lambda: Session)
    jobs.purge_tenant_task(purge_id="p1", tenant_id="t1", requested_by_user_id="u1")

    with Session() as s:
        receipt = s.get(PurgeReceipt, "p1")
        assert receipt.status == "failed"
        assert "s3 down" in receipt.error
