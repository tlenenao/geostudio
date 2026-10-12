# SPDX-License-Identifier: Apache-2.0
"""collection_relations : relations 1-1 / 1-N / N-N entre collections (ARC-21, ADR 0021)

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def _coll_fk(nullable: bool) -> sa.ForeignKey:
    return sa.ForeignKey("collections.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "collection_relations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("cardinality", sa.String(), nullable=False),
        sa.Column("parent_collection_id", sa.String(), _coll_fk(False), nullable=False),
        sa.Column("child_collection_id", sa.String(), _coll_fk(False), nullable=False),
        sa.Column("parent_key", sa.String(), nullable=False),
        sa.Column("child_key", sa.String(), nullable=False),
        sa.Column("link_collection_id", sa.String(), _coll_fk(True), nullable=True),
        sa.Column("link_parent_key", sa.String(), nullable=True),
        sa.Column("link_child_key", sa.String(), nullable=True),
        sa.Column("on_delete", sa.String(), nullable=False, server_default="restrict"),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("parent_collection_id", "name", name="uq_collection_relations_name"),
    )
    op.create_index("ix_collection_relations_tenant", "collection_relations", ["tenant_id"])
    op.create_index(
        "ix_collection_relations_parent", "collection_relations", ["parent_collection_id"]
    )
    op.create_index(
        "ix_collection_relations_child", "collection_relations", ["child_collection_id"]
    )
    op.create_index("ix_collection_relations_link", "collection_relations", ["link_collection_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_relations_link", table_name="collection_relations")
    op.drop_index("ix_collection_relations_child", table_name="collection_relations")
    op.drop_index("ix_collection_relations_parent", table_name="collection_relations")
    op.drop_index("ix_collection_relations_tenant", table_name="collection_relations")
    op.drop_table("collection_relations")
