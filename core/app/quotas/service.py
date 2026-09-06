# SPDX-License-Identifier: Apache-2.0
"""Compteurs et mesure d'usage par tenant (SP-58, GAP-73/GAP-11).

Module volontairement bas dans le contrat de couches (juste après
app.configs — cf. pyproject.toml, contrat "layered architecture") : il doit
pouvoir importer les modèles de presque tout le reste de l'application
(items, collections, users, export, appexport) pour compter/sommer, et doit
être importable par les points de création (configs/collections/attachments/
tileset3d/terrain3d/ingestion routes)."""

from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob
from app.collections.models import Collection
from app.export.models import ExportJob
from app.items.models import Item
from app.users.models import User


def count_items_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(select(func.count()).select_from(Item).where(Item.tenant_id == tenant_id))
        or 0
    )


def count_collections_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Collection).where(Collection.tenant_id == tenant_id)
        )
        or 0
    )


def count_users_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant_id))
        or 0
    )


def tenant_prefixed_storage_bytes(s3, bucket: str, tenant_id: str) -> int:
    """Somme les tailles de tous les objets sous le préfixe `{tenant_id}/`
    d'un bucket tenant-préfixé (S3_UPLOADS_BUCKET/S3_ATTACHMENTS_BUCKET/
    S3_TILESET3D_BUCKET/S3_TERRAIN3D_BUCKET, cf. spec §1.4). Pagine
    explicitement : list_objects_v2 tronque à 1000 clés par page — piège
    documenté par la spec (§3.1.2 Tâche 3 Step 2), déjà vécu ailleurs dans
    ce dépôt si oublié."""
    total = 0
    prefix = f"{tenant_id}/"
    continuation_token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token is not None:
            kwargs["ContinuationToken"] = continuation_token
        page = s3.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            total += obj["Size"]
        if page.get("IsTruncated"):
            continuation_token = page.get("NextContinuationToken")
        else:
            break
    return total


def job_output_storage_bytes(session: Session, tenant_id: str) -> int:
    """Octets cumulés des 2 buckets de sortie de job non tenant-préfixés
    (S3_EXPORTS_BUCKET/S3_APPEXPORTS_BUCKET, cf. spec §1.4) : leurs clés
    portent un job_id, pas un tenant_id, donc pas de préfixe S3 possible —
    on somme la colonne byte_size (Tâche 2) filtrée tenant_id à la place.
    COALESCE(...,0) : les lignes historiques (avant migration 0035) ont
    byte_size NULL, traitées comme 0 (limitation assumée, spec §3.1)."""
    export_total = (
        session.scalar(
            select(func.coalesce(func.sum(ExportJob.byte_size), 0)).where(
                ExportJob.tenant_id == tenant_id
            )
        )
        or 0
    )
    appexport_total = (
        session.scalar(
            select(func.coalesce(func.sum(AppExportJob.byte_size), 0)).where(
                AppExportJob.tenant_id == tenant_id
            )
        )
        or 0
    )
    return export_total + appexport_total


_TENANT_PREFIXED_BUCKET_ENV_VARS_AND_DEFAULTS = (
    ("S3_UPLOADS_BUCKET", "geostudio-uploads"),
    ("S3_ATTACHMENTS_BUCKET", "geostudio-attachments"),
    ("S3_TILESET3D_BUCKET", "geostudio-tileset3d"),
    ("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d"),
)


class UsageSnapshot:
    """Porteur interne, converti en schéma Pydantic par quotas/routes.py
    (GET /admin/usage)."""

    def __init__(
        self,
        *,
        item_count: int,
        collection_count: int,
        user_count: int,
        storage_bytes: int,
    ) -> None:
        self.item_count = item_count
        self.collection_count = collection_count
        self.user_count = user_count
        self.storage_bytes = storage_bytes


def usage_for_tenant(session: Session, s3, tenant_id: str) -> UsageSnapshot:
    """Agrège comptages + stockage. Coût réel : au moins 4 appels S3 paginés
    — pas un chemin à appeler sur chaque requête chaude (spec §3.1.1,
    décision : calcul à la demande, uniquement à GET /admin/usage ou à la
    confirmation d'un upload, jamais en continu)."""
    storage = job_output_storage_bytes(session, tenant_id)
    for env_var, default_bucket in _TENANT_PREFIXED_BUCKET_ENV_VARS_AND_DEFAULTS:
        bucket = os.environ.get(env_var, default_bucket)
        storage += tenant_prefixed_storage_bytes(s3, bucket, tenant_id)
    return UsageSnapshot(
        item_count=count_items_for_tenant(session, tenant_id),
        collection_count=count_collections_for_tenant(session, tenant_id),
        user_count=count_users_for_tenant(session, tenant_id),
        storage_bytes=storage,
    )


def max_items_per_tenant() -> int | None:
    """CORE_QUOTA_MAX_ITEMS_PER_TENANT — None = pas de limite configurée,
    même quand CORE_QUOTAS_ENABLED est actif (spec §3.1, décision : une
    seule limite instance-wide, appliquée identiquement à tout tenant)."""
    raw = os.environ.get("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "")
    return int(raw) if raw else None


def max_collections_per_tenant() -> int | None:
    raw = os.environ.get("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "")
    return int(raw) if raw else None


def max_storage_bytes_per_tenant() -> int | None:
    raw = os.environ.get("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "")
    return int(raw) if raw else None
