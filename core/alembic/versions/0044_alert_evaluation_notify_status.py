# SPDX-License-Identifier: Apache-2.0
"""Statut de livraison de la notification par évaluation d'alerte (P20.01/03)

`notify_status` : NULL (aucune notification tentée), 'delivered' ou 'failed' ;
`notify_error` : motif de l'échec (canaux en erreur). Un 'failed' est retenté
à l'évaluation suivante (borné, cf. app.alerts.jobs). Les lignes existantes
restent NULL (historique inchangé, rien à rejouer).

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_evaluations", sa.Column("notify_status", sa.String(), nullable=True))
    op.add_column("alert_evaluations", sa.Column("notify_error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_evaluations", "notify_error")
    op.drop_column("alert_evaluations", "notify_status")
