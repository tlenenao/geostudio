# SPDX-License-Identifier: Apache-2.0
"""users.locale / users.timezone : préférences de langue et de fuseau (AUD-115)

Revision ID: 0180
Revises: 0170
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0180"
down_revision = "0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("locale", sa.String(8), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "timezone")
    op.drop_column("users", "locale")
