# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import init_db, make_engine, make_session_factory
from app.harvest.models import HarvestRecord, HarvestSource
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_harvest_tables_are_created_by_init_db():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    table_names = set(inspect(engine).get_table_names())
    assert {"harvest_sources", "harvest_records"} <= table_names
    engine.dispose()


def test_harvest_source_and_record_round_trip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        source = HarvestSource(
            id="src-1", tenant_id=tenant.id, owner_id=user.id, type="stac",
            url="https://example.com/stac", mode="reference", enabled=True,
            interval_minutes=60,
        )
        s.add(source)
        s.flush()
        record = HarvestRecord(
            id="rec-1", tenant_id=tenant.id, source_id=source.id,
            external_id="ext-1", item_id=None, collection_id=None,
        )
        s.add(record)
        s.commit()

        fetched = s.get(HarvestSource, "src-1")
        assert fetched.url == "https://example.com/stac"
        assert fetched.last_status is None
        fetched_record = s.get(HarvestRecord, "rec-1")
        assert fetched_record.source_id == "src-1"
        assert fetched_record.is_stale is False
    engine.dispose()
