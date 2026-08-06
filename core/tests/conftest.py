# SPDX-License-Identifier: Apache-2.0
"""Fixtures partagées. Les fixtures SQLite restent locales à chaque fichier
(pattern existant) ; ce conftest ne porte que l'infra PostGIS optionnelle."""
import os
from pathlib import Path

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


@pytest.fixture(scope="session")
def qgis_worker_url():
    url = os.environ.get("CORE_TEST_QGIS_WORKER_URL")
    if not url:
        pytest.skip("CORE_TEST_QGIS_WORKER_URL non défini — test qgis skippé")
    return url


@pytest.fixture(scope="session")
def qgis_scratch_dir():
    path = os.environ.get("CORE_TEST_QGIS_SCRATCH_DIR")
    if not path:
        pytest.skip("CORE_TEST_QGIS_SCRATCH_DIR non défini — test qgis skippé")
    return Path(path)


@pytest.fixture()
def pg_session_factory(pg_engine):
    return make_session_factory(pg_engine)


@pytest.fixture(scope="session")
def pg_engine_with_procrastinate_schema(pg_engine):
    """pg_engine, avec le schéma procrastinate (table procrastinate_jobs et
    dépendances) appliqué s'il est absent. apply_schema() n'est PAS
    idempotent — un second appel sur une base où le schéma existe déjà lève
    (CREATE TYPE échoue), vérifié empiriquement — d'où la garde has_table()
    pour rester rejouable d'une session pytest à l'autre sur une base de
    test persistante."""
    import procrastinate
    from sqlalchemy import inspect as sa_inspect

    if not sa_inspect(pg_engine).has_table("procrastinate_jobs"):
        conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
            "postgresql+psycopg://", "postgresql://"
        )
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))
        with app.open():
            app.schema_manager.apply_schema()
    return pg_engine


@pytest.fixture(scope="session")
def dcat_shacl_shapes():
    """Shapes SHACL DCAT-AP 2.1.1 officielles, vendues statiquement (jamais de
    récupération réseau en test). Chargées une fois par session pytest."""
    import rdflib

    g = rdflib.Graph()
    g.parse(
        Path(__file__).parent / "fixtures" / "dcat" / "dcat-ap-SHACL.ttl",
        format="turtle",
    )
    return g
