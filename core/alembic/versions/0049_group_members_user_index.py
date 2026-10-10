# SPDX-License-Identifier: Apache-2.0
"""Index group_members(user_id) (REV-279 c, trouvé au rejeu sur Postgres réel)

La PK (group_id, user_id) ne sert pas `WHERE user_id = ?` (can(), catalogue).
CONCURRENTLY, IF NOT EXISTS : même patron que 0045.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-06
"""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_group_members_user_id "
            "ON group_members (user_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_group_members_user_id")
