# ruff: noqa: E501
"""Pic mémoire d'un GROUP BY DuckDB à cardinalité croissante (REV-280 d).

memory_limit = celui du cœur (app/analytics/duckdb_conn.py : CORE_DUCKDB_MEMORY_LIMIT, défaut 2GB).
Mesure dans un sous-processus par palier : ru_maxrss est un pic monotone, un seul processus
masquerait les paliers suivants. GROUPBY_CARDS (liste séparée par des virgules) pour un test rapide.
"""

import os
import subprocess
import sys

LIMIT = os.environ.get("CORE_DUCKDB_MEMORY_LIMIT") or "2GB"  # = défaut du cœur
CARDS = [int(x) for x in os.environ.get("GROUPBY_CARDS", "10000,100000,1000000,5000000").split(",")]

CHILD = """
import resource, sys, duckdb
card, limit = int(sys.argv[1]), sys.argv[2]
con = duckdb.connect()
con.execute(f"SET memory_limit='{limit}'")
r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
try:
    con.execute(
        "SELECT k, count(*) c, sum(v) s FROM (SELECT (i * 2654435761) % ? AS k, i AS v "
        "FROM range(?) t(i)) GROUP BY k",
        [card, max(card * 2, 2_000_000)],
    ).fetchall()
    status = "ok"
except Exception as e:
    status = "erreur:" + type(e).__name__
r1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"RESULT groupby card={card} limit={limit} status={status} rss_peak_mb={r1 // 1024} delta_mb={(r1 - r0) // 1024}")
"""


def main() -> int:
    for card in CARDS:
        r = subprocess.run(
            [sys.executable, "-c", CHILD, str(card), LIMIT], capture_output=True, text=True
        )
        sys.stdout.write(r.stdout)
        if r.returncode:
            print(f"RESULT groupby card={card} limit={LIMIT} status=crash rc={r.returncode}")
    return 0  # mesure, pas un seuil : la décision MAX_GROUPS se prend sur les chiffres


if __name__ == "__main__":
    sys.exit(main())
