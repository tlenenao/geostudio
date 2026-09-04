# SPDX-License-Identifier: Apache-2.0
import logging
import uuid

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attachments.models import Attachment

logger = logging.getLogger(__name__)


def create_attachment(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    field_key: str,
    filename: str,
    content_type: str,
    byte_size: int,
    s3_key: str,
    created_by: str,
) -> Attachment:
    attachment = Attachment(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        collection_id=collection_id,
        fid=fid,
        field_key=field_key,
        filename=filename,
        content_type=content_type,
        byte_size=byte_size,
        s3_key=s3_key,
        created_by=created_by,
    )
    session.add(attachment)
    session.flush()
    return attachment


def list_attachments(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    field_key: str | None = None,
) -> list[Attachment]:
    stmt = select(Attachment).where(
        Attachment.tenant_id == tenant_id,
        Attachment.collection_id == collection_id,
        Attachment.fid == fid,
    )
    if field_key is not None:
        stmt = stmt.where(Attachment.field_key == field_key)
    return list(session.scalars(stmt.order_by(Attachment.created_at)).all())


def get_attachment(
    session: Session, *, tenant_id: str, collection_id: str, fid: str, attachment_id: str
) -> Attachment | None:
    return session.scalar(
        select(Attachment).where(
            Attachment.tenant_id == tenant_id,
            Attachment.collection_id == collection_id,
            Attachment.fid == fid,
            Attachment.id == attachment_id,
        )
    )


def _delete_s3_object_best_effort(s3_client, bucket: str, key: str) -> None:
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
    except ClientError:
        logger.warning("attachment %s: objet S3 non supprimé", key, exc_info=True)


def delete_attachment(
    session: Session,
    s3_client,
    bucket: str,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    attachment_id: str,
) -> bool:
    attachment = get_attachment(
        session,
        tenant_id=tenant_id,
        collection_id=collection_id,
        fid=fid,
        attachment_id=attachment_id,
    )
    if attachment is None:
        return False
    _delete_s3_object_best_effort(s3_client, bucket, attachment.s3_key)
    session.delete(attachment)
    session.flush()
    return True


def delete_all_for_feature(
    session: Session, s3_client, bucket: str, *, tenant_id: str, collection_id: str, fid: str
) -> None:
    rows = list_attachments(session, tenant_id=tenant_id, collection_id=collection_id, fid=fid)
    for attachment in rows:
        _delete_s3_object_best_effort(s3_client, bucket, attachment.s3_key)
        session.delete(attachment)
    session.flush()
