# SPDX-License-Identifier: Apache-2.0
"""api_keys : clés d'API de service (ARC-06, ADR 0016)

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_api_keys_tenant_created_by", "api_keys", ["tenant_id", "created_by"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_tenant_created_by", table_name="api_keys")
    op.drop_table("api_keys")
