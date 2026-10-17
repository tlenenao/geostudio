# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.heartbeat_at — battement de cœur des runs vivants (AUD-026).

Revision ID: 0082
Revises: 0081
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_runs", "heartbeat_at")
