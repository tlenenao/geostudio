# SPDX-License-Identifier: Apache-2.0
"""app.reports — report_runs (SP-17b)

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-09
"""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("report_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("export_job_id", sa.String(), nullable=False),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_report_runs_tenant_id", "report_runs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_report_runs_tenant_id", table_name="report_runs")
    op.drop_table("report_runs")
