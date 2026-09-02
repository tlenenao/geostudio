# SPDX-License-Identifier: Apache-2.0
import importlib.util
import pathlib

from sqlalchemy import text

from app.db import Base, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _import_0030():
    """alembic/versions n'est pas un paquet importable par son nom :
    chargement direct par chemin de fichier (patron identique à
    tests/test_collections_spatial_index.py::_import_0028)."""
    path = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "0030_roles.py"
    spec = importlib.util.spec_from_file_location("mig_0030", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_migrate_and_revert_on_a_non_empty_database(pg_engine):
    Base.metadata.create_all(pg_engine)  # forme actuelle (post-migration) : roles + users.role_id
    Session_ = make_session_factory(pg_engine)
    mod = _import_0030()

    # Tâches 1-5 ont déjà fait évoluer app/users/models.py vers la forme
    # FINALE (post-migration) : role_id NOT NULL, is_analyst absent (jamais
    # gardée en colonne de transition — cf. commentaire de 0030_roles.py).
    # Mais Base.metadata.create_all() ne fait JAMAIS d'ALTER sur une table
    # déjà présente : ce conteneur Postgres de test étant persistant
    # (réutilisé de session en session), la table `users` peut déjà exister
    # sous une forme antérieure aux Tâches 1-5 — vérifié empiriquement ici :
    # `role_id` absent, `is_analyst` déjà présent. On ramène la table à
    # l'état "avant migration" attendu par ce test de façon robuste aux deux
    # cas (conteneur neuf où create_all() a produit la forme finale, ou
    # conteneur persistant resté sur l'ancienne forme) plutôt que de
    # supposer l'un ou l'autre — piège n°3 (CLAUDE.md), le texte du plan
    # supposait à tort que create_all() donnerait toujours la forme
    # intermédiaire visée par ce test.
    with pg_engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id VARCHAR REFERENCES roles(id)")
        )
        conn.execute(text("ALTER TABLE users ALTER COLUMN role_id DROP NOT NULL"))
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_analyst "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )
        # ADD COLUMN IF NOT EXISTS est un no-op complet quand la colonne
        # préexiste déjà (cas observé ici) : elle n'a alors PAS de DEFAULT
        # (NOT NULL sans défaut), ce qui casse tout INSERT ORM ultérieur qui
        # ne connaît pas cette colonne (get_or_create_user ci-dessous).
        # SET DEFAULT est idempotent dans les deux cas.
        conn.execute(text("ALTER TABLE users ALTER COLUMN is_analyst SET DEFAULT false"))

    with Session_() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mig-a",
            username="mig-a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        analyst = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mig-b",
            username="mig-b",
            email=None,
            first_name="",
            last_name="",
            bootstrap_analyst=True,
        )
        plain = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mig-c",
            username="mig-c",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        admin_id, analyst_id, plain_id, tenant_id = admin.id, analyst.id, plain.id, tenant.id

    try:
        with pg_engine.begin() as conn:
            # Repart d'un état "à l'ancienne" : rôles absents, role_id nul,
            # is_admin/is_analyst posés directement (comme juste après
            # op.add_column("users", "role_id", nullable=True), avant tout
            # backfill).
            # Ordre inversé par rapport au texte du plan (piège n°3) : role_id
            # porte une FK vers roles.id (users_role_id_fkey), donc NULLer
            # role_id doit précéder la suppression des rôles, pas la suivre —
            # sinon ForeignKeyViolation puisque les 3 utilisateurs créés
            # ci-dessus référencent déjà de vrais rôles via get_or_create_user.
            conn.execute(
                text("UPDATE users SET role_id = NULL WHERE tenant_id = :t"), {"t": tenant_id}
            )
            conn.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": tenant_id})
            conn.execute(
                text("UPDATE users SET is_admin = true, is_analyst = false WHERE id = :id"),
                {"id": admin_id},
            )
            conn.execute(
                text("UPDATE users SET is_admin = false, is_analyst = true WHERE id = :id"),
                {"id": analyst_id},
            )
            conn.execute(
                text("UPDATE users SET is_admin = false, is_analyst = false WHERE id = :id"),
                {"id": plain_id},
            )

            mod.seed_built_in_roles(conn)
            role_ids = {
                row[0]: row[1]
                for row in conn.execute(
                    text("SELECT slug, id FROM roles WHERE tenant_id = :t"), {"t": tenant_id}
                ).all()
            }
            assert set(role_ids) == {"admin", "creator", "analyst", "reader"}

            mod.migrate_users_to_roles(conn)
            assigned = dict(
                conn.execute(
                    text("SELECT id, role_id FROM users WHERE tenant_id = :t"), {"t": tenant_id}
                ).all()
            )
            assert assigned[admin_id] == role_ids["admin"]
            assert assigned[analyst_id] == role_ids["analyst"]
            assert assigned[plain_id] == role_ids["creator"]

            # Downgrade : efface is_admin/is_analyst, les redérive de role_id.
            conn.execute(
                text("UPDATE users SET is_admin = false, is_analyst = false WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            mod.migrate_roles_to_booleans(conn)
            reverted = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    text("SELECT id, is_admin, is_analyst FROM users WHERE tenant_id = :t"),
                    {"t": tenant_id},
                ).all()
            }
            assert reverted[admin_id] == (True, False)
            assert reverted[analyst_id] == (False, True)
            assert reverted[plain_id] == (False, False)
    finally:
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM users WHERE id IN (:a, :b, :c)"),
                {"a": admin_id, "b": analyst_id, "c": plain_id},
            )
            conn.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": tenant_id})
            # Ne pas retirer role_id/is_analyst : les deux colonnes restent
            # cohérentes avec la forme finale visée par app/users/models.py
            # (role_id) ou préexistaient déjà (is_analyst) — les laisser en
            # place ne casse aucun autre test partageant ce même pg_engine
            # de portée session (SQLAlchemy ignore une colonne DB non
            # mappée ; Base.metadata.create_all() n'est de toute façon
            # jamais destructif sur une table déjà présente).
