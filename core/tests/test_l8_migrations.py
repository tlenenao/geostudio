# SPDX-License-Identifier: Apache-2.0
"""Migrations L8 (0160+) rejouées pour de vrai, sur une base NON vide, dans les deux sens
(piège n°8). Base jetable, jamais le schéma partagé."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    name = f"l8_migration_{uuid.uuid4().hex[:8]}"
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


@pytest.fixture()
def migrate(throwaway_url):
    """Renvoie (cfg, engine) ; DATABASE_URL pointe la base jetable le temps du test."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_url
    engine = sa.create_engine(throwaway_url)
    try:
        yield _cfg(), engine
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _insert(conn, table, **vals):
    """INSERT qui complète les colonnes NOT NULL sans défaut avec une valeur neutre."""
    cols = conn.execute(
        sa.text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :t AND is_nullable = 'NO' AND column_default IS NULL"
        ),
        {"t": table},
    ).all()
    row = dict(vals)
    for name, dtype in cols:
        if name in row:
            continue
        if dtype in ("integer", "bigint"):
            row[name] = 0
        elif dtype.startswith("timestamp"):
            row[name] = sa.text("now()")
        elif dtype in ("json", "jsonb"):
            row[name] = "{}"
        elif dtype == "boolean":
            row[name] = False
        else:
            row[name] = f"x-{name}"
    names = ", ".join(row)
    params = {k: v for k, v in row.items() if not isinstance(v, sa.TextClause)}
    placeholders = ", ".join(
        v.text if isinstance(v, sa.TextClause) else f":{k}" for k, v in row.items()
    )
    conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({placeholders})"), params)


def _base(conn):
    _insert(conn, "tenants", id="t1", slug="t1", name="T")
    _insert(conn, "roles", id="r1", tenant_id="t1", name="r")
    _insert(conn, "users", id="u1", tenant_id="t1", oidc_sub="s1", username="u1", role_id="r1")
    _insert(
        conn,
        "collections",
        id="c1",
        tenant_id="t1",
        owner_id="u1",
        table_name="c1",
        title="C",
        pk_column="id",
    )


def test_0160_collect_client_ops_round_trips_on_a_non_empty_base(migrate):
    cfg, engine = migrate
    command.upgrade(cfg, "0123")
    with engine.begin() as conn:
        _base(conn)
    command.upgrade(cfg, "0160")
    op = dict(
        id="o1", tenant_id="t1", collection_id="c1", actor_id="u1", client_op_id="k", kind="feature"
    )
    with engine.begin() as conn:
        _insert(conn, "collect_client_ops", **op)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(conn, "collect_client_ops", **{**op, "id": "o2"})
    with engine.begin() as conn:  # kind différent : autorisé
        _insert(conn, "collect_client_ops", **{**op, "id": "o3", "kind": "attachment"})
        conn.execute(sa.text("DELETE FROM collections WHERE id = 'c1'"))  # CASCADE
        assert conn.scalar(sa.text("SELECT count(*) FROM collect_client_ops")) == 0
        _insert(
            conn,
            "collections",
            id="c1",
            tenant_id="t1",
            owner_id="u1",
            table_name="c1",
            title="C",
            pk_column="id",
        )
    command.downgrade(cfg, "0123")
    with engine.begin() as conn:
        assert conn.scalar(sa.text("SELECT to_regclass('collect_client_ops')")) is None
        assert conn.scalar(sa.text("SELECT count(*) FROM collections WHERE id = 'c1'")) == 1
    command.upgrade(cfg, "head")


def test_single_head():
    from alembic.script import ScriptDirectory

    assert len(ScriptDirectory.from_config(_cfg()).get_heads()) == 1


def test_0161_dedupes_attachments_then_enforces_unique_s3_key(migrate):
    cfg, engine = migrate
    command.upgrade(cfg, "0160")
    with engine.begin() as conn:
        _base(conn)
        for att_id, created in (("a2", "2026-01-02"), ("a1", "2026-01-01"), ("a3", "2026-01-03")):
            _insert(
                conn,
                "attachments",
                id=att_id,
                tenant_id="t1",
                collection_id="c1",
                fid="1",
                field_key="photo",
                s3_key="t1/c1/1/same.jpg" if att_id != "a3" else "t1/c1/1/other.jpg",
                created_by="u1",
                created_at=sa.text(f"'{created}'::timestamp"),
            )
    command.upgrade(cfg, "0161")
    with engine.begin() as conn:
        ids = conn.execute(sa.text("SELECT id FROM attachments ORDER BY id")).scalars().all()
        assert ids == ["a1", "a3"]  # doublon : la plus ancienne gagne
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(
            conn,
            "attachments",
            id="a4",
            tenant_id="t1",
            collection_id="c1",
            fid="2",
            field_key="photo",
            s3_key="t1/c1/1/same.jpg",
            created_by="u1",
        )
    command.downgrade(cfg, "0160")
    with engine.begin() as conn:
        _insert(
            conn,
            "attachments",
            id="a5",
            tenant_id="t1",
            collection_id="c1",
            fid="2",
            field_key="photo",
            s3_key="t1/c1/1/same.jpg",
            created_by="u1",
        )  # plus d'unicité après le downgrade
    command.upgrade(cfg, "head")  # a5 est un doublon : le re-upgrade le dédoublonne
    with engine.begin() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM attachments")) == 2


def test_0162_geometry_required_defaults_false_on_existing_rows_and_round_trips(migrate):
    cfg, engine = migrate
    command.upgrade(cfg, "0161")
    with engine.begin() as conn:
        _base(conn)
    command.upgrade(cfg, "0162")
    with engine.begin() as conn:
        assert conn.scalar(sa.text("SELECT geometry_required FROM collections")) is False
        conn.execute(sa.text("UPDATE collections SET geometry_required = true"))
    command.downgrade(cfg, "0161")
    with engine.begin() as conn:
        cols = conn.scalar(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'collections' AND column_name = 'geometry_required'"
            )
        )
        assert cols == 0
        assert conn.scalar(sa.text("SELECT count(*) FROM collections")) == 1
    command.upgrade(cfg, "head")


def test_0163_keeps_pending_submissions_and_enforces_client_op_uniqueness(migrate, monkeypatch):
    cfg, engine = migrate
    command.upgrade(cfg, "0162")
    with engine.begin() as conn:
        _base(conn)
        _insert(
            conn,
            "submission_tokens",
            id="tk1",
            tenant_id="t1",
            collection_id="c1",
            created_by="u1",
            name="f",
            token_prefix="gss_x",
            expires_at=sa.text("now()"),
        )
        _insert(
            conn,
            "submissions",
            id="s1",
            tenant_id="t1",
            collection_id="c1",
            token_id="tk1",
            status="pending",
            payload="{}",
            attachment='{"fieldKey": "photo"}',
            attachment_key="t1/c1/pending-x/a.png",
        )
    command.upgrade(cfg, "0163")
    with engine.begin() as conn:  # soumission en attente conservée, client_op_id nul
        assert conn.scalar(sa.text("SELECT client_op_id FROM submissions WHERE id = 's1'")) is None
        _insert(
            conn,
            "submissions",
            id="s2",
            tenant_id="t1",
            collection_id="c1",
            token_id="tk1",
            status="pending",
            payload="{}",
            client_op_id="op",
        )
        _insert(
            conn,
            "submissions",
            id="s3",
            tenant_id="t1",
            collection_id="c1",
            token_id="tk1",
            status="pending",
            payload="{}",
        )  # plusieurs NULL autorisés
        _insert(
            conn, "submission_files", id="f1", tenant_id="t1", submission_id="s1", field_key="photo"
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(
            conn,
            "submissions",
            id="s4",
            tenant_id="t1",
            collection_id="c1",
            token_id="tk1",
            status="pending",
            payload="{}",
            client_op_id="op",
        )
    monkeypatch.delenv("GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="downgrade refusé"):  # AUD-192 : submission_files
        command.downgrade(cfg, "0162")
    monkeypatch.setenv("GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE", "1")
    command.downgrade(cfg, "0162")
    with engine.begin() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM submissions")) == 3
        assert conn.scalar(sa.text("SELECT to_regclass('submission_files')")) is None
    command.upgrade(cfg, "head")
