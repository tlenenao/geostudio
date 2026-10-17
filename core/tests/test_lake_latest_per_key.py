# SPDX-License-Identifier: Apache-2.0
"""AUD-013 : latest_per_key (ANTI + SEMI JOIN) doit donner exactement la dernière version
par PK de la fenêtre complète sur base ∪ delta — tombstones et backfill tardif compris."""

import random

import duckdb

from app.analytics.snapshot import latest_per_key

ORDER = "_lsn DESC, COALESCE(_seq, -1) DESC"
_DDL = "(id INT, _op VARCHAR, _lsn BIGINT, _seq INT, v VARCHAR)"


def _history(rng, lsns, n):
    # (_lsn, _seq) uniques : pas d'ex-aequo, donc un résultat de référence déterministe.
    return [
        (
            rng.randrange(30),
            rng.choice(["insert", "update", "delete"]),
            next(lsns),
            rng.choice([None, 0, 1]),
            f"v{rng.randrange(1000)}",
        )
        for _ in range(n)
    ]


def test_latest_per_key_equals_full_window_on_random_histories():
    conn = duckdb.connect(":memory:")
    rng = random.Random(1234)
    for _ in range(50):
        lsns = iter(rng.sample(range(-500, 5000), 200))  # LSN basses = backfill tardif
        conn.execute(f"CREATE OR REPLACE TABLE base {_DDL}")
        conn.execute(f"CREATE OR REPLACE TABLE delta {_DDL}")
        snapshot = {}
        for row in _history(rng, lsns, 40):
            snapshot[row[0]] = row  # un snapshot = une ligne par PK
        conn.executemany("INSERT INTO base VALUES (?, ?, ?, ?, ?)", list(snapshot.values()))
        conn.executemany("INSERT INTO delta VALUES (?, ?, ?, ?, ?)", _history(rng, lsns, 25))
        ref = conn.execute(
            "SELECT * FROM (SELECT * FROM base UNION ALL BY NAME SELECT * FROM delta) "
            f"QUALIFY row_number() OVER (PARTITION BY id ORDER BY {ORDER}) = 1 ORDER BY id"
        ).fetchall()
        sql = latest_per_key("SELECT * FROM base", "SELECT * FROM delta", "id", ORDER)
        got = conn.execute(f"SELECT * FROM ({sql}) ORDER BY id").fetchall()
        assert got == ref
