# SPDX-License-Identifier: Apache-2.0
"""app.mapicons — table map_icons (SP-27 §3.4).

Bibliothèque d'icônes personnalisées par tenant : métadonnées en base, octets
en S3 (bucket S3_MAPICONS_BUCKET). Table neuve, sans donnée à migrer ; les
deux sens sont vérifiés sur base non vide à l'étape 12 de la tâche.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_icons",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_map_icons_tenant_id", "map_icons", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_map_icons_tenant_id", table_name="map_icons")
    op.drop_table("map_icons")
