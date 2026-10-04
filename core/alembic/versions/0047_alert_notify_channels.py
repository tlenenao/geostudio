# SPDX-License-Identifier: Apache-2.0
"""Statut de livraison par canal d'une évaluation d'alerte (REV-277d)

`notify_channels` : {clé de canal: "delivered" | "failed"}, la clé étant une
empreinte du canal (jamais l'URL en clair, qui peut porter un jeton). Une
relance (P20.03) ne renvoie qu'aux canaux non livrés. Les lignes existantes
restent NULL : aucun canal connu livré, donc relance sur tous (comportement
d'avant cette migration). Le downgrade ne perd que ce détail par canal ;
notify_status/notify_error (0044) restent.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_evaluations", sa.Column("notify_channels", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_evaluations", "notify_channels")
