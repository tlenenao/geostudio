# SPDX-License-Identifier: Apache-2.0
import os
import uuid
from collections.abc import Callable

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion import repository as repo
from app.ingestion.parsers import IngestionParseError, list_layers, read_xlsx_header_fields
from app.ingestion.schemas import (
    IngestionJobCreate,
    IngestionJobCreated,
    IngestionJobStatus,
    InspectRequest,
    InspectResponse,
    LayerInfoOut,
    PresignRequest,
    PresignResponse,
)
from app.ingestion.storage import (
    download_object,
    ensure_uploads_bucket,
    generate_presigned_put_url,
)
from app.ingestion.tasks import run_ingestion_task
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


def get_uploads_bucket() -> str:
    return os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")


# Hors périmètre SP-7 (revue finale de branche, finding Important) : ce
# `.defer(...)` suppose que le connecteur de app.jobs.app est ouvert, ce qui
# n'est pas garanti dans le process FastAPI du cœur (contrairement au worker,
# rien n'ouvre explicitement l'App procrastinate dans core/app/main.py) — un
# déploiement réel peut voir POST /uploads échouer avec AppNotOpen. SP-7 a
# rencontré et corrigé le même risque pour les nouveaux enqueues d'embedding
# (voir le wrapper fail-open app/items/repository.py::_enqueue_embedding),
# mais n'a pas touché ce call site pré-existant de SP-6a : le fixer (ouvrir
# app.jobs.app dans le lifespan, ou appliquer le même wrapper fail-open ici)
# est un changement de comportement distinct, à traiter séparément.
def get_task_deferrer() -> Callable[[str, str], None]:
    def deferrer(job_id: str, tenant_id: str) -> None:
        run_ingestion_task.defer(job_id=job_id, tenant_id=tenant_id)

    return deferrer


@router.post("/uploads/presign", response_model=PresignResponse)
def presign_upload(
    body: PresignRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_uploads_bucket),
) -> PresignResponse:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type=body.contentType)
    return PresignResponse(uploadUrl=url, key=key)


@router.post("/uploads/inspect", response_model=InspectResponse)
def inspect_upload(
    body: InspectRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_uploads_bucket),
) -> InspectResponse:
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    try:
        content = download_object(s3, bucket=bucket, key=body.key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc
    if body.filename.lower().endswith(".xlsx"):
        try:
            fields = read_xlsx_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
    try:
        layers = list_layers(content, body.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InspectResponse(
        layers=[
            LayerInfoOut(
                name=layer.name, featureCount=layer.feature_count, geometryType=layer.geometry_type
            )
            for layer in layers
        ]
    )


@router.post("/uploads", response_model=IngestionJobCreated, status_code=201)
def create_upload_job(
    body: IngestionJobCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> IngestionJobCreated:
    # SP-42, correctif 1 (F-securite-autorisation-01) : ce job exécute du DDL
    # (création de table PostGIS) au worker — réservé à data.manage, comme
    # POST /collections/empty (Créateur l'a, Lecteur non).
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    # SP-42, revue de la dernière passe de correctifs (point 5, Important) :
    # app.ingestion.importer::import_job crée AUSSI un
    # Item(resource_type="map") + Config(kind="map") pour afficher le
    # résultat (app.roles.kind_registry::privilege_for_kind mappe "map" sur
    # maps.manage) — la garde ci-dessus ne couvrait que la moitié de ce que
    # cette route crée réellement.
    require_privilege(session, user, Privilege.MAPS_MANAGE.value)
    # La clé est censée venir du présigné (/uploads/presign), qui la préfixe
    # toujours par le tenant de l'appelant — un client qui en soumet une
    # sous le préfixe d'un AUTRE tenant (deviné, réutilisé depuis une fuite,
    # etc.) ferait sinon lire par le worker un objet S3 hors de son tenant
    # (confused deputy) sous son propre job/collection/tenant courant.
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    job = repo.create_job(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        source_key=body.key,
        filename=body.filename,
        collection_title=body.collectionTitle,
        lat_field=body.latField,
        lon_field=body.lonField,
        layer_name=body.layerName,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="ingestion.job_create",
        object_type="ingestion_job",
        object_id=job.id,
        payload={"filename": body.filename, "collectionTitle": body.collectionTitle},
    )
    # Commit avant de déférer : procrastinate insère la tâche via sa propre
    # connexion, hors de cette transaction SQLAlchemy — un worker pourrait la
    # ramasser avant le commit implicite de fin de requête et ne pas trouver
    # la ligne ingestion_jobs (job "zombie", l'inverse du critère
    # d'acceptation SP-6a). Commit explicite ici pour que la ligne soit
    # visible avant que la tâche n'existe.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return IngestionJobCreated(jobId=job.id)


@router.get("/uploads/{job_id}", response_model=IngestionJobStatus)
def get_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IngestionJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestionJobStatus(
        status=job.status,
        errorMessage=job.error_message,
        collectionId=job.collection_id,
        itemId=job.item_id,
    )
