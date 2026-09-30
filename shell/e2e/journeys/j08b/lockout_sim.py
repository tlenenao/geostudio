"""Simulation anti-lockout dans un tenant jetable (jamais le tenant default).

Lancé par les specs j08b via `docker exec -i geostudio-core-1 python - <tag>`.
Affiche un objet JSON : résultats des gardes anti-lockout du cœur (services réels).
"""
import json
import os
import sys
import uuid

from sqlalchemy import select

from app.compliance.service import (
    AnonymizationLockoutError,
    anonymize_user,
)
from app.db import make_engine, make_session_factory
from app.roles.repository import count_users_with_privileges, ensure_built_in_roles
from app.tenants.models import Tenant
from app.users.models import User
from app.users.repository import set_user_role

tag = sys.argv[1]
sf = make_session_factory(make_engine(os.environ["DATABASE_URL"]))
out: dict = {}
with sf() as s:
    tid = uuid.uuid4().hex
    s.add(Tenant(id=tid, slug=tag, name=tag))
    s.flush()
    roles = ensure_built_in_roles(s, tenant_id=tid)
    admin = roles["admin"]
    reader = roles["reader"]

    def mk(name: str, role) -> str:
        u = User(
            id=uuid.uuid4().hex,
            tenant_id=tid,
            oidc_sub=f"{tag}-{name}",
            username=f"{tag}-{name}",
            role_id=role.id,
            is_admin=role.slug == "admin",
        )
        s.add(u)
        s.flush()
        return u.id

    a1, a2 = mk("a1", admin), mk("a2", admin)
    out["holders_before"] = count_users_with_privileges(
        s, tenant_id=tid, privileges=["admin.users.manage"]
    )
    anonymize_user(s, tenant_id=tid, user_id=a2, actor_id=a1)
    out["erase_a2_ok"] = True
    out["holders_after_erasing_a2"] = count_users_with_privileges(
        s, tenant_id=tid, privileges=["admin.users.manage"]
    )
    out["active_admins_after_erasing_a2"] = len(
        s.scalars(
            select(User).where(
                User.tenant_id == tid, User.role_id == admin.id, User.erased_at.is_(None)
            )
        ).all()
    )
    try:
        anonymize_user(s, tenant_id=tid, user_id=a1, actor_id=a1)
        out["erase_last_active_admin"] = "accepted"
    except AnonymizationLockoutError:
        out["erase_last_active_admin"] = "refused"
    out["active_admins_final"] = len(
        s.scalars(
            select(User).where(
                User.tenant_id == tid, User.role_id == admin.id, User.erased_at.is_(None)
            )
        ).all()
    )
    s.commit()
print(json.dumps(out))
