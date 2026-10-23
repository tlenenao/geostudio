# SPDX-License-Identifier: Apache-2.0
"""attachments : unicité (tenant_id, s3_key) (L8, AUD-004, constat M1)

Le rejeu d'une confirmation de pièce jointe (file hors-ligne) pouvait créer deux lignes pour le
même objet S3. Dédoublonnage préalable : on garde la plus ancienne ligne (created_at, id) ; les
objets S3 ne sont jamais touchés (la ligne conservée les référence encore).

Revision ID: 0161
Revises: 0160
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM attachments a USING attachments b "
            "WHERE a.tenant_id = b.tenant_id AND a.s3_key = b.s3_key "
            "AND (a.created_at, a.id) > (b.created_at, b.id)"
        )
    )
    op.create_index(
        "uq_attachments_tenant_s3_key", "attachments", ["tenant_id", "s3_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_attachments_tenant_s3_key", table_name="attachments")
