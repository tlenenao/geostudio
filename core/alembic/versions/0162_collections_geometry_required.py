# SPDX-License-Identifier: Apache-2.0
"""collections.geometry_required : géométrie obligatoire à l'écriture (L8, AUD-070)

L'import XLSForm déclarait une géométrie requise « approximée : non imposée ». Le drapeau est
désormais lu par `validate_feature` (tous les chemins d'écriture). Défaut false : comportement
historique inchangé.

Revision ID: 0162
Revises: 0161
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("geometry_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("collections", "geometry_required")
