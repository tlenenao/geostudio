"""items table; configs.item_id becomes a real FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("abstract", sa.String(), nullable=False, server_default=""),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # AUD-191 : backfill avant contrainte. Chaque config existante reçoit un item (id = ancien
    # item_id, sinon l'id de la config), propriété du plus ancien utilisateur de son tenant ; la
    # colonne est conservée (pas de drop/add qui perdait la valeur) puis passée NOT NULL + FK.
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text(
            "SELECT count(*) FROM configs c WHERE NOT EXISTS "
            "(SELECT 1 FROM users u WHERE u.tenant_id = c.tenant_id)"
        )
    ).scalar_one()
    if orphans:
        msg = (
            f"migration 0005 : {orphans} config(s) dans un tenant sans utilisateur — "
            "aucun propriétaire possible pour l'item à créer ; créez un utilisateur ou purgez-les."
        )
        raise RuntimeError(msg)
    conn.execute(
        sa.text(
            "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, abstract, keywords,"
            " is_published, created_at, updated_at) "
            "SELECT COALESCE(c.item_id, c.id), c.tenant_id, "
            "(SELECT u.id FROM users u WHERE u.tenant_id = c.tenant_id ORDER BY u.created_at, u.id "
            "LIMIT 1), c.kind, c.kind || ' ' || c.id, '', '[]', false, now(), now() "
            "FROM configs c ON CONFLICT (id) DO NOTHING"
        )
    )
    op.execute("UPDATE configs SET item_id = id WHERE item_id IS NULL")
    op.alter_column("configs", "item_id", nullable=False)
    op.create_foreign_key(
        "configs_item_id_fkey", "configs", "items", ["item_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("configs_item_id_fkey", "configs", type_="foreignkey")
    op.alter_column("configs", "item_id", nullable=True)
    op.drop_table("items")
