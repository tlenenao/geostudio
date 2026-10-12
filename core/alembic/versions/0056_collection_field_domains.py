# SPDX-License-Identifier: Apache-2.0
"""collections.field_domains / subtypes + ingestion_jobs.target_collection_id / report
(ARC-13 : domaines et sous-types d'attributs)

Colonnes JSON nullables-par-défaut `{}` : pas de rétro-application sur les données
existantes (une collection sans domaine se comporte exactement comme avant).

Revision ID: 0056
Revises: 0054
Create Date: 2026-10-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0056"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("field_domains", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "collections",
        sa.Column("subtypes", sa.JSON(), nullable=False, server_default="{}"),
    )
    # Import dans une collection existante + rapport de rejet (ARC-13, critère 3).
    op.add_column("ingestion_jobs", sa.Column("target_collection_id", sa.String(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("report", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "report")
    op.drop_column("ingestion_jobs", "target_collection_id")
    op.drop_column("collections", "subtypes")
    op.drop_column("collections", "field_domains")
