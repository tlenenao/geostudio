# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.failed_node_id — nœud fautif d'un run en échec (AUD-087).

Revision ID: 0088
Revises: 0087
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("failed_node_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_runs", "failed_node_id")
