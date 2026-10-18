# SPDX-License-Identifier: Apache-2.0
"""llm_usage + tenant_llm_settings : consommation LLM et fournisseur par tenant (AUD-106/149)

Revision ID: 0170
Revises: 0123
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0170"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("surface", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_llm_usage_tenant_created", "llm_usage", ["tenant_id", "created_at"])
    op.create_table(
        "tenant_llm_settings",
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("api_url", sa.String(512), nullable=True),
        sa.Column("key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("key_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("daily_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_llm_settings")
    op.drop_index("ix_llm_usage_tenant_created", table_name="llm_usage")
    op.drop_table("llm_usage")
