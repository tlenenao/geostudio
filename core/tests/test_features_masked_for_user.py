# SPDX-License-Identifier: Apache-2.0
"""get_masked_for_user (GAP-22) — appel direct, sans FastAPI.

`env` (test_features_routes_read.py) ne fournit qu'une paire (app, client) et
n'expose aucune Session SQLite réelle aux tests — la seule utilisée dans ce
fichier vit et meurt à l'intérieur de la fixture. On reprend donc ici le
patron autonome de test_roles_guards.py (engine SQLite en mémoire +
make_session_factory), qui n'a pas cette limite."""

from app.db import init_db, make_engine, make_session_factory
from app.features.routes import get_masked_for_user
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_get_masked_for_user_true_for_anonymous():
    assert get_masked_for_user(user=None, session=None) is True


def test_get_masked_for_user_reflects_privilege():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.flush()

        # admin porte data.view_sensitive (rôle admin, Tâche 1) -> non masqué
        assert get_masked_for_user(user=admin, session=s) is False
        # regular (rôle par défaut "creator", ne porte pas data.view_sensitive) -> masqué
        assert get_masked_for_user(user=regular, session=s) is True
