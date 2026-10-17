# SPDX-License-Identifier: Apache-2.0
"""collections.keywords + collections.inspire_theme (AUD-047).

Revision ID: 0095
Revises: 0088
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0095"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "collections",
        sa.Column("inspire_theme", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("collections", "inspire_theme")
    op.drop_column("collections", "keywords")
