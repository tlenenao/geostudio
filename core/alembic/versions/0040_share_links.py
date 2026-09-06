# SPDX-License-Identifier: Apache-2.0
"""share_link table (GAP-12, chantier 4.23) — liens de partage à échéance.

Table neuve, aucune donnée existante à migrer (même patron que
0031_notifications.py) : create_table/drop_table suffisent dans les deux
sens. revoked_at nullable — révocation par ligne de base (pas seulement par
TTL du jeton, cf. app/sharing/share_links.py) : chaque résolution
re-consulte cette colonne en plus de l'expiration du JWT lui-même.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_link",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "item_id", sa.String(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_share_link_tenant_item",
        "share_link",
        ["tenant_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_share_link_tenant_item", table_name="share_link")
    op.drop_table("share_link")
