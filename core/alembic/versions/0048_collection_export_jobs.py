# SPDX-License-Identifier: Apache-2.0
"""collection_export_jobs : export asynchrone de collection (REV-283e)

Table dédiée (l'`export_jobs` PDF/PNG exige un `item_id`). Le downgrade
supprime la table et les jobs en cours ; les fichiers S3 restants sont purgés
par le TTL (`expires_at`) côté stockage.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-05
"""

import sqlalchemy as sa

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_export_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("query", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("masked", sa.Boolean(), nullable=False),
        sa.Column("result_key", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_collection_export_jobs_tenant_status", "collection_export_jobs", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_collection_export_jobs_expires_at", "collection_export_jobs", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("collection_export_jobs")
