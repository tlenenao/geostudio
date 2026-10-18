# SPDX-License-Identifier: Apache-2.0
"""L8 T2 : `Idempotency-Key` sur POST /items (PostGIS réel, base non vide)."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

BASE = "/v1/collections/demo_idem/items"
KEY = "11111111-1111-4111-8111-111111111111"


def _feat(titre="x", x=1.0):
    return {
        "type": "Feature",
        "properties": {"titre": titre},
        "geometry": {"type": "Point", "coordinates": [x, 45.0]},
    }


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_idem"))
        conn.execute(
            text(
                "CREATE TABLE demo_idem (id serial PRIMARY KEY, titre text NOT NULL, "
                "geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        users = [
            get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub=sub,
                username=sub,
                email=None,
                first_name="",
                last_name="",
                bootstrap_admin=True,
            )
            for sub in ("a", "b")
        ]
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    class _S3:
        def delete_object(self, *, Bucket, Key):
            pass

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: users[0]
    app.dependency_overrides[get_current_user_optional] = lambda: users[0]
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    c = TestClient(app)
    assert c.post("/v1/collections", json={"tableName": "demo_idem"}).status_code == 201
    for i in range(2):  # base non vide
        assert c.post(BASE, json=_feat(f"pre{i}", i)).status_code == 201
    yield app, c, users, pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_idem"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _scalar(engine, sql, **p):
    with engine.connect() as conn:
        return conn.scalar(text(sql), p)


def test_replay_returns_same_id_and_writes_once(env):
    _app, c, _u, engine = env
    first = c.post(BASE, json=_feat("a"), headers={"Idempotency-Key": KEY})
    assert first.status_code == 201 and "Idempotent-Replay" not in first.headers
    again = c.post(BASE, json=_feat("a"), headers={"Idempotency-Key": KEY})
    assert again.status_code == 200
    assert again.headers["Idempotent-Replay"] == "true"
    assert again.json() == first.json()
    assert again.headers["Location"] == first.headers["Location"]
    assert _scalar(engine, "SELECT count(*) FROM demo_idem") == 3
    assert _scalar(engine, "SELECT feature_count FROM collections WHERE id='demo_idem'") == 3
    assert (
        _scalar(
            engine,
            "SELECT count(*) FROM audit_log WHERE action='feature.create' "
            "AND payload->>'clientOpId' = :k",
            k=KEY,
        )
        == 1
    )
    assert (
        _scalar(
            engine, "SELECT count(*) FROM entity_history WHERE fid = :f", f=str(first.json()["id"])
        )
        == 1
    )


def test_without_header_each_post_creates(env):
    _app, c, _u, engine = env
    assert c.post(BASE, json=_feat()).status_code == 201
    assert c.post(BASE, json=_feat()).status_code == 201
    assert _scalar(engine, "SELECT count(*) FROM demo_idem") == 4
    assert _scalar(engine, "SELECT count(*) FROM collect_client_ops") == 0


def test_same_key_other_actor_is_a_distinct_write(env):
    app, c, users, engine = env
    assert c.post(BASE, json=_feat(), headers={"Idempotency-Key": KEY}).status_code == 201
    app.dependency_overrides[get_current_user] = lambda: users[1]
    app.dependency_overrides[get_current_user_optional] = lambda: users[1]
    r = c.post(BASE, json=_feat(), headers={"Idempotency-Key": KEY})
    assert r.status_code == 201
    assert _scalar(engine, "SELECT count(*) FROM demo_idem") == 4


def test_concurrent_requests_create_one_row_and_share_the_id(env):
    _app, c, _u, engine = env

    def post(_):
        return c.post(BASE, json=_feat("race"), headers={"Idempotency-Key": KEY})

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(post, range(6)))
    assert {r.status_code for r in results} <= {200, 201}
    assert sum(r.status_code == 201 for r in results) == 1
    assert len({r.json()["id"] for r in results}) == 1
    assert _scalar(engine, "SELECT count(*) FROM demo_idem WHERE titre = 'race'") == 1
    assert _scalar(engine, "SELECT count(*) FROM collect_client_ops") == 1


def test_validation_failure_reserves_nothing_and_key_stays_usable(env):
    _app, c, _u, engine = env
    bad = {"type": "Feature", "properties": {}, "geometry": None}  # titre NOT NULL requis
    r = c.post(BASE, json=bad, headers={"Idempotency-Key": KEY})
    assert r.status_code == 400
    assert _scalar(engine, "SELECT count(*) FROM collect_client_ops") == 0
    assert c.post(BASE, json=_feat(), headers={"Idempotency-Key": KEY}).status_code == 201


def test_malformed_key_is_400(env):
    _app, c, _u, _e = env
    r = c.post(BASE, json=_feat(), headers={"Idempotency-Key": "x"})
    assert r.status_code == 400


def test_offline_created_at_is_recorded_in_the_audit_payload(env):
    _app, c, _u, engine = env
    c.post(
        BASE,
        json=_feat(),
        headers={"Idempotency-Key": KEY, "X-GS-Offline-Created-At": "2026-10-18T10:00:00Z"},
    )
    assert (
        _scalar(
            engine,
            "SELECT payload->'offline'->>'createdAt' FROM audit_log "
            "WHERE action='feature.create' AND payload->>'clientOpId' = :k",
            k=KEY,
        )
        == "2026-10-18T10:00:00Z"
    )
