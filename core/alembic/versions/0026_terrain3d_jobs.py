# SPDX-License-Identifier: Apache-2.0
"""app.terrain3d — terrain3d_jobs

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terrain3d_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("converted_key", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_terrain3d_jobs_tenant_id", "terrain3d_jobs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_terrain3d_jobs_tenant_id", table_name="terrain3d_jobs")
    op.drop_table("terrain3d_jobs")
