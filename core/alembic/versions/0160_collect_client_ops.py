# SPDX-License-Identifier: Apache-2.0
"""collect_client_ops : idempotence des écritures de collecte hors-ligne (L8, AUD-004)

Une ligne par opération client appliquée (clé `Idempotency-Key`) ; un rejeu rend le résultat
d'origine sans réécrire. Unique (tenant, collection, acteur, kind, client_op_id).

Revision ID: 0160
Revises: 0123
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0160"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collect_client_ops",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("client_op_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "collection_id",
            "actor_id",
            "kind",
            "client_op_id",
            name="uq_collect_client_ops_op",
        ),
    )
    op.create_index("ix_collect_client_ops_created_at", "collect_client_ops", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_collect_client_ops_created_at", table_name="collect_client_ops")
    op.drop_table("collect_client_ops")
