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

        # schéma servi par l'MCP (LLM, formulaire généré) : même verdict
        from types import SimpleNamespace

        from app.collections.introspection import ColumnInfo, TableInfo
        from app.mcp.tools.identity import visible_table_info

        info = TableInfo(
            table_name="t",
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
            columns=[ColumnInfo("nom", "string", True), ColumnInfo("salary", "integer", False)],
        )
        col = SimpleNamespace(sensitive_fields=["salary"])
        assert [c.name for c in visible_table_info(s, admin, col, info).columns] == [
            "nom",
            "salary",
        ]
        assert [c.name for c in visible_table_info(s, regular, col, info).columns] == ["nom"]


def test_owner_of_a_collection_is_masked_without_view_sensitive_rev270_p15_05():
    """Décision produit REV-270/P15.05 (Tanguy, 2026-10-10) : PAS d'exception
    propriétaire — le propriétaire (et l'éditeur) d'une collection ne lit pas
    ses champs sensibles sans data.view_sensitive. Le verdict de masquage ne
    dépend que du privilège de l'utilisateur, jamais de la collection ; ce test
    échoue si une exception propriétaire est un jour introduite."""
    from app.collections import repository as collections_repo

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="rh",
            title="RH",
            description="",
            is_public=False,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.flush()
        assert get_masked_for_user(user=owner, session=s) is True
