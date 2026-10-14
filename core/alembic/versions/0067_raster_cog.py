# SPDX-License-Identifier: Apache-2.0
"""raster_jobs + raster_assets : rasters COG servis par proxy TiTiler (ARC-33, ADR 0024)

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-14
"""

import sqlalchemy as sa

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raster_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("converted_key", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("limit_collection_id", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_raster_jobs_tenant_id", "raster_jobs", ["tenant_id", "id"])
    op.create_table(
        "raster_assets",
        sa.Column(
            "item_id",
            sa.String(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("srid", sa.Integer(), nullable=False),
        sa.Column("bounds", sa.JSON(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("dtype", sa.String(), nullable=False),
        sa.Column("nodata", sa.Float(), nullable=True),
        sa.Column("bands", sa.JSON(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("limit_collection_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_raster_assets_tenant_id", "raster_assets", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_raster_assets_tenant_id", table_name="raster_assets")
    op.drop_table("raster_assets")
    op.drop_index("ix_raster_jobs_tenant_id", table_name="raster_jobs")
    op.drop_table("raster_jobs")
