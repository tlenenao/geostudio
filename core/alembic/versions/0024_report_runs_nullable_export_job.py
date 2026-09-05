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
    """Ce relâchement de contrainte est permanent par construction : une
    ligne report_runs avec export_job_id NULL marque un déclenchement de
    rapport en échec (propriétaire ayant perdu l'accès, capacité export
    coupée) et n'a par nature aucun export_jobs valide derrière elle — cf.
    app/reports/models.py, commentaire du champ. Aucune valeur ne permet de
    revalider honnêtement la contrainte NOT NULL sans invention de donnée.
    Restaurer l'ancienne contrainte casserait donc downgrade() sur toute
    base ayant ne serait-ce qu'une ligne de ce type (situation normale de
    fonctionnement, pas un cas limite) — documenté depuis 2026-08-22
    (migration 0028), corrigé par SP-49 : ce no-op est une décision assumée,
    pas un oubli. Voir
    docs/superpowers/specs/2026-09-05-sp49-fiabilite-jobs-design.md §1.1.
    """
