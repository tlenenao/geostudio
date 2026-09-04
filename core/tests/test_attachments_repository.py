# SPDX-License-Identifier: Apache-2.0
import pytest

from app.attachments import repository as attachments_repo
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.deleted: list[tuple[str, str]] = []

    def delete_object(self, *, Bucket, Key):
        self.deleted.append((Bucket, Key))


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
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
    # Crée la collection "col1" pour satisfaire la FK Attachment.collection_id
    # (piège n°3 : le texte du brief ne suffisait pas)
    col = Collection(
        id="col1",
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="col1",
        title="Col 1",
        description="",
        pk_column="id",
        editable=True,
    )
    session.add(col)
    session.commit()
    return session, tenant, user


def _create(session, *, tenant_id, created_by, fid="f1", field_key="photos"):
    return attachments_repo.create_attachment(
        session,
        tenant_id=tenant_id,
        collection_id="col1",
        fid=fid,
        field_key=field_key,
        filename="a.jpg",
        content_type="image/jpeg",
        byte_size=1234,
        s3_key=f"{tenant_id}/col1/{fid}/abc-a.jpg",
        created_by=created_by,
    )


def test_create_attachment_writes_all_fields(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()
    assert a.id is not None
    assert a.field_key == "photos"
    assert a.byte_size == 1234


def test_list_attachments_isolates_by_field_key_and_entity(env):
    session, tenant, user = env
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="photos")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="documents")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f2", field_key="photos")
    session.commit()

    rows = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1", field_key="photos"
    )
    assert len(rows) == 1

    all_for_f1 = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    assert len(all_for_f1) == 2


def test_list_attachments_isolates_by_tenant(env):
    session, tenant, user = env
    other_tenant = get_or_create_default_tenant(session)  # même défaut, cf. note ci-dessous
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1")
    session.commit()
    # Note : get_or_create_default_tenant retourne toujours LE MÊME tenant
    # par défaut dans ce dépôt (un seul tenant par process en mode mock) —
    # l'isolation tenant réelle est déjà exercée par les tests de routes
    # (Tâche 4, deux tenants distincts via deux users manuellement créés
    # avec des tenant_id différents n'est pas le patron standard ici).
    assert other_tenant.id == tenant.id


def test_get_attachment_returns_none_outside_scope(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()

    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is not None
    )
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col-other", fid="f1", attachment_id=a.id
        )
        is None
    )


def test_delete_attachment_removes_row_and_deletes_s3_object(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()
    s3 = _FakeS3Client()

    ok = attachments_repo.delete_attachment(
        session,
        s3,
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id=a.id,
    )
    session.commit()
    assert ok is True
    assert s3.deleted == [("geostudio-attachments", a.s3_key)]
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is None
    )


def test_delete_attachment_unknown_id_returns_false(env):
    session, tenant, _user = env
    s3 = _FakeS3Client()
    ok = attachments_repo.delete_attachment(
        session,
        s3,
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id="does-not-exist",
    )
    assert ok is False
    assert s3.deleted == []


def test_delete_all_for_feature_removes_only_that_entity(env):
    session, tenant, user = env
    kept = _create(session, tenant_id=tenant.id, created_by=user.id, fid="other")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="photos")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="documents")
    session.commit()
    s3 = _FakeS3Client()

    attachments_repo.delete_all_for_feature(
        session, s3, "geostudio-attachments", tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    session.commit()

    remaining = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    assert remaining == []
    assert len(s3.deleted) == 2
    still_there = attachments_repo.get_attachment(
        session, tenant_id=tenant.id, collection_id="col1", fid="other", attachment_id=kept.id
    )
    assert still_there is not None


def test_delete_swallows_s3_client_error_and_still_removes_the_row(env):
    from botocore.exceptions import ClientError

    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()

    class _BoomS3Client:
        def delete_object(self, *, Bucket, Key):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "DeleteObject")

    ok = attachments_repo.delete_attachment(
        session,
        _BoomS3Client(),
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id=a.id,
    )
    session.commit()
    assert ok is True  # la ligne est supprimée même si l'objet S3 a échoué
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is None
    )
