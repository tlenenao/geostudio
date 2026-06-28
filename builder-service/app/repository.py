import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Config, ConfigRevision
from app.schemas import BuilderConfig


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


def create_config(session: Session, config: BuilderConfig, item_id: str | None) -> ConfigRead:
    config_id = uuid.uuid4().hex
    record = Config(id=config_id, kind=config.kind, item_id=item_id, current_version=1)
    revision = ConfigRevision(
        config_id=config_id, version=1, data=config.model_dump(by_alias=True)
    )
    session.add(record)
    session.add(revision)
    session.commit()
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


def update_config(session: Session, config_id: str, config: BuilderConfig) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    new_version = record.current_version + 1
    revision = ConfigRevision(
        config_id=config_id, version=new_version, data=config.model_dump(by_alias=True)
    )
    record.current_version = new_version
    session.add(revision)
    session.commit()
    session.refresh(record)
    return _to_read(record, revision)


def list_revisions(session: Session, config_id: str) -> list[RevisionInfo]:
    revisions = session.scalars(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id)
        .order_by(ConfigRevision.version.asc())
    ).all()
    return [RevisionInfo(version=r.version, created_at=r.created_at) for r in revisions]


def rollback_config(session: Session, config_id: str, version: int) -> ConfigRead | None:
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
    revision = ConfigRevision(config_id=config_id, version=new_version, data=source.data)
    record.current_version = new_version
    session.add(revision)
    session.commit()
    session.refresh(record)
    return _to_read(record, revision)
