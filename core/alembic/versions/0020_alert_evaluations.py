# SPDX-License-Identifier: Apache-2.0
"""app.alerts — alert_evaluations (SP-16b)

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_evaluations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("alert_rule_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("transitioned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alert_evaluations")
