"""tenants table; tenant_id on configs/config_revisions

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "default"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    tenants_table = sa.table(
        "tenants",
        sa.column("id", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        tenants_table,
        [
            {
                "id": DEFAULT_TENANT_ID,
                "slug": "default",
                "name": "Default",
                "created_at": datetime.now(UTC),
            }
        ],
    )

    for table in ("configs", "config_revisions"):
        op.add_column(table, sa.Column("tenant_id", sa.String(), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '{DEFAULT_TENANT_ID}'")
        op.alter_column(table, "tenant_id", nullable=False)
        op.create_foreign_key(f"fk_{table}_tenant", table, "tenants", ["tenant_id"], ["id"])


def downgrade() -> None:
    for table in ("config_revisions", "configs"):
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
    op.drop_table("tenants")
