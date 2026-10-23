# SPDX-License-Identifier: Apache-2.0
"""extensions : manifeste v1 du SDK (AUD-109, AUD-110)

`sdk_version` (contrat DOM), `integrity` (SRI du module), `connect_hosts`/`img_hosts`
(origines ajoutées à la CSP). Les lignes existantes prennent v1, sans intégrité, sans hôte.

Revision ID: 0171
Revises: 0170
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extensions",
        sa.Column("sdk_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("extensions", sa.Column("integrity", sa.String(), nullable=True))
    for column in ("connect_hosts", "img_hosts"):
        op.add_column(
            "extensions",
            sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )


def downgrade() -> None:
    for column in ("img_hosts", "connect_hosts", "integrity", "sdk_version"):
        op.drop_column("extensions", column)
