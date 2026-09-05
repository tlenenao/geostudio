# SPDX-License-Identifier: Apache-2.0
"""attachments.collection_id : ON DELETE CASCADE (SP-42/F-securite-tenant-rls-03)

Filet de sécurité DB en plus de la purge applicative explicite
(attachments_repo.delete_all_for_collection, appelée par unregister_collection
avant la suppression de la collection) : sans lui, DELETE /collections/{id}
échouait en 500 (IntegrityError, sqlalchemy.exc.IntegrityError côté SQLite,
psycopg.errors.ForeignKeyViolation côté Postgres) dès qu'une pièce jointe
existait sur l'une des entités de la collection. Même patron que
CollectionShare.collection_id (app/sharing/models.py, migration 0008).

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-05
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "attachments_collection_id_fkey"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "attachments", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "attachments",
        "collections",
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "attachments", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "attachments",
        "collections",
        ["collection_id"],
        ["id"],
    )
