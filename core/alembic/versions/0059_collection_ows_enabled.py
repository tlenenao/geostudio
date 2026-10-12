# SPDX-License-Identifier: Apache-2.0
"""Activation WFS/OGC API Tiles par collection (ARC-11, ADR 0018) :
`collections.ows_enabled`, faux par défaut (aucune collection existante n'est
exposée tant qu'un propriétaire ne l'active pas).

Revision ID: 0059
Revises: 0054
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("ows_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("collections", "ows_enabled")
