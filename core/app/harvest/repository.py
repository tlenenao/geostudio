# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.harvest.models import HarvestRecord, HarvestSource
from app.harvest.schemas import normalize_source_url
from app.items.models import Item


def _now() -> datetime:
    return datetime.now(UTC)


_RUNNING_RECLAIM_MINUTES = 60


def create_source(
    session: Session,
    *,
    tenant_id: str,
    owner_id: str,
    type: str,
    url: str,
    mode: str,
    enabled: bool,
    interval_minutes: int | None,
) -> HarvestSource:
    source = HarvestSource(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        owner_id=owner_id,
        type=type,
        url=url,
        mode=mode,
        enabled=enabled,
        interval_minutes=interval_minutes,
    )
    session.add(source)
    session.flush()
    return source


def get_source(session: Session, *, tenant_id: str, source_id: str) -> HarvestSource | None:
    return session.scalar(
        select(HarvestSource).where(
            HarvestSource.id == source_id,
            HarvestSource.tenant_id == tenant_id,
        )
    )


def list_sources(session: Session, *, tenant_id: str) -> list[HarvestSource]:
    return list(
        session.scalars(
            select(HarvestSource)
            .where(HarvestSource.tenant_id == tenant_id)
            .order_by(HarvestSource.created_at)
        ).all()
    )


def update_source(session: Session, source: HarvestSource, **fields) -> HarvestSource:
    for key, value in fields.items():
        setattr(source, key, value)
    session.flush()
    return source


def find_duplicate_source(
    session: Session,
    *,
    tenant_id: str,
    type: str,
    url: str,
    exclude_id: str | None = None,
) -> HarvestSource | None:
    # La course entre deux POST simultanés est bornée par l'index unique
    # uq_harvest_sources_tenant_type_url (0046) → 409 dans les routes.
    # ponytail: comparaison normalisée en Python sur les sources du tenant et
    # du type (quelques dizaines) ; colonne normalisée indexée si ça grossit.
    stmt = select(HarvestSource).where(
        HarvestSource.tenant_id == tenant_id, HarvestSource.type == type
    )
    if exclude_id is not None:
        stmt = stmt.where(HarvestSource.id != exclude_id)
    wanted = normalize_source_url(url)
    for source in session.scalars(stmt):
        if normalize_source_url(source.url) == wanted:
            return source
    return None


def delete_source(session: Session, source: HarvestSource) -> int:
    """Supprime la source, ses enregistrements (cascade) et les items `external`
    qu'elle avait créés (mode référence). Les items d'une copie (jeux de données
    réels) sont conservés. Retourne le nombre d'items retirés (j07-007)."""
    item_ids = list(
        session.scalars(
            select(HarvestRecord.item_id)
            .join(Item, Item.id == HarvestRecord.item_id)
            .where(
                HarvestRecord.source_id == source.id,
                HarvestRecord.tenant_id == source.tenant_id,
                Item.resource_type == "external",
            )
        ).all()
    )
    session.delete(source)
    session.flush()
    if item_ids:
        session.execute(sa_delete(Item).where(Item.id.in_(item_ids)))
    return len(item_ids)


def record_counts(
    session: Session, *, tenant_id: str, source_ids: list[str]
) -> dict[str, tuple[int, int]]:
    """source_id -> (total, stale) en une seule requête."""
    if not source_ids:
        return {}
    rows = session.execute(
        select(
            HarvestRecord.source_id,
            func.count(),
            func.count().filter(HarvestRecord.is_stale.is_(True)),
        )
        .where(HarvestRecord.tenant_id == tenant_id, HarvestRecord.source_id.in_(source_ids))
        .group_by(HarvestRecord.source_id)
    ).all()
    return {sid: (total, stale) for sid, total, stale in rows}


def list_source_records(
    session: Session, *, tenant_id: str, source_id: str, limit: int, offset: int
) -> list[HarvestRecord]:
    return list(
        session.scalars(
            select(HarvestRecord)
            .where(HarvestRecord.tenant_id == tenant_id, HarvestRecord.source_id == source_id)
            .order_by(HarvestRecord.external_id)
            .limit(limit)
            .offset(offset)
        ).all()
    )


def _is_stale_running(source: HarvestSource, now: datetime) -> bool:
    """Run « running » présumé planté (crash entre le commit de mark_running et
    la fin de harvest_source) : plus vieux que _RUNNING_RECLAIM_MINUTES."""
    updated = source.updated_at
    if updated is not None and updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return updated is not None and (now - updated) >= timedelta(minutes=_RUNNING_RECLAIM_MINUTES)


def is_run_active(source: HarvestSource) -> bool:
    """Source « running » et non périmée : un nouveau run serait un no-op."""
    return source.last_status == "running" and not _is_stale_running(source, _now())


def _refresh(session: Session, source_id: str) -> None:
    # l'UPDATE en masse ne rafraîchit pas l'objet déjà chargé dans la session
    loaded = session.get(HarvestSource, source_id)
    if loaded is not None:
        session.refresh(loaded)


def mark_running(session: Session, *, tenant_id: str, source_id: str) -> bool:
    """REV-295 : prise conditionnelle (UPDATE ... WHERE, jumelle de
    pipelines.repository.mark_running). False si la source est inconnue,
    étrangère au tenant, ou déjà « running » et non périmée : l'appelant sort
    sans moissonner."""
    claim = update(HarvestSource).where(
        HarvestSource.id == source_id, HarvestSource.tenant_id == tenant_id
    )
    result = session.execute(
        claim.where(
            (HarvestSource.last_status.is_(None)) | (HarvestSource.last_status != "running")
        )
        .values(last_status="running")
        .execution_options(synchronize_session=False)
    )
    if result.rowcount:  # type: ignore[attr-defined]
        _refresh(session, source_id)
        return True
    source = get_source(session, tenant_id=tenant_id, source_id=source_id)
    if source is None or not _is_stale_running(source, _now()):
        return False
    # compare-and-swap : seul le worker dont la lecture périmée est encore
    # exacte (updated_at inchangé) reprend la source.
    result = session.execute(
        claim.where(
            HarvestSource.last_status == "running",
            HarvestSource.updated_at == source.updated_at,
        )
        .values(last_status="running")
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:  # type: ignore[attr-defined]
        return False
    _refresh(session, source_id)
    return True


def get_record(
    session: Session,
    *,
    tenant_id: str,
    source_id: str,
    external_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.source_id == source_id,
            HarvestRecord.external_id == external_id,
        )
    )


def create_record(
    session: Session,
    *,
    tenant_id: str,
    source_id: str,
    external_id: str,
    item_id: str | None,
    collection_id: str | None,
    content_hash: str | None,
    external_url: str | None = None,
    tiles_url: str | None = None,
    layer_kind: str | None = None,
) -> HarvestRecord:
    record = HarvestRecord(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        source_id=source_id,
        external_id=external_id,
        item_id=item_id,
        collection_id=collection_id,
        content_hash=content_hash,
        external_url=external_url,
        tiles_url=tiles_url,
        layer_kind=layer_kind,
    )
    session.add(record)
    session.flush()
    return record


def update_record(session: Session, record: HarvestRecord, **fields) -> HarvestRecord:
    for key, value in fields.items():
        setattr(record, key, value)
    session.flush()
    return record


def mark_missing_as_stale(
    session: Session,
    *,
    tenant_id: str,
    source_id: str,
    seen_external_ids: set[str],
) -> None:
    records = session.scalars(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.source_id == source_id,
        )
    ).all()
    for record in records:
        if record.external_id not in seen_external_ids and not record.is_stale:
            record.is_stale = True
    session.flush()


_LIST_RECORDS_LIMIT = 1000  # même plafond que _MAX_LIMIT (app.harvest.routes) —
# garde-fou de volumétrie immédiat (GAP-64.2, SP-49), pas la pagination
# complète de GAP-57 (curseur, page/page_size), hors périmètre ici.


def list_layer_records(session: Session, *, tenant_id: str, q: str | None = None):
    stmt = (
        select(HarvestRecord.item_id, Item.title, HarvestRecord.tiles_url, HarvestRecord.layer_kind)
        .join(Item, Item.id == HarvestRecord.item_id)
        .where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.tiles_url.is_not(None),
        )
    )
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    stmt = stmt.limit(_LIST_RECORDS_LIMIT)
    return list(session.execute(stmt).all())


def get_feature_layer_record(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.item_id == item_id,
            HarvestRecord.layer_kind == "feature",
        )
    )


def list_feature_layer_records(session: Session, *, tenant_id: str, q: str | None = None):
    stmt = (
        select(HarvestRecord.item_id, Item.title, HarvestRecord.external_url)
        .join(Item, Item.id == HarvestRecord.item_id)
        .where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.layer_kind == "feature",
        )
    )
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    stmt = stmt.limit(_LIST_RECORDS_LIMIT)
    return list(session.execute(stmt).all())


_BACKOFF_CAP = timedelta(hours=24)


def _effective_interval(source: HarvestSource) -> timedelta:
    """REV-276d : intervalle × 2^échecs consécutifs, plafonné à max(intervalle, 24 h)."""
    base = timedelta(minutes=source.interval_minutes)
    failures = source.consecutive_failures or 0
    if failures <= 0:
        return base
    return min(base * 2 ** min(failures, 10), max(base, _BACKOFF_CAP))


def list_due_sources(session: Session) -> list[HarvestSource]:
    now = _now()
    candidates = session.scalars(
        select(HarvestSource).where(
            HarvestSource.enabled.is_(True),
            HarvestSource.interval_minutes.is_not(None),
        )
    ).all()
    due = []
    for source in candidates:
        if source.last_status == "running":
            # Une source déjà en cours de moissonnage est sautée pour éviter un
            # double-travail concurrent (gap 2-phase-commit : crash entre le
            # passage à "running" — committé par mark_running — et la fin de
            # harvest_source). Reclaim par âge : si le run est plus vieux que
            # _RUNNING_RECLAIM_MINUTES, il est présumé planté et redevient
            # éligible — sinon un crash la coincerait en "running" à jamais.
            if not _is_stale_running(source, now):
                continue
            due.append(source)
            continue
        if source.last_run_at is None:
            due.append(source)
            continue
        last_run_at = source.last_run_at
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=UTC)
        threshold = last_run_at + _effective_interval(source)
        if threshold <= now:
            due.append(source)
    return due
