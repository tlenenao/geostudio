# SPDX-License-Identifier: Apache-2.0
"""P09.04 : le garde If-Match doit tenir face à deux PUT concurrents. Les deux
écrivains ont déjà chargé la Config (la route lit `get_config` avant
`update_config`) : le second, débloqué par le verrou de ligne, doit relire la
version committée par le premier, pas celle de son identity map. Postgres réel
(SQLite ignore FOR UPDATE)."""

import os
import threading
import uuid

import pytest
from sqlalchemy import select

from app.configs import repository as repo
from app.configs.models import Config
from app.configs.schemas import BuilderConfig
from app.db import make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant

pytestmark = pytest.mark.postgis

_MAP = BuilderConfig.model_validate(
    {"kind": "map", "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}}}
)


def test_second_concurrent_writer_sees_version_committed_by_first():
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CORE_TEST_DATABASE_URL requis")
    Session = make_session_factory(make_engine(url))
    from app.items.models import Item

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item = Item(
            id=uuid.uuid4().hex,
            tenant_id=tenant.id,
            resource_type="map",
            title="race",
            owner_id=_owner(s, tenant.id),
        )
        s.add(item)
        s.flush()
        created = repo.create_config(s, _MAP, item.id, tenant_id=tenant.id)
        s.commit()
        config_id, tenant_id = created.id, tenant.id

    first_has_lock = threading.Event()
    second_has_loaded = threading.Event()
    results: dict[str, object] = {}

    def first():
        with Session() as s:
            s.scalars(select(Config).where(Config.id == config_id)).one()
            repo.update_config(s, config_id, _MAP, tenant_id=tenant_id, expected_version=1)
            first_has_lock.set()
            second_has_loaded.wait(5)
            s.commit()
            results["first"] = "ok"

    def second():
        with Session() as s:
            first_has_lock.wait(5)
            s.get(Config, config_id)  # comme la route : get_config avant update
            second_has_loaded.set()
            try:
                repo.update_config(s, config_id, _MAP, tenant_id=tenant_id, expected_version=1)
                s.commit()
                results["second"] = "written"
            except repo.StaleConfigVersion:
                results["second"] = "stale"

    t1, t2 = threading.Thread(target=first), threading.Thread(target=second)
    t1.start()
    t2.start()
    t1.join(15)
    t2.join(15)
    assert results == {"first": "ok", "second": "stale"}


def _owner(s, tenant_id):
    from app.users.repository import get_or_create_user

    return get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=f"race-{uuid.uuid4().hex}",
        username="race",
        email=None,
        first_name="",
        last_name="",
    ).id
