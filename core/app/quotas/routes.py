# SPDX-License-Identifier: Apache-2.0
"""GET /admin/usage (SP-58 Tâche 3, GAP-73/GAP-11).

get_s3_client est un STUB PROPRE à ce module, redéfini localement (pas
importé d'app.ingestion.routes) — même patron que app.attachments.routes/
app.collections.routes (cf. leurs docstrings de tête) : app.quotas est placé
juste sous app.configs dans le contrat de couches, plus bas qu'app.ingestion,
donc importer son get_s3_client demanderait une exemption qu'un stub local
évite complètement."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.quotas.service import usage_for_tenant
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


@router.get("/admin/usage", response_model=UsageSnapshotResponse)
def get_usage(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
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
    )
