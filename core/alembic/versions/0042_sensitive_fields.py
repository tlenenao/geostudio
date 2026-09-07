# SPDX-License-Identifier: Apache-2.0
"""Collection.sensitive_fields + rôle gis_rls_masked (GAP-22, masquage de
champ par colonne)

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-06

Renumérotée 0041 -> 0042 lors du rebasage sur dev (2026-09-13) : 0041 a été
pris entre-temps par 0041_ingestion_jobs_wkt_geometry_mode.py (GAP-29),
mergé dans dev pendant que cette branche restait ouverte — CLAUDE.md piège
n°9, collision de numéro de migration entre sessions concurrentes.
"""

import sqlalchemy as sa

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("sensitive_fields", sa.JSON(), nullable=False, server_default="[]"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS "
            "(SELECT FROM pg_roles WHERE rolname = 'gis_rls_masked') "
            "THEN CREATE ROLE gis_rls_masked NOLOGIN; END IF; END $$;"
        )
        op.execute("GRANT gis_rls_masked TO current_user")
        # Backfill : toute collection déjà enregistrée avant cette migration a
        # `sensitive_fields = []` par construction (colonne neuve) — le rôle
        # masqué doit donc voir TOUTES ses colonnes réelles dès l'activation,
        # sinon la première requête sous gis_rls_masked contre une collection
        # préexistante échoue en "permission denied for table" (aucune
        # colonne grantée). Recalcule dynamiquement (nom de table/colonnes
        # inconnus statiquement) via un bloc PL/pgSQL — une migration
        # n'importe pas app.collections.ddl.
        op.execute(
            """
            DO $$
            DECLARE
                col RECORD;
                colname text;
            BEGIN
                FOR col IN SELECT table_name FROM collections LOOP
                    FOR colname IN
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = col.table_name
                    LOOP
                        EXECUTE format(
                            'GRANT SELECT (%I) ON public.%I TO gis_rls_masked',
                            colname, col.table_name
                        );
                    END LOOP;
                END LOOP;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP OWNED BY gis_rls_masked")
        op.execute("DROP ROLE IF EXISTS gis_rls_masked")
    op.drop_column("collections", "sensitive_fields")
