# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale d'un item map (SP-55 §2, GAP-06) : 4 colonnes
nullables sur items — bbox_min_x/min_y/max_x/max_y. NULL sur les 4 =
« pas d'emprise connue » (item non géographique, ou config jamais
réévaluée depuis ce SP). Recalculées par
app.configs.bbox::recompute_item_bbox, jamais posées directement ailleurs.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("bbox_min_x", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("bbox_min_y", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("bbox_max_x", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("bbox_max_y", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "bbox_max_y")
    op.drop_column("items", "bbox_max_x")
    op.drop_column("items", "bbox_min_y")
    op.drop_column("items", "bbox_min_x")
