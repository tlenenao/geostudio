# SPDX-License-Identifier: Apache-2.0
"""collection_geo_limits : restriction géographique de lecture (REV-121/GAP-27)

Table seule : la fonction `app_geo_limit()` et la policy RLS restrictive par
collection sont posées par `app.collections.ddl` (apply_collection_ddl, puis
ensure_geo_limit_policy à la création de la première limite d'une collection
préexistante) — jamais ici, pour qu'il n'existe qu'une définition.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-10
"""

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_geo_limits",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "collection_id", "target_type", "target_id", name="uq_geo_limit_target"
        ),
    )
    op.create_index(
        "ix_geo_limits_tenant_collection", "collection_geo_limits", ["tenant_id", "collection_id"]
    )


def downgrade() -> None:
    op.drop_table("collection_geo_limits")
