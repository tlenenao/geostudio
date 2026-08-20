# SPDX-License-Identifier: Apache-2.0
"""Applique le schéma procrastinate (table `procrastinate_jobs` et
dépendances) une seule fois. `SchemaManager.apply_schema()` n'est PAS
idempotente (`CREATE TYPE` échoue au second appel sur une base où le schéma
existe déjà) — ce qui faisait boucler le service `worker` en redémarrage
sous `docker-compose.yml` (`schema --apply && worker`, relancé en entier
par `restart: unless-stopped` à chaque crash, cf. CLAUDE.md « suivis non
bloquants »). Ce script se substitue à `procrastinate schema --apply` dans
le `command:` du worker : il vérifie d'abord si le schéma est déjà là
(`has_table`) et ne rappelle `apply_schema()` que s'il est absent — même
garde que `core/tests/conftest.py::pg_engine_with_procrastinate_schema`."""

import os
import sys

import procrastinate
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect


def schema_is_applied(conninfo: str) -> bool:
    engine = create_engine(conninfo)
    try:
        return sa_inspect(engine).has_table("procrastinate_jobs")
    finally:
        engine.dispose()


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if schema_is_applied(database_url):
        print("procrastinate: schéma déjà appliqué, rien à faire.")
        return
    app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=database_url))
    with app.open():
        app.schema_manager.apply_schema()
    print("procrastinate: schéma appliqué.")


if __name__ == "__main__":
    main()
    sys.exit(0)
