# SPDX-License-Identifier: Apache-2.0
"""saved_queries : requêtes SQL Lab enregistrées par utilisateur (AUD-062)

Revision ID: 0172
Revises: 0171
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_queries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "owner_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "owner_id", "name", name="uq_saved_query_name"),
    )
    op.create_index("ix_saved_queries_tenant_id", "saved_queries", ["tenant_id"])
    op.create_index("ix_saved_queries_owner_id", "saved_queries", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_queries_owner_id", table_name="saved_queries")
    op.drop_index("ix_saved_queries_tenant_id", table_name="saved_queries")
    op.drop_table("saved_queries")
