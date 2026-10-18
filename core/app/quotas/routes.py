# SPDX-License-Identifier: Apache-2.0
"""GET /admin/usage (SP-58 Tâche 3, GAP-73/GAP-11).

get_s3_client est un STUB PROPRE à ce module, redéfini localement (pas
importé d'app.ingestion.routes) — même patron que app.attachments.routes/
app.collections.routes (cf. leurs docstrings de tête) : app.quotas est placé
juste sous app.configs dans le contrat de couches, plus bas qu'app.ingestion,
donc importer son get_s3_client demanderait une exemption qu'un stub local
évite complètement."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.quotas.models import TenantLimits
from app.quotas.service import (
    max_active_runs_per_tenant,
    max_collections_per_tenant,
    max_items_per_tenant,
    max_storage_bytes_per_tenant,
    max_users_per_tenant,
    usage_for_tenant,
)
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


class UsageSnapshotResponse(BaseModel):
    itemCount: int
    collectionCount: int
    userCount: int
    storageBytes: int
    maxItems: int | None
    maxCollections: int | None
    maxStorageBytes: int | None
    maxUsers: int | None
    maxActiveRuns: int | None


@router.get("/admin/usage", response_model=UsageSnapshotResponse)
def get_usage(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    s3=Depends(get_s3_client),
) -> UsageSnapshotResponse:
    # SETTINGS_INSTANCE_MANAGE (§1.7 de la spec) : privilège le plus proche
    # par nature (action instance-wide, réservée aux opérateurs de tenant),
    # décision confirmée à l'exécution du plan plutôt qu'un privilège dédié
    # admin.quotas.view (cf. spec §6) — pas de besoin identifié de séparer
    # la lecture d'usage de la passerelle admin-tools existante.
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    snapshot = usage_for_tenant(session, s3, user.tenant_id)
    return UsageSnapshotResponse(
        itemCount=snapshot.item_count,
        collectionCount=snapshot.collection_count,
        userCount=snapshot.user_count,
        storageBytes=snapshot.storage_bytes,
        maxItems=max_items_per_tenant(session, user.tenant_id),
        maxCollections=max_collections_per_tenant(session, user.tenant_id),
        maxStorageBytes=max_storage_bytes_per_tenant(session, user.tenant_id),
        maxUsers=max_users_per_tenant(session, user.tenant_id),
        maxActiveRuns=max_active_runs_per_tenant(session, user.tenant_id),
    )


_Limit = int | None


class TenantLimitsBody(BaseModel):
    """SP-L4 : plafonds propres au tenant ; `null` retombe sur la limite d'instance."""

    maxItems: _Limit = Field(default=None, ge=0)
    maxCollections: _Limit = Field(default=None, ge=0)
    maxStorageBytes: _Limit = Field(default=None, ge=0)
    maxUsers: _Limit = Field(default=None, ge=0)
    maxActiveRuns: _Limit = Field(default=None, ge=0)


_COLUMNS = {
    "maxItems": "max_items",
    "maxCollections": "max_collections",
    "maxStorageBytes": "max_storage_bytes",
    "maxUsers": "max_users",
    "maxActiveRuns": "max_active_runs",
}


@router.put("/admin/usage/limits", response_model=TenantLimitsBody)
def put_tenant_limits(
    body: TenantLimitsBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> TenantLimitsBody:
    """Remplace les plafonds du tenant de l'appelant (PUT complet, audité)."""
    require_privilege(session, user, Privilege.ADMIN_QUOTAS_MANAGE.value)
    row = session.get(TenantLimits, user.tenant_id)
    if row is None:
        row = TenantLimits(tenant_id=user.tenant_id)
        session.add(row)
    values = body.model_dump()
    for field, column in _COLUMNS.items():
        setattr(row, column, values[field])
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="tenant_limits.update",
        object_type="tenant",
        object_id=user.tenant_id,
        payload=values,
    )
    session.commit()
    return body
