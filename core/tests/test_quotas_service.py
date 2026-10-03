# SPDX-License-Identifier: Apache-2.0
import pytest

from app.appexport.models import AppExportJob
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.export.models import ExportJob
from app.items.models import Item
from app.quotas.service import (
    QuotaExceededError,
    check_quota_or_raise,
    count_collections_for_tenant,
    count_items_for_tenant,
    count_users_for_tenant,
    enforce_storage_quota,
    job_output_storage_bytes,
    max_collections_per_tenant,
    max_items_per_tenant,
    max_storage_bytes_per_tenant,
    tenant_prefixed_storage_bytes,
    usage_for_tenant,
)
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def _quotas_on(monkeypatch):
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant_a = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant_a.id)
        # Un deuxième tenant, créé à la main (get_or_create_default_tenant ne
        # sait créer que "le" tenant par défaut) — un second User avec un
        # tenant_id distinct suffit à distinguer les compteurs.
        from app.tenants.models import Tenant

        tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        s.add(tenant_b)
        s.flush()
        ensure_built_in_roles(s, tenant_id=tenant_b.id)
        user_a = get_or_create_user(
            s,
            tenant_id=tenant_a.id,
            oidc_sub="a1",
            username="a1",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        user_b = get_or_create_user(
            s,
            tenant_id=tenant_b.id,
            oidc_sub="b1",
            username="b1",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.add(
            Item(
                id="item-a1",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                resource_type="map",
                title="A1",
            )
        )
        s.add(
            Item(
                id="item-a2",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                resource_type="map",
                title="A2",
            )
        )
        s.add(
            Item(
                id="item-b1",
                tenant_id=tenant_b.id,
                owner_id=user_b.id,
                resource_type="map",
                title="B1",
            )
        )
        s.add(
            Collection(
                id="col-a1",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                table_name="col_a1",
                title="Col A1",
                pk_column="id",
            )
        )
        s.commit()
        yield s, tenant_a.id, tenant_b.id, user_a.id, user_b.id


def test_count_items_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b, _user_a, _user_b = env
    assert count_items_for_tenant(session, tenant_a) == 2
    assert count_items_for_tenant(session, tenant_b) == 1


def test_count_collections_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b, _user_a, _user_b = env
    assert count_collections_for_tenant(session, tenant_a) == 1
    assert count_collections_for_tenant(session, tenant_b) == 0


def test_count_users_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b, _user_a, _user_b = env
    assert count_users_for_tenant(session, tenant_a) == 1
    assert count_users_for_tenant(session, tenant_b) == 1


class _FakeS3Client:
    """Double en mémoire de list_objects_v2, paginé (1000 clés) — la vraie
    API S3 tronque à 1000 clés par page (IsTruncated/NextContinuationToken),
    piège explicitement visé par test_tenant_prefixed_storage_bytes_
    paginates_past_1000_keys ci-dessous."""

    def __init__(self, objects: dict[str, int], *, bucket: str = "bucket"):
        # objects: {key: size} — tous supposés vivre dans `bucket` (un seul
        # bucket par instance, suffisant pour ces tests : usage_for_tenant
        # interroge 4 buckets différents, cf. _multi_bucket_s3 ci-dessous
        # pour le test qui doit distinguer plusieurs buckets).
        self.objects = objects
        self.bucket = bucket

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):  # noqa: N803
        if Bucket != self.bucket:
            return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        page_size = 1000
        start = 0
        if ContinuationToken is not None:
            start = int(ContinuationToken)
        page_keys = keys[start : start + page_size]
        truncated = start + page_size < len(keys)
        return {
            "Contents": [{"Key": k, "Size": self.objects[k]} for k in page_keys],
            "IsTruncated": truncated,
            "NextContinuationToken": str(start + page_size) if truncated else None,
        }


def test_tenant_prefixed_storage_bytes_sums_only_this_tenant_prefix():
    s3 = _FakeS3Client(
        {
            "tenant-a/f1.gpkg": 100,
            "tenant-a/f2.gpkg": 250,
            "tenant-b/f3.gpkg": 999999,
        }
    )
    assert tenant_prefixed_storage_bytes(s3, "bucket", "tenant-a") == 350
    assert tenant_prefixed_storage_bytes(s3, "bucket", "tenant-b") == 999999
    assert tenant_prefixed_storage_bytes(s3, "bucket", "tenant-c") == 0


def test_tenant_prefixed_storage_bytes_paginates_past_1000_keys():
    objects = {f"tenant-a/{i}.bin": 1 for i in range(1500)}
    s3 = _FakeS3Client(objects)
    # 1500 objets d'1 octet chacun : une implémentation qui ne suit pas
    # IsTruncated/NextContinuationToken s'arrêterait à 1000 (piège spec
    # §3.1.2 Tâche 3 Step 2).
    assert tenant_prefixed_storage_bytes(s3, "bucket", "tenant-a") == 1500


def test_job_output_storage_bytes_sums_export_and_appexport_filtered_by_tenant(env):
    session, tenant_a, tenant_b, user_a, _user_b = env
    session.add(
        ExportJob(
            id="ex-a1",
            tenant_id=tenant_a,
            item_id="item-a1",
            user_id=user_a,
            format="png",
            status="done",
            byte_size=1000,
        )
    )
    session.add(
        AppExportJob(
            id="aex-a1",
            tenant_id=tenant_a,
            item_id="item-a1",
            user_id=user_a,
            mode="static",
            status="done",
            byte_size=250,
        )
    )
    session.commit()
    # Un job d'un autre tenant (b) ne doit pas compter dans le total de a.
    total_a = job_output_storage_bytes(session, tenant_a)
    total_b = job_output_storage_bytes(session, tenant_b)
    assert total_a == 1250
    assert total_b == 0


def test_usage_for_tenant_aggregates_counts_and_storage(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    s3 = _FakeS3Client(
        {
            f"{tenant_a}/f1.gpkg": 500,
        },
        bucket="geostudio-uploads",
    )
    monkeypatch.setenv("S3_UPLOADS_BUCKET", "geostudio-uploads")
    monkeypatch.setenv("S3_ATTACHMENTS_BUCKET", "geostudio-attachments")
    monkeypatch.setenv("S3_TILESET3D_BUCKET", "geostudio-tileset3d")
    monkeypatch.setenv("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
    snapshot = usage_for_tenant(session, s3, tenant_a)
    assert snapshot.item_count == 2
    assert snapshot.collection_count == 1
    assert snapshot.user_count == 1
    # 4 buckets tenant-préfixés interrogés avec le même préfixe : seul
    # celui qui porte réellement un objet sous ce préfixe contribue.
    assert snapshot.storage_bytes == 500


def test_limit_readers_default_to_none_when_unset(monkeypatch):
    monkeypatch.delenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", raising=False)
    monkeypatch.delenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", raising=False)
    monkeypatch.delenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", raising=False)
    assert max_items_per_tenant() is None
    assert max_collections_per_tenant() is None
    assert max_storage_bytes_per_tenant() is None


def test_limit_readers_parse_configured_values(monkeypatch):
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "1000")
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "50")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "10737418240")
    assert max_items_per_tenant() == 1000
    assert max_collections_per_tenant() == 50
    assert max_storage_bytes_per_tenant() == 10737418240


def test_check_quota_or_raise_items_no_limit_configured_is_a_noop(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    monkeypatch.delenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", raising=False)
    check_quota_or_raise(session, tenant_id=tenant_a, kind="items")  # ne lève pas


def test_check_quota_or_raise_items_raises_409_at_limit(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    # tenant_a a déjà 2 items (fixture) — limite à 2 doit refuser le 3e.
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "2")
    with pytest.raises(QuotaExceededError) as excinfo:
        check_quota_or_raise(session, tenant_id=tenant_a, kind="items")
    assert excinfo.value.status_code == 409


def test_check_quota_or_raise_items_allows_below_limit(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "3")
    check_quota_or_raise(session, tenant_id=tenant_a, kind="items")  # 2 < 3, ne lève pas


def test_check_quota_or_raise_collections_raises_409_at_limit(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    # tenant_a a déjà 1 collection (fixture) — limite à 1 doit refuser la 2e.
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")
    with pytest.raises(QuotaExceededError) as excinfo:
        check_quota_or_raise(session, tenant_id=tenant_a, kind="collections")
    assert excinfo.value.status_code == 409


def test_enforce_storage_quota_no_limit_is_a_noop(env, monkeypatch):
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.delenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", raising=False)
    enforce_storage_quota(session, _FakeS3Client({"t/x": 10**12}), tenant_id=tenant_a)


def test_enforce_storage_quota_boundary_plus_one_byte(env, monkeypatch):
    """P26 : l'objet est déjà compté — exactement la limite passe, +1 octet
    est refusé (413 quota-exceeded) et l'objet fautif est supprimé."""
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    monkeypatch.setenv("S3_UPLOADS_BUCKET", "bucket")
    key = f"{tenant_a}/up.bin"
    ok = _FakeS3Client({key: 1000})
    enforce_storage_quota(session, ok, tenant_id=tenant_a, bucket="bucket", key=key)
    over = _FakeS3Client({key: 1001})
    deleted = []
    over.delete_object = lambda *, Bucket, Key: deleted.append(Key)  # noqa: N803
    with pytest.raises(QuotaExceededError) as excinfo:
        enforce_storage_quota(session, over, tenant_id=tenant_a, bucket="bucket", key=key)
    assert excinfo.value.status_code == 413
    assert (excinfo.value.quota, excinfo.value.current, excinfo.value.limit) == (
        "storage",
        1001,
        1000,
    )
    assert deleted == [key]


def test_usage_counts_pipeline_exports_and_cdc(env, monkeypatch):
    """t03b-006 : sorties writer.export et lakehouse CDC comptés."""
    session, tenant_a, _tenant_b, _user_a, _user_b = env
    monkeypatch.setenv("S3_EXPORTS_BUCKET", "bucket")
    s3 = _FakeS3Client(
        {
            f"{tenant_a}/pipelines/out.csv": 70,
            f"{tenant_a}/other": 5,  # hors périmètre (jobs d'export : byte_size)
            f"cdc/tenant_id={tenant_a}/collection_id=c/dt=1/p.parquet": 30,
            "cdc/tenant_id=autre/collection_id=c/dt=1/p.parquet": 999,
        }
    )
    monkeypatch.setenv("S3_CDC_BUCKET", "bucket")
    assert usage_for_tenant(session, s3, tenant_a).storage_bytes == 100


def test_count_users_for_tenant_excludes_erased_accounts_j08_013(env):
    from datetime import UTC, datetime

    from app.users.models import User

    session, tenant_a, _tenant_b, user_a, _user_b = env
    session.get(User, user_a).erased_at = datetime.now(UTC)
    session.flush()
    assert count_users_for_tenant(session, tenant_a) == 0
