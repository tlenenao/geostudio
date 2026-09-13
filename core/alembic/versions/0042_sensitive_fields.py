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
        conn = op.get_bind()
        conn.execute(sa.text("DROP OWNED BY gis_rls_masked"))
        # Un rôle est un objet global au cluster Postgres, pas à cette seule
        # base : si une AUTRE base du même cluster (ex. la base de test
        # partagée, dans une suite complète où de nombreuses collections
        # ont réellement grante ce rôle) lui a encore accordé des
        # privilèges, DROP ROLE échoue en DependentObjectsStillExist bien
        # que `DROP OWNED BY` ci-dessus ait déjà nettoyé la base courante
        # (portée documentée de `DROP OWNED BY` : la base courante
        # uniquement). SAVEPOINT pour ne pas empoisonner la transaction de
        # migration si cette tentative échoue — seule la colonne compte
        # pour la validité du downgrade, la suppression du rôle est un
        # nettoyage best-effort.
        try:
            with conn.begin_nested():
                conn.execute(sa.text("DROP ROLE IF EXISTS gis_rls_masked"))
        except sa.exc.DBAPIError:
            pass
    op.drop_column("collections", "sensitive_fields")
