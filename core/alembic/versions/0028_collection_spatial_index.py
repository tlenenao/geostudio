# SPDX-License-Identifier: Apache-2.0
"""Index GiST de rattrapage sur les collections déjà enregistrées (SP-24 §3.2).

Aucun index spatial n'existait dans le dépôt : apply_collection_ddl le crée
désormais à l'enregistrement (Task 4), cette migration comble le passé.
Les deux sens sont testés sur base non vide — le downgrade de la 0024
(SP-17b) échouait sur des lignes existantes faute de ce test.

CREATE INDEX plain (pas CONCURRENTLY) : décision assumée avec le porteur du
projet — le verrou d'écriture est un coût connu et accepté (dépôt à une
seule release publiée, v0.1.0, pas de déploiement en production connu),
CONCURRENTLY forcerait un autocommit hors la transaction Alembic et laisse
un index INVALID à nettoyer à la main en cas d'échec.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-22
"""

import sys
from pathlib import Path

# Première migration à importer du code applicatif (`app.collections.ddl`,
# pour partager spatial_index_name plutôt qu'en redéfinir une seconde
# convention). alembic/env.py insère déjà `core/` dans sys.path avant
# d'exécuter les migrations (upgrade/downgrade en passent toujours par là),
# mais `alembic heads`/`history`/`current` chargent les fichiers de
# versions/ directement, sans jamais exécuter env.py — sans cette ligne,
# `alembic heads` seul échouerait en ModuleNotFoundError. Un appel nu
# (comme dans env.py, jamais un `if`/une affectation) : ruff (règle E402)
# traite spécifiquement `sys.path.insert`/`.append` comme autorisé avant
# des imports de module, mesuré — toute autre forme (variable
# intermédiaire, garde conditionnelle) redevient un E402 sur les imports
# suivants. Doublon inoffensif si env.py a déjà tourné.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text

from alembic import op
from app.collections.ddl import spatial_index_name

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def _registered_geometry_tables(conn) -> list[tuple[str, str]]:
    """(table, colonne de géométrie) pour chaque collection du registre qui a
    réellement une géométrie. Cross-tenant par construction : une migration
    n'a pas d'utilisateur courant.

    GROUP BY table_name, f_geometry_column déduplique le cas
    multi-tenants-une-table. Il ne protège PAS le cas d'une table à deux
    colonnes de géométrie (spatial_index_name ne dépend que du nom de
    table : la seconde ligne produirait un no-op silencieux). Laissé tel
    quel, à l'identique de apply_collection_ddl (Task 4, qui prend la
    première ligne via .scalar()) : introspect_table lève
    UnsupportedTable("multiple geometry columns are not supported") avant
    qu'une collection à deux géométries puisse même être enregistrée — ce
    cas est donc inatteignable aujourd'hui avec les deux fonctions
    partageant la même limite. Documenté ici plutôt que gardé, pour ne pas
    introduire une divergence de comportement avec Task 4 sans le dire.
    """
    return [
        (row[0], row[1])
        for row in conn.execute(
            text(
                "SELECT c.table_name, g.f_geometry_column FROM collections c "
                "JOIN geometry_columns g ON g.f_table_name = c.table_name "
                "WHERE g.f_table_schema = 'public' "
                "GROUP BY c.table_name, g.f_geometry_column"
            )
        ).all()
    ]


def backfill(conn) -> None:
    preparer = conn.dialect.identifier_preparer
    for table, geom in _registered_geometry_tables(conn):
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {preparer.quote(spatial_index_name(table))} "
                f"ON public.{preparer.quote(table)} USING GIST ({preparer.quote(geom)})"
            )
        )


def drop_backfilled(conn) -> None:
    preparer = conn.dialect.identifier_preparer
    for table, _ in _registered_geometry_tables(conn):
        conn.execute(
            text(f"DROP INDEX IF EXISTS public.{preparer.quote(spatial_index_name(table))}")
        )


def upgrade() -> None:
    backfill(op.get_bind())


def downgrade() -> None:
    drop_backfilled(op.get_bind())
