# SPDX-License-Identifier: Apache-2.0
"""app.tileset3d — tileset3d_jobs

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tileset3d_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("upload_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tileset3d_jobs_tenant_id",
        "tileset3d_jobs",
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tileset3d_jobs_tenant_id", table_name="tileset3d_jobs")
    op.drop_table("tileset3d_jobs")
