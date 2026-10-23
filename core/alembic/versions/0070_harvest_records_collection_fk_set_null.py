# SPDX-License-Identifier: Apache-2.0
"""harvest_records.collection_id : ON DELETE SET NULL (REV-347)

Supprimer une collection issue d'un moissonnage levait une violation de FK
(500) : la FK n'avait pas d'ON DELETE alors que `item_id` est déjà SET NULL
(0043). L'enregistrement de moissonnage garde sa trace, sans le lien.

Revision ID: 0070
Revises: 0068
Create Date: 2026-10-15
"""

from alembic import op

revision = "0070"
# ponytail: 0069 est réservé à une migration du lot 1 ; rebaser ce
# `down_revision` au merge si elle existe (sinon deux têtes).
down_revision = "0068"
branch_labels = None
depends_on = None

_NAME = "harvest_records_collection_id_fkey"


def _recreate(ondelete: str | None) -> None:
    op.drop_constraint(_NAME, "harvest_records", type_="foreignkey")
    op.create_foreign_key(
        _NAME,
        "harvest_records",
        "collections",
        ["collection_id"],
        ["id"],
        ondelete=ondelete,
        postgresql_not_valid=True,  # AUD-189 : validation à part, sans bloquer les écritures
    )
    op.execute(f'ALTER TABLE harvest_records VALIDATE CONSTRAINT "{_NAME}"')


def upgrade() -> None:
    _recreate("SET NULL")


def downgrade() -> None:
    _recreate(None)
