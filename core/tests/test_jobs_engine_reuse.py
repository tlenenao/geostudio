# SPDX-License-Identifier: Apache-2.0
"""P01.06 (c02-013) : un seul Engine par URL et par process worker."""

from app.jobs.engine import session_factory


def test_session_factory_reuses_one_engine_per_url(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/x.db")
    assert session_factory().kw["bind"] is session_factory().kw["bind"]


def test_postgres_engine_pings_before_reuse():
    # L'Engine mis en cache survit à un redémarrage de pgbouncer/postgres : sans
    # pre_ping, la première tâche suivante échouerait sur une connexion morte.
    from app.db import make_engine

    assert make_engine("postgresql+psycopg://u:p@localhost/db").pool._pre_ping is True


def test_in_memory_sqlite_stays_a_fresh_database_per_call(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    assert session_factory().kw["bind"] is not session_factory().kw["bind"]
