"""Spike SP-3b : SET LOCAL ROLE gis_rls + set_config('app.tenant_id') à
travers PgBouncer en pool 'transaction'.

Vérifie, DANS L'ORDRE, sur une table jetable RLS :
1. isolation lecture/écriture sous le rôle + GUC via pgbouncer ;
2. AUCUNE fuite de rôle ni de GUC dans la transaction suivante sur la même
   connexion poolée (le point qui peut invalider l'architecture) ;
3. RESET ROLE en milieu de transaction rend l'accès aux tables du cœur
   (pattern write_audit).

Usage :
  SPIKE_DATABASE_URL=postgresql+psycopg://gis:<PG_PASSWORD>@127.0.0.1:26432/gis \
    uv run python -m scripts.spike_pgbouncer_rls
Sort avec code 0 (PASS) ou 1 (FAIL, assertion affichée).
"""

import os
import sys

from sqlalchemy import create_engine, text

DDL = [
    "DROP TABLE IF EXISTS spike_rls",
    "CREATE TABLE spike_rls (id serial PRIMARY KEY, v text, tenant_id text NOT NULL)",
    "ALTER TABLE spike_rls ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS tenant_isolation ON spike_rls",
    "CREATE POLICY tenant_isolation ON spike_rls "
    "USING (tenant_id = current_setting('app.tenant_id')) "
    "WITH CHECK (tenant_id = current_setting('app.tenant_id'))",
    "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gis_rls') "
    "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$",
    "GRANT gis_rls TO current_user",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON spike_rls TO gis_rls",
    "GRANT USAGE, SELECT ON SEQUENCE spike_rls_id_seq TO gis_rls",
    "INSERT INTO spike_rls (v, tenant_id) VALUES ('a', 'default'), ('b', 'other')",
    "DROP TABLE IF EXISTS spike_core",
    "CREATE TABLE spike_core (id serial PRIMARY KEY, note text)",  # non grantée à gis_rls
]


def main() -> int:
    engine = create_engine(os.environ["SPIKE_DATABASE_URL"], pool_size=1, max_overflow=0)
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    with engine.begin() as c:
        for stmt in DDL:
            c.execute(text(stmt))

    # 1. Isolation sous rôle + GUC, à travers pgbouncer (pool transaction).
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": "default"})
        c.execute(text("SET LOCAL ROLE gis_rls"))
        rows = c.execute(text("SELECT v FROM spike_rls ORDER BY v")).scalars().all()
        check("lecture bornée au tenant via pgbouncer", rows == ["a"])
        try:
            c.execute(text("INSERT INTO spike_rls (v, tenant_id) VALUES ('x', 'other')"))
            check("WITH CHECK rejette l'écriture hors tenant", False)
        except Exception:
            check("WITH CHECK rejette l'écriture hors tenant", True)
        # Note d'adaptation (brief task-1) : l'INSERT rejeté ci-dessus met la
        # transaction psycopg en état "aborted" ; un `RESET ROLE` ici lèverait
        # à son tour (InFailedSqlTransaction). On l'omet volontairement — le
        # `with engine.begin()` fait un ROLLBACK à la sortie du bloc, ce qui
        # termine proprement la transaction et libère le rôle de toute façon.

    # 2. Pas de fuite de rôle/GUC dans la transaction suivante (même connexion, pool_size=1).
    with engine.begin() as c:
        who = c.execute(text("SELECT current_user")).scalar()
        guc = c.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
        check("pas de fuite de rôle entre transactions", who == "gis")
        check("pas de fuite de GUC entre transactions", guc in (None, ""))
        rows = c.execute(text("SELECT count(*) FROM spike_rls")).scalar()
        check("le propriétaire voit tout hors scope RLS", rows == 2)

    # 3. Pattern write_audit : rôle rendu en milieu de transaction.
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": "default"})
        c.execute(text("SET LOCAL ROLE gis_rls"))
        c.execute(text("INSERT INTO spike_rls (v, tenant_id) VALUES ('c', 'default')"))
        c.execute(text("RESET ROLE"))
        c.execute(text("INSERT INTO spike_core (note) VALUES ('audit ok')"))
        check("RESET ROLE rend l'accès aux tables du cœur dans la même tx", True)

    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS spike_rls, spike_core"))

    print("\nRésultat spike :", "PASS" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
