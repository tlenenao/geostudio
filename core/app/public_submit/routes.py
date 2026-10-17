# SPDX-License-Identifier: Apache-2.0
"""Soumission publique modérée (ARC-10, ADR 0017).

Un seul chemin d'écriture anonyme : `POST /public/submit/{token}`, qui ne fait
qu'INSÉRER une soumission en attente dans `submissions` (jamais dans la table de la
collection). Modération et gestion des jetons : authentifiées, droit d'écriture."""

import copy
import json
import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.attachments import repository as attachments_repo
from app.attachments.routes import (
    MAX_ATTACHMENT_BYTES,
    _reject_dangerous_extension,
    _sanitize_filename,
    get_attachments_bucket,
    get_s3_client,
)
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections.domains import with_attribute_rules
from app.collections.introspection import hide_sensitive_columns
from app.collections.models import Collection
from app.collections.repository import get_collection
from app.collections.routes import get_introspector
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import get_session
from app.features.routes import (
    _get_writable,
    _raise_if_outside_geo_limit,
    _snapshot,
    _validation_error,
    get_features_repo,
    get_rls_scope,
)
from app.features.validation import validate_for_write
from app.history import service as history
from app.ingestion.storage import ensure_uploads_bucket
from app.public_submit import service
from app.public_submit.models import Submission, SubmissionToken
from app.quotas.service import enforce_storage_quota
from app.ratelimit.limiter import ip_bucket
from app.sharing.geo_limits import refuse_if_geo_limited

router = APIRouter()

_ACCEPTED = {"status": "pending"}


# --------------------------------------------------------------------------- public


@router.post("/public/submit/{token}", status_code=202)
def submit(
    token: str,
    request: Request,
    payload: str = Form(..., description="GeoJSON Feature (JSON)"),
    website: str = Form("", description="honeypot : doit rester vide"),
    fieldKey: str | None = Form(None),  # noqa: N803
    file: UploadFile | None = File(None),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    s3=Depends(get_s3_client),
):
    ip = ip_bucket(request.client.host if request.client else None)  # AUD-154 : /64 en IPv6
    if not service.ip_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="too many submissions, retry later")
    if not service.token_limiter.has_room(token):
        raise HTTPException(
            status_code=429, detail="too many submissions for this form, retry later"
        )
    row = service.find_token(session, token)
    if row is None:
        raise HTTPException(status_code=404, detail="submission link not found")
    if not service.token_is_usable(row):
        raise HTTPException(status_code=410, detail="submission link expired or revoked")
    if website.strip():
        # Honeypot : réponse indiscernable d'un succès, rien n'est stocké ni décompté.
        return _ACCEPTED
    col = get_collection(session, tenant_id=row.tenant_id, collection_id=row.collection_id)
    if col is None or not col.editable:
        raise HTTPException(status_code=410, detail="submission link expired or revoked")
    if len(payload.encode()) > service.MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    try:
        feature = json.loads(payload)
    except ValueError:
        raise _validation_error(
            [{"field": "payload", "code": "invalid_json", "message": "payload must be JSON"}]
        ) from None
    # Le public n'écrit jamais un champ sensible : retiré du schéma, il est refusé.
    # Domaines/sous-types/règles (ARC-13/14) contrôlés sur une copie : la charge brute est
    # stockée, défauts et calculs sont posés à l'approbation (règles alors en vigueur).
    info = with_attribute_rules(
        hide_sensitive_columns(introspect(session, col.table_name), col.sensitive_fields), col
    )
    if errors := validate_for_write(info, copy.deepcopy(feature)):
        raise _validation_error(errors)
    # Quota réservé AVANT tout envoi S3 : un jeton épuisé n'écrit rien. Un échec ensuite
    # (fichier refusé, S3) annule la transaction, donc la réservation avec.
    if not service.reserve_slot(session, row):
        raise HTTPException(status_code=429, detail="submission quota exhausted")
    attachment, attachment_key = None, None
    if file is not None and file.filename:
        attachment, attachment_key = _store_attachment(session, s3, col, file, fieldKey)
    sub = service.create_submission(
        session,
        token=row,
        payload={
            "properties": feature.get("properties") or {},
            "geometry": feature.get("geometry"),
        },
        attachment=attachment,
        attachment_key=attachment_key,
    )
    del sub
    service.token_limiter.allow(token)  # revue SP-L2 I4 : seule une soumission acceptée compte
    service.notify_moderators(session, col)
    return _ACCEPTED


def _delete_object(s3, key: str) -> None:
    try:
        s3.delete_object(Bucket=get_attachments_bucket(), Key=key)
    except ClientError:  # best-effort
        pass


def _store_attachment(session, s3, col: Collection, file: UploadFile, field_key: str | None):
    declared = [f["key"] for f in col.attachment_fields]
    if not declared:
        raise HTTPException(status_code=400, detail="this collection does not accept attachments")
    key_name = field_key or (declared[0] if len(declared) == 1 else None)
    if key_name not in declared:
        raise HTTPException(status_code=400, detail=f"unknown attachment field: {field_key}")
    filename = file.filename or "fichier"
    _reject_dangerous_extension(filename)
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="fichier trop volumineux (> 25 Mo)")
    content_type = service.sniff_content_type(data[:16])
    if content_type is None:
        raise HTTPException(status_code=415, detail="type de fichier non autorisé")
    bucket = get_attachments_bucket()
    ensure_uploads_bucket(s3, bucket)
    s3_key = f"{col.tenant_id}/{col.id}/pending-{uuid.uuid4().hex}/{_sanitize_filename(filename)}"
    s3.put_object(Bucket=bucket, Key=s3_key, Body=data, ContentType=content_type)
    enforce_storage_quota(session, s3, tenant_id=col.tenant_id, bucket=bucket, key=s3_key)
    meta = {
        "fieldKey": key_name,
        "filename": filename,
        "contentType": content_type,
        "byteSize": len(data),
    }
    return meta, s3_key


# ------------------------------------------------------------------ gestion (auth.)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expiresInDays: int = Field(ge=1, le=service.MAX_LIFETIME_DAYS)  # noqa: N815
    maxSubmissions: int = Field(ge=1, le=100_000)  # noqa: N815


def _iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=None).isoformat() + "Z" if dt else None


def _token_json(t: SubmissionToken) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "prefix": t.token_prefix,
        "expiresAt": _iso(t.expires_at),
        "maxSubmissions": t.max_submissions,
        "submissionCount": t.submission_count,
        "revokedAt": _iso(t.revoked_at),
        "createdAt": _iso(t.created_at),
    }


@router.post("/collections/{collection_id}/submission-tokens", status_code=201)
def create_submission_token(
    collection_id: str,
    body: TokenCreate,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    col = _get_writable(session, user, collection_id)
    row, token = service.create_token(
        session,
        collection=col,
        user=user,
        name=body.name,
        expires_in_days=body.expiresInDays,
        max_submissions=body.maxSubmissions,
    )
    return {**_token_json(row), "token": token}  # le jeton n'est montré qu'ici


@router.get("/collections/{collection_id}/submission-tokens")
def list_submission_tokens(
    collection_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    col = _get_writable(session, user, collection_id)
    rows = session.scalars(
        select(SubmissionToken)
        .where(SubmissionToken.tenant_id == col.tenant_id, SubmissionToken.collection_id == col.id)
        .order_by(SubmissionToken.created_at.desc())
    )
    return {"tokens": [_token_json(r) for r in rows]}


@router.delete("/collections/{collection_id}/submission-tokens/{token_id}", status_code=204)
def revoke_submission_token(
    collection_id: str,
    token_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    col = _get_writable(session, user, collection_id)
    row = session.get(SubmissionToken, token_id)
    if row is None or row.collection_id != col.id or row.tenant_id != col.tenant_id:
        raise HTTPException(status_code=404, detail="token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        write_audit(
            session,
            tenant_id=col.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="submission_token.revoke",
            object_type="submission_token",
            object_id=row.id,
            payload={"collection": col.id},
        )


def _submission_json(s: Submission) -> dict:
    return {
        "id": s.id,
        "status": s.status,
        "properties": (s.payload or {}).get("properties", {}),
        "geometry": (s.payload or {}).get("geometry"),
        "attachment": s.attachment,
        "createdAt": _iso(s.created_at),
        "moderatedBy": s.moderated_by,
        "moderatedAt": _iso(s.moderated_at),
        "rejectReason": s.reject_reason,
        "featureId": s.feature_id,
    }


def _get_moderable(session: Session, user, collection_id: str, geo_limits) -> Collection:
    """Droit d'écriture + fail-closed sous limite géographique : la file d'attente n'est
    pas découpée (comme le journal d'entité et les rapports de qualité)."""
    col = _get_writable(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="submission moderation")
    return col


def _get_submission(session: Session, col: Collection, submission_id: str) -> Submission:
    sub = session.scalar(
        select(Submission)
        .where(
            Submission.id == submission_id,
            Submission.tenant_id == col.tenant_id,
            Submission.collection_id == col.id,
        )
        .with_for_update()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return sub


@router.get("/collections/{collection_id}/submissions")
def list_submissions(
    collection_id: str,
    status: str = "pending",
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
):
    col = _get_moderable(session, user, collection_id, geo_limits)
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="invalid status")
    rows = session.scalars(
        select(Submission)
        .where(
            Submission.tenant_id == col.tenant_id,
            Submission.collection_id == col.id,
            Submission.status == status,
        )
        .order_by(Submission.created_at)
        .limit(200)
    )
    return {"submissions": [_submission_json(r) for r in rows]}


@router.get("/collections/{collection_id}/submissions/{submission_id}/attachment")
def read_submission_attachment(
    collection_id: str,
    submission_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
    geo_limits=Depends(get_request_geo_limits),
):
    col = _get_moderable(session, user, collection_id, geo_limits)
    sub = _get_submission(session, col, submission_id)
    if sub.status != "pending" or not sub.attachment_key or not sub.attachment:
        raise HTTPException(status_code=404, detail="attachment not found")
    try:
        obj = s3.get_object(Bucket=get_attachments_bucket(), Key=sub.attachment_key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="attachment file not found") from exc
    return Response(
        content=obj["Body"].read(),
        media_type=sub.attachment["contentType"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment",
        },
    )


@router.post("/collections/{collection_id}/submissions/{submission_id}/approve")
def approve_submission(
    collection_id: str,
    submission_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    geo_limits=Depends(get_request_geo_limits),
):
    """Insère la soumission dans la collection par l'écriture normale (droit d'écriture,
    validation, RLS, journal d'entité) ; la ligne d'attente est vidée."""
    col = _get_moderable(session, user, collection_id, geo_limits)
    sub = _get_submission(session, col, submission_id)
    if sub.status != "pending":
        raise HTTPException(status_code=409, detail="submission already moderated")
    # Même validation que le POST REST (ARC-13/14) ; le schéma et les règles ont pu évoluer.
    info = with_attribute_rules(introspect(session, col.table_name), col)
    feature = {"type": "Feature", **copy.deepcopy(sub.payload)}
    if errors := validate_for_write(info, feature):
        raise _validation_error(errors)
    try:
        with rls(session, col.tenant_id):
            fid = repo.insert_feature(
                session,
                info,
                properties=feature.get("properties") or {},  # défauts/calculs posés
                geometry=feature.get("geometry"),
            )
        after = _snapshot(session, repo, info, fid)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="feature conflicts with an existing row"
        ) from exc
    except DBAPIError as exc:
        _raise_if_outside_geo_limit(exc)
        raise
    history.record_change(
        session,
        tenant_id=col.tenant_id,
        collection_id=col.id,
        fid=str(fid),
        op="create",
        before=None,
        after=after,
        actor_id=user.id,
    )
    session.execute(
        text("UPDATE collections SET feature_count = feature_count + 1 WHERE id = :id"),
        {"id": col.id},
    )
    if sub.attachment and sub.attachment_key:
        attachments_repo.create_attachment(
            session,
            tenant_id=col.tenant_id,
            collection_id=col.id,
            fid=str(fid),
            field_key=sub.attachment["fieldKey"],
            filename=sub.attachment["filename"],
            content_type=sub.attachment["contentType"],
            byte_size=sub.attachment["byteSize"],
            s3_key=sub.attachment_key,
            created_by=user.id,
        )
    sub.status = "approved"
    sub.moderated_by = user.id
    sub.moderated_at = datetime.now(UTC).replace(tzinfo=None)
    sub.feature_id = str(fid)
    sub.payload = {}
    sub.attachment = None
    # attachment_key conservé : la pièce jointe (devenue ligne `attachments`) reste vivante.
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="submission.approve",
        object_type="submission",
        object_id=sub.id,
        payload={"collection": col.id, "fid": str(fid)},
    )
    return {"fid": str(fid)}


class RejectBody(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.post("/collections/{collection_id}/submissions/{submission_id}/reject", status_code=204)
def reject_submission(
    collection_id: str,
    submission_id: str,
    body: RejectBody,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
    geo_limits=Depends(get_request_geo_limits),
):
    col = _get_moderable(session, user, collection_id, geo_limits)
    sub = _get_submission(session, col, submission_id)
    if sub.status != "pending":
        raise HTTPException(status_code=409, detail="submission already moderated")
    if sub.attachment_key:
        _delete_object(s3, sub.attachment_key)
    sub.status = "rejected"
    sub.moderated_by = user.id
    sub.moderated_at = datetime.now(UTC).replace(tzinfo=None)
    sub.reject_reason = body.reason or None
    # Donnée personnelle citoyenne inutile : effacée (RGPD).
    sub.payload = {}
    sub.attachment = None
    sub.attachment_key = None
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="submission.reject",
        object_type="submission",
        object_id=sub.id,
        payload={"collection": col.id, "reason": body.reason},
    )
