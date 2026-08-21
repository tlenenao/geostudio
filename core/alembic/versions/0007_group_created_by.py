"""groups.created_by

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `groups` was only introduced in migration 0006 of this same branch and
    # no cutover to production has happened yet (see 0005's precedent: reset
    # a stale dev DB rather than backfill). There is no real created_by data
    # to reconstruct, so this column goes straight in as NOT NULL — matching
    # the ORM model — rather than adding it nullable and leaving the schema
    # and model inconsistent.
    op.add_column(
        "groups",
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("groups", "created_by")
