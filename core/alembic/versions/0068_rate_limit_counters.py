# SPDX-License-Identifier: Apache-2.0
"""rate_limit_counters : limiteur de débit partagé entre réplicas (ARC-32)

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-14
"""

import sqlalchemy as sa

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # UNLOGGED : compteurs éphémères (fenêtre 60 s), perte au crash sans conséquence.
    op.create_table(
        "rate_limit_counters",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("grp", sa.String(), primary_key=True),
        sa.Column("window_start", sa.BigInteger(), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False),
        prefixes=["UNLOGGED"],
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
