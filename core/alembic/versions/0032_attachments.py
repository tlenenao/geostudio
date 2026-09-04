# SPDX-License-Identifier: Apache-2.0
"""app.attachments — table attachments + Collection.attachment_fields
(chantier 4.12, docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md)

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("fid", sa.String(), nullable=False),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_attachments_entity",
        "attachments",
        ["tenant_id", "collection_id", "fid", "field_key"],
    )
    op.add_column(
        "collections",
        sa.Column("attachment_fields", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("collections", "attachment_fields")
    op.drop_index("ix_attachments_entity", table_name="attachments")
    op.drop_table("attachments")
