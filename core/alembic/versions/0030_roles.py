# SPDX-License-Identifier: Apache-2.0
"""Table roles + users.role_id — remplace is_analyst comme source de vérité
du rôle (docs/superpowers/specs/2026-09-01-roles-privileges-design.md).

Chaque tenant existant reçoit sa propre copie des 4 rôles prédéfinis
(is_built_in=true, immuables en application — app/roles/routes.py).
users.is_admin RESTE une colonne synchronisée (pas supprimée) : ~20 lectures
existantes dans core/ la consomment comme signal, préservées à l'identique.
users.is_analyst, lui, disparaît (un seul consommateur, SQL Lab, remplacé
par require_privilege() — voir la tâche 11 du plan d'implémentation).

Testée dans les deux sens sur base non vide (piège n°8 de CLAUDE.md) —
tests/test_roles_migration.py appelle seed_built_in_roles/
migrate_users_to_roles/migrate_roles_to_booleans directement, hors
upgrade()/downgrade() (qui utilisent l'API `op`, non testable hors contexte
Alembic réel — même limite que 0028_collection_spatial_index.py).

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-02
"""

import json
import sys
import uuid
from pathlib import Path

# Cf. commentaire identique dans 0028_collection_spatial_index.py : nécessaire
# pour que `alembic heads`/`history` (qui chargent les fichiers de
# versions/ directement, sans exécuter env.py) trouvent `app.roles.privileges`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op
from app.roles.privileges import BUILT_IN_ROLE_NAMES, BUILT_IN_ROLE_PRIVILEGES

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def seed_built_in_roles(conn) -> None:
    tenant_ids = [row[0] for row in conn.execute(text("SELECT id FROM tenants")).all()]
    for tenant_id in tenant_ids:
        existing_slugs = {
            row[0]
            for row in conn.execute(
                text("SELECT slug FROM roles WHERE tenant_id = :tenant_id AND is_built_in = true"),
                {"tenant_id": tenant_id},
            ).all()
        }
        for slug, privileges in BUILT_IN_ROLE_PRIVILEGES.items():
            if slug in existing_slugs:
                continue
            conn.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) VALUES "
                    "(:id, :tenant_id, :name, :slug, :is_built_in, :privileges, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid.uuid4().hex,
                    "tenant_id": tenant_id,
                    "name": BUILT_IN_ROLE_NAMES[slug],
                    "slug": slug,
                    "is_built_in": True,
                    "privileges": json.dumps(privileges),
                },
            )


def migrate_users_to_roles(conn) -> None:
    role_id_by_tenant_and_slug: dict[tuple[str, str], str] = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            text("SELECT tenant_id, slug, id FROM roles WHERE is_built_in = true")
        ).all()
    }
    users = conn.execute(text("SELECT id, tenant_id, is_admin, is_analyst FROM users")).all()
    for user_id, tenant_id, is_admin, is_analyst in users:
        if is_admin:
            slug = "admin"
        elif is_analyst:
            slug = "analyst"
        else:
            slug = "creator"
        role_id = role_id_by_tenant_and_slug[(tenant_id, slug)]
        conn.execute(
            text("UPDATE users SET role_id = :role_id WHERE id = :user_id"),
            {"role_id": role_id, "user_id": user_id},
        )


def migrate_roles_to_booleans(conn) -> None:
    """Inverse de migrate_users_to_roles, pour downgrade() — limite acceptée
    (design §2) : un rôle sur mesure créé après l'upgrade n'a pas d'équivalent
    booléen, ses porteurs redeviennent is_admin=False/is_analyst=False."""
    role_slug_by_id: dict[str, str] = {
        row[0]: row[1] for row in conn.execute(text("SELECT id, slug FROM roles")).all()
    }
    users = conn.execute(text("SELECT id, role_id FROM users")).all()
    for user_id, role_id in users:
        slug = role_slug_by_id.get(role_id, "")
        conn.execute(
            text(
                "UPDATE users SET is_admin = :is_admin, is_analyst = :is_analyst "
                "WHERE id = :user_id"
            ),
            {"is_admin": slug == "admin", "is_analyst": slug == "analyst", "user_id": user_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    op.create_table(
        "roles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("privileges", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_slug"),
    )
    seed_built_in_roles(conn)
    op.add_column(
        "users", sa.Column("role_id", sa.String(), sa.ForeignKey("roles.id"), nullable=True)
    )
    migrate_users_to_roles(conn)
    op.alter_column("users", "role_id", nullable=False)
    op.drop_column("users", "is_analyst")


def downgrade() -> None:
    conn = op.get_bind()
    op.add_column(
        "users", sa.Column("is_analyst", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    migrate_roles_to_booleans(conn)
    op.drop_column("users", "role_id")
    op.drop_table("roles")
