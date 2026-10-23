# SPDX-License-Identifier: Apache-2.0
"""Soumission publique modérée (ARC-10, ADR 0017).

Un seul chemin d'écriture anonyme : `POST /public/submit/{token}`, qui ne fait
qu'INSÉRER une soumission en attente dans `submissions` (jamais dans la table de la
collection). Modération et gestion des jetons : authentifiées, droit d'écriture."""

import copy
import json
import re
import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
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
from app.collect import pow as collect_pow
from app.collect.kit import build_kit, if_none_match_hits
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
from app.public_submit.models import Submission, SubmissionFile, SubmissionToken
from app.quotas.service import enforce_storage_quota
from app.ratelimit.limiter import ip_bucket
from app.relations import service as relations_service
from app.sharing.geo_limits import refuse_if_geo_limited
from app.upload_sniff import HEAD_BYTES, allowed_for_kind, looks_executable, sniff_content_type

router = APIRouter()

_ACCEPTED = {"status": "pending"}
_CLIENT_OP_RE = re.compile(r"[0-9a-fA-F-]{32,40}")


# --------------------------------------------------------------------------- public


@router.post("/public/submit/{token}", status_code=202)
def submit(
    token: str,
    request: Request,
    payload: str = Form(..., description="GeoJSON Feature (JSON)"),
    website: str = Form("", description="honeypot : doit rester vide"),
    fieldKey: str | None = Form(None),  # noqa: N803
    # fieldKeys : un par fichier de `files`, dans l'ordre
    fieldKeys: list[str] | None = Form(None),  # noqa: N803, B008
    clientOpId: str | None = Form(None),  # noqa: N803
    powChallenge: str | None = Form(None),  # noqa: N803
    powNonce: str | None = Form(None),  # noqa: N803
    file: UploadFile | None = File(None),
    files: list[UploadFile] = File(default=[]),
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
    if clientOpId is not None and not _CLIENT_OP_RE.fullmatch(clientOpId):
        raise _validation_error(
            [{"field": "clientOpId", "code": "invalid", "message": "clientOpId must be a UUID"}]
        )
    if service.find_replay(session, row, clientOpId):
        return _ACCEPTED  # rejeu hors-ligne : déjà reçue, aucun slot ni fichier de plus
    if not collect_pow.disabled() and not collect_pow.verify(
        row.token_prefix, powChallenge or "", powNonce or ""
    ):
        raise HTTPException(status_code=403, detail="proof of work missing, invalid or expired")
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
    uploads = [f for f in ([file] if file is not None else []) + files if f.filename]
    if len(uploads) > service.MAX_FILES:
        raise HTTPException(status_code=400, detail=f"at most {service.MAX_FILES} files")
    keys = list(fieldKeys or []) if fieldKeys else [fieldKey] * len(uploads)
    if len(keys) != len(uploads):
        raise HTTPException(status_code=400, detail="fieldKeys must match the files one to one")
    # Quota réservé AVANT tout envoi S3 : un jeton épuisé n'écrit rien. Le tout dans un
    # SAVEPOINT : un échec (fichier refusé, S3, course sur clientOpId) annule la réservation.
    stored: list[tuple[dict, str]] = []
    try:
        with session.begin_nested():
            if not service.reserve_slot(session, row):
                raise HTTPException(status_code=429, detail="submission quota exhausted")
            total = 0
            for up, key_name in zip(uploads, keys, strict=True):
                meta, s3_key = _store_attachment(
                    session, s3, col, up, key_name, max_bytes=service.MAX_FILE_BYTES
                )
                stored.append((meta, s3_key))
                total += meta["byteSize"]
                if total > service.MAX_TOTAL_BYTES:
                    raise HTTPException(status_code=413, detail="files too large (> 25 MB total)")
            service.create_submission(
                session,
                token=row,
                payload={
                    "properties": feature.get("properties") or {},
                    "geometry": feature.get("geometry"),
                },
                files=stored,
                client_op_id=clientOpId,
            )
    except IntegrityError:
        for _meta, k in stored:
            _delete_object(s3, k)
        return _ACCEPTED  # course sur le même clientOpId : l'autre requête a gagné
    except Exception:
        for _meta, k in stored:
            _delete_object(s3, k)
        raise
    service.token_limiter.allow(token)  # revue SP-L2 I4 : seule une soumission acceptée compte
    service.notify_moderators(session, col)
    return _ACCEPTED


def _usable_token(session: Session, token: str) -> SubmissionToken:
    """Mêmes garanties que le POST : 404 jeton inconnu, 410 expiré/révoqué ; ne décompte aucun
    slot. Budget par IP : groupe `public-submit` du middleware (le kit et le défi y sont inclus,
    donc le brute-force du jeton n'est jamais gratuit)."""
    row = service.find_token(session, token)
    if row is None:
        raise HTTPException(status_code=404, detail="submission link not found")
    if not service.token_is_usable(row):
        raise HTTPException(status_code=410, detail="submission link expired or revoked")
    return row


@router.get("/public/submit/{token}/kit")
def public_kit(
    token: str,
    request: Request,
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
):
    """Kit de collecte public (L8) : schéma sans nom de table ni champ sensible, aucune donnée."""
    row = _usable_token(session, token)
    col = get_collection(session, tenant_id=row.tenant_id, collection_id=row.collection_id)
    if col is None or not col.editable:
        raise HTTPException(status_code=410, detail="submission link expired or revoked")
    kit = build_kit(session, col, introspect, sees_sensitive=False, public=True)
    headers = {"ETag": f'"{kit["etag"]}"', "Cache-Control": "private, no-cache"}
    if if_none_match_hits(request.headers.get("if-none-match"), kit["etag"]):
        return Response(status_code=304, headers=headers)
    return Response(content=json.dumps(kit), media_type="application/json", headers=headers)


@router.get("/public/submit/{token}/challenge")
def public_challenge(
    token: str,
    session: Session = Depends(get_session, scope="function"),
):
    """Défi de preuve de travail (hashcash) à joindre au POST ; jamais mis en cache."""
    row = _usable_token(session, token)
    return Response(
        content=json.dumps(
            {**collect_pow.issue(row.token_prefix), "required": not collect_pow.disabled()}
        ),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def _delete_object(s3, key: str) -> None:
    try:
        s3.delete_object(Bucket=get_attachments_bucket(), Key=key)
    except ClientError:  # best-effort
        pass


def _store_attachment(
    session,
    s3,
    col: Collection,
    file: UploadFile,
    field_key: str | None,
    *,
    max_bytes: int = MAX_ATTACHMENT_BYTES,
):
    declared = [f["key"] for f in col.attachment_fields]
    if not declared:
        raise HTTPException(status_code=400, detail="this collection does not accept attachments")
    key_name = field_key or (declared[0] if len(declared) == 1 else None)
    if key_name not in declared:
        raise HTTPException(status_code=400, detail=f"unknown attachment field: {field_key}")
    filename = file.filename or "fichier"
    _reject_dangerous_extension(filename)
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"fichier trop volumineux (> {max_bytes // (1024 * 1024)} Mo)"
        )
    content_type = sniff_content_type(data[:HEAD_BYTES])
    kind = next((f.get("kind") for f in col.attachment_fields if f["key"] == key_name), None)
    if looks_executable(data[:HEAD_BYTES]) or not allowed_for_kind(content_type, kind):
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


def _files_by_submission(session: Session, ids: list[str]) -> dict[str, list[SubmissionFile]]:
    out: dict[str, list[SubmissionFile]] = {}
    if not ids:
        return out
    for f in session.scalars(
        select(SubmissionFile)
        .where(SubmissionFile.submission_id.in_(ids))
        .order_by(SubmissionFile.id)
    ):
        out.setdefault(f.submission_id, []).append(f)
    return out


def _file_json(f: SubmissionFile) -> dict:
    meta = f.attachment or {}
    return {
        "id": f.id,
        "fieldKey": f.field_key,
        "filename": meta.get("filename"),
        "contentType": meta.get("contentType"),
        "byteSize": meta.get("byteSize"),
    }


def _submission_json(s: Submission, files: list[SubmissionFile] | None = None) -> dict:
    return {
        "id": s.id,
        "status": s.status,
        "properties": (s.payload or {}).get("properties", {}),
        "geometry": (s.payload or {}).get("geometry"),
        # compat : l'ancien champ unique reste renseigné (premier fichier), clients d'avant L8
        "attachment": s.attachment
        or next((f.attachment for f in files or [] if f.attachment), None),
        "files": [_file_json(f) for f in files or [] if f.attachment],
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
    ).all()
    files = _files_by_submission(session, [r.id for r in rows])
    return {"submissions": [_submission_json(r, files.get(r.id)) for r in rows]}


@router.get("/collections/{collection_id}/submissions/{submission_id}/attachment")
def read_submission_attachment(
    collection_id: str,
    submission_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
    geo_limits=Depends(get_request_geo_limits),
    fileId: str | None = Query(default=None),  # noqa: N803  (L8 : un des fichiers multiples)
):
    col = _get_moderable(session, user, collection_id, geo_limits)
    sub = _get_submission(session, col, submission_id)
    meta, key = sub.attachment, sub.attachment_key
    if fileId is not None:
        f = session.get(SubmissionFile, fileId)
        if f is None or f.submission_id != sub.id:
            raise HTTPException(status_code=404, detail="attachment not found")
        meta, key = f.attachment, f.attachment_key
    elif not meta:  # compat : sans fileId, le premier fichier (anciens clients de la modération)
        first = next(iter(_files_by_submission(session, [sub.id]).get(sub.id, [])), None)
        if first is not None:
            meta, key = first.attachment, first.attachment_key
    if sub.status != "pending" or not key or not meta:
        raise HTTPException(status_code=404, detail="attachment not found")
    try:
        obj = s3.get_object(Bucket=get_attachments_bucket(), Key=key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="attachment file not found") from exc
    return Response(
        content=obj["Body"].read(),
        media_type=meta["contentType"],
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
    # AUD-165 : clé étrangère logique des relations, comme le POST REST (422/409).
    relations_service.check_write(session, user, col, feature.get("properties") or {}, None, rls)
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
    for meta, key in _submission_attachments(session, sub):
        attachments_repo.create_attachment(
            session,
            tenant_id=col.tenant_id,
            collection_id=col.id,
            fid=str(fid),
            field_key=meta["fieldKey"],
            filename=meta["filename"],
            content_type=meta["contentType"],
            byte_size=meta["byteSize"],
            s3_key=key,
            created_by=user.id,
        )
    for f in session.scalars(select(SubmissionFile).where(SubmissionFile.submission_id == sub.id)):
        f.attachment = None  # attachment_key conservée : la pièce jointe reste vivante
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


def _submission_attachments(session: Session, sub: Submission) -> list[tuple[dict, str]]:
    """Tous les fichiers d'une soumission : ancienne colonne (avant L8) puis `submission_files`."""
    out: list[tuple[dict, str]] = []
    if sub.attachment and sub.attachment_key:
        out.append((sub.attachment, sub.attachment_key))
    for f in session.scalars(
        select(SubmissionFile)
        .where(SubmissionFile.submission_id == sub.id)
        .order_by(SubmissionFile.id)
    ):
        if f.attachment and f.attachment_key:
            out.append((f.attachment, f.attachment_key))
    return out


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
    for f in session.scalars(select(SubmissionFile).where(SubmissionFile.submission_id == sub.id)):
        if f.attachment_key:
            _delete_object(s3, f.attachment_key)
        f.attachment = None
        f.attachment_key = None
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
