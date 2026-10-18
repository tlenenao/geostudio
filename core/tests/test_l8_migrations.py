# SPDX-License-Identifier: Apache-2.0
"""Migrations L8 (0160+) rejouées pour de vrai, sur une base NON vide, dans les deux sens
(piège n°8). Base jetable, jamais le schéma partagé."""

import json
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


_ = json
