# SPDX-License-Identifier: Apache-2.0
"""pipeline_reader_state : curseur incrémental par reader connecteur (ARC-K2/F4)

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_reader_state",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        # CASCADE : l'état est purgé avec le pipeline (et donc par purge_tenant,
        # qui supprime les items).
        sa.Column(
            "pipeline_item_id",
            sa.String(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("cursor_value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("pipeline_item_id", "node_id", name="uq_pipeline_reader_state_node"),
    )


def downgrade() -> None:
    op.drop_table("pipeline_reader_state")
