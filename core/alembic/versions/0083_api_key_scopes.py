# SPDX-License-Identifier: Apache-2.0
"""api_keys.scopes / read_only — portée et mode lecture seule des clés (AUD-091).

Revision ID: 0083
Revises: 0082
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("scopes", sa.JSON(), nullable=True))
    op.add_column(
        "api_keys",
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "read_only")
    op.drop_column("api_keys", "scopes")
