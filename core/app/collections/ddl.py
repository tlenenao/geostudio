"""DDL par collection (spec SP-3 §2/§5, arbitrage A3) : tenant_id + RLS +
GRANTs au rôle non-propriétaire gis_rls. Idempotent — ré-enregistrer une table
ou rejouer un seed ne casse rien. Les identifiants sont quotés via le preparer
SQLAlchemy (le nom vient du registre, mais la défense vaut pour tout appelant)."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def _qi(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


def apply_collection_ddl(session: Session, table_name: str) -> None:
    t = _qi(session, table_name)
    stmts = [
        f"ALTER TABLE public.{t} ADD COLUMN IF NOT EXISTS tenant_id text "
        "NOT NULL DEFAULT 'default'",
        f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS tenant_isolation ON public.{t}",
        f"CREATE POLICY tenant_isolation ON public.{t} "
        "USING (tenant_id = current_setting('app.tenant_id')) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id'))",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{t} TO gis_rls",
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    # Les INSERT sous gis_rls doivent pouvoir tirer la séquence de la PK (serial).
    seq = session.execute(
        text("SELECT pg_get_serial_sequence(:t, a.attname) FROM pg_index i "
             "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
             "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass "
             "AND i.indisprimary"),
        {"t": table_name},
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
