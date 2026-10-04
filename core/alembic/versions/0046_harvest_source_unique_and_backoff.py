# SPDX-License-Identifier: Apache-2.0
"""Unicité (tenant_id, type, url) des sources de moissonnage + compteur d'échecs (REV-276c/d)

Les URL stockées ne sont PAS réécrites (normalisation) : le slash final est
porteur de sens pour la résolution urljoin des liens STAC et les external_id
déjà moissonnés en dépendent. La normalisation (slash final, casse de l'hôte)
est faite à la comparaison applicative (app.harvest.repository.
find_duplicate_source). Seuls les doublons EXACTS bloquent cet index : la
migration échoue alors proprement en les listant (transactionnelle, la base
reste en 0045) ; supprimer ou corriger les sources listées, puis relancer.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_INDEX = "uq_harvest_sources_tenant_type_url"


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT tenant_id, type, url, string_agg(id, ',' ORDER BY id) "
                "FROM harvest_sources GROUP BY tenant_id, type, url HAVING count(*) > 1"
            )
        )
        .all()
    )
    if duplicates:
        listing = "; ".join(f"{t}/{ty} {u}: {ids}" for t, ty, u, ids in duplicates)
        raise RuntimeError(
            "0046 : sources de moissonnage en double (tenant/type url : ids) — "
            f"supprimer les doublons puis relancer : {listing}"
        )
    op.create_index(_INDEX, "harvest_sources", ["tenant_id", "type", "url"], unique=True)
    op.add_column(
        "harvest_sources",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("harvest_sources", "consecutive_failures")
    op.drop_index(_INDEX, table_name="harvest_sources")
