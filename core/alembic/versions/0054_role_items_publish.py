# SPDX-License-Identifier: Apache-2.0
"""Privilège `items.publish` (ARC-07 / REV-335) : ajouté, par donnée, aux rôles
prédéfinis Administrateur et Créateur de chaque tenant (le Lecteur et l'Analyste
n'en bénéficient pas). La définition immuable des rôles vit dans
BUILT_IN_ROLE_PRIVILEGES (resynchronisée à chaque requête) ; cette migration
évite seulement la fenêtre avant la première requête d'un tenant. Les rôles sur
mesure ne sont PAS modifiés : un administrateur leur attribue `items.publish`
à la carte. Une ligne audit_log « role.privilege_added » par rôle touché.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-11
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

_PRIVILEGE = "items.publish"
_SLUGS = ("admin", "creator")


def _rewrite(add: bool) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, tenant_id, privileges FROM roles WHERE is_built_in AND slug IN :s"
        ).bindparams(sa.bindparam("s", expanding=True)),
        {"s": list(_SLUGS)},
    ).all()
    for role_id, tenant_id, raw in rows:
        privs = list(raw if isinstance(raw, list) else json.loads(raw))
        if (_PRIVILEGE in privs) == add:
            continue
        privs = [*privs, _PRIVILEGE] if add else [p for p in privs if p != _PRIVILEGE]
        conn.execute(
            sa.text("UPDATE roles SET privileges = CAST(:p AS json) WHERE id = :id"),
            {"p": json.dumps(privs), "id": role_id},
        )
        if add:
            conn.execute(
                sa.text(
                    "INSERT INTO audit_log (tenant_id, actor_id, actor_kind, action, "
                    "object_type, object_id, payload, created_at) VALUES (:t, NULL, 'system', "
                    "'role.privilege_added', 'role', :id, CAST(:pl AS json), now())"
                ),
                {"t": tenant_id, "id": role_id, "pl": json.dumps({"privilege": _PRIVILEGE})},
            )


def upgrade() -> None:
    _rewrite(add=True)


def downgrade() -> None:
    _rewrite(add=False)
