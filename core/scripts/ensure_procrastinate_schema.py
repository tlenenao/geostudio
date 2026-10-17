# SPDX-License-Identifier: Apache-2.0
"""Applique puis migre le schéma procrastinate, avec table de suivi
`gs_procrastinate_migrations` (AUD-015).

`SchemaManager.apply_schema()` n'est PAS idempotente (`CREATE TYPE` échoue au
second appel) : sur base vierge on l'applique, sinon on rejoue seulement les
migrations de procrastinate pas encore suivies (une base ancienne sans suivi
est baselinée par sondes d'artefacts). Remplace `procrastinate schema --apply`
dans le `command:` du worker (qui bouclait en redémarrage)."""

import os
import sys
from pathlib import Path

import procrastinate
import psycopg
from procrastinate.schema import SchemaManager
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect

from app.jobs import CONNECTION_KWARGS


def schema_is_applied(conninfo: str) -> bool:
    engine = create_engine(conninfo)
    try:
        return sa_inspect(engine).has_table("procrastinate_jobs")
    finally:
        engine.dispose()


def _migration_files() -> list[Path]:
    return sorted(Path(SchemaManager.get_migrations_path()).glob("*.sql"))


# Version -> artefact créé par la migration `pre` de cette version (vérifiés
# dans les .sql de procrastinate 3.9.0). 03.03.00 n'a pas d'artefact propre.
_PROBES = {
    "03.00.00": "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
    "WHERE table_name = 'procrastinate_jobs' AND column_name = 'abort_requested')",
    "03.01.00": "SELECT to_regclass('procrastinate_workers') IS NOT NULL",
    "03.02.00": "SELECT to_regproc('procrastinate_defer_jobs_v1') IS NOT NULL",
    "03.04.00": "SELECT to_regproc('procrastinate_retry_job_v2') IS NOT NULL",
}


def _baseline_names(conn, files: list[Path]) -> list[str]:
    """Base ancienne sans suivi : tout ce qui précède la première migration
    sondée dont l'artefact manque est tenu pour appliqué."""
    first_missing = next(
        (v for v, q in _PROBES.items() if not conn.execute(q).fetchone()[0]), "99.99.99"
    )
    return [f.name for f in files if f.name[:8] < first_missing]


def ensure_schema(conninfo: str) -> list[str]:
    """Applique le schéma s'il manque, puis les migrations procrastinate pas
    encore suivies. Idempotent. Retourne les noms de migrations appliquées."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext('gs_procrastinate_schema'))")
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS gs_procrastinate_migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            files = _migration_files()
            seen = {r[0] for r in conn.execute("SELECT name FROM gs_procrastinate_migrations")}
            if not schema_is_applied(conninfo):
                app = procrastinate.App(
                    connector=procrastinate.PsycopgConnector(
                        conninfo=conninfo, kwargs=dict(CONNECTION_KWARGS)
                    )
                )
                with app.open():
                    app.schema_manager.apply_schema()  # schéma courant = toutes les migrations
                baseline = [f.name for f in files]
            elif not seen:
                baseline = _baseline_names(conn, files)
            else:
                baseline = []
            for n in baseline:
                conn.execute(
                    "INSERT INTO gs_procrastinate_migrations(name) VALUES (%s) "
                    "ON CONFLICT DO NOTHING",
                    (n,),
                )
            seen |= set(baseline)
            applied = []
            for f in files:
                if f.name in seen:
                    continue
                conn.execute(f.read_text())
                conn.execute("INSERT INTO gs_procrastinate_migrations(name) VALUES (%s)", (f.name,))
                applied.append(f.name)
            return applied
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext('gs_procrastinate_schema'))")


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    applied = ensure_schema(database_url)
    print(f"procrastinate: schéma à jour ({len(applied)} migration(s) appliquée(s)).")


if __name__ == "__main__":
    main()
    sys.exit(0)
