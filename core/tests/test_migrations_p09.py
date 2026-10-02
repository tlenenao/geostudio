# SPDX-License-Identifier: Apache-2.0
"""P09.03/P09.09/P09.10 : migrations 0043 (FK items.id ON DELETE), 0008/0039/0042
(downgrades) testées sur base Postgres NON VIDE, dans les deux sens (piège
n°8). Base jetable créée/détruite par chaque test, jamais `postgis-test`."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"p09_migration_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", base_url)
    eng = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        for ext in ("postgis", "vector", "pg_trgm"):
            conn.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    eng.dispose()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin.dispose()


def _cfg() -> Config:
    cfg = Config()  # sans ini : cf. test_migration_0042_sensitive_fields.py
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    return cfg


def _seed_base(conn) -> None:
    conn.execute(
        sa.text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1','t1','T',now())")
    )
    conn.execute(
        sa.text(
            "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
            "created_at, updated_at) VALUES ('r1','t1','A','a',true,'[]',now(),now())"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, last_name, "
            "is_admin, role_id, created_at, updated_at) "
            "VALUES ('u1','t1','s','alice','','',true,'r1',now(),now())"
        )
    )


def _scalar(url: str, sql: str):
    eng = sa.create_engine(url)
    try:
        with eng.connect() as conn:
            return conn.execute(sa.text(sql)).scalar_one()
    finally:
        eng.dispose()


def test_0043_cascades_history_and_nulls_harvest_link_both_ways(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0042")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('i1','t1','u1','pipeline','P','[]',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO pipeline_runs (id, tenant_id, pipeline_item_id, created_at) "
                "VALUES ('pr1','t1','i1',now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO export_jobs (id, tenant_id, item_id, user_id, format, created_at) "
                "VALUES ('e1','t1','i1','u1','csv',now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO harvest_sources (id, tenant_id, owner_id, type, url, created_at, "
                "updated_at) VALUES ('hs1','t1','u1','stac','http://x',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO harvest_records (id, tenant_id, source_id, external_id, item_id, "
                "harvested_at) VALUES ('h1','t1','hs1','x','i1',now())"
            )
        )
    eng.dispose()

    # avant 0043 : la suppression est refusée par la FK (le défaut c03-001)
    eng = sa.create_engine(url)
    with pytest.raises(sa.exc.IntegrityError), eng.begin() as conn:
        conn.execute(sa.text("DELETE FROM items WHERE id = 'i1'"))
    eng.dispose()

    command.upgrade(_cfg(), "0043")
    command.downgrade(_cfg(), "0042")  # les lignes survivent au downgrade
    assert _scalar(url, "SELECT count(*) FROM pipeline_runs") == 1
    command.upgrade(_cfg(), "0043")

    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(sa.text("DELETE FROM items WHERE id = 'i1'"))
    eng.dispose()
    assert _scalar(url, "SELECT count(*) FROM pipeline_runs") == 0
    assert _scalar(url, "SELECT count(*) FROM export_jobs") == 0
    assert _scalar(url, "SELECT item_id FROM harvest_records WHERE id = 'h1'") is None


def test_destructive_downgrades_are_refused_while_rows_exist(throwaway_database_url, monkeypatch):
    url = throwaway_database_url
    monkeypatch.delenv("GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    command.upgrade(_cfg(), "0042")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, is_public, editable, sensitive_fields, created_at, "
                "updated_at) VALUES ('c1','t1','u1','villes','V','','id',false,true,"
                "'[\"name\"]',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO purge_receipts (id, tenant_slug, requested_by_user_id, "
                "requested_at, counts) VALUES ('p1','gone','u1',now(),'{}')"
            )
        )
    eng.dispose()

    # 0042 : champ sensible masqué => refus, rien n'est détruit
    with pytest.raises(RuntimeError, match="champs sensibles"):
        command.downgrade(_cfg(), "0041")
    assert _scalar(url, "SELECT sensitive_fields::text FROM collections") == '["name"]'

    # marquage levé => 0042 repasse ; 0039 refuse tant que la preuve existe
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(sa.text("UPDATE collections SET sensitive_fields = '[]'"))
    eng.dispose()
    with pytest.raises(RuntimeError, match="purge_receipts"):
        command.downgrade(_cfg(), "0038")
    assert _scalar(url, "SELECT count(*) FROM purge_receipts") == 1

    # accord explicite : le downgrade passe, puis la chaîne remonte à head
    monkeypatch.setenv("GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE", "1")
    command.downgrade(_cfg(), "0038")
    command.upgrade(_cfg(), "head")


def test_0008_downgrade_tolerates_a_role_still_granted_elsewhere(throwaway_database_url):
    # Le rôle gis_rls est global au cluster : un downgrade de 0008 ne doit pas
    # échouer parce que le DROP ROLE est refusé — on le provoque en rendant le
    # rôle propriétaire d'un objet d'une AUTRE base.
    url = throwaway_database_url
    base_url = os.environ["CORE_TEST_DATABASE_URL"]
    command.upgrade(_cfg(), "0008")
    other = f"p09_other_{uuid.uuid4().hex[:8]}"
    admin = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{other}"'))
    other_url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{other}\1", base_url)
    try:
        o = sa.create_engine(other_url, isolation_level="AUTOCOMMIT")
        with o.connect() as conn:
            conn.execute(sa.text("CREATE TABLE held (id int)"))
            conn.execute(sa.text("GRANT SELECT ON held TO gis_rls"))
        o.dispose()
        command.downgrade(_cfg(), "0007")
        assert (
            _scalar(
                url,
                "SELECT count(*) FROM information_schema.tables WHERE table_name = 'collections'",
            )
            == 0
        )
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{other}" WITH (FORCE)'))
        admin.dispose()


def test_0044_adds_notify_columns_on_a_non_empty_table_both_ways(throwaway_database_url):
    """P20 : statut de livraison d'une évaluation d'alerte (base non vide)."""
    url = throwaway_database_url
    command.upgrade(_cfg(), "0043")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('a1','t1','u1','alert','A','[]',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO alert_evaluations (id, tenant_id, alert_rule_item_id, state, "
                "transitioned, created_at) VALUES ('ev1','t1','a1','firing',true,now())"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0044")
    assert _scalar(url, "SELECT notify_status FROM alert_evaluations WHERE id='ev1'") is None
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE alert_evaluations SET notify_status='failed', notify_error='500' "
                "WHERE id='ev1'"
            )
        )
    eng.dispose()
    assert _scalar(url, "SELECT notify_error FROM alert_evaluations WHERE id='ev1'") == "500"

    command.downgrade(_cfg(), "0043")
    assert _scalar(url, "SELECT count(*) FROM alert_evaluations") == 1
    cols = _scalar(
        url,
        "SELECT count(*) FROM information_schema.columns WHERE table_name='alert_evaluations' "
        "AND column_name IN ('notify_status','notify_error')",
    )
    assert cols == 0
