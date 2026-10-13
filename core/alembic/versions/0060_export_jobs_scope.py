# SPDX-License-Identifier: Apache-2.0
"""Portée d'un export PDF d'app (ARC-26 fiche d'entité, ARC-30 atlas) :
`export_jobs.scope`, NULL pour tous les jobs existants.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("scope", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "scope")
