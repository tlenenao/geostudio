# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.harvest.models import HarvestRecord, HarvestSource


def _now() -> datetime:
    return datetime.now(timezone.utc)


_RUNNING_RECLAIM_MINUTES = 60


def create_source(
    session: Session, *, tenant_id: str, owner_id: str, type: str, url: str,
    mode: str, enabled: bool, interval_minutes: int | None,
) -> HarvestSource:
    source = HarvestSource(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id, type=type,
        url=url, mode=mode, enabled=enabled, interval_minutes=interval_minutes,
    )
    session.add(source)
    session.flush()
    return source


def get_source(session: Session, *, tenant_id: str, source_id: str) -> HarvestSource | None:
    return session.scalar(
        select(HarvestSource).where(
            HarvestSource.id == source_id, HarvestSource.tenant_id == tenant_id,
        )
    )


def list_sources(session: Session, *, tenant_id: str) -> list[HarvestSource]:
    return list(session.scalars(
        select(HarvestSource)
        .where(HarvestSource.tenant_id == tenant_id)
        .order_by(HarvestSource.created_at)
    ).all())


def update_source(session: Session, source: HarvestSource, **fields) -> HarvestSource:
    for key, value in fields.items():
        setattr(source, key, value)
    session.flush()
    return source


def delete_source(session: Session, source: HarvestSource) -> None:
    session.delete(source)
    session.flush()


def mark_running(session: Session, *, tenant_id: str, source_id: str) -> None:
    source = get_source(session, tenant_id=tenant_id, source_id=source_id)
    if source is None:
        return
    source.last_status = "running"
    session.flush()


def get_record(
    session: Session, *, tenant_id: str, source_id: str, external_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.source_id == source_id,
            HarvestRecord.external_id == external_id,
        )
    )


def create_record(
    session: Session, *, tenant_id: str, source_id: str, external_id: str,
    item_id: str | None, collection_id: str | None, content_hash: str | None,
) -> HarvestRecord:
    record = HarvestRecord(
        id=uuid.uuid4().hex, tenant_id=tenant_id, source_id=source_id,
        external_id=external_id, item_id=item_id, collection_id=collection_id,
        content_hash=content_hash,
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
    session: Session, *, tenant_id: str, source_id: str, seen_external_ids: set[str],
) -> None:
    records = session.scalars(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id, HarvestRecord.source_id == source_id,
        )
    ).all()
    for record in records:
        if record.external_id not in seen_external_ids and not record.is_stale:
            record.is_stale = True
    session.flush()


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
            updated = source.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated is None or (now - updated) < timedelta(minutes=_RUNNING_RECLAIM_MINUTES):
                continue
            due.append(source)
            continue
        if source.last_run_at is None:
            due.append(source)
            continue
        last_run_at = source.last_run_at
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        threshold = last_run_at + timedelta(minutes=source.interval_minutes)
        if threshold <= now:
            due.append(source)
    return due
