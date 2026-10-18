# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications import repository as notifications_repo
from app.notifications import stream
from tests.test_notifications_routes import _make_client


def _fast(monkeypatch):
    monkeypatch.setattr(stream, "POLL_INTERVAL_S", 0.05)
    monkeypatch.setattr(stream, "STREAM_LIFETIME_S", 0.3)
    stream._leases.clear()


def _notify(s, tenant, user):
    notifications_repo.create_notification(
        s,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        kind="alert",
        status="failure",
        item_id=None,
        item_resource_type="alert",
        item_title="r",
    )


def test_stream_pushes_initial_unread_count_then_ends(monkeypatch):
    _fast(monkeypatch)
    client, Session, tenant, user, other = _make_client()
    with Session() as s:
        _notify(s, tenant, user)
        _notify(s, tenant, other)
        s.commit()
    res = client.get("/v1/notifications/stream")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.text.count('data: {"unread": 1}') == 1  # état initial, pas celui des autres
    assert ": ping" in res.text  # inchangé -> battement de coeur


def test_stream_requires_auth():
    assert TestClient(create_app()).get("/v1/notifications/stream").status_code in (401, 403)


def test_stream_limits_per_user(monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(stream, "STREAM_LIFETIME_S", 60.0)
    client, _, tenant, user, other = _make_client()
    for _ in range(stream.MAX_STREAMS_PER_USER):
        assert stream.try_acquire(tenant.id, user.id)
    res = client.get("/v1/notifications/stream")
    assert res.status_code == 429
    assert res.headers["retry-after"] == "10"
    assert stream.try_acquire(tenant.id, other.id)  # un autre utilisateur n'est pas bloqué


def test_stream_limits_per_tenant(monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(stream, "MAX_STREAMS_PER_TENANT", 2)
    assert stream.try_acquire("t", "a")
    assert stream.try_acquire("t", "b")
    assert not stream.try_acquire("t", "c")
    assert stream.try_acquire("t2", "c")


def test_leases_expire_without_release(monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(stream, "STREAM_LIFETIME_S", -10.0)
    for _ in range(stream.MAX_STREAMS_PER_USER + 2):
        assert stream.try_acquire("t", "a")
