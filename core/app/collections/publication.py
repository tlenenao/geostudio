# SPDX-License-Identifier: Apache-2.0
"""Publication PostgreSQL pour le CDC (SP-11a, arbitrage A16) : une seule
publication `geostudio_cdc`, tenue à jour par apply_collection_ddl (register
manuel SP-3a et ingestion automatique SP-6a/6b partagent ce point d'entrée
unique, cf. app.ingestion.importer.run_import) et par unregister_collection.
cdc-worker ne touche jamais à cette publication — il ne fait que la
consommer (app.cdc.consumer).

Le quoting vient de `app.sql_ident` (GAP-15, premier volet), pas de
`app.collections.ddl` : ddl.py importe ce module pour appeler
add_table_to_publication depuis apply_collection_ddl, un import dans l'autre
sens créerait un cycle — `app.sql_ident` est indépendant des deux, la
duplication historique n'est donc plus nécessaire."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sql_ident import quote_ident as _qi

PUBLICATION_NAME = "geostudio_cdc"


def ensure_publication_exists(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    exists = session.execute(
        text("SELECT 1 FROM pg_publication WHERE pubname = :name"),
        {"name": PUBLICATION_NAME},
    ).scalar()
    if not exists:
        session.execute(text(f"CREATE PUBLICATION {PUBLICATION_NAME}"))


def add_table_to_publication(session: Session, table_name: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    ensure_publication_exists(session)
    already = session.execute(
        text(
            "SELECT 1 FROM pg_publication_tables "
            "WHERE pubname = :name AND schemaname = 'public' AND tablename = :t"
        ),
        {"name": PUBLICATION_NAME, "t": table_name},
    ).scalar()
    if not already:
        t = _qi(session, table_name)
        session.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} ADD TABLE public.{t}"))


def remove_table_from_publication(session: Session, table_name: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    exists_pub = session.execute(
        text("SELECT 1 FROM pg_publication WHERE pubname = :name"),
        {"name": PUBLICATION_NAME},
    ).scalar()
    if not exists_pub:
        return
    member = session.execute(
        text(
            "SELECT 1 FROM pg_publication_tables "
            "WHERE pubname = :name AND schemaname = 'public' AND tablename = :t"
        ),
        {"name": PUBLICATION_NAME, "t": table_name},
    ).scalar()
    if member:
        t = _qi(session, table_name)
        session.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} DROP TABLE public.{t}"))
