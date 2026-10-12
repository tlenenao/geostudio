# SPDX-License-Identifier: Apache-2.0
"""items.content_status + items.categories (ARC-05) : statut de contenu
(none|authoritative|deprecated) et catégories libres. Les items existants
reçoivent 'none' / '[]' (server_default).

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("content_status", sa.String(), nullable=False, server_default="none"),
    )
    op.add_column("items", sa.Column("categories", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("items", "categories")
    op.drop_column("items", "content_status")
