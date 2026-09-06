# SPDX-License-Identifier: Apache-2.0
"""export_jobs.byte_size + app_export_jobs.byte_size (SP-58 Tâche 2, GAP-73)

Colonnes additives, nullable : aucune des deux tables ne connaissait jusqu'ici
la taille du fichier qu'elle vient d'écrire sur S3 (vérifié directement dans
app/export/models.py et app/appexport/models.py, spec SP-58 §1.1/§1.4). Les
lignes historiques (jobs "done" avant cette migration) restent NULL et sont
traitées comme 0 par la somme de app.quotas.service::job_output_storage_bytes
— limitation assumée et documentée : ces jobs anciens ne compteront jamais
dans le quota de stockage, seuls les nouveaux jobs après déploiement de cette
migration seront mesurés (spec §3.1).

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("byte_size", sa.Integer(), nullable=True))
    op.add_column("app_export_jobs", sa.Column("byte_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_export_jobs", "byte_size")
    op.drop_column("export_jobs", "byte_size")
