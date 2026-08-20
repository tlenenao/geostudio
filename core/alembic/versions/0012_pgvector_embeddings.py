"""pgvector (SP-7) — extensions vector/pg_trgm, colonne embedding sur
items/collections, index de recherche (GIN trigram, ivfflat cosine).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("items", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column("collections", sa.Column("embedding", Vector(1536), nullable=True))

    op.execute(
        "CREATE INDEX ix_items_trgm ON items USING gin ((title || ' ' || abstract) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_collections_trgm ON collections "
        "USING gin ((title || ' ' || description) gin_trgm_ops)"
    )
    # ivfflat sur une table possiblement vide au moment de la migration :
    # accepté (index sous-optimal jusqu'au premier ANALYZE avec des lignes),
    # pas de VACUUM/reindex piloté en v1 (spec §Hors périmètre).
    op.execute(
        "CREATE INDEX ix_items_embedding ON items "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX ix_collections_embedding ON collections "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_items_embedding")
    op.execute("DROP INDEX IF EXISTS ix_collections_embedding")
    op.execute("DROP INDEX IF EXISTS ix_items_trgm")
    op.execute("DROP INDEX IF EXISTS ix_collections_trgm")
    op.drop_column("collections", "embedding")
    op.drop_column("items", "embedding")
