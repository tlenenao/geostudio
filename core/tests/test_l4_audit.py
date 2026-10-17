# SPDX-License-Identifier: Apache-2.0
"""L4 : audit_log scellé/vérifiable/retenu (AUD-092), export RGPD (AUD-120), rattrapage S3 de
purge et rejeu des effacements (AUD-121)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import db
from app.audit import chain
from app.audit.models import AuditLog
from app.audit.retention import apply_retention
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.compliance.export import export_user_data
from app.compliance.models import PurgeReceipt
from app.compliance.purge import S3_PENDING, retry_pending_s3_purges
from app.compliance.service import anonymize_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        alice = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="alice",
            username="alice",
            email="alice@example.org",
            first_name="Alice",
            last_name="Martin",
        )
        s.commit()
        ids = (tenant.id, admin.id, alice.id)
    yield Session, ids
    engine.dispose()


def _audit(session, tenant_id, n, **kw):
    for i in range(n):
        write_audit(
            session,
            tenant_id=tenant_id,
            actor_id=kw.get("actor_id"),
            actor_kind="user",
            action="x.y",
            object_type="o",
            object_id=str(i),
            payload=kw.get("payload"),
        )
    session.commit()


def test_seal_chains_rows_and_verify_detects_tampering_and_gaps(env):
    Session, (tenant_id, *_rest) = env
    with Session() as s:
        _audit(s, tenant_id, 5)
        assert chain.verify(s, tenant_id)["unsealed"] == 5
        assert chain.seal_all(s, tenant_id) == 5
        ok = chain.verify(s, tenant_id)
        assert ok["ok"] and ok["checked"] == 5 and ok["lastSeq"] == 5 and ok["unsealed"] == 0
        # le scellement est incrémental : de nouvelles lignes prolongent la même chaîne
        _audit(s, tenant_id, 2)
        chain.seal_all(s, tenant_id)
        assert chain.verify(s, tenant_id)["checked"] == 7
        # falsification d'une ligne : détectée
        s.execute(update(AuditLog).where(AuditLog.chain_seq == 3).values(action="forged"))
        s.commit()
        assert chain.verify(s, tenant_id)["brokenAtSeq"] == 3
        s.execute(update(AuditLog).where(AuditLog.chain_seq == 3).values(action="x.y"))
        s.commit()
        assert chain.verify(s, tenant_id)["ok"]
        # suppression au milieu : détectée (trou de séquence)
        s.execute(AuditLog.__table__.delete().where(AuditLog.chain_seq == 4))
        s.commit()
        assert chain.verify(s, tenant_id)["brokenAtSeq"] == 5


def test_payload_is_not_part_of_the_hash_so_it_can_be_erased(env):
    Session, (tenant_id, *_rest) = env
    with Session() as s:
        _audit(s, tenant_id, 1, payload={"filename": "dupont.csv"})
        chain.seal_all(s, tenant_id)
        s.execute(update(AuditLog).values(payload={}))
        s.commit()
        assert chain.verify(s, tenant_id)["ok"]


def test_anonymize_scrubs_pii_payload_keys_but_keeps_action_and_chain(env):
    Session, (tenant_id, _admin, alice) = env
    with Session() as s:
        _audit(s, tenant_id, 1, actor_id=alice, payload={"filename": "dupont.csv", "rows": 3})
        chain.seal_all(s, tenant_id)
        anonymize_user(s, tenant_id=tenant_id, user_id=alice)
        s.commit()
        row = s.scalars(select(AuditLog).where(AuditLog.object_id == "0")).one()
        assert row.payload == {"rows": 3} and row.action == "x.y"
        chain.seal_all(s, tenant_id)
        assert chain.verify(s, tenant_id)["ok"]


def test_retention_archives_then_deletes_old_rows_only(env):
    Session, (tenant_id, *_rest) = env

    class _S3:
        def __init__(self):
            self.objects = {}

        def create_bucket(self, **kw):
            pass

        def put_object(self, *, Bucket, Key, Body, **kw):
            self.objects[Key] = Body

    s3 = _S3()
    with Session() as s:
        _audit(s, tenant_id, 4)
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=400)
        s.execute(update(AuditLog).where(AuditLog.object_id.in_(["0", "1"])).values(created_at=old))
        s.commit()
        assert apply_retention(s, s3, days=0) == 0  # 0 = conservation illimitée
        assert apply_retention(s, s3, days=365) == 2
        s.commit()
        assert [r.object_id for r in s.scalars(select(AuditLog).order_by(AuditLog.id))] == [
            "2",
            "3",
        ]
        (body,) = s3.objects.values()
        archived = [json.loads(line) for line in body.decode().splitlines()]
        assert [a["objectId"] for a in archived] == ["0", "1"] and all(a["hash"] for a in archived)
        # les lignes conservées restent vérifiables (la 1re sert d'ancre)
        assert chain.verify(s, tenant_id)["ok"]


def test_user_export_contains_the_subject_data_and_is_scoped(env):
    Session, (tenant_id, _admin, alice) = env
    with Session() as s:
        _audit(s, tenant_id, 2, actor_id=alice)
        dossier = export_user_data(s, tenant_id=tenant_id, user_id=alice)
        assert dossier["profile"]["email"] == "alice@example.org"
        assert len(dossier["auditLog"]) == 2 and dossier["truncated"] == []
        with pytest.raises(LookupError):
            export_user_data(s, tenant_id="autre", user_id=alice)


def test_export_route_self_vs_other_and_audited(env):
    Session, (tenant_id, admin, alice) = env
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    api = TestClient(app)
    with Session() as s:
        alice_user = s.get(User, alice)
        s.expunge(alice_user)
        admin_user = s.get(User, admin)
        s.expunge(admin_user)
    app.dependency_overrides[get_current_user] = lambda: alice_user
    me = api.get("/v1/compliance/users/me/export")
    assert me.status_code == 200 and me.json()["profile"]["id"] == alice
    # un utilisateur sans compliance.manage ne lit pas le dossier d'un autre
    assert api.get(f"/v1/compliance/users/{admin}/export").status_code == 403
    assert api.get("/v1/compliance/audit/verify").status_code == 403
    with Session() as s:
        actions = [r.action for r in s.scalars(select(AuditLog))]
        assert "user.export" in actions


def test_retry_pending_s3_purges_settles_the_receipt(env, monkeypatch):
    Session, _ids = env
    purged = []
    monkeypatch.setattr(
        "app.compliance.purge._purge_tenant_s3",
        lambda s3, tenant_id, export_keys, appexport_keys: (
            purged.append((tenant_id, tuple(export_keys))) or 7
        ),
    )
    with Session() as s:
        s.add(
            PurgeReceipt(
                id="p1",
                tenant_slug="acme",
                purged_tenant_id="t-acme",
                requested_by_user_id="u",
                requested_at=datetime.now(UTC),
                counts={"s3_cleanup_failed": 1, "s3_pending_export_keys": ["renders/a.pdf"]},
                status=S3_PENDING,
            )
        )
        s.commit()
        assert retry_pending_s3_purges(s, object()) == 1
        s.commit()
        receipt = s.get(PurgeReceipt, "p1")
        assert receipt.status == "done" and "s3_cleanup_failed" not in receipt.counts
        assert receipt.counts["s3_objects_deleted"] == 7
    assert purged == [("t-acme", ("renders/a.pdf",))]
