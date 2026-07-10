"""DDL par collection (spec SP-3 §2/§5, arbitrage A3) : tenant_id + RLS +
GRANTs au rôle non-propriétaire gis_rls. Idempotent — ré-enregistrer une table
ou rejouer un seed ne casse rien. Les identifiants sont quotés via le preparer
SQLAlchemy (le nom vient du registre, mais la défense vaut pour tout appelant)."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def quote_ident(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


_qi = quote_ident


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
        # L'index sert toutes les requêtes RLS — current_setting est comparé à
        # chaque ligne sinon ; nom borné à 63 octets par construction v1.
        f"CREATE INDEX IF NOT EXISTS "
        f"{quote_ident(session, 'ix_' + table_name + '_tenant_id')} "
        f"ON public.{t} (tenant_id)",
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    # Les INSERT sous gis_rls doivent pouvoir tirer la séquence de la PK (serial).
    seq = session.execute(
        text("SELECT pg_get_serial_sequence('public.' || quote_ident(:t), a.attname) "
             "FROM pg_index i "
             "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
             "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass "
             "AND i.indisprimary"),
        {"t": table_name},
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
