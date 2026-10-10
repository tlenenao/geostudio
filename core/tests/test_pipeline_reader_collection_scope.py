# SPDX-License-Identifier: Apache-2.0
"""REV-296 / décision D3 : `reader.collection` suit le partage explicite seulement
— `admin.collections.manage` n'ouvre PAS la lecture d'une collection depuis un
pipeline (contrairement aux lectures REST/MCP, REV-185)."""

import pytest

from app.collections import repository as collections_repo
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import runtime
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _user(session, tenant, sub):
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
    )


def test_collections_manage_privilege_does_not_open_reader_collection():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as session:
        tenant = get_or_create_default_tenant(session)
        owner = _user(session, tenant, "owner")
        manager = _user(session, tenant, "manager")
        role = create_role(
            session,
            tenant_id=tenant.id,
            name="Gestionnaire collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        manager.role_id = role.id
        collections_repo.create_collection(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="privee",
            title="Privée",
            description="",
            is_public=False,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        session.commit()

        # Le propriétaire lit ; le porteur du seul privilège de gestion, non.
        assert (
            runtime._require_readable_collection_id(
                session, tenant_id=tenant.id, user=owner, collection_id="privee"
            )
            == "privee"
        )
        with pytest.raises(runtime.PipelineRuntimeError, match="not found"):
            runtime._require_readable_collection_id(
                session, tenant_id=tenant.id, user=manager, collection_id="privee"
            )
