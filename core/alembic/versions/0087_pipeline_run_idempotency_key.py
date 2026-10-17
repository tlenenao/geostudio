# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.idempotency_key — idempotence du déclencheur webhook (AUD-084).

Revision ID: 0087
Revises: 0082
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0087"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index(
        "ux_pipeline_runs_idempotency",
        "pipeline_runs",
        ["pipeline_item_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_pipeline_runs_idempotency", table_name="pipeline_runs")
    op.drop_column("pipeline_runs", "idempotency_key")
