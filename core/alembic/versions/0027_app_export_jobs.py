# SPDX-License-Identifier: Apache-2.0
"""app.appexport — app_export_jobs

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_export_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("result_key", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_app_export_jobs_tenant_id", "app_export_jobs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_app_export_jobs_tenant_id", table_name="app_export_jobs")
    op.drop_table("app_export_jobs")
