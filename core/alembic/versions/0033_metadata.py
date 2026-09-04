# SPDX-License-Identifier: Apache-2.0
"""Métadonnées ouvertes sur Collection (licence, producteur, contact,
fréquence, généalogie, langue, version, emprise temporelle) et sur Item
(licence, langue) — chantier 4.9,
docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("license", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("license_uri", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("producer", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("contact", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections",
        sa.Column("update_frequency", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "collections", sa.Column("lineage", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("language", sa.String(), nullable=False, server_default="fr")
    )
    op.add_column(
        "collections", sa.Column("version", sa.String(), nullable=False, server_default="")
    )
    op.add_column("collections", sa.Column("temporal_start", sa.Date(), nullable=True))
    op.add_column("collections", sa.Column("temporal_end", sa.Date(), nullable=True))
    op.add_column("items", sa.Column("license", sa.String(), nullable=False, server_default=""))
    op.add_column("items", sa.Column("language", sa.String(), nullable=False, server_default="fr"))


def downgrade() -> None:
    op.drop_column("items", "language")
    op.drop_column("items", "license")
    op.drop_column("collections", "temporal_end")
    op.drop_column("collections", "temporal_start")
    op.drop_column("collections", "version")
    op.drop_column("collections", "language")
    op.drop_column("collections", "lineage")
    op.drop_column("collections", "update_frequency")
    op.drop_column("collections", "contact")
    op.drop_column("collections", "producer")
    op.drop_column("collections", "license_uri")
    op.drop_column("collections", "license")
