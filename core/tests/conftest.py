# SPDX-License-Identifier: Apache-2.0
"""Fixtures partagées. Les fixtures SQLite restent locales à chaque fichier
(pattern existant) ; ce conftest ne porte que l'infra PostGIS optionnelle."""
import os

import pytest
from sqlalchemy import create_engine, text

from app.db import make_session_factory


@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    engine = create_engine(url)
    # Le rôle RLS et les extensions vector/pg_trgm existent dans la base de
    # test (idempotent) : les tests DDL (SP-3) et d'embedding (SP-7)
    # construisent leur schéma via Base.metadata.create_all(), jamais
    # `alembic upgrade head` — la migration seule ne suffit donc pas ici.
    with engine.begin() as conn:
        conn.execute(text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gis_rls') "
            "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;"
        ))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_session_factory(pg_engine):
    return make_session_factory(pg_engine)
