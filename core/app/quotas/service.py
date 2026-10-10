# SPDX-License-Identifier: Apache-2.0
"""Compteurs et mesure d'usage par tenant (SP-58, GAP-73/GAP-11).

Module volontairement bas dans le contrat de couches (juste après
app.configs — cf. pyproject.toml, contrat "layered architecture") : il doit
pouvoir importer les modèles de presque tout le reste de l'application
(items, collections, users, export, appexport) pour compter/sommer, et doit
être importable par les points de création (configs/collections/attachments/
tileset3d/terrain3d/ingestion routes)."""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException
from sqlalchemy import func, select, text
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
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant_id, User.erased_at.is_(None))
        )
        or 0
    )


def tenant_prefixed_storage_bytes(
    s3, bucket: str, tenant_id: str, prefix: str | None = None
) -> int:
    """Somme les tailles de tous les objets sous le préfixe `{tenant_id}/`
    d'un bucket tenant-préfixé (S3_UPLOADS_BUCKET/S3_ATTACHMENTS_BUCKET/
    S3_TILESET3D_BUCKET/S3_TERRAIN3D_BUCKET, cf. spec §1.4). Pagine
    explicitement : list_objects_v2 tronque à 1000 clés par page — piège
    documenté par la spec (§3.1.2 Tâche 3 Step 2), déjà vécu ailleurs dans
    ce dépôt si oublié."""
    total = 0
    prefix = prefix or f"{tenant_id}/"
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
    COALESCE(...,0) : les lignes historiques (avant migration 0038) ont
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
    # t03b-006 : sorties writer.export (`{tenant}/pipelines/` du bucket des
    # exports, hors byte_size des jobs) et lakehouse CDC (partition tenant).
    # Exclusions assumées et documentées (j08b-012) : lignes PostGIS des
    # collections, miniatures et icônes — non mesurées, donc jamais bloquantes.
    storage += tenant_prefixed_storage_bytes(
        s3,
        os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
        tenant_id,
        prefix=f"{tenant_id}/pipelines/",
    )
    # REV-283e : exports de collection asynchrones (TTL 24 h, mais comptés).
    storage += tenant_prefixed_storage_bytes(
        s3,
        os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
        tenant_id,
        prefix=f"{tenant_id}/data-exports/",
    )
    storage += tenant_prefixed_storage_bytes(
        s3,
        os.environ.get("S3_CDC_BUCKET", "geostudio-cdc"),
        tenant_id,
        prefix=f"cdc/tenant_id={tenant_id}/",
    )
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


class QuotaExceededError(HTTPException):
    """Quota atteint (P26.09, t02-014) : 409 pour un comptage, 413 pour le
    stockage ; rendu en problem+json `type: "quota-exceeded"` (app.main) avec
    `quota`/`current`/`limit` que le shell traduit sans parser le texte."""

    def __init__(self, quota: str, current: int, limit: int, detail: str) -> None:
        super().__init__(status_code=413 if quota == "storage" else 409, detail=detail)
        self.quota, self.current, self.limit = quota, current, limit

    def __str__(self) -> str:
        return str(self.detail)


def quotas_enabled() -> bool:
    """Même lecture que app.auth.dependency.is_quotas_enabled (ce module ne
    peut pas importer app.auth, cf. docstring de tête)."""
    return os.environ.get("CORE_QUOTAS_ENABLED", "false").lower() == "true"


def _lock_tenant_kind(session: Session, tenant_id: str, kind: str) -> None:
    """Sérialise compte-puis-insère par (tenant, kind) jusqu'à la fin de la
    transaction (verrou consultatif PostgreSQL) : deux créations simultanées
    au plafond ne passent plus toutes les deux (TOCTOU, c02-014)."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"quota:{kind}:{tenant_id}"},
        )


def check_quota_or_raise(session: Session, *, tenant_id: str, kind: str) -> None:
    """Lève QuotaExceededError si la limite instance-wide de comptage `kind`
    ("items" ou "collections") serait dépassée par une création de plus.
    Appelée au point unique de création (items.repository.create_item,
    collections.repository.create_collection) : REST, MCP, jobs, moissonnage.
    Sans effet quand CORE_QUOTAS_ENABLED est éteint."""
    if kind not in ("items", "collections"):
        raise ValueError(f"unknown quota kind: {kind}")
    if not quotas_enabled():
        return
    limit = max_items_per_tenant() if kind == "items" else max_collections_per_tenant()
    if limit is None:
        return
    _lock_tenant_kind(session, tenant_id, kind)
    count = count_items_for_tenant if kind == "items" else count_collections_for_tenant
    current = count(session, tenant_id)
    if current >= limit:
        label = "d'items" if kind == "items" else "de collections"
        raise QuotaExceededError(
            kind, current, limit, f"quota {label} du tenant dépassé : {current}/{limit}"
        )


def enforce_storage_quota(
    session: Session, s3, *, tenant_id: str, bucket: str | None = None, key: str | None = None
) -> None:
    """Appelée APRÈS le téléversement : l'objet est déjà dans le bucket, donc
    déjà compté par usage_for_tenant (j08b-003 : plus de double comptage) —
    refus seulement si l'usage réel dépasse la limite (limite+1 octet refusé,
    limite exacte acceptée). Au refus, l'objet fautif est supprimé (j08b-002)
    pour ne pas laisser d'orphelin compté."""
    limit = max_storage_bytes_per_tenant()
    if not quotas_enabled() or limit is None:
        return
    current = usage_for_tenant(session, s3, tenant_id).storage_bytes
    if current > limit:
        if bucket and key:
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception:  # best-effort : le refus prime
                logging.getLogger(__name__).warning("quota: objet %s non supprimé", key)
        raise QuotaExceededError(
            "storage",
            current,
            limit,
            f"quota de stockage du tenant dépassé : {current}/{limit} octets",
        )
