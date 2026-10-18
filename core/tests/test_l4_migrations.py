# SPDX-License-Identifier: Apache-2.0
"""Migrations L4 (0120+) rejouées pour de vrai, sur une base NON vide, dans les deux sens
(piège n°8). Base jetable, jamais le schéma partagé."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import DBAPIError

from alembic import command

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    name = f"l4_migration_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{name}\1", test_db_url)
    eng = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        for ext in ("postgis", "vector", "pg_trgm"):
            conn.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    eng.dispose()
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _cfg():
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    return cfg


def test_audit_log_trigger_is_append_only_and_migration_round_trips(throwaway_url):
    cfg = _cfg()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_url
    try:
        command.upgrade(cfg, "0095")
        engine = sa.create_engine(throwaway_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
            for i in range(2):
                conn.execute(
                    sa.text(
                        "INSERT INTO audit_log (tenant_id, actor_kind, action, object_type, "
                        "object_id, payload, created_at) "
                        "VALUES ('t1', 'user', 'a', 'o', :i, '{}', now())"
                    ),
                    {"i": str(i)},
                )
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            # lignes préexistantes conservées, non scellées
            assert conn.scalar(sa.text("SELECT count(*) FROM audit_log WHERE hash IS NULL")) == 2
            for stmt in (
                "UPDATE audit_log SET actor_id = NULL",
                "UPDATE audit_log SET action = 'forged'",
                "DELETE FROM audit_log",
            ):
                with pytest.raises(DBAPIError, match="append-only"):
                    conn.execute(sa.text(stmt))
                conn.rollback()
            # le scellement (poser hash/prev_hash/chain_seq sur une ligne non scellée) passe
            conn.execute(
                sa.text(
                    "UPDATE audit_log SET chain_seq = 1, prev_hash = '', hash = 'h' "
                    "WHERE object_id = '0'"
                )
            )
            conn.commit()
            # …mais une ligne scellée ne se réécrit plus, ni ne se descelle
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(sa.text("UPDATE audit_log SET hash = 'x' WHERE object_id = '0'"))
            conn.rollback()
            # la maintenance explicite lève la garde, le temps de la transaction
            conn.execute(sa.text("SELECT set_config('app.audit_maintenance', 'on', true)"))
            conn.execute(sa.text("DELETE FROM audit_log WHERE object_id = '1'"))
            conn.commit()
            assert conn.scalar(sa.text("SELECT count(*) FROM audit_log")) == 1
            purged_cols = {
                r[0]
                for r in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'purge_receipts'"
                    )
                )
            }
            assert "purged_tenant_id" in purged_cols
        engine.dispose()

        command.downgrade(cfg, "0095")
        engine = sa.create_engine(throwaway_url)
        with engine.begin() as conn:
            assert conn.scalar(sa.text("SELECT count(*) FROM audit_log")) == 1
            assert not conn.scalar(
                sa.text("SELECT count(*) FROM pg_trigger WHERE tgname = 'audit_log_guard'")
            )
            conn.execute(sa.text("DELETE FROM audit_log"))  # plus de garde
        engine.dispose()
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def test_orm_seal_scrub_and_retention_work_through_the_real_trigger(throwaway_url):
    from datetime import UTC, datetime
    from datetime import timedelta as td

    from sqlalchemy import select, update
    from sqlalchemy.orm import Session

    from app.audit import chain
    from app.audit.models import AuditLog
    from app.audit.retention import apply_retention
    from app.audit.writer import write_audit

    cfg = _cfg()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    engine = sa.create_engine(throwaway_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1','t1','T',now())")
        )

    class _S3:
        def __init__(self):
            self.objects = {}

        def create_bucket(self, **kw):
            pass

        def put_object(self, *, Bucket, Key, Body, **kw):
            self.objects[Key] = Body

    with Session(engine) as s:
        for i in range(3):
            write_audit(
                s,
                tenant_id="t1",
                actor_id="u",
                actor_kind="user",
                action="a",
                object_type="o",
                object_id=str(i),
                payload={"filename": "f"},
            )
        s.commit()
        assert chain.seal_all(s, "t1") == 3
        s.commit()
        assert chain.verify(s, "t1")["ok"]
        # le payload (hors hachage) s'efface sous maintenance, la chaîne reste valide
        with chain.audit_maintenance(s):
            s.execute(update(AuditLog).values(payload={}))
        s.commit()
        assert chain.verify(s, "t1")["ok"]
        # hors maintenance, la même écriture est refusée par le trigger
        with pytest.raises(DBAPIError, match="append-only"):
            s.execute(update(AuditLog).values(payload={"x": 1}))
        s.rollback()
        old = datetime.now(UTC).replace(tzinfo=None) - td(days=400)
        with chain.audit_maintenance(s):
            s.execute(update(AuditLog).where(AuditLog.object_id == "0").values(created_at=old))
        s.commit()
        s3 = _S3()
        assert apply_retention(s, s3, days=365) == 1
        s.commit()
        assert [r.object_id for r in s.scalars(select(AuditLog).order_by(AuditLog.id))] == [
            "1",
            "2",
        ]
        assert chain.verify(s, "t1")["ok"] and len(s3.objects) == 1
    engine.dispose()


def test_tenant_limits_migration_round_trips_on_a_non_empty_base(throwaway_url):
    cfg = _cfg()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_url
    try:
        command.upgrade(cfg, "0121")
        engine = sa.create_engine(throwaway_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO tenant_limits (tenant_id, max_users) VALUES ('t1', 5)")
            )
            for table in ("item_shares", "collection_shares"):  # 0123 (AUD-097)
                conn.execute(sa.text(f"SELECT expires_at FROM {table}"))
            conn.execute(sa.text("DELETE FROM tenants WHERE id = 't1'"))  # CASCADE
            assert conn.scalar(sa.text("SELECT count(*) FROM tenant_limits")) == 0
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
        command.downgrade(cfg, "0121")
        with engine.begin() as conn:
            assert conn.scalar(sa.text("SELECT count(*) FROM tenants WHERE id = 't1'")) == 1
            assert conn.scalar(sa.text("SELECT to_regclass('tenant_limits')")) is None
        command.upgrade(cfg, "head")
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
