# SPDX-License-Identifier: Apache-2.0
"""Index d'embedding : ivfflat -> HNSW (REV-348)

0012 créait un index ivfflat (lists = 100) sur des tables généralement vides :
centroïdes dégénérés, rappel médiocre, aucun REINDEX prévu. HNSW ne demande
aucun entraînement et se construit correctement à tout volume. Mêmes noms
d'index (le comparateur modèle/Alembic les filtre nommément).

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-15
"""

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

_INDEXES = [("ix_items_embedding", "items"), ("ix_collections_embedding", "collections")]


def _rebuild(using: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name, table in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
        with_clause = " WITH (lists = 100)" if using == "ivfflat" else ""
        op.execute(
            f"CREATE INDEX {name} ON {table} USING {using} "
            f"(embedding vector_cosine_ops){with_clause}"
        )


def upgrade() -> None:
    _rebuild("hnsw")


def downgrade() -> None:
    _rebuild("ivfflat")
