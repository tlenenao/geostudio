# SPDX-License-Identifier: Apache-2.0
"""submission_tokens + submissions : soumission publique modérée (ARC-10, ADR 0017)

Revision ID: 0058
Revises: 0055
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0058"
# INTÉGRATION : 0056 (domaines, ARC-13) et 0057 (règles, ARC-14) sont écrites par d'autres
# voies ; à la fusion, `down_revision` doit devenir "0057" (tête linéaire).
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("token_prefix", sa.String(), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("max_submissions", sa.Integer(), nullable=False),
        sa.Column("submission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_submission_tokens_collection", "submission_tokens", ["tenant_id", "collection_id"]
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_id",
            sa.String(),
            sa.ForeignKey("submission_tokens.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attachment", sa.JSON(), nullable=True),
        sa.Column("attachment_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("moderated_by", sa.String(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(), nullable=True),
        sa.Column("feature_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_submissions_queue",
        "submissions",
        ["tenant_id", "collection_id", "status", "created_at"],
    )
    op.create_index("ix_submissions_attachment_key", "submissions", ["attachment_key"])


def downgrade() -> None:
    op.drop_index("ix_submissions_attachment_key", table_name="submissions")
    op.drop_index("ix_submissions_queue", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_submission_tokens_collection", table_name="submission_tokens")
    op.drop_table("submission_tokens")
