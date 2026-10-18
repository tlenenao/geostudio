# SPDX-License-Identifier: Apache-2.0
"""audit_log append-only + chaînage de hachage (AUD-092)

Colonnes `chain_seq`/`prev_hash`/`hash` (posées par le scellement, jamais à l'écriture :
aucun verrou ni attente sur le chemin chaud) et trigger `BEFORE UPDATE OR DELETE` : seul
le scellement d'une ligne non scellée, ou une session de maintenance explicite
(`app.audit_maintenance = on` : rétention, purge de tenant, effacement RGPD du payload)
peut modifier ou supprimer une ligne. Un trigger vaut mieux qu'un REVOKE : il s'applique
aussi au propriétaire des tables.

Revision ID: 0120
Revises: 0095
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0120"
down_revision = "0095"
branch_labels = None
depends_on = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_guard() RETURNS trigger AS $$
BEGIN
  IF current_setting('app.audit_maintenance', true) = 'on' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.hash IS NULL AND NEW.hash IS NOT NULL
     AND (to_jsonb(NEW) - 'hash' - 'prev_hash' - 'chain_seq')
       = (to_jsonb(OLD) - 'hash' - 'prev_hash' - 'chain_seq') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("chain_seq", sa.Integer(), nullable=True))
    op.add_column("audit_log", sa.Column("prev_hash", sa.String(), nullable=True))
    op.add_column("audit_log", sa.Column("hash", sa.String(), nullable=True))
    op.create_index("ix_audit_log_tenant_chain", "audit_log", ["tenant_id", "chain_seq"])
    op.create_index(
        "ix_audit_log_unsealed",
        "audit_log",
        ["tenant_id", "id"],
        postgresql_where=sa.text("hash IS NULL"),
    )
    op.execute(_FUNCTION)
    op.execute(
        "CREATE TRIGGER audit_log_guard BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_guard ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_guard()")
    op.drop_index("ix_audit_log_unsealed", table_name="audit_log")
    op.drop_index("ix_audit_log_tenant_chain", table_name="audit_log")
    op.drop_column("audit_log", "hash")
    op.drop_column("audit_log", "prev_hash")
    op.drop_column("audit_log", "chain_seq")
