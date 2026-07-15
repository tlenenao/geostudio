# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import init_db, make_engine, make_session_factory
from app.tenants.models import Tenant


def test_init_db_creates_all_tables_on_sqlite():
    """create_all() must still run for the SQLite fast-test/dev path: every
    other test in the suite relies on init_db() populating the schema on an
    in-memory SQLite engine."""
    engine = make_engine("sqlite+pysqlite:///:memory:")
    try:
        init_db(engine)

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert {"tenants", "users", "audit_log", "configs", "config_revisions"} <= table_names

        # And the schema is actually usable, not just present.
        Session = make_session_factory(engine)
        with Session() as session:
            session.add(Tenant(id="t1", name="Tenant 1", slug="tenant-1"))
            session.commit()
    finally:
        engine.dispose()


def test_init_db_skips_create_all_on_non_sqlite_dialect():
    """On any non-SQLite dialect (Postgres in practice), init_db() must not
    call Base.metadata.create_all() — Alembic migrations are the sole source
    of truth for schema there, and running create_all() first would make
    `alembic upgrade head` fail with "relation already exists" the first
    time it's run against that database.

    We can't spin up a real Postgres for this unit test, so we assert the
    dialect-detection branch directly against the engine's dialect name
    (this is exactly the condition init_db() branches on) and confirm that
    calling init_db() against a dialect reporting a non-sqlite name does not
    raise and does not attempt to touch Base.metadata (verified by asserting
    it never reaches a real connection: a bogus, unreachable "postgresql"
    URL would fail loudly the moment create_all() tried to open a
    connection, whereas init_db() returning cleanly here proves the
    create_all() call was skipped).
    """
    engine = make_engine("postgresql+psycopg://user:pass@unreachable-host:1/db")
    try:
        assert engine.dialect.name != "sqlite"
        # If init_db() were still calling create_all() unconditionally, this
        # would raise (DNS/connection failure to "unreachable-host"). It must
        # return cleanly because the sqlite-only branch skips create_all().
        init_db(engine)
    finally:
        engine.dispose()
