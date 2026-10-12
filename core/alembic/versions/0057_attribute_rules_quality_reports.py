# SPDX-License-Identifier: Apache-2.0
"""collections.attribute_rules + table quality_reports (ARC-14 : règles d'attributs CEL)

Une collection sans règle se comporte exactement comme avant (`[]`, aucune rétro-application).

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("attribute_rules", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("masked", sa.Boolean(), nullable=False),
        sa.Column("checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("violations", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_quality_reports_collection",
        "quality_reports",
        ["tenant_id", "collection_id", "created_at"],
    )
    op.create_index("ix_quality_reports_status", "quality_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_quality_reports_status", table_name="quality_reports")
    op.drop_index("ix_quality_reports_collection", table_name="quality_reports")
    op.drop_table("quality_reports")
    op.drop_column("collections", "attribute_rules")
