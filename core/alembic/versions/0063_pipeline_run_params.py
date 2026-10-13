# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.params : paramètres de run publiés d'un pipeline (ARC-K2/F3)

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL pour tous les runs existants (aucun paramètre n'existait).
    op.add_column("pipeline_runs", sa.Column("params", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_runs", "params")
