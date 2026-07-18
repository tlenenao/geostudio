# SPDX-License-Identifier: Apache-2.0
"""users.is_analyst — rôle analyste (SP-11c)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_analyst", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_analyst")
