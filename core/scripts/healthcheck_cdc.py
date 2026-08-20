# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité du worker CDC, pour le `healthcheck` de son service.

Pourquoi pas une sonde de process : `python -m app.cdc.main` peut être vivant
et ne rien consommer (boucle bloquée, exception avalée dans une tâche), et
c'est exactement le cas que I5 du plan d'action 2026-08-20 signale. Le slot
de réplication donne le signal côté serveur : `active` n'est true que tant
qu'un consommateur le tient.

Usage (healthcheck docker) : `python -m scripts.healthcheck_cdc`
Sortie 0 = sain, 1 = pas sain.
"""

import os
import sys

from app.cdc.consumer import SLOT_NAME

__all__ = ["SLOT_NAME", "main", "slot_is_active"]

QUERY = "select active from pg_replication_slots where slot_name = %s"


def slot_is_active(connection, slot_name: str) -> bool:
    row = connection.execute(QUERY, (slot_name,)).fetchone()
    return bool(row and row[0])


def main() -> int:
    dsn = os.environ.get("CDC_DATABASE_URL")
    if not dsn:
        print("CDC_DATABASE_URL absent", file=sys.stderr)
        return 1
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            return 0 if slot_is_active(connection, SLOT_NAME) else 1
    except Exception as exc:  # une sonde ne doit jamais lever, seulement échouer
        print(f"sonde CDC en échec : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
