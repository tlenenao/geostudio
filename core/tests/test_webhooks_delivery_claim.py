# SPDX-License-Identifier: Apache-2.0
"""Revue finale vague 4 ARC (I4/I6 + mineurs) : réservation par lot de l'outbox
(aucune double livraison entre balayages concurrents), équité entre tenants,
purges de rétention, plafond de webhooks, audit de la désactivation automatique."""

import collections
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import requests
from sqlalchemy import select

from app.audit.models import AuditLog
from app.db import Base, init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.outbox.models import FileTrigger, FileTriggerSeen, OutboundWebhook, OutboxEvent
from app.secrets.schemas import BearerTokenPayload
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user
from app.webhooks import delivery, triggers
from tests.test_webhooks_outbox import KEY_B64, _secret

NOW = datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", KEY_B64)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _tenant_with_hook(Session, *, events: int, age_s: int = 60) -> tuple[str, list[str]]:
    """Tenant neuf + destination + `events` événements dus depuis `age_s` secondes."""
    tid = uuid.uuid4().hex
    with Session() as s:
        s.add(Tenant(id=tid, slug=f"t-{tid}", name=tid))
        s.flush()
        user = get_or_create_user(
            s,
            tenant_id=tid,
            oidc_sub=f"u-{tid}",
            username=f"u-{tid}",
            email=None,
            first_name="",
            last_name="",
        )
        _secret(s, tid, user.id, "sig", BearerTokenPayload(token="k"))
        hook = OutboundWebhook(
            id=uuid.uuid4().hex,
            tenant_id=tid,
            url="https://hook.example.test/in",
            event_types=["item.created"],
            secret_name="sig",
            created_by=user.id,
        )
        s.add(hook)
        ids = []
        for i in range(events):
            ev = OutboxEvent(
                id=uuid.uuid4().hex,
                tenant_id=tid,
                webhook_id=hook.id,
                event_type="item.created",
                payload={"n": i},
                next_attempt_at=NOW - timedelta(seconds=age_s - i * 0.001),
            )
            s.add(ev)
            ids.append(ev.id)
        s.commit()
    return tid, ids


# I6 : équité ------------------------------------------------------------------


def test_a_tenant_backlog_does_not_starve_another_tenant(db):
    _, backlog = _tenant_with_hook(db, events=50, age_s=3600)  # A : vieux backlog
    _, (fresh,) = _tenant_with_hook(db, events=1, age_s=1)  # B : un événement récent
    sent: list[str] = []
    with db() as s:
        # Un seul lot (budget nul) de 5 : l'ancien FIFO global ne servait que A.
        delivery.deliver_due(
            s, post=lambda u, b, h: sent.append(h["X-GeoStudio-Delivery"]), limit=5, budget_s=0
        )
    assert fresh in sent
    assert len(sent) == 5 and set(sent) - {fresh} <= set(backlog)


def test_the_sweep_drains_more_than_one_batch_within_its_budget(db):
    _, ids = _tenant_with_hook(db, events=45)
    sent: list[str] = []
    with db() as s:
        n = delivery.deliver_due(s, post=lambda u, b, h: sent.append(h["X-GeoStudio-Delivery"]))
    assert n == 45 and sorted(sent) == sorted(ids)


# I4 : pas de double livraison (Postgres réel, deux sessions) ------------------------


@pytest.mark.postgis
def test_concurrent_sweeps_never_deliver_an_event_twice(pg_engine, monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", KEY_B64)
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    _, ids = _tenant_with_hook(Session, events=12)
    mine = set(ids)
    sent: list[str] = []
    a_second_post = threading.Event()
    b_done = threading.Event()
    lock = threading.Lock()

    def post(_url, _body, headers):
        eid = headers["X-GeoStudio-Delivery"]
        with lock:
            sent.append(eid)
            a_posts = sum(1 for e in sent if e in mine)
        if threading.current_thread().name == "A" and a_posts == 2:
            # A a déjà COMMITÉ sa 1re livraison : l'ancien code avait alors relâché
            # les verrous de tout son lot, que B relivrait.
            a_second_post.set()
            b_done.wait(20)

    def sweep_a():
        with Session() as s:
            delivery.deliver_due(s, post=post, limit=6)

    def sweep_b():
        a_second_post.wait(20)
        try:
            with Session() as s:
                delivery.deliver_due(s, post=post, limit=6)
        finally:
            b_done.set()

    threads = [threading.Thread(target=sweep_a, name="A"), threading.Thread(target=sweep_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    counts = collections.Counter(e for e in sent if e in mine)
    assert max(counts.values()) == 1, counts
    assert set(counts) == mine


# Mineurs ----------------------------------------------------------------------


def test_auto_disable_is_audited(db):
    tid, (eid,) = _tenant_with_hook(db, events=1)

    def failing(*_a):
        raise delivery.DeliveryError("boom")

    with db() as s:
        hook = s.scalars(select(OutboundWebhook).where(OutboundWebhook.tenant_id == tid)).one()
        hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1
        s.get(OutboxEvent, eid).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)
        s.commit()
        delivery.deliver_due(s, post=failing)
        assert hook.enabled is False
        log = s.scalars(select(AuditLog).where(AuditLog.action == "webhook.disabled")).one()
        assert (log.tenant_id, log.object_id, log.actor_kind) == (tid, hook.id, "system")


def test_old_outbox_rows_are_purged_pending_included(db):
    _, (old_done, old_pending, recent_done) = _tenant_with_hook(db, events=3)
    with db() as s:
        long_ago = NOW - timedelta(days=delivery.OUTBOX_RETENTION_DAYS + 1)
        for eid, status, created in (
            (old_done, "delivered", long_ago),
            (old_pending, "pending", long_ago),
            (recent_done, "failed", NOW),
        ):
            ev = s.get(OutboxEvent, eid)
            ev.status, ev.created_at = status, created
        s.commit()
        assert delivery.purge_outbox(s) == 2
        assert {e.id for e in s.scalars(select(OutboxEvent))} == {recent_done}


# AUD-085 / AUD-170 / AUD-168 --------------------------------------------------


def _fail_with(status):
    def post(*_a):
        resp = requests.Response()
        resp.status_code = status
        try:
            raise requests.HTTPError(f"{status}", response=resp)
        except requests.HTTPError as exc:
            raise delivery.DeliveryError(f"livraison échouée : {exc}") from exc

    return post


def _hook_of(s, tid):
    return s.scalars(select(OutboundWebhook).where(OutboundWebhook.tenant_id == tid)).one()


def test_a_short_outage_neither_disables_nor_drops_events(db):
    """AUD-085 : 5 échecs en ~7 min désactivaient la destination et détruisaient l'outbox."""
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        hook = _hook_of(s, tid)
        hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert hook.enabled is True
        assert hook.consecutive_failures == delivery.MAX_CONSECUTIVE_FAILURES
        assert s.get(OutboxEvent, eid).status == "pending"


def test_a_day_long_outage_disables_but_keeps_pending_events_for_reenable(db):
    tid, (old, recent) = _tenant_with_hook(db, events=2)
    with db() as s:
        hook = _hook_of(s, tid)
        hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1
        s.get(OutboxEvent, old).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert hook.enabled is False
        old_ev, recent_ev = s.get(OutboxEvent, old), s.get(OutboxEvent, recent)
        assert old_ev.status == "failed" and "abandonné" in old_ev.last_error
        assert recent_ev.status == "pending"
        # réactivation (PATCH enabled=true) : l'événement gardé repart
        hook.enabled, hook.consecutive_failures = True, 0
        recent_ev.next_attempt_at = NOW - timedelta(seconds=1)
        s.commit()
        assert delivery.deliver_due(s, post=lambda *a: None) == 1
        assert recent_ev.status == "delivered"


def test_a_payload_rejection_fails_only_that_event(db):
    """AUD-170 : un 4xx propre au contenu n'est plus rejoué indéfiniment ni compté contre
    la destination."""
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        delivery.deliver_due(s, post=_fail_with(422))
        ev, hook = s.get(OutboxEvent, eid), _hook_of(s, tid)
        assert ev.status == "failed"
        assert (hook.enabled, hook.consecutive_failures) == (True, 0)


def test_a_too_old_event_is_given_up(db):
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        s.get(OutboxEvent, eid).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert s.get(OutboxEvent, eid).status == "failed"
        assert _hook_of(s, tid).enabled is True  # 1 seul échec consécutif


def test_a_database_error_on_one_event_does_not_abort_the_sweep(db, monkeypatch):
    """AUD-168 : destination supprimée pendant la livraison -> StaleDataError propagée
    jusqu'à la tâche (reste du lot en attente du bail, purges sautées)."""
    tid, (first, second) = _tenant_with_hook(db, events=2)
    real = delivery.deliver_one

    def flaky(session, event, hook, *, post):
        if event.id == first:
            raise RuntimeError("ligne disparue")
        return real(session, event, hook, post=post)

    monkeypatch.setattr(delivery, "deliver_one", flaky)
    with db() as s:
        assert delivery.deliver_due(s, post=lambda *a: None) == 1
        assert s.get(OutboxEvent, first).status == "pending"  # bail : repris plus tard
        assert s.get(OutboxEvent, second).status == "delivered"


def test_seen_keys_are_purged_and_older_objects_are_ignored(db):
    tid, _ = _tenant_with_hook(db, events=0)
    with db() as s:
        owner = s.scalars(select(OutboundWebhook.created_by)).first()
        item = items_repo.create_item(
            s, tenant_id=tid, owner_id=owner, resource_type="pipeline", title="p"
        )
        trigger = FileTrigger(
            id="ft1",
            tenant_id=tid,
            pipeline_item_id=item.id,
            secret_name="s3",
            prefix="s3://b/in/",
            created_by=owner,
            created_at=NOW - timedelta(days=60),
        )
        s.add(trigger)
        horizon = timedelta(days=triggers.SEEN_RETENTION_DAYS)
        s.add_all(
            [
                FileTriggerSeen(
                    id="old",
                    tenant_id=tid,
                    trigger_id="ft1",
                    object_key="a",
                    etag="e",
                    created_at=NOW - horizon - timedelta(days=2),
                ),
                FileTriggerSeen(
                    id="new", tenant_id=tid, trigger_id="ft1", object_key="b", etag="e"
                ),
            ]
        )
        s.commit()
        assert triggers.purge_seen(s) == 1
        assert [r.id for r in s.scalars(select(FileTriggerSeen))] == ["new"]
        # un objet plus vieux que l'horizon n'est plus candidat (sa clé a pu être purgée)
        assert triggers.considered_since(trigger, now=NOW) == NOW - horizon
        trigger.created_at = NOW - timedelta(hours=1)
        assert triggers.considered_since(trigger, now=NOW) == trigger.created_at
