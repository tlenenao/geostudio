# SPDX-License-Identifier: Apache-2.0
"""app.alerts/app.pipelines — index manquants sur alert_evaluations/
pipeline_runs (GAP-63, SP-49)

Les deux tables sont interrogées par (tenant_id, <item>_id) puis triées par
created_at DESC à chaque tick de balayage cron (5 minutes) depuis leur
création (migrations 0018/0020) sans qu'aucun index ne le supporte — scan
séquentiel complet à chaque appel de get_latest_run/get_latest_evaluation.

Colonne <item>_id EN TÊTE (pas tenant_id) : corrigé en revue finale de
branche (SP-49, croisement Tâche 2/Tâche 3 explicitement demandé par le
plan) — vérifié par EXPLAIN ANALYZE sur une base jetable à échelle réaliste
(2000 items, 300k runs, 2.5% de sélectivité) que get_latest_runs_for_items
(Tâche 3, WHERE <item>_id IN (...) SANS filtre tenant_id — appelants
cross-tenant par construction) ignore un index (tenant_id, <item>_id, …)
: `tenant_id` en tête ne filtre rien pour cette requête précise, donc
Postgres retombe sur un Seq/Parallel Seq Scan de la table entière (mesuré :
28,6ms, 2851 buffers). Avec <item>_id en tête, la même requête devient un
Bitmap Index Scan (mesuré : 7,2ms, 397 buffers — 4x plus rapide). Les
requêtes tenant_id+<item>_id à filtre égalité (get_latest_run/list_runs)
restent tout aussi bien servies par cet ordre : pour deux prédicats
d'égalité, l'ordre des colonnes en tête d'un index btree ne change rien à
son utilisabilité (vérifié aussi par EXPLAIN : Index Scan Backward
inchangé).

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-05
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_pipeline_runs_pipeline",
        "pipeline_runs",
        ["pipeline_item_id", "tenant_id", "created_at"],
    )
    op.create_index(
        "ix_alert_evaluations_rule",
        "alert_evaluations",
        ["alert_rule_item_id", "tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_evaluations_rule", table_name="alert_evaluations")
    op.drop_index("ix_pipeline_runs_pipeline", table_name="pipeline_runs")
