# SPDX-License-Identifier: Apache-2.0
"""group_claim_mappings + group_members.origin : groupes alimentés par claims (ARC-24, ADR 0022)

Revision ID: 0061
Revises: 0059
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0061"
# INTÉGRATION : la voie H prend 0060 ; à la fusion, `down_revision` doit devenir "0060".
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "group_members",
        sa.Column("origin", sa.String(), nullable=False, server_default="manual"),
    )
    op.create_table(
        "group_claim_mappings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "group_id", sa.String(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("claim_value", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "claim_value", "group_id", name="uq_gcm"),
    )


def downgrade() -> None:
    op.drop_table("group_claim_mappings")
    op.drop_column("group_members", "origin")
