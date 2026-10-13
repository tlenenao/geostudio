# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs : retry/reprise par nœud (ARC-K2/F5)

`attempt` (1 = première exécution), `next_retry_at` (statut `retrying`),
`resume_of` (run racine dont les points de reprise sont réutilisés),
`resumable` (des points de reprise existent côté worker : calculé par le worker,
car l'API tourne dans un autre conteneur).

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("pipeline_runs", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("resume_of", sa.String(), nullable=True))
    op.add_column(
        "pipeline_runs",
        sa.Column("resumable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "resumable")
    op.drop_column("pipeline_runs", "resume_of")
    op.drop_column("pipeline_runs", "next_retry_at")
    op.drop_column("pipeline_runs", "attempt")
