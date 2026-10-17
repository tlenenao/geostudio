# SPDX-License-Identifier: Apache-2.0
"""purge_receipts.purged_tenant_id : retrouver les préfixes S3 d'une purge à rattraper (AUD-121)

Le reçu portait seulement le slug (≠ id en général). Statut `done_with_s3_pending` : purge
acquise en base, nettoyage S3 à reprendre (`retry_pending_s3_purges`). Sans FK : le tenant
n'existe plus.

Revision ID: 0121
Revises: 0120
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purge_receipts", sa.Column("purged_tenant_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("purge_receipts", "purged_tenant_id")
