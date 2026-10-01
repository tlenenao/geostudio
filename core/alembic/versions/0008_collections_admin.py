"""users.is_admin, collections, collection_shares, rôle gis_rls

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "collections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("pk_column", sa.String(), nullable=False),
        sa.Column("geometry_column", sa.String(), nullable=True),
        sa.Column("geometry_type", sa.String(), nullable=True),
        sa.Column("srid", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "table_name", name="uq_collections_tenant_table"),
    )
    op.create_table(
        "collection_shares",
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "group_id",
            sa.String(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
    )
    # Rôle non-propriétaire pour la RLS (spec §2/§5) — Postgres uniquement,
    # idempotent (la base de test CI et un redéploiement peuvent l'avoir déjà).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gis_rls') "
            "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;"
        )
        op.execute("GRANT gis_rls TO current_user")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        conn = op.get_bind()
        # P09.09 (c03-008) : un rôle est global au cluster. DROP OWNED BY lève
        # si le rôle a disparu, DROP ROLE si une AUTRE base du cluster lui a
        # encore accordé des privilèges — chaque instruction a son savepoint
        # (même patron que 0042.downgrade) pour ne pas empoisonner la
        # transaction de migration ; seule compte l'absence de privilèges
        # gis_rls dans CETTE base.
        for stmt in ("DROP OWNED BY gis_rls", "DROP ROLE IF EXISTS gis_rls"):
            try:
                with conn.begin_nested():
                    conn.execute(sa.text(stmt))
            except sa.exc.DBAPIError:
                pass
    op.drop_table("collection_shares")
    op.drop_table("collections")
    op.drop_column("users", "is_admin")
