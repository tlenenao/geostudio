# SPDX-License-Identifier: Apache-2.0
"""geocode_jobs — géocodage par lot asynchrone avec reprise (REV-367 j).

Table neuve. `down_revision` : 0080 sur cette branche ; à rebaser avec 0080
sur la dernière révision du lot 5 (0079) à la fusion.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-16
"""

import sqlalchemy as sa

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geocode_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("addresses", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_geocode_jobs_tenant_id", "geocode_jobs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_geocode_jobs_tenant_id", table_name="geocode_jobs")
    op.drop_table("geocode_jobs")
