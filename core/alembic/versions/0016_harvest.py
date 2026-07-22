# SPDX-License-Identifier: Apache-2.0
"""app.harvest — harvest_sources + harvest_records (SP-12c)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harvest_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="reference"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "harvest_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "source_id", sa.String(),
            sa.ForeignKey("harvest_sources.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("collection_id", sa.String(), sa.ForeignKey("collections.id"), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("harvested_at", sa.DateTime(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_harvest_records_tenant_source_external",
        "harvest_records",
        ["tenant_id", "source_id", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_harvest_records_tenant_source_external", table_name="harvest_records")
    op.drop_table("harvest_records")
    op.drop_table("harvest_sources")
