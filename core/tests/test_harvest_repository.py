# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as repo
from app.harvest.models import HarvestSource
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE harvest_records, harvest_sources, items, users, tenants CASCADE")
        )


@pytest.fixture()
def tenant(tenant_and_user):
    t, _ = tenant_and_user
    return t


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


def test_create_get_list_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://stac.example.com/collections",
        mode="reference",
        enabled=True,
        interval_minutes=60,
    )
    fetched = repo.get_source(session, tenant_id=tenant.id, source_id=source.id)
    assert fetched.url == "https://stac.example.com/collections"
    assert [s.id for s in repo.list_sources(session, tenant_id=tenant.id)] == [source.id]


def test_get_source_cross_tenant_returns_none(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    assert repo.get_source(session, tenant_id="other-tenant", source_id=source.id) is None


def test_update_source_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    repo.update_source(session, source, url="https://b", enabled=False)
    assert source.url == "https://b"
    assert source.enabled is False


def test_delete_source_cascades_to_records(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="ext-1",
        item_id=None,
        collection_id=None,
        content_hash="h",
    )
    session.flush()
    repo.delete_source(session, source)
    session.flush()
    assert repo.get_source(session, tenant_id=tenant.id, source_id=source.id) is None
    from app.harvest.models import HarvestRecord

    assert session.query(HarvestRecord).count() == 0


def test_mark_running_sets_status(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    repo.mark_running(session, tenant_id=tenant.id, source_id=source.id)
    assert source.last_status == "running"


def test_mark_missing_as_stale_flags_unseen_records_only(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    seen = repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="keep",
        item_id=None,
        collection_id=None,
        content_hash="h1",
    )
    gone = repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="gone",
        item_id=None,
        collection_id=None,
        content_hash="h2",
    )
    session.flush()
    repo.mark_missing_as_stale(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        seen_external_ids={"keep"},
    )
    assert seen.is_stale is False
    assert gone.is_stale is True


def test_list_due_sources_includes_never_run_and_overdue_enabled_sources(session, tenant_and_user):
    tenant, user = tenant_and_user

    def make(url, *, enabled=True, interval_minutes=30, last_run_at=None):
        s = repo.create_source(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            type="stac",
            url=url,
            mode="reference",
            enabled=enabled,
            interval_minutes=interval_minutes,
        )
        s.last_run_at = last_run_at
        return s

    never_run = make("https://a")
    overdue = make("https://b", last_run_at=datetime.now(UTC) - timedelta(hours=1))
    fresh = make("https://c", last_run_at=datetime.now(UTC))
    make("https://d", enabled=False, last_run_at=None)
    make("https://e", interval_minutes=None, last_run_at=None)
    session.commit()

    # Force a cold fetch: expire the identity map so `last_run_at` is
    # re-deserialized from the DB (tz-naive column) instead of returning the
    # same tz-aware in-memory object we just assigned above. This is the
    # path a real scheduler (fresh session per job) always takes, and it is
    # the path that reproduced the tz-naive/tz-aware TypeError.
    session.expire_all()

    due_ids = {s.id for s in repo.list_due_sources(session)}
    assert due_ids == {never_run.id, overdue.id}
    assert fresh.id not in due_ids


def _make_source(session, tenant_id, owner_id, **overrides):
    src = repo.create_source(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=15,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    session.flush()
    return src


def test_list_due_excludes_recently_running_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    _make_source(
        session,
        tenant.id,
        user.id,
        last_status="running",
        updated_at=now - timedelta(minutes=1),
    )
    assert repo.list_due_sources(session) == []


def test_list_due_reclaims_stuck_running_source(session, tenant_and_user):
    from app.harvest.repository import _RUNNING_RECLAIM_MINUTES

    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(
        session,
        tenant.id,
        user.id,
        last_status="running",
        updated_at=now - timedelta(minutes=_RUNNING_RECLAIM_MINUTES + 5),
    )
    due = repo.list_due_sources(session)
    assert [s.id for s in due] == [src.id]


def test_list_due_still_returns_a_due_idle_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(
        session,
        tenant.id,
        user.id,
        last_status="ok",
        last_run_at=now - timedelta(minutes=30),
    )
    due = repo.list_due_sources(session)
    assert src.id in [s.id for s in due]


@pytest.mark.postgis
def test_unique_constraint_rejects_duplicate_external_id_for_same_source(
    pg_session, pg_tenant_and_user
):
    tenant, user = pg_tenant_and_user
    source = repo.create_source(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    pg_session.commit()
    repo.create_record(
        pg_session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="dup",
        item_id=None,
        collection_id=None,
        content_hash="h",
    )
    pg_session.commit()
    with pytest.raises(IntegrityError):
        repo.create_record(
            pg_session,
            tenant_id=tenant.id,
            source_id=source.id,
            external_id="dup",
            item_id=None,
            collection_id=None,
            content_hash="h2",
        )
        pg_session.commit()
    pg_session.rollback()


def test_get_feature_layer_record_returns_feature_kind_only(session, tenant_and_user):
    from app.items import repository as items_repo

    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="arcgis",
        url="https://gis.example.com/FeatureServer",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    feature_item = items_repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="external",
        title="Feature Layer",
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="a",
        item_id=feature_item.id,
        collection_id=None,
        content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0",
        layer_kind="feature",
    )
    raster_item = items_repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="external",
        title="Raster Layer",
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="b",
        item_id=raster_item.id,
        collection_id=None,
        content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x",
        layer_kind="raster",
    )
    found = repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id=feature_item.id)
    assert found is not None
    assert found.external_url == "https://gis.example.com/FeatureServer/0"
    assert (
        repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id=raster_item.id) is None
    )
    assert (
        repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="no-such-item") is None
    )


def test_list_feature_layer_records_excludes_raster_and_filters_by_q(session, tenant_and_user):
    from app.items import repository as items_repo

    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="arcgis",
        url="https://gis.example.com/FeatureServer",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    feature_item = items_repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="external",
        title="Bâtiments",
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="a",
        item_id=feature_item.id,
        collection_id=None,
        content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0",
        layer_kind="feature",
    )
    raster_item = items_repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="external",
        title="Ortho",
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="b",
        item_id=raster_item.id,
        collection_id=None,
        content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x",
        layer_kind="raster",
    )
    session.commit()

    rows = repo.list_feature_layer_records(session, tenant_id=tenant.id)
    ids = {r[0] for r in rows}
    assert feature_item.id in ids
    assert raster_item.id not in ids

    filtered = repo.list_feature_layer_records(session, tenant_id=tenant.id, q="zzz-nomatch")
    assert filtered == []


def test_delete_source_removes_external_items_it_created(session, tenant_and_user):
    # P19.07 / j07-007 : plus d'items `external` orphelins après suppression.
    from app.items.models import Item

    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="external", title="t"
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="e1",
        item_id=item.id,
        collection_id=None,
        content_hash="h",
    )
    assert repo.record_counts(session, tenant_id=tenant.id, source_ids=[source.id]) == {
        source.id: (1, 0)
    }
    assert repo.delete_source(session, source) == 1
    session.expire_all()
    assert session.get(Item, item.id) is None


def test_delete_source_keeps_copied_dataset_items(session, tenant_and_user):
    # Revue finale P19 : seuls les items `external` sont retirés, jamais ceux d'une copie.
    from app.items.models import Item

    tenant, user = tenant_and_user
    source = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://c",
        mode="copy",
        enabled=True,
        interval_minutes=None,
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="d"
    )
    repo.create_record(
        session,
        tenant_id=tenant.id,
        source_id=source.id,
        external_id="e1",
        item_id=item.id,
        collection_id=None,
        content_hash="h",
    )
    assert repo.delete_source(session, source) == 0
    session.expire_all()
    assert session.get(Item, item.id) is not None


def test_list_due_backs_off_exponentially_after_failures(session, tenant_and_user):
    """REV-276d : intervalle 15 min, 1 échec → 30 min avant la relance."""
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(session, tenant.id, user.id, last_run_at=now - timedelta(minutes=20))
    assert src in repo.list_due_sources(session)
    src.consecutive_failures = 1
    session.flush()
    assert src not in repo.list_due_sources(session)
    src.last_run_at = now - timedelta(minutes=31)
    session.flush()
    assert src in repo.list_due_sources(session)


def test_list_due_backoff_is_capped_at_one_day(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(
        session,
        tenant.id,
        user.id,
        consecutive_failures=50,
        last_run_at=now - timedelta(hours=24, minutes=1),
    )
    assert src in repo.list_due_sources(session)


def test_find_duplicate_source_compares_normalized_urls(session, tenant_and_user):
    """REV-276c : slash final et casse du schéma/hôte ne font pas une autre source."""
    tenant, user = tenant_and_user
    src = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://stac.example/api/",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )

    def dup(url, **kw):
        return repo.find_duplicate_source(session, tenant_id=tenant.id, type="stac", url=url, **kw)

    assert dup("HTTPS://STAC.Example/api") is src
    assert dup("https://stac.example/API") is None  # le chemin reste sensible à la casse
    assert dup("https://stac.example/api", exclude_id=src.id) is None


def _idle_source(session, tenant, user, *, status=None, updated_at=None):
    src = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    src.last_status = status
    session.commit()
    if updated_at is not None:
        session.execute(
            update(HarvestSource).where(HarvestSource.id == src.id).values(updated_at=updated_at)
        )
        session.commit()
        session.expire_all()
    return src


def test_mark_running_claims_an_idle_source_once(session, tenant_and_user):
    tenant, user = tenant_and_user
    src = _idle_source(session, tenant, user, status="ok")
    assert repo.mark_running(session, tenant_id=tenant.id, source_id=src.id) is True
    session.commit()
    assert repo.mark_running(session, tenant_id=tenant.id, source_id=src.id) is False


def test_mark_running_refuses_a_foreign_tenant_and_an_unknown_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    src = _idle_source(session, tenant, user)
    assert repo.mark_running(session, tenant_id="other", source_id=src.id) is False
    assert repo.mark_running(session, tenant_id=tenant.id, source_id="ghost") is False


def test_mark_running_reclaim_is_compare_and_swap(session, tenant_and_user, monkeypatch):
    """Deux workers lisent la même source périmée : un seul doit la reprendre."""
    tenant, user = tenant_and_user
    old = datetime.now(UTC) - timedelta(minutes=90)
    src = _idle_source(session, tenant, user, status="running", updated_at=old)
    stale = repo.get_source(session, tenant_id=tenant.id, source_id=src.id)
    session.expunge(stale)
    assert repo.mark_running(session, tenant_id=tenant.id, source_id=src.id) is True
    session.commit()
    monkeypatch.setattr(repo, "get_source", lambda *a, **k: stale)  # lecture périmée du 2e worker
    assert repo.mark_running(session, tenant_id=tenant.id, source_id=src.id) is False


def test_mark_running_reclaims_a_stale_running_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    old = datetime.now(UTC) - timedelta(minutes=90)
    src = _idle_source(session, tenant, user, status="running", updated_at=old)
    assert repo.mark_running(session, tenant_id=tenant.id, source_id=src.id) is True
