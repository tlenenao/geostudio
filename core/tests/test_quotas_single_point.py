# SPDX-License-Identifier: Apache-2.0
"""P26 (RC-12) : le quota d'items/collections est contrôlé au point UNIQUE de
création (items.create_item / collections.create_collection), donc aussi par
les jobs (import, pipelines, moissonnage, tileset3d/terrain3d), et sérialisé
par tenant sous concurrence."""

import threading
import uuid

import pytest

from app.collections import repository as collections_repo
from app.db import Base, init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.quotas import service as quotas_service
from app.quotas.service import QuotaExceededError
from app.roles.repository import ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _collection(session, tenant_id, owner_id, name):
    return collections_repo.create_collection(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=name,
        title=name,
        description="",
        is_public=False,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )


def test_every_creation_path_hits_the_quota_at_limit(monkeypatch):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="a", email=None,
            first_name="", last_name="",
        )  # fmt: skip
        monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
        monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "1")
        monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")
        kw = {"tenant_id": tenant.id, "owner_id": user.id, "resource_type": "map"}
        items_repo.create_item(s, title="un", **kw)
        with pytest.raises(QuotaExceededError) as ei:
            items_repo.create_item(s, title="deux", **kw)  # import, pipeline, harvest, 3D...
        assert ei.value.status_code == 409 and (ei.value.current, ei.value.limit) == (1, 1)
        _collection(s, tenant.id, user.id, "c1")
        with pytest.raises(QuotaExceededError):
            _collection(s, tenant.id, user.id, "c2")  # register, import, provisioning
        # capacité éteinte : plus aucune limite
        monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
        items_repo.create_item(s, title="trois", **kw)


@pytest.mark.parametrize("kind", ["items", "collections"])
def test_concurrent_creations_at_the_limit_admit_exactly_one(pg_engine, monkeypatch, kind):
    """Deux créations simultanées avec un seul emplacement libre : une seule
    passe (verrou consultatif). Le compte est ralenti après lecture pour que,
    sans verrou, les deux lisent 0 avant que l'une ne commite."""
    Base.metadata.create_all(pg_engine)
    factory = make_session_factory(pg_engine)
    tid = f"qt-{uuid.uuid4().hex[:8]}"
    with factory() as s:
        s.add(Tenant(id=tid, slug=tid, name=tid))
        s.flush()
        ensure_built_in_roles(s, tenant_id=tid)
        user = get_or_create_user(
            s, tenant_id=tid, oidc_sub=tid, username=tid, email=None,
            first_name="", last_name="",
        )  # fmt: skip
        uid = user.id
        s.commit()
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "1")
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")
    attr = "count_items_for_tenant" if kind == "items" else "count_collections_for_tenant"
    real = getattr(quotas_service, attr)

    def slow_count(session, tenant_id):
        n = real(session, tenant_id)
        threading.Event().wait(0.4)  # élargit la fenêtre TOCTOU
        return n

    monkeypatch.setattr(quotas_service, attr, slow_count)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker(i):
        with factory() as s:
            barrier.wait()
            try:
                if kind == "items":
                    items_repo.create_item(
                        s, tenant_id=tid, owner_id=uid, resource_type="map", title=f"t{i}"
                    )
                else:
                    _collection(s, tid, uid, f"{tid}_{i}")
                s.commit()
                results.append("ok")
            except QuotaExceededError:
                s.rollback()
                results.append("refused")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results) == ["ok", "refused"]
