# SPDX-License-Identifier: Apache-2.0
"""app.export — export_jobs.page_id / export_jobs.ctx (SP-17b)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("page_id", sa.String(), nullable=True))
    op.add_column("export_jobs", sa.Column("ctx", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "ctx")
    op.drop_column("export_jobs", "page_id")
