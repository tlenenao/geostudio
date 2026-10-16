# SPDX-License-Identifier: Apache-2.0
"""tenant_basemaps — fonds de carte partagés par tenant (REV-367 i, ARC-09a).

Table neuve, sans donnée à migrer. `down_revision` : 0072 sur cette branche ;
à rebaser sur la dernière révision du lot 5 (0079) à la fusion.

Revision ID: 0080
Revises: 0072
Create Date: 2026-10-16
"""

import sqlalchemy as sa

from alembic import op

revision = "0080"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_basemaps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("style", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tenant_basemaps_tenant_id", "tenant_basemaps", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_basemaps_tenant_id", table_name="tenant_basemaps")
    op.drop_table("tenant_basemaps")
