# SPDX-License-Identifier: Apache-2.0
"""items.slug + unicité partielle par tenant (SP-16a)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("slug", sa.String(), nullable=True))
    op.create_index(
        "uq_items_tenant_slug",
        "items",
        ["tenant_id", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_items_tenant_slug", table_name="items")
    op.drop_column("items", "slug")
