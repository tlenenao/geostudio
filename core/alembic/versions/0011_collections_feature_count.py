"""collections.feature_count (SP-6c) — backfill via COUNT(*) sur chaque
collection déjà enregistrée

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("feature_count", sa.Integer(), nullable=True)
    )
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    existing_tables = {
        row[0] for row in conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )).all()
    }
    quote = conn.dialect.identifier_preparer.quote
    rows = conn.execute(sa.text("SELECT id, table_name FROM collections")).all()
    for collection_id, table_name in rows:
        if table_name not in existing_tables:
            logger.warning(
                "SP-6c backfill: table public.%s introuvable pour la collection "
                "%s, feature_count laissé NULL", table_name, collection_id,
            )
            continue
        t = quote(table_name)
        count = conn.execute(sa.text(f"SELECT count(*) FROM public.{t}")).scalar_one()
        conn.execute(
            sa.text("UPDATE collections SET feature_count = :n WHERE id = :id"),
            {"n": count, "id": collection_id},
        )


def downgrade() -> None:
    op.drop_column("collections", "feature_count")
