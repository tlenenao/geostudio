# SPDX-License-Identifier: Apache-2.0
"""users.erased_at + table purge_receipts (SP-58 Tâche 6, GAP-74)

users.erased_at : colonne additive, nullable — horodatage de l'anonymisation
(Tâche 7). Sert à l'idempotence (un second appel d'anonymize_user sur un
compte déjà anonymisé est un échec explicite) et à l'affichage admin.

purge_receipts : nouvelle table, VOLONTAIREMENT sans ForeignKey vers
`tenants` (spec §3.3 Step 8) — la ligne doit survivre à la suppression du
tenant qu'elle documente (preuve d'effacement). Aucune donnée personnelle :
tenant_slug/requested_by_user_id sont des chaînes libres (snapshot, même
rationale que audit_log.actor_id, cf. app/audit/models.py), counts est un
JSON de comptages agrégés uniquement.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-06
"""

import os

import sqlalchemy as sa

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("erased_at", sa.DateTime(), nullable=True))
    op.create_table(
        "purge_receipts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_slug", sa.String(), nullable=False),
        sa.Column("requested_by_user_id", sa.String(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("counts", sa.JSON(), nullable=False),
    )


ALLOW_ENV = "GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE"


def _refuse_if_data(what: str, count: int) -> None:
    # P09.10 (c03-009) : ce downgrade détruit un état de conformité. Il échoue
    # tant que des lignes existent, sauf accord explicite (restaurer une
    # sauvegarde est le chemin normal, cf. deploy/backup).
    if count and os.environ.get(ALLOW_ENV) != "1":
        raise RuntimeError(
            f"downgrade refusé : {count} {what} seraient détruit(e)s. "
            f"Restaurez une sauvegarde, ou exportez ces données puis relancez avec {ALLOW_ENV}=1."
        )


def downgrade() -> None:
    conn = op.get_bind()
    _refuse_if_data(
        "preuve(s) d'effacement (purge_receipts)",
        conn.execute(sa.text("SELECT count(*) FROM purge_receipts")).scalar_one(),
    )
    _refuse_if_data(
        "horodatage(s) d'anonymisation (users.erased_at)",
        conn.execute(
            sa.text("SELECT count(*) FROM users WHERE erased_at IS NOT NULL")
        ).scalar_one(),
    )
    op.drop_table("purge_receipts")
    op.drop_column("users", "erased_at")
