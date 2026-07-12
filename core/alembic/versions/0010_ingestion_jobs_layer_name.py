"""ingestion_jobs.layer_name (SP-6b — GeoPackage/Shapefile multi-couches)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs", sa.Column("layer_name", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "layer_name")
