# SPDX-License-Identifier: Apache-2.0
"""Index GiST par collection (spec SP-24 §3.2). Aucun index spatial n'existait
dans le dépôt avant SP-24 : tout filtre bbox (OGC Features, geom_intersects du
cross-filter, et désormais les tuiles) était un scan complet de table."""

import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl, spatial_index_name

pytestmark = pytest.mark.postgis


def _indexes(conn, table: str) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t"),
        {"t": table},
    ).scalars()
    return set(rows)


@pytest.fixture()
def table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))
        conn.execute(
            text("CREATE TABLE idx_probe (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        )
    yield "idx_probe"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))


def test_apply_collection_ddl_creates_a_gist_index(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name(table) in _indexes(conn, table)
        method = conn.execute(
            text(
                "SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam "
                "WHERE c.relname = :n"
            ),
            {"n": spatial_index_name(table)},
        ).scalar()
        assert method == "gist"


def test_apply_collection_ddl_is_still_idempotent(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        apply_collection_ddl(s, table)
        s.commit()


def test_a_table_without_geometry_is_left_alone(pg_engine):
    from sqlalchemy.orm import Session

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))
        conn.execute(text("CREATE TABLE idx_flat (id serial PRIMARY KEY, nom text)"))
    with Session(pg_engine) as s:
        apply_collection_ddl(s, "idx_flat")
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name("idx_flat") not in _indexes(conn, "idx_flat")
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))


def test_the_index_name_stays_within_the_postgres_identifier_limit():
    # tableName est plafonné à 50 par CollectionCreate (configs/schemas.py) ;
    # le préfixe doit laisser la marge.
    assert len(spatial_index_name("x" * 50)) <= 63


def _import_0028():
    """Les fichiers de `alembic/versions` ne sont pas un paquet importable
    par leur nom (pas de `alembic/versions/__init__.py` en registre de
    modules Python) : chargement direct par chemin de fichier."""
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "0028_collection_spatial_index.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0028", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_backfills_an_already_registered_collection(pg_engine):
    """Une collection enregistrée avant SP-24 n'a pas d'index : la 0028 doit
    le créer, et son downgrade le retirer."""
    from app.collections import models as collections_models  # noqa: F401
    from app.db import Base, make_session_factory
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    Base.metadata.create_all(pg_engine)
    Session_ = make_session_factory(pg_engine)

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS legacy_probe"))
        conn.execute(
            text("CREATE TABLE legacy_probe (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        )
    with Session_() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="legacy-probe-owner",
            username="legacy-probe-owner",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        # Enregistrement "à l'ancienne" : la ligne de registre, sans l'index
        # (apply_collection_ddl n'est pas appelé, contrairement au chemin de
        # registration normal — c'est exactement ce que la 0028 rattrape).
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, geometry_column, is_public, editable, "
                "created_at, updated_at) VALUES "
                "('legacy_probe', :t, :o, 'legacy_probe', 'Legacy', '', 'id', 'geom', "
                "false, true, now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.commit()
    try:
        with pg_engine.begin() as conn:
            assert spatial_index_name("legacy_probe") not in _indexes(conn, "legacy_probe")

        mod = _import_0028()
        with pg_engine.begin() as conn:
            mod.backfill(conn)
            assert spatial_index_name("legacy_probe") in _indexes(conn, "legacy_probe")
            mod.drop_backfilled(conn)
            assert spatial_index_name("legacy_probe") not in _indexes(conn, "legacy_probe")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM collections WHERE id = 'legacy_probe'"))
            conn.execute(text("DROP TABLE IF EXISTS legacy_probe"))
