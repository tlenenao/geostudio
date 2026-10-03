"""Index manquants audit_log, configs, config_revisions, report_runs (P24.01-04)

Créés CONCURRENTLY (hors transaction) : audit_log grossit sans borne et ne
doit pas être verrouillée en écriture pendant la migration. IF NOT EXISTS :
rejouable après un CREATE INDEX CONCURRENTLY interrompu (index invalide à
supprimer à la main).

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-03
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_audit_log_tenant_created", "audit_log", "tenant_id, created_at"),
    ("ix_audit_log_tenant_actor_created", "audit_log", "tenant_id, actor_id, created_at"),
    ("ix_configs_item_id", "configs", "item_id"),
    ("ix_configs_kind_tenant_id", "configs", "kind, tenant_id"),
    ("ix_config_revisions_config_version", "config_revisions", "config_id, version"),
    ("ix_report_runs_report", "report_runs", "report_item_id, tenant_id, created_at"),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, cols in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({cols})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _cols in reversed(_INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
