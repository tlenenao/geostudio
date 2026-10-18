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
import re
import uuid
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from app.collect import repository as collect_ops
from app.collections.introspection import TableNotFound
from app.collections.repository import get_access_facts
from app.collections.routes import get_collection_for_read, get_readable_collection
from app.collections.sensitive import masked_attachment_keys
from app.configs.geo_limits_dep import get_request_geo_limits
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.quotas.service import enforce_storage_quota
from app.sharing.authorization import can
from app.sharing.geo_limits import refuse_if_geo_limited
from app.upload_sniff import HEAD_BYTES, allowed_for_kind, looks_executable, sniff_content_type
from app.users.models import User

router = APIRouter()

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
# Liste non exhaustive d'extensions exécutables/scripts courantes — la spec
# (§2, décision 4) demande une liste noire sans en donner le contenu exact ;
# ajustable si Tanguy le demande.
_DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".com",
        ".bat",
        ".cmd",
        ".msi",
        ".scr",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".sh",
        ".app",
    }
)
# Forme MIME minimale (type/subtype, jetons RFC 2045 usuels) — un contentType
# hors ASCII fait lever la même UnicodeEncodeError que le nom de fichier
# (Starlette encode les en-têtes en latin-1), mais sur Content-Type cette
# fois. Revue finale de branche (Important #1, SP-40 Task 21).
_CONTENT_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)


def _sanitize_filename(filename: str) -> str:
    """Assainit le nom de fichier fourni par le client avant de le stocker
    et de le servir dans Content-Disposition — même mécanisme que
    app/mapicons/routes.py::_SAFE_FILENAME (dupliqué localement, pas
    importé : cf. le commentaire d'en-tête de ce module sur get_s3_client,
    même rationale). Sans cette garde, un nom hors latin-1 fait lever
    UnicodeEncodeError à la lecture (Starlette encode les en-têtes en
    latin-1) et un guillemet permettrait d'injecter des paramètres dans
    l'en-tête."""
    safe = _SAFE_FILENAME.sub("_", filename)[:80]
    return safe or "fichier"


def _reject_dangerous_extension(filename: str) -> None:
    # rstrip(" .") ferme un contournement réel (revue finale, fix bonus) :
    # "evil.exe." a pour extension os.path.splitext ".", jamais refusée, et
    # Windows tronque le point final à l'enregistrement — servi tel quel, le
    # fichier redevient "evil.exe" sur le poste de la victime.
    ext = os.path.splitext(filename.rstrip(" ."))[1].lower()
    if ext in _DANGEROUS_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"extension de fichier non autorisée : {ext}")


def _reject_invalid_content_type(content_type: str) -> None:
    # fullmatch, pas match : `$` en Python matche aussi juste avant un
    # unique retour à la ligne terminal — .match() laissait donc passer
    # "image/png\n" (revue finale, 2e passe), même défaut que ce validateur
    # visait à fermer, sur une forme d'entrée différente.
    if not _CONTENT_TYPE_PATTERN.fullmatch(content_type):
        raise HTTPException(status_code=400, detail="type de contenu invalide")


def _content_disposition_header(filename: str) -> str:
    """RFC 6266 : filename= est un repli ASCII sûr (pour un client qui ne
    comprendrait pas filename*), filename*=UTF-8''<percent-encodé> porte
    la valeur EXACTE et est compris par tous les navigateurs modernes —
    contrairement à un simple assainissement appliqué au stockage (Task 21,
    régression sur les noms accentués), le nom brut n'est jamais mutilé en
    base ; seul cet en-tête encode la valeur correctement (Starlette encode
    les en-têtes en latin-1). quote(..., safe="") empêche aussi l'injection
    de paramètres via un guillemet ou un CR/LF dans le nom brut : aucun des
    deux composants de l'en-tête ne peut plus les porter."""
    ascii_fallback = _sanitize_filename(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


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
        actor_is_admin=user.acts_as_admin(),
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


def _require_declared_field(col, field_key: str) -> dict:
    spec = next((f for f in col.attachment_fields if f["key"] == field_key), None)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"unknown attachment field: {field_key}")
    return spec


def get_entity_checker():  # overridé dans main.py (app.features, au-dessus dans le contrat)
    """`(session, col, fid) -> bool` : la ligne `fid` existe-t-elle, sous RLS ? Défaut permissif
    pour les tests sans table dynamique ; create_app() branche toujours le vrai contrôle."""
    return lambda session, col, fid: True


def _require_existing_entity(exists, session: Session, col, fid: str) -> None:
    """M1 : aucune pièce jointe (ni URL présignée) sur un fid inexistant ou invisible."""
    try:
        found = exists(session, col, fid)
    except TableNotFound:
        found = False
    if not found:
        raise HTTPException(status_code=404, detail="feature not found")


def _discard_object(s3, bucket: str, key: str) -> None:
    try:
        s3.delete_object(Bucket=bucket, Key=key)
    except ClientError:
        logger.warning("attachment rejeté %s: objet non supprimé", key, exc_info=True)


def _read_head(s3, bucket: str, key: str) -> bytes:
    try:
        obj = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{HEAD_BYTES - 1}")
        return obj["Body"].read()
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc


@router.post(
    "/collections/{collection_id}/items/{fid}/attachments/presign",
    response_model=AttachmentPresignResponse,
)
def presign_attachment(
    collection_id: str,
    fid: str,
    body: AttachmentPresignRequest,
    user: User = Depends(get_current_user),
    geo_limits=Depends(get_request_geo_limits),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
    entity_exists=Depends(get_entity_checker),
) -> AttachmentPresignResponse:
    col = _get_writable_collection(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="attachments")
    _require_declared_field(col, body.fieldKey)
    _require_existing_entity(entity_exists, session, col, fid)
    _reject_dangerous_extension(body.filename)
    _reject_invalid_content_type(body.contentType)
    bucket = get_attachments_bucket()
    ensure_uploads_bucket(s3, bucket)
    safe_filename = _sanitize_filename(body.filename)
    if body.size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="attachment too large")
    key = f"{col.tenant_id}/{collection_id}/{fid}/{uuid.uuid4().hex}-{safe_filename}"
    url = generate_presigned_put_url(
        s3, bucket=bucket, key=key, content_type=body.contentType, content_length=body.size
    )
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
    response: Response,
    idempotency_key: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    geo_limits=Depends(get_request_geo_limits),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
    entity_exists=Depends(get_entity_checker),
) -> AttachmentRead:
    col = _get_writable_collection(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="attachments")
    field_spec = _require_declared_field(col, body.fieldKey)
    _reject_dangerous_extension(body.filename)
    _reject_invalid_content_type(body.contentType)
    _require_existing_entity(entity_exists, session, col, fid)
    # L8 : rejeu d'une confirmation (file hors-ligne) = même pièce jointe, rien d'écrit.
    op_key = collect_ops.parse_key(idempotency_key)
    claimed = None
    if op_key:
        claimed, replay = collect_ops.claim(
            session,
            tenant_id=col.tenant_id,
            collection_id=col.id,
            actor_id=user.id,
            kind="attachment",
            client_op_id=op_key,
        )
        if replay:
            prior_id = (claimed.result or {}).get("attachmentId")
            prior = session.get(Attachment, prior_id) if prior_id else None
            if prior is None or prior.tenant_id != col.tenant_id or prior.fid != fid:
                raise HTTPException(status_code=409, detail="idempotent operation unavailable")
            response.status_code = 200
            response.headers["Idempotent-Replay"] = "true"
            return _attachment_json(prior)
    # Même garde anti-confused-deputy que POST /uploads (app/ingestion/routes.py),
    # étendue au préfixe COMPLET (REV-013) : la clé est censée venir du
    # présigné ci-dessus (presign_attachment), qui la préfixe toujours par
    # tenant/collection/fid — valider seulement le tenant laissait passer
    # une clé pointant vers une AUTRE collection ou une AUTRE entité sous le
    # même tenant (devinée ou réutilisée depuis un autre upload).
    if not body.key.startswith(f"{col.tenant_id}/{collection_id}/{fid}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    bucket = get_attachments_bucket()
    try:
        head = s3.head_object(Bucket=bucket, Key=body.key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc
    size = head["ContentLength"]
    if size > MAX_ATTACHMENT_BYTES:
        _discard_object(s3, bucket, body.key)
        raise HTTPException(
            status_code=400,
            detail=f"fichier trop volumineux (> {MAX_ATTACHMENT_BYTES} octets)",
        )
    # Le contenu prime sur le type déclaré (jumelle de la soumission publique, upload_sniff) :
    # un exécutable déguisé est refusé ; un champ typé image/audio/vidéo exige son type.
    head_bytes = _read_head(s3, bucket, body.key)
    sniffed = sniff_content_type(head_bytes)
    kind = field_spec.get("kind")
    if looks_executable(head_bytes) or (
        kind in ("image", "audio", "video") and not allowed_for_kind(sniffed, kind)
    ):
        _discard_object(s3, bucket, body.key)
        raise HTTPException(status_code=415, detail="type de fichier non autorisé")
    content_type = sniffed or head.get("ContentType") or body.contentType
    _reject_invalid_content_type(content_type)
    # SP-58 Tâche 5 (GAP-73/GAP-11) : même patron de nettoyage que le
    # plafond par fichier ci-dessus — un rejet de quota ne doit jamais
    # laisser un objet orphelin en S3.
    enforce_storage_quota(session, s3, tenant_id=col.tenant_id, bucket=bucket, key=body.key)
    already = session.scalar(
        select(Attachment.id).where(
            Attachment.tenant_id == col.tenant_id, Attachment.s3_key == body.key
        )
    )
    if already is not None:  # un objet S3 ne porte qu'une pièce jointe (M1)
        raise HTTPException(status_code=409, detail="attachment already registered")
    try:
        attachment = _create_attachment(
            session, col, collection_id, fid, body, content_type, size, user
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="attachment already registered") from exc
    if claimed is not None:
        collect_ops.record_result(session, claimed, {"attachmentId": attachment.id})
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="attachment.create",
        object_type="attachment",
        object_id=attachment.id,
        payload={
            "collection": collection_id,
            "fid": fid,
            "fieldKey": body.fieldKey,
            **({"clientOpId": op_key} if op_key else {}),
        },
    )
    session.commit()
    return _attachment_json(attachment)


def _create_attachment(session, col, collection_id, fid, body, content_type, size, user):
    return attachments_repo.create_attachment(
        session,
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        field_key=body.fieldKey,
        # Nom brut préservé (pas _sanitize_filename ici) : le nom stocké est
        # celui affiché/téléchargé par l'utilisateur — un accent français
        # (« Relevé été.pdf ») était déjà encodable en latin-1 et ne cassait
        # jamais Content-Disposition ; l'assainir aurait mutilé ce cas de
        # façon définitive et irréversible (revue finale, Important #2). Seul
        # _content_disposition_header (lecture, ci-dessous) a besoin d'un
        # repli ASCII, calculé à la volée, jamais stocké. La clé S3 du
        # presigné (ligne ~155), elle, reste assainie : problème différent.
        filename=body.filename,
        content_type=content_type,
        byte_size=size,
        s3_key=body.key,
        created_by=user.id,
    )


@router.get(
    "/collections/{collection_id}/items/{fid}/attachments",
    response_model=AttachmentList,
)
def list_attachments_route(
    collection_id: str,
    fid: str,
    fieldKey: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    geo_limits=Depends(get_request_geo_limits),
    session: Session = Depends(get_session, scope="function"),
):
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    refuse_if_geo_limited(geo_limits, col.table_name, path="attachments")
    rows = attachments_repo.list_attachments(
        session, tenant_id=col.tenant_id, collection_id=collection_id, fid=fid, field_key=fieldKey
    )
    hidden = masked_attachment_keys(session, user, col)  # AUD-093
    rows = [a for a in rows if a.field_key not in hidden]
    return AttachmentList(attachments=[_attachment_json(a) for a in rows])


@router.get("/collections/{collection_id}/items/{fid}/attachments/{attachment_id}/file")
def read_attachment_file(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    geo_limits=Depends(get_request_geo_limits),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
) -> Response:
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    refuse_if_geo_limited(geo_limits, col.table_name, path="attachments")
    attachment = attachments_repo.get_attachment(
        session,
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        attachment_id=attachment_id,
    )
    if attachment is None or attachment.field_key in masked_attachment_keys(session, user, col):
        raise HTTPException(status_code=404, detail="attachment not found")  # AUD-093
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
            "Content-Disposition": _content_disposition_header(attachment.filename),
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
    geo_limits=Depends(get_request_geo_limits),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
) -> None:
    col = _get_writable_collection(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="attachments")
    hidden = masked_attachment_keys(session, user, col)  # AUD-093
    if hidden:
        target = attachments_repo.get_attachment(
            session,
            tenant_id=col.tenant_id,
            collection_id=collection_id,
            fid=fid,
            attachment_id=attachment_id,
        )
        if target is not None and target.field_key in hidden:
            raise HTTPException(status_code=404, detail="attachment not found")
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
