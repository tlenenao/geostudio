"""items table; configs.item_id becomes a real FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("abstract", sa.String(), nullable=False, server_default=""),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # No pre-existing `configs` rows are expected in any real deployment yet
    # (no prod cutover has happened — see A15). If a dev database has stale
    # rows from manual testing, reset it (`docker compose down -v` on
    # `postgis`) rather than migrating them: there is no real title/owner
    # data to reconstruct an `items` row from at the DB level.
    op.drop_column("configs", "item_id")
    op.add_column(
        "configs",
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("configs", "item_id")
    op.add_column("configs", sa.Column("item_id", sa.String(), nullable=True))
    op.drop_table("items")
