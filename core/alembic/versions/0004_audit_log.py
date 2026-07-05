"""audit_log table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_kind", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
