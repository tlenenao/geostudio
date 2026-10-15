# SPDX-License-Identifier: Apache-2.0
"""purge_receipts.status/error : cycle de vie d'une purge de tenant (REV-344)

Le reçu est désormais créé `pending` à la demande de purge (verrou d'idempotence : une
2e demande est refusée en 409 tant qu'une purge est en cours), puis `running`, `done` ou
`failed` (+ message). Les reçus existants sont des purges terminées : `done`.

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purge_receipts",
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'done'")),
    )
    op.add_column("purge_receipts", sa.Column("error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("purge_receipts", "error")
    op.drop_column("purge_receipts", "status")
