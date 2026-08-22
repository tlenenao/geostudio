# SPDX-License-Identifier: Apache-2.0
"""DDL par collection (spec SP-3 §2/§5, arbitrage A3) : tenant_id + RLS +
GRANTs au rôle non-propriétaire gis_rls. Idempotent — ré-enregistrer une table
ou rejouer un seed ne casse rien. Les identifiants sont quotés via le preparer
SQLAlchemy (le nom vient du registre, mais la défense vaut pour tout appelant)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.publication import add_table_to_publication


def quote_ident(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


_qi = quote_ident


def spatial_index_name(table_name: str) -> str:
    """Nom de l'index GiST d'une collection. Partagé avec la migration 0028 —
    une seule définition, jamais deux conventions de nommage."""
    return f"ix_{table_name}_geom_gist"


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
        # chaque ligne sinon ; nom ≤ 63 octets garanti : tableName est borné à
        # 50 par CollectionCreate (schemas.py).
        f"CREATE INDEX IF NOT EXISTS "
        f"{quote_ident(session, 'ix_' + table_name + '_tenant_id')} "
        f"ON public.{t} (tenant_id)",
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    # Index spatial : sans lui, tout filtre bbox (OGC Features, geom_intersects
    # du cross-filter SP-14n, tuiles MVT SP-24) est un scan complet de table.
    # Le nom de la colonne de géométrie vient de geometry_columns, jamais de
    # l'appelant.
    geom_col = session.execute(
        text(
            "SELECT f_geometry_column FROM geometry_columns "
            "WHERE f_table_schema = 'public' AND f_table_name = :t"
        ),
        {"t": table_name},
    ).scalar()
    if geom_col:
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_qi(session, spatial_index_name(table_name))} "
                f"ON public.{t} USING GIST ({_qi(session, geom_col)})"
            )
        )
    # Les INSERT sous gis_rls doivent pouvoir tirer la séquence de la PK (serial).
    seq = session.execute(
        text(
            "SELECT pg_get_serial_sequence('public.' || quote_ident(:t), a.attname) "
            "FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass "
            "AND i.indisprimary"
        ),
        {"t": table_name},
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
    add_table_to_publication(session, table_name)
