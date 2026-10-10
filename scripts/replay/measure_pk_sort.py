# ruff: noqa: E501
"""EXPLAIN du tri PK sur N entités (REV-283 f). Échoue si durée > 2 s.

Un Sort top-N sur le résultat du GiST est légitime (le plan du cœur filtre par bbox puis trie
sur la PK avec LIMIT) : explicit_sort est rapporté, pas bloquant ; seule la durée est un seuil.

PK_SORT_ROWS (défaut 1_000_000) permet un test sur petit volume.
"""

import os
import re
import sys

from sqlalchemy import create_engine, text

ROWS = int(os.environ.get("PK_SORT_ROWS", "1000000"))


def main() -> int:
    eng = create_engine(os.environ["CORE_TEST_DATABASE_URL"])
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS replay_pk_sort"))
        c.execute(
            text(
                "CREATE TABLE replay_pk_sort (fid bigserial PRIMARY KEY, geom geometry(Point,4326), v int)"
            )
        )
        c.execute(
            text(
                "INSERT INTO replay_pk_sort (geom, v) SELECT "
                "ST_SetSRID(ST_MakePoint(random()*10, 45+random()*5),4326), g "
                "FROM generate_series(1,:n) g"
            ),
            {"n": ROWS},
        )
        c.execute(text("CREATE INDEX replay_pk_sort_geom ON replay_pk_sort USING gist (geom)"))
        c.execute(text("ANALYZE replay_pk_sort"))
        plan = "\n".join(
            r[0]
            for r in c.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS) SELECT fid FROM replay_pk_sort "
                    "WHERE geom && ST_MakeEnvelope(2,46,3,47,4326) ORDER BY fid LIMIT 5000"
                )
            )
        )
        print(plan)
        m = re.search(r"Execution Time: ([\d.]+) ms", plan)
        assert m, "pas de 'Execution Time' dans le plan"
        ms = float(m.group(1))
        explicit_sort = "Sort Method" in plan
        print(f"RESULT pk_sort rows={ROWS} exec_ms={ms:.1f} explicit_sort={explicit_sort}")
        c.execute(text("DROP TABLE replay_pk_sort"))
    return 1 if ms > 2000 else 0


if __name__ == "__main__":
    sys.exit(main())
