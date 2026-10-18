# SPDX-License-Identifier: Apache-2.0
"""item_shares / collection_shares : échéance facultative du partage (AUD-097)

NULL = sans échéance (comportement historique inchangé). Lue partout via
`app.sharing.models.share_active`.

Revision ID: 0123
Revises: 0122
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None

_TABLES = ("item_shares", "collection_shares")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "expires_at")
