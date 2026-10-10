# SPDX-License-Identifier: Apache-2.0
"""Rôle de partage « manager » (gestionnaire) — REV-270 / P14.12

Distingue « peut modifier » (editor) de « peut gérer le partage » (manager).
Jusqu'ici editor ouvrait aussi le partage ; pour ne retirer silencieusement
aucun droit existant, les partages `editor` actuels sont promus `manager`
(même pouvoir qu'avant) — un administrateur rétrograde ensuite à la carte.
Ajoute une contrainte CHECK sur le rôle (aucune n'existait). Une ligne
audit_log « sharing.role_migrated » par tenant et par table touchés.

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-10
"""

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_TABLES = {
    "item_shares": "ck_item_shares_role",
    "collection_shares": "ck_collection_shares_role",
}


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            "INSERT INTO audit_log (tenant_id, actor_id, actor_kind, action, object_type, "
            "object_id, payload, created_at) "
            "SELECT tenant_id, NULL, 'system', 'sharing.role_migrated', 'tenant', tenant_id, "
            f"json_build_object('table', '{table}', 'from', 'editor', 'to', 'manager', "
            "'count', count(*)), now() "
            f"FROM {table} WHERE role = 'editor' GROUP BY tenant_id"
        )
        op.execute(f"UPDATE {table} SET role = 'manager' WHERE role = 'editor'")
    for table, ck in _TABLES.items():
        op.create_check_constraint(ck, table, "role IN ('viewer', 'editor', 'manager')")


def downgrade() -> None:
    for table, ck in _TABLES.items():
        op.drop_constraint(ck, table, type_="check")
        op.execute(f"UPDATE {table} SET role = 'editor' WHERE role = 'manager'")
