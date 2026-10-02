# SPDX-License-Identifier: Apache-2.0
"""P09.04 : le verrou de ligne de update_config sérialise réellement deux écrivains
concurrents (SQLite ignore FOR UPDATE — il faut Postgres)."""

import threading
import time

import pytest

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import Base, make_session_factory
from app.items.repository import create_item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

_MAP = BuilderConfig(
    kind="map",
    map={
        "basemap": {"style": "https://x.test/s.json"},
        "view": {"center": [0.0, 0.0], "zoom": 2.0},
    },
)


def test_repository_refuses_an_oversized_config_for_every_writer(monkeypatch):
    # P09.07 : le plafond ne doit pas dépendre du middleware HTTP (MCP, pipelines).
    monkeypatch.setattr(configs_repo, "MAX_CONFIG_BYTES", 100)
    with pytest.raises(ValueError, match="too large"):
        configs_repo.create_config(None, _MAP, None, tenant_id="t")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="too large"):
        configs_repo.update_config(None, "x", _MAP, tenant_id="t")  # type: ignore[arg-type]


def test_second_writer_blocks_on_the_row_lock_then_sees_the_new_version(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="lock-owner",
            username="lock-owner",
            email=None,
            first_name="",
            last_name="",
        )
        item = create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="map", title="Lock"
        )
        config_id = configs_repo.create_config(s, _MAP, item.id, tenant_id=tenant.id).id
        s.commit()

    result: dict = {}

    def second_writer() -> None:
        with Session() as s2:
            try:
                configs_repo.update_config(
                    s2, config_id, _MAP, tenant_id=tenant.id, expected_version=1
                )
                result["outcome"] = "written"
            except configs_repo.StaleConfigVersion as exc:
                result["outcome"] = ("stale", exc.current)
            result["done_at"] = time.monotonic()

    with Session() as s1:
        configs_repo.update_config(s1, config_id, _MAP, tenant_id=tenant.id, expected_version=1)
        thread = threading.Thread(target=second_writer)
        thread.start()
        time.sleep(1.0)
        # Le second écrivain est bloqué tant que le premier n'a pas commité.
        assert "outcome" not in result
        committed_at = time.monotonic()
        s1.commit()
    thread.join(timeout=10)
    assert result["outcome"] == ("stale", 2)
    assert result["done_at"] >= committed_at
