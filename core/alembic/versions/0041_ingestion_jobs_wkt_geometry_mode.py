# SPDX-License-Identifier: Apache-2.0
"""ingestion_jobs.wkt_field + ingestion_jobs.geometry_mode (GAP-29, Task 11)
— même patron que 0010_ingestion_jobs_layer_name.py : deux colonnes
nullables ajoutées à une table déjà en place, aucune donnée existante à
migrer.

`alembic revision -m ...` échoue dans ce dépôt (`alembic/script.py.mako`
absent, jamais commité — piège CLAUDE.md n°3, vérifié en session plutôt que
supposé) : ce fichier est écrit à la main en suivant exactement le format
généré habituel (mêmes noms de champs, même ordre revision/down_revision).

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("wkt_field", sa.String(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("geometry_mode", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "geometry_mode")
    op.drop_column("ingestion_jobs", "wkt_field")
