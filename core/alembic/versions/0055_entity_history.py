# SPDX-License-Identifier: Apache-2.0
"""entity_history : journal d'entité avant/après (ARC-15)

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fid", sa.String(), nullable=False),
        sa.Column("op", sa.String(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_entity_history_entity", "entity_history", ["collection_id", "fid", "id"])
    op.create_index(
        "ix_entity_history_tenant_at",
        "entity_history",
        ["tenant_id", "collection_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_entity_history_tenant_at", table_name="entity_history")
    op.drop_index("ix_entity_history_entity", table_name="entity_history")
    op.drop_table("entity_history")
