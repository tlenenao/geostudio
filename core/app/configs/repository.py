# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from datetime import datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.configs.models import Config, ConfigRevision
from app.configs.schemas import BuilderConfig

logger = logging.getLogger(__name__)


class ConfigRead(BaseModel):
    id: str
    kind: str
    itemId: str | None
    version: int
    config: BuilderConfig


class RevisionInfo(BaseModel):
    version: int
    created_at: datetime


def _to_read(config: Config, revision: ConfigRevision) -> ConfigRead:
    return ConfigRead(
        id=config.id,
        kind=config.kind,
        itemId=config.item_id,
        version=revision.version,
        config=BuilderConfig.model_validate(revision.data),
    )


def _latest_revision(session: Session, config_id: str) -> ConfigRevision | None:
    return session.scalar(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id)
        .order_by(ConfigRevision.version.desc())
    )


def create_config(
    session: Session, config: BuilderConfig, item_id: str | None, *, tenant_id: str
) -> ConfigRead:
    config_id = uuid.uuid4().hex
    record = Config(
        id=config_id,
        tenant_id=tenant_id,
        kind=config.kind,
        item_id=item_id,
        current_version=1,
    )
    revision = ConfigRevision(
        tenant_id=tenant_id,
        config_id=config_id,
        version=1,
        data=config.model_dump(by_alias=True),
    )
    session.add(record)
    session.add(revision)
    session.flush()
    session.refresh(record)
    return _to_read(record, revision)


def get_config(session: Session, config_id: str) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    revision = _latest_revision(session, config_id)
    if revision is None:
        return None
    return _to_read(record, revision)


def get_config_by_item(session: Session, item_id: str) -> ConfigRead | None:
    record = session.scalar(select(Config).where(Config.item_id == item_id))
    if record is None:
        return None
    revision = _latest_revision(session, record.id)
    if revision is None:
        return None
    return _to_read(record, revision)


def list_configs_by_kind(session: Session, kind: str) -> list[tuple[str, str, BuilderConfig]]:
    """Scan cross-tenant (pas de filtre tenant_id) — réservé aux tâches
    système (balayage périodique, SP-15h), jamais exposé via une route :
    contrairement à ConfigRead (response_model public), le tuple retourné
    porte tenant_id en clair."""
    records = session.scalars(select(Config).where(Config.kind == kind)).all()
    result: list[tuple[str, str, BuilderConfig]] = []
    for record in records:
        if record.item_id is None:
            continue
        revision = _latest_revision(session, record.id)
        if revision is None:
            continue
        try:
            config = BuilderConfig.model_validate(revision.data)
        except ValidationError:
            # Une config stockée corrompue (édition manuelle en base,
            # durcissement de schéma depuis l'écriture) ne doit jamais faire
            # planter tout le balayage cross-tenant (SP-15h) : on la
            # journalise et on l'ignore, plutôt que de bloquer le
            # traitement de tous les autres tenants.
            logger.warning(
                "list_configs_by_kind: config invalide ignorée (item_id=%s, tenant_id=%s, kind=%s)",
                record.item_id, record.tenant_id, kind,
            )
            continue
        result.append((record.item_id, record.tenant_id, config))
    return result


def list_configs_by_kind_and_tenant(
    session: Session, *, kind: str, tenant_id: str
) -> list[tuple[str, BuilderConfig]]:
    """Variante tenant-scopée de list_configs_by_kind, sûre à exposer via une
    route (le filtre tenant_id est appliqué en SQL, jamais après coup en
    mémoire) : contrairement à sa sœur cross-tenant, aucune ligne d'un autre
    tenant n'est jamais chargée par le process."""
    records = session.scalars(
        select(Config).where(Config.kind == kind, Config.tenant_id == tenant_id)
    ).all()
    result: list[tuple[str, BuilderConfig]] = []
    for record in records:
        if record.item_id is None:
            continue
        revision = _latest_revision(session, record.id)
        if revision is None:
            continue
        try:
            config = BuilderConfig.model_validate(revision.data)
        except ValidationError:
            # Même discipline que list_configs_by_kind : une config stockée
            # corrompue est journalisée et ignorée plutôt que de faire
            # planter la requête pour tout le tenant.
            logger.warning(
                "list_configs_by_kind_and_tenant: config invalide ignorée (item_id=%s, tenant_id=%s, kind=%s)",
                record.item_id, record.tenant_id, kind,
            )
            continue
        result.append((record.item_id, config))
    return result


def update_config(
    session: Session, config_id: str, config: BuilderConfig, *, tenant_id: str
) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    new_version = record.current_version + 1
    revision = ConfigRevision(
        tenant_id=tenant_id,
        config_id=config_id,
        version=new_version,
        data=config.model_dump(by_alias=True),
    )
    record.current_version = new_version
    session.add(revision)
    session.flush()
    session.refresh(record)
    return _to_read(record, revision)


def list_revisions(session: Session, config_id: str) -> list[RevisionInfo]:
    revisions = session.scalars(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id)
        .order_by(ConfigRevision.version.asc())
    ).all()
    return [RevisionInfo(version=r.version, created_at=r.created_at) for r in revisions]


def rollback_config(
    session: Session, config_id: str, version: int, *, tenant_id: str
) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    source = session.scalar(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id, ConfigRevision.version == version)
    )
    if source is None:
        return None
    new_version = record.current_version + 1
    revision = ConfigRevision(
        tenant_id=tenant_id, config_id=config_id, version=new_version, data=source.data
    )
    record.current_version = new_version
    session.add(revision)
    session.flush()
    session.refresh(record)
    return _to_read(record, revision)


def delete_config(session: Session, config_id: str) -> bool:
    record = session.get(Config, config_id)
    if record is None:
        return False
    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.delete(record)
    session.flush()
    return True
