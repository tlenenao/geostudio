# SPDX-License-Identifier: Apache-2.0
"""ARC4-F6 (ADR 0027) : outbox transactionnelle, livraison signée, désactivation après
5 échecs, egress gardé, déclencheur fichier S3 (un fichier = un run). Base sqlite
en mémoire (même patron que test_pipeline_webhook_tokens.py)."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.notifications.models import Notification
from app.outbox.emit import emit
from app.outbox.models import FileTrigger, FileTriggerSeen, OutboundWebhook, OutboxEvent
from app.pipelines.models import PipelineRun
from app.secrets import crypto as secrets_crypto
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, BearerTokenPayload, S3CredentialsPayload
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from app.webhooks import triggers
from app.webhooks.delivery import DeliveryError, deliver_due

KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", KEY_B64)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _secret(s, tenant_id, user_id, name, payload):
    ct, nonce = secrets_crypto.encrypt(SECRET_PAYLOAD_ADAPTER.dump_python(payload))
    secrets_repo.create_secret(
        s,
        tenant_id=tenant_id,
        created_by=user_id,
        name=name,
        kind=payload.kind,
        ciphertext=ct,
        nonce=nonce,
    )


def _seed(Session, *, events=("item.created", "pipeline.run.finished")):
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="u",
            username="u",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        _secret(s, tenant.id, user.id, "sig", BearerTokenPayload(token="topsecret"))
        hook = OutboundWebhook(
            id="h1",
            tenant_id=tenant.id,
            url="https://hook.example.test/in",
            event_types=list(events),
            secret_name="sig",
            created_by=user.id,
        )
        s.add(hook)
        s.commit()
        return tenant.id, user.id


# 1) même transaction que l'écriture -------------------------------------------


def test_emit_is_atomic_with_the_emitting_write(db):
    tenant_id, user_id = _seed(db)
    with db() as s:
        items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=user_id, resource_type="map", title="rolled back"
        )
        s.rollback()  # crash/échec de l'écriture : aucun événement ne doit survivre
    with db() as s:
        assert s.scalars(select(OutboxEvent)).all() == []
        item = items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=user_id, resource_type="map", title="kept"
        )
        s.commit()
        events = s.scalars(select(OutboxEvent)).all()
        assert [(e.event_type, e.payload["itemId"], e.status) for e in events] == [
            ("item.created", item.id, "pending")
        ]


def test_emit_only_reaches_enabled_subscribed_destinations(db):
    tenant_id, _ = _seed(db)
    with db() as s:
        assert emit(s, tenant_id=tenant_id, event_type="item.updated", payload={}) == 0
        assert emit(s, tenant_id=tenant_id, event_type="item.created", payload={}) == 1
        s.get(OutboundWebhook, "h1").enabled = False
        s.flush()
        assert emit(s, tenant_id=tenant_id, event_type="item.created", payload={}) == 0


# 2) livraison signée / retries / désactivation ---------------------------------


def _event(s, tenant_id):
    emit(s, tenant_id=tenant_id, event_type="item.created", payload={"itemId": "i1"})
    s.commit()
    return s.scalars(select(OutboxEvent)).all()[-1]


def test_delivery_is_signed_with_the_vault_secret(db):
    tenant_id, _ = _seed(db)
    sent = []
    with db() as s:
        ev = _event(s, tenant_id)
        assert (
            deliver_due(s, post=lambda url, body, headers: sent.append((url, body, headers))) == 1
        )
        assert ev.status == "delivered"
    url, body, headers = sent[0]
    assert url == "https://hook.example.test/in"
    assert headers["X-GeoStudio-Signature"] == (
        "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    )
    assert json.loads(body)["itemId"] == "i1"


def _failing(url, body, headers):
    raise DeliveryError("boom")


def test_failures_back_off_then_disable_after_five_and_notify(db):
    tenant_id, user_id = _seed(db)
    with db() as s:
        ev = _event(s, tenant_id)
        hook = s.get(OutboundWebhook, "h1")
        previous = None
        for attempt in range(1, 6):
            ev.next_attempt_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            s.commit()
            assert deliver_due(s, post=_failing) == 0
            assert ev.attempts == attempt
            if attempt < 5:
                assert hook.enabled and ev.status == "pending"
                delay = ev.next_attempt_at - datetime.now(UTC).replace(tzinfo=None)
                assert previous is None or delay > previous  # backoff exponentiel
                previous = delay
        assert hook.enabled is False and hook.consecutive_failures == 5
        assert ev.status == "failed"
        notif = s.scalars(select(Notification)).one()
        assert (notif.kind, notif.recipient_user_id, notif.status) == (
            "webhook_disabled",
            user_id,
            "failure",
        )
        # plus de livraison tant que la destination est désactivée
        assert deliver_due(s, post=_failing) == 0


def test_a_success_resets_the_failure_counter(db):
    tenant_id, _ = _seed(db)
    with db() as s:
        ev = _event(s, tenant_id)
        hook = s.get(OutboundWebhook, "h1")
        hook.consecutive_failures = 4
        s.commit()
        assert deliver_due(s, post=lambda *a: None) == 1
        assert hook.consecutive_failures == 0 and ev.status == "delivered"


def test_private_destination_is_refused_by_the_egress_guard(db):
    tenant_id, _ = _seed(db)
    with db() as s:
        hook = s.get(OutboundWebhook, "h1")
        hook.url = "http://10.0.0.5/hook"  # RFC1918
        ev = _event(s, tenant_id)
        # vraie livraison (garde SSRF réelle) : refusée, comptée comme échec
        assert deliver_due(s) == 0
        assert "egress" in (ev.last_error or "")
        assert ev.status == "pending" and hook.consecutive_failures == 1


# 3) déclencheur fichier S3 ------------------------------------------------------


def _pipeline(Session, tenant_id, user_id):
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=user_id, resource_type="pipeline", title="P"
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "r1",
                                "kind": "reader",
                                "op": "reader.collection",
                                "params": {"collectionId": "x"},
                            },
                            {
                                "id": "w1",
                                "kind": "writer",
                                "op": "writer.export",
                                "params": {"format": "csv", "key": "o.csv"},
                            },
                        ],
                        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                    },
                }
            ),
            item_id=item.id,
            tenant_id=tenant_id,
        )
        s.add(
            FileTrigger(
                id="t1",
                tenant_id=tenant_id,
                pipeline_item_id=item.id,
                secret_name="s3",
                prefix="s3://dropbox/in/",
                created_by=user_id,
                created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
            )
        )
        _secret(
            s,
            tenant_id,
            user_id,
            "s3",
            S3CredentialsPayload(
                awsAccessKeyId="k", awsSecretAccessKey="s", bucketUrl="s3://dropbox"
            ),
        )
        s.commit()
        return item.id


def _lister(files):
    return lambda secret, bucket, prefix: files


def test_a_dropped_file_triggers_exactly_one_run(db):
    tenant_id, user_id = _seed(db)
    pipeline_id = _pipeline(db, tenant_id, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    files = [("in/a.csv", "etag1", now), ("in/old.csv", "e0", now - timedelta(days=1))]
    deferred = []
    with db() as s:
        t = s.get(FileTrigger, "t1")
        n = triggers.poll_trigger(
            s, t, defer_task=lambda r, tn: deferred.append(r), lister=_lister(files)
        )
        assert n == 1 and t.last_error is None  # old.csv antérieur au déclencheur : ignoré
        # sondages suivants sans nouveau fichier : aucun run supplémentaire
        for _ in range(3):
            assert (
                triggers.poll_trigger(
                    s, t, defer_task=lambda r, tn: deferred.append(r), lister=_lister(files)
                )
                == 0
            )
        assert len(deferred) == 1
        runs = s.scalars(select(PipelineRun)).all()
        assert len(runs) == 1 and runs[0].pipeline_item_id == pipeline_id
        assert s.scalars(select(FileTriggerSeen)).one().run_id == runs[0].id


def test_a_second_file_waits_for_the_active_run_then_runs_once(db):
    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    files = [("in/a.csv", "e1", now - timedelta(minutes=2)), ("in/b.csv", "e2", now)]
    with db() as s:
        t = s.get(FileTrigger, "t1")
        assert (
            triggers.poll_trigger(s, t, defer_task=lambda r, tn: None, lister=_lister(files)) == 1
        )
        run = s.scalars(select(PipelineRun)).one()
        run.status = "succeeded"
        s.commit()
        assert (
            triggers.poll_trigger(s, t, defer_task=lambda r, tn: None, lister=_lister(files)) == 1
        )
        assert len(s.scalars(select(PipelineRun)).all()) == 2
        assert len(s.scalars(select(FileTriggerSeen)).all()) == 2


def test_prefix_outside_the_secret_scope_is_refused(db):
    with pytest.raises(triggers.TriggerConfigError):
        triggers.check_scope(
            S3CredentialsPayload(
                awsAccessKeyId="k", awsSecretAccessKey="s", bucketUrl="s3://dropbox/in"
            ),
            "s3://dropbox/other/",
        )
    with pytest.raises(triggers.TriggerConfigError):
        triggers.check_scope(
            S3CredentialsPayload(awsAccessKeyId="k", awsSecretAccessKey="s"), "s3://dropbox/in/"
        )


def test_unusable_secret_is_traced_not_raised(db):
    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    with db() as s:
        t = s.get(FileTrigger, "t1")
        t.secret_name = "absent"
        assert triggers.poll_trigger(s, t, defer_task=lambda r, tn: None, lister=_lister([])) == 0
        assert "absent" in (t.last_error or "")


def test_http_exception_from_run_service_is_not_swallowed_silently(db, monkeypatch):
    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)

    def _deny(*a, **k):
        raise HTTPException(status_code=403, detail="not allowed")

    monkeypatch.setattr(triggers, "run_pipeline_service", _deny)
    with db() as s:
        t = s.get(FileTrigger, "t1")
        n = triggers.poll_trigger(
            s, t, defer_task=lambda r, tn: None, lister=_lister([("in/a.csv", "e", now)])
        )
        assert n == 0 and t.last_error == "not allowed"
        assert s.scalars(select(FileTriggerSeen)).all() == []  # fichier repris au prochain passage


def test_queue_unavailable_is_not_reported_as_a_trigger_config_error(db, monkeypatch):
    """AUD-025 (M5) : un 503 de mise en file est transitoire, pas une config invalide."""
    monkeypatch.setattr("app.jobs.defer.time.sleep", lambda _s: None)
    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)

    def down(run_id, tn):
        raise RuntimeError("down")

    with db() as s:
        t = s.get(FileTrigger, "t1")
        n = triggers.poll_trigger(s, t, defer_task=down, lister=_lister([("in/a.csv", "e1", now)]))
        assert n == 0
        assert "mise en file impossible" in t.last_error
        assert s.scalars(select(FileTriggerSeen)).all() == []  # repris au passage suivant


def test_an_erased_creator_neither_signs_nor_triggers(db):
    # Revue SP-L2 I3 : un compte effacé n'agit plus, même si sa destination ou son
    # déclencheur a été réactivé (erased_at testé au point d'usage du secret).
    from app.users.models import User

    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    with db() as s:
        s.get(User, user_id).erased_at = datetime.now(UTC).replace(tzinfo=None)
        s.commit()
        ev = _event(s, tenant_id)
        sent = []
        deliver_due(s, post=lambda url, body, headers: sent.append(url))
        assert sent == [] and ev.status != "delivered"
        t = s.get(FileTrigger, "t1")
        files = [("in/a.csv", "e1", datetime.now(UTC).replace(tzinfo=None))]
        assert (
            triggers.poll_trigger(s, t, defer_task=lambda r, tn: None, lister=_lister(files)) == 0
        )
        assert s.scalars(select(PipelineRun)).all() == []


def test_anonymize_disables_the_creator_webhooks_and_triggers(db):
    from app.compliance.service import anonymize_user

    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    with db() as s:
        get_or_create_user(  # second admin : le garde anti-lockout laisse effacer le premier
            s,
            tenant_id=tenant_id,
            oidc_sub="other-admin",
            username="other",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        anonymize_user(s, tenant_id=tenant_id, user_id=user_id)
        s.commit()
        assert s.get(OutboundWebhook, "h1").enabled is False
        assert s.get(FileTrigger, "t1").enabled is False
