# SPDX-License-Identifier: Apache-2.0
"""app.reports — report_runs.export_job_id nullable (revue finale SP-17b, I2)

Un déclenchement de rapport qui échoue doit tout de même laisser une ligne
report_runs : list_due_reports dérive la cadence cron de get_latest_run, donc
sans ligne le rapport était rejugé « dû » à chaque balayage de 5 minutes au
lieu de respecter son cron. Une telle ligne n'a aucun export_jobs derrière
elle, d'où le passage de la colonne en nullable (relâchement de contrainte
uniquement — aucune donnée existante n'est touchée).

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-09
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "report_runs",
        "export_job_id",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "report_runs",
        "export_job_id",
        existing_type=sa.String(),
        nullable=False,
    )
