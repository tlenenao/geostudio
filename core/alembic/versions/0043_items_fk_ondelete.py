# SPDX-License-Identifier: Apache-2.0
"""FK vers items.id : ON DELETE CASCADE / SET NULL (P09.03, c03-001)

Sept tables d'historique référençaient `items.id` sans ON DELETE :
DELETE /items/{id} d'un pipeline/alerte/rapport/export déjà exécuté levait
IntegrityError (500). L'historique d'un item supprimé n'a plus de sens
(CASCADE) ; un enregistrement de moissonnage garde sa trace mais perd le
lien vers l'item (SET NULL, colonne déjà nullable). Même patron que 0034.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-02
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# (table, colonne, ondelete) — noms de contrainte = défaut Postgres
# `<table>_<colonne>_fkey` (créées sans nom explicite).
_FKS = [
    ("pipeline_runs", "pipeline_item_id", "CASCADE"),
    ("pipeline_webhook_tokens", "pipeline_item_id", "CASCADE"),
    ("alert_evaluations", "alert_rule_item_id", "CASCADE"),
    ("report_runs", "report_item_id", "CASCADE"),
    ("export_jobs", "item_id", "CASCADE"),
    ("app_export_jobs", "item_id", "CASCADE"),
    ("harvest_records", "item_id", "SET NULL"),
]


def _recreate(*, cascade: bool) -> None:
    for table, column, ondelete in _FKS:
        name = f"{table}_{column}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, "items", [column], ["id"], ondelete=ondelete if cascade else None
        )


def upgrade() -> None:
    _recreate(cascade=True)


def downgrade() -> None:
    _recreate(cascade=False)
