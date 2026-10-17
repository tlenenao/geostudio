# SPDX-License-Identifier: Apache-2.0
"""tenant_limits : plafonds par tenant (AUD-098)

Une ligne par tenant, colonnes NULL = « retomber sur la limite d'instance »
(`CORE_QUOTA_MAX_*`). Supprimée avec le tenant (ON DELETE CASCADE).

Revision ID: 0122
Revises: 0121
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_limits",
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("max_items", sa.BigInteger(), nullable=True),
        sa.Column("max_collections", sa.BigInteger(), nullable=True),
        sa.Column("max_storage_bytes", sa.BigInteger(), nullable=True),
        sa.Column("max_users", sa.BigInteger(), nullable=True),
        sa.Column("max_active_runs", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tenant_limits")
