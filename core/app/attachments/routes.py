# SPDX-License-Identifier: Apache-2.0
"""Routes self-scoped pour les pièces jointes d'une entité (chantier 4.12).

get_s3_client est un STUB PROPRE à ce module, pas réutilisé depuis
app.ingestion.routes : app.attachments est placé sous app.features dans le
contrat de couches (pour que remove_feature puisse l'importer normalement,
Tâche 7), mais app.ingestion est au-dessus d'app.features — réutiliser
ingestion_routes.get_s3_client demanderait une exemption ; le dupliquer
localement n'en demande aucune ET permet à app.features de réutiliser CE
stub pour la cascade de suppression avec la même clé d'override. Voir
docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md §3.1."""

import logging
import os
import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.attachments import repository as attachments_repo
from app.attachments.models import Attachment
from app.attachments.schemas import (
    AttachmentConfirmRequest,
    AttachmentList,
    AttachmentPresignRequest,
    AttachmentPresignResponse,
    AttachmentRead,
)
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.repository import get_access_facts
from app.collections.routes import get_readable_collection
from app.db import get_session
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


def get_attachments_bucket() -> str:
    return os.environ.get("S3_ATTACHMENTS_BUCKET", "geostudio-attachments")


def _get_writable_collection(session: Session, user: User, collection_id: str):
    """Mirrors app/features/routes.py::_get_writable — ne peut pas l'importer
    (app.attachments est sous app.features dans le contrat de couches)."""
    col = get_readable_collection(session, user, collection_id)
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    ):
        raise HTTPException(status_code=403, detail="write access required")
    if not col.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    return col


def _attachment_json(a: Attachment) -> AttachmentRead:
    return AttachmentRead(
        id=a.id,
        fieldKey=a.field_key,
        filename=a.filename,
        contentType=a.content_type,
        byteSize=a.byte_size,
        createdAt=a.created_at.isoformat(),
    )


def _require_declared_field(col, field_key: str) -> None:
    declared = {f["key"] for f in col.attachment_fields}
    if field_key not in declared:
        raise HTTPException(status_code=400, detail=f"unknown attachment field: {field_key}")


@router.post(
    "/collections/{collection_id}/items/{fid}/attachments/presign",
    response_model=AttachmentPresignResponse,
)
def presign_attachment(
    collection_id: str,
    fid: str,
    body: AttachmentPresignRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> AttachmentPresignResponse:
    col = _get_writable_collection(session, user, collection_id)
    _require_declared_field(col, body.fieldKey)
    bucket = get_attachments_bucket()
    ensure_uploads_bucket(s3, bucket)
    key = f"{col.tenant_id}/{collection_id}/{fid}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type=body.contentType)
    return AttachmentPresignResponse(uploadUrl=url, key=key)


@router.post(
    "/collections/{collection_id}/items/{fid}/attachments",
    response_model=AttachmentRead,
    status_code=201,
)
def confirm_attachment(
    collection_id: str,
    fid: str,
    body: AttachmentConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> AttachmentRead:
    col = _get_writable_collection(session, user, collection_id)
    _require_declared_field(col, body.fieldKey)
    # Même garde anti-confused-deputy que POST /uploads (app/ingestion/routes.py) :
    # la clé est censée venir du présigné ci-dessus, toujours préfixée par le
    # tenant de l'appelant.
    if not body.key.startswith(f"{col.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    bucket = get_attachments_bucket()
    try:
        head = s3.head_object(Bucket=bucket, Key=body.key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc
    size = head["ContentLength"]
    if size > MAX_ATTACHMENT_BYTES:
        try:
            s3.delete_object(Bucket=bucket, Key=body.key)
        except ClientError:
            logger.warning("attachment oversize %s: objet non supprimé", body.key, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"fichier trop volumineux (> {MAX_ATTACHMENT_BYTES} octets)",
        )
    attachment = attachments_repo.create_attachment(
        session,
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        field_key=body.fieldKey,
        filename=body.filename,
        content_type=body.contentType,
        byte_size=size,
        s3_key=body.key,
        created_by=user.id,
    )
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="attachment.create",
        object_type="attachment",
        object_id=attachment.id,
        payload={"collection": collection_id, "fid": fid, "fieldKey": body.fieldKey},
    )
    session.commit()
    return _attachment_json(attachment)


@router.get(
    "/collections/{collection_id}/items/{fid}/attachments",
    response_model=AttachmentList,
)
def list_attachments_route(
    collection_id: str,
    fid: str,
    fieldKey: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    col = get_readable_collection(session, user, collection_id)
    rows = attachments_repo.list_attachments(
        session, tenant_id=col.tenant_id, collection_id=collection_id, fid=fid, field_key=fieldKey
    )
    return AttachmentList(attachments=[_attachment_json(a) for a in rows])


@router.get("/collections/{collection_id}/items/{fid}/attachments/{attachment_id}/file")
def read_attachment_file(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> Response:
    col = get_readable_collection(session, user, collection_id)
    attachment = attachments_repo.get_attachment(
        session,
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    bucket = get_attachments_bucket()
    try:
        obj = s3.get_object(Bucket=bucket, Key=attachment.s3_key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="attachment file not found") from exc
    return Response(
        content=obj["Body"].read(),
        media_type=attachment.content_type,
        headers={
            # Mêmes trois en-têtes que GET /map-icons/{id}/file
            # (app/mapicons/routes.py) — patron déjà établi pour servir un
            # fichier utilisateur authentifié.
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{attachment.filename}"',
        },
    )


@router.delete(
    "/collections/{collection_id}/items/{fid}/attachments/{attachment_id}", status_code=204
)
def delete_attachment_route(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> None:
    col = _get_writable_collection(session, user, collection_id)
    ok = attachments_repo.delete_attachment(
        session,
        s3,
        get_attachments_bucket(),
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        attachment_id=attachment_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="attachment not found")
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="attachment.delete",
        object_type="attachment",
        object_id=attachment_id,
        payload={"collection": collection_id, "fid": fid},
    )
    session.commit()
