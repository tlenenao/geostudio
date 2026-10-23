"""groups.created_by

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AUD-191 : ajout nullable, backfill (plus ancien utilisateur du tenant), puis NOT NULL + FK.
    op.add_column("groups", sa.Column("created_by", sa.String(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE groups g SET created_by = (SELECT u.id FROM users u "
            "WHERE u.tenant_id = g.tenant_id ORDER BY u.created_at, u.id LIMIT 1)"
        )
    )
    orphans = conn.execute(
        sa.text("SELECT count(*) FROM groups WHERE created_by IS NULL")
    ).scalar_one()
    if orphans:
        msg = f"migration 0007 : {orphans} groupe(s) dans un tenant sans utilisateur."
        raise RuntimeError(msg)
    op.alter_column("groups", "created_by", nullable=False)
    op.create_foreign_key("groups_created_by_fkey", "groups", "users", ["created_by"], ["id"])


def downgrade() -> None:
    op.drop_column("groups", "created_by")
