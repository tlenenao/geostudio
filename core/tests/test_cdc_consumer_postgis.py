# SPDX-License-Identifier: Apache-2.0
import os

import psycopg2
import psycopg2.extras
import pytest
from sqlalchemy import text

from app.cdc.consumer import (
    SLOT_NAME,
    decode_wal2json_message,
    ensure_replication_slot,
    stream_changes,
)

pytestmark = pytest.mark.postgis


@pytest.fixture()
def cdc_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS test_cdc_pub"))
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_consumer"))
        conn.execute(text("CREATE TABLE t_cdc_consumer (id serial PRIMARY KEY, v text)"))
        conn.execute(text("CREATE PUBLICATION test_cdc_pub FOR TABLE t_cdc_consumer"))
    yield "t_cdc_consumer"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS test_cdc_pub"))
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_consumer"))


def _raw_dsn() -> str:
    # CORE_TEST_DATABASE_URL est au format SQLAlchemy (postgresql+psycopg://) ;
    # psycopg2 attend un DSN postgresql:// nu.
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(autouse=True)
def _drop_slot_after():
    yield
    raw_dsn = _raw_dsn()
    conn = psycopg2.connect(
        raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection
    )
    cur = conn.cursor()
    try:
        cur.drop_replication_slot(SLOT_NAME)
    except Exception:
        pass
    cur.close()
    conn.close()


def test_stream_changes_decodes_and_stops_on_should_stop(cdc_table, pg_engine):
    raw_dsn = _raw_dsn()
    ensure_replication_slot(raw_dsn)

    with pg_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {cdc_table} (v) VALUES ('a')"))

    received = []
    state = {"count": 0}

    def on_message(payload, lsn):
        for decoded in decode_wal2json_message(
            payload, lsn=lsn, collection_meta={cdc_table: ("id", None)}
        ):
            received.append(decoded)
            state["count"] += 1

    stream_changes(
        raw_dsn,
        on_message=on_message,
        is_flush_due=lambda: False,
        do_flush=lambda: None,
        should_stop=lambda: state["count"] >= 1,
        poll_timeout_s=0.2,
    )
    assert len(received) == 1
    assert received[0].table_name == cdc_table
    assert received[0].row.op == "insert"


def _confirmed_flush_lsn(pg_engine) -> str | None:
    with pg_engine.connect() as conn:
        row = conn.execute(
            text("SELECT confirmed_flush_lsn FROM pg_replication_slots WHERE slot_name = :name"),
            {"name": SLOT_NAME},
        ).fetchone()
        return row[0] if row else None


def test_stream_changes_ack_advances_confirmed_flush_lsn(cdc_table, pg_engine):
    """Preuve empirique du fix (Task 1, déviation 1) : la LSN passée à
    send_feedback doit provenir de cur.wal_end (propriété du curseur), pas de
    msg.data_start (attribut du message) — sinon confirmed_flush_lsn
    n'avance jamais côté serveur, même si send_feedback ne lève pas
    d'exception. Interroge pg_replication_slots directement, sur une
    connexion séparée de celle utilisée par stream_changes."""
    raw_dsn = _raw_dsn()
    ensure_replication_slot(raw_dsn)

    lsn_before = _confirmed_flush_lsn(pg_engine)
    assert (
        lsn_before is not None
    )  # le slot existe, la colonne est lisible (peut être NULL au tout début)

    with pg_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {cdc_table} (v) VALUES ('a')"))

    received = []
    state = {"count": 0, "last_lsn": None}

    def on_message(payload, lsn):
        state["last_lsn"] = lsn
        for decoded in decode_wal2json_message(
            payload, lsn=lsn, collection_meta={cdc_table: ("id", None)}
        ):
            received.append(decoded)
            state["count"] += 1

    def do_flush():
        # Simule un flush GeoParquet réussi : confirme jusqu'à la dernière
        # LSN vue (même contrat que CdcBufferManager.safe_ack_lsn côté
        # appelant réel, Task 9 — ici on ack directement pour isoler le
        # comportement de stream_changes/send_feedback).
        return state["last_lsn"]

    stream_changes(
        raw_dsn,
        on_message=on_message,
        is_flush_due=lambda: state["count"] >= 1,
        do_flush=do_flush,
        should_stop=lambda: state["count"] >= 1,
        poll_timeout_s=0.2,
    )
    assert len(received) == 1

    lsn_after = _confirmed_flush_lsn(pg_engine)
    assert lsn_after is not None
    if lsn_before is None:
        assert lsn_after is not None
    else:
        assert lsn_after > lsn_before, (
            f"confirmed_flush_lsn did not advance: before={lsn_before} after={lsn_after}"
        )
