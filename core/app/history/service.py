# SPDX-License-Identifier: Apache-2.0
"""Journal d'entité (ARC-15). Les fonctions écrivent dans la session de l'appelant :
le journal est donc dans la MÊME transaction que l'écriture qu'il décrit (commit ou
rollback communs). À appeler HORS `rls_scope` (rôle propriétaire : `entity_history`
n'est pas accordée à gis_rls).

Limites connues (revue finale vague 1 ARC) :
- sont journalisées : les écritures REST (`app.features.routes`), l'approbation d'une
  soumission publique et, pour `writer.collection`, les mises à jour et suppressions
  (modes upsert/update/delete) ; les créations d'un upsert/append et l'import en ajout
  (`app.ingestion.importer.run_append`) ne le sont pas ;
- l'import en ajout ne met pas non plus à jour `collections.feature_count`."""

from datetime import UTC, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.history.models import EntityHistory

# Quota : versions conservées par entité (les plus anciennes sont purgées à l'écriture).
MAX_VERSIONS_PER_ENTITY = 200
# ponytail: rétention fixe ; à rendre configurable (compose par valeur) si un tenant l'exige
RETENTION_DAYS = 365


def snapshot(feature: dict | None) -> dict | None:
    """Feature GeoJSON -> instantané {properties, geometry} (sans id)."""
    if feature is None:
        return None
    # Colonnes date/numeric/uuid : la colonne `before`/`after` est JSON, pas le driver.
    return jsonable_encoder(
        {"properties": feature.get("properties") or {}, "geometry": feature.get("geometry")}
    )


def mask_snapshot(snap: dict | None, masked_fields: frozenset[str]) -> dict | None:
    """GAP-22 : un champ masqué le reste dans l'historique."""
    if snap is None or not masked_fields:
        return snap
    props = {k: v for k, v in (snap.get("properties") or {}).items() if k not in masked_fields}
    return {**snap, "properties": props}


def record_change(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    op: str,
    before: dict | None,
    after: dict | None,
    actor_id: str | None,
) -> EntityHistory:
    row = EntityHistory(
        tenant_id=tenant_id,
        collection_id=collection_id,
        fid=str(fid),
        op=op,
        before=before,
        after=after,
        actor_id=actor_id,
    )
    session.add(row)
    session.flush()
    # Quota par entité : on ne garde que les MAX_VERSIONS_PER_ENTITY dernières.
    cutoff = session.scalars(
        select(EntityHistory.id)
        .where(EntityHistory.collection_id == collection_id, EntityHistory.fid == str(fid))
        .order_by(EntityHistory.id.desc())
        .offset(MAX_VERSIONS_PER_ENTITY)
        .limit(1)
    ).first()
    if cutoff is not None:
        session.execute(
            delete(EntityHistory).where(
                EntityHistory.collection_id == collection_id,
                EntityHistory.fid == str(fid),
                EntityHistory.id <= cutoff,
            )
        )
    return row


def list_entity_history(
    session: Session, *, tenant_id: str, collection_id: str, fid: str
) -> list[EntityHistory]:
    return list(
        session.scalars(
            select(EntityHistory)
            .where(
                EntityHistory.tenant_id == tenant_id,
                EntityHistory.collection_id == collection_id,
                EntityHistory.fid == str(fid),
            )
            .order_by(EntityHistory.id.desc())
        )
    )


def get_version(
    session: Session, *, tenant_id: str, collection_id: str, fid: str, version_id: int
) -> EntityHistory | None:
    return session.scalar(
        select(EntityHistory).where(
            EntityHistory.id == version_id,
            EntityHistory.tenant_id == tenant_id,
            EntityHistory.collection_id == collection_id,
            EntityHistory.fid == str(fid),
        )
    )


def list_changes_since(
    session: Session, *, tenant_id: str, collection_id: str, since: datetime, limit: int
) -> list[EntityHistory]:
    return list(
        session.scalars(
            select(EntityHistory)
            .where(
                EntityHistory.tenant_id == tenant_id,
                EntityHistory.collection_id == collection_id,
                EntityHistory.created_at > since,
            )
            .order_by(EntityHistory.id)
            .limit(limit)
        )
    )


def purge_expired(session: Session, *, now: datetime | None = None) -> int:
    """Rétention : supprime le journal plus vieux que 365 jours."""
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).replace(tzinfo=None)
    return session.execute(delete(EntityHistory).where(EntityHistory.created_at < cutoff)).rowcount


def erase_actor(session: Session, *, tenant_id: str, user_id: str) -> int:
    """Anonymisation SP-58 : efface l'auteur du journal (les versions survivent)."""
    return session.execute(
        update(EntityHistory)
        .where(EntityHistory.tenant_id == tenant_id, EntityHistory.actor_id == user_id)
        .values(actor_id=None)
    ).rowcount
