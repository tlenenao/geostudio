# SPDX-License-Identifier: Apache-2.0
"""Mesure empirique jetable (pas un test permanent) — débit réel de
stream_changes() sous une rafale de N transactions séparées (une seule
ligne, un seul commit chacune), pour objectiver le plafond de débit du
settle de ~100ms/message (cf. review Task 7, Finding 2).

Usage :
    cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
        uv run python scripts/measure_cdc_consumer_throughput.py [N]

N par défaut : 80. Écrit N INSERT individuels (chacun son propre commit,
simulant N écritures OGC API Features séparées), puis consomme le flux de
réplication avec stream_changes() jusqu'à voir les N messages, et rapporte
le temps réel écoulé + le débit messages/s. Ne mesure PAS la correction du
décodage (déjà couverte par Task 6/7) — seulement le débit et l'absence de
perte.
"""

import os
import sys
import time

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cdc.consumer import (  # noqa: E402
    SLOT_NAME,
    decode_wal2json_message,
    ensure_replication_slot,
    stream_changes,
)

TABLE = "t_cdc_throughput_measure"
PUB = "throughput_measure_pub"


def _raw_dsn() -> str:
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    sa_url = os.environ["CORE_TEST_DATABASE_URL"]
    raw_dsn = _raw_dsn()
    engine = create_engine(sa_url)

    with engine.begin() as conn:
        conn.execute(text(f"DROP PUBLICATION IF EXISTS {PUB}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id serial PRIMARY KEY, v text)"))
        conn.execute(text(f"CREATE PUBLICATION {PUB} FOR TABLE {TABLE}"))

    # Nettoyage d'un slot laissé par un run précédent.
    try:
        conn2 = psycopg2.connect(
            raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection
        )
        cur2 = conn2.cursor()
        try:
            cur2.drop_replication_slot(SLOT_NAME)
        except Exception:
            pass
        cur2.close()
        conn2.close()
    except Exception:
        pass

    ensure_replication_slot(raw_dsn)

    print(f"Écriture de {n} INSERT individuels (1 commit chacun)...")
    write_start = time.monotonic()
    with engine.connect() as conn:
        for i in range(n):
            with conn.begin():
                conn.execute(text(f"INSERT INTO {TABLE} (v) VALUES (:v)"), {"v": f"row-{i}"})
    write_elapsed = time.monotonic() - write_start
    print(f"  écriture terminée en {write_elapsed:.3f}s")

    received = []
    state = {"count": 0}

    def on_message(payload, lsn):
        for decoded in decode_wal2json_message(
            payload, lsn=lsn, collection_meta={TABLE: ("id", None)}
        ):
            received.append(decoded)
            state["count"] += 1

    print(f"Consommation via stream_changes() jusqu'à voir les {n} messages...")
    consume_start = time.monotonic()
    stream_changes(
        raw_dsn,
        on_message=on_message,
        is_flush_due=lambda: False,
        do_flush=lambda: None,
        should_stop=lambda: state["count"] >= n,
        poll_timeout_s=0.2,
    )
    consume_elapsed = time.monotonic() - consume_start

    with engine.begin() as conn:
        conn.execute(text(f"DROP PUBLICATION IF EXISTS {PUB}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    try:
        conn3 = psycopg2.connect(
            raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection
        )
        cur3 = conn3.cursor()
        cur3.drop_replication_slot(SLOT_NAME)
        cur3.close()
        conn3.close()
    except Exception:
        pass

    assert len(received) == n, f"perte de données : {len(received)}/{n} messages reçus"
    assert {r.row.columns.get("v") for r in received} == {f"row-{i}" for i in range(n)}, (
        "perte/duplication de données : contenu des lignes reçues ne correspond pas "
        "exactement aux N écrites"
    )

    throughput = n / consume_elapsed if consume_elapsed > 0 else float("inf")
    print()
    print("=== REPORT ===")
    print(f"N messages          : {n}")
    print(f"Temps écriture      : {write_elapsed:.3f}s")
    print(f"Temps consommation  : {consume_elapsed:.3f}s")
    print(f"Débit mesuré        : {throughput:.2f} messages/s")
    print(f"Lag total (rafale)  : {consume_elapsed:.3f}s pour {n} messages")
    print("Aucune perte de données : OK (N messages reçus, contenu vérifié)")


if __name__ == "__main__":
    main()
