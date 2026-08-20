# SPDX-License-Identifier: Apache-2.0
"""harvest_records : external_url + tiles_url + layer_kind (SP-12e)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-23
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("harvest_records", sa.Column("external_url", sa.String(), nullable=True))
    op.add_column("harvest_records", sa.Column("tiles_url", sa.String(), nullable=True))
    op.add_column("harvest_records", sa.Column("layer_kind", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("harvest_records", "layer_kind")
    op.drop_column("harvest_records", "tiles_url")
    op.drop_column("harvest_records", "external_url")
