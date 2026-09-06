# SPDX-License-Identifier: Apache-2.0
"""app.pipelines — pipeline_webhook_tokens (GAP-24, SP-53 : déclenchement de
pipeline par webhook entrant). Table neuve, aucune donnée existante à
migrer : create_table/drop_table suffisent dans les deux sens.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_webhook_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("pipeline_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_pipeline_webhook_tokens_pipeline",
        "pipeline_webhook_tokens",
        ["tenant_id", "pipeline_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_webhook_tokens_pipeline", table_name="pipeline_webhook_tokens")
    op.drop_table("pipeline_webhook_tokens")
