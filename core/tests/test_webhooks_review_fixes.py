# SPDX-License-Identifier: Apache-2.0
"""ARC4-F6, corrections de revue : listage S3 paginé et plafonné visiblement, émission
de `pipeline.run.finished` par annulation et reprise, échec inattendu isolé par destination."""

import sys
import types
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.outbox.models import FileTrigger, OutboundWebhook, OutboxEvent
from app.pipelines import repository as prepo
from app.secrets import repository as secrets_repo
from app.secrets.schemas import S3CredentialsPayload
from app.webhooks import triggers
from app.webhooks.delivery import deliver_due
from tests.test_webhooks_outbox import _event, _lister, _pipeline, _seed, db  # noqa: F401


def test_s3_lister_paginates_past_1000_keys_and_sees_the_late_recent_file(monkeypatch):
    now = datetime.now(UTC)
    pages = [
        {
            "Contents": [
                {"Key": f"in/{i:05d}.csv", "ETag": '"e"', "LastModified": now - timedelta(days=9)}
                for i in range(start, start + 1000)
            ]
        }
        for start in (0, 1000)
    ]
    pages.append({"Contents": [{"Key": "in/zzz-new.csv", "ETag": '"n"', "LastModified": now}]})

    class _Pager:
        def paginate(self, **kw):
            assert "PaginationConfig" not in kw  # pas de troncature à 1000
            return iter(pages)

    fake = types.SimpleNamespace(
        client=lambda *a, **k: types.SimpleNamespace(get_paginator=lambda name: _Pager())
    )
    monkeypatch.setitem(sys.modules, "boto3", fake)
    out = triggers.s3_lister(
        S3CredentialsPayload(awsAccessKeyId="k", awsSecretAccessKey="s", bucketUrl="s3://b"),
        "b",
        "in/",
    )
    assert len(out) == 2001 and out[-1][0] == "in/zzz-new.csv"


def test_a_capped_listing_is_visible_in_last_error(db, monkeypatch):  # noqa: F811
    tenant_id, user_id = _seed(db)
    _pipeline(db, tenant_id, user_id)
    monkeypatch.setattr(triggers, "MAX_KEYS", 2)
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    files = [("in/a.csv", "e1", old), ("in/b.csv", "e2", old)]
    with db() as s:
        t = s.get(FileTrigger, "t1")
        triggers.poll_trigger(s, t, defer_task=lambda r, tn: None, lister=_lister(files))
        assert t.last_error and "tronqué" in t.last_error


def test_cancel_and_reclaim_emit_pipeline_run_finished(db):  # noqa: F811
    tenant_id, user_id = _seed(db)
    pipeline_id = _pipeline(db, tenant_id, user_id)
    with db() as s:
        cancelled = prepo.create_run(s, tenant_id=tenant_id, pipeline_item_id=pipeline_id)
        stuck = [
            prepo.create_run(s, tenant_id=tenant_id, pipeline_item_id=pipeline_id) for _ in range(2)
        ]
        s.commit()
        prepo.mark_cancelled(s, run_id=cancelled.id)
        for r in stuck:
            r.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=5)
        s.commit()
        assert prepo.reclaim_stuck_runs(s) == 2
        s.commit()
        got = [
            (e.payload["runId"], e.payload["status"])
            for e in s.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "pipeline.run.finished")
            )
        ]
        want = [(cancelled.id, "cancelled")] + [(r.id, "failed") for r in stuck]
        assert sorted(got) == sorted(want)


def test_an_unexpected_error_is_counted_on_the_faulty_destination(db, monkeypatch):  # noqa: F811
    tenant_id, _ = _seed(db)
    with db() as s:
        ev = _event(s, tenant_id)

        def boom(*a, **k):
            raise ValueError("déchiffrement")

        monkeypatch.setattr(secrets_repo, "get_secret_payload", boom)
        assert deliver_due(s, post=lambda *a: None) == 0
        hook = s.get(OutboundWebhook, "h1")
        assert hook.consecutive_failures == 1 and ev.attempts == 1 and ev.status == "pending"


def test_reclaim_leaves_a_finished_run_untouched_and_silent(db):  # noqa: F811
    tenant_id, user_id = _seed(db)
    pipeline_id = _pipeline(db, tenant_id, user_id)
    with db() as s:
        done = prepo.create_run(s, tenant_id=tenant_id, pipeline_item_id=pipeline_id)
        done.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=5)
        s.commit()
        prepo.mark_succeeded(s, run_id=done.id, node_stats={})
        s.commit()
        before = s.scalar(select(func.count()).select_from(OutboxEvent))
        assert prepo.reclaim_stuck_runs(s) == 0
        s.commit()
        assert done.status == "succeeded" and done.error is None
        assert s.scalar(select(func.count()).select_from(OutboxEvent)) == before


def test_rejects_and_direct_cancels_emit_their_terminal_status(db):  # noqa: F811
    """Intégration vague 4 (K1×K2×L) : `succeeded_with_rejects` part tel quel dans
    `pipeline.run.finished`, et une annulation directe (queued/retrying -> cancelled,
    sans passage par le worker) émet aussi la fin du run."""
    tenant_id, user_id = _seed(db)
    pipeline_id = _pipeline(db, tenant_id, user_id)
    with db() as s:
        rejects, queued, retrying = (
            prepo.create_run(s, tenant_id=tenant_id, pipeline_item_id=pipeline_id) for _ in range(3)
        )
        retrying.status = "retrying"
        s.commit()
        prepo.mark_succeeded(s, run_id=rejects.id, node_stats={"w1": {"rejected": 7}})
        assert prepo.request_cancel(s, queued) == "cancelled"
        assert prepo.request_cancel(s, retrying) == "cancelled"
        s.commit()
        got = {
            e.payload["runId"]: e.payload["status"]
            for e in s.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "pipeline.run.finished")
            )
        }
        assert got == {
            rejects.id: "succeeded_with_rejects",
            queued.id: "cancelled",
            retrying.id: "cancelled",
        }
