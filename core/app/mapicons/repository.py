# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import Text, cast, select
from sqlalchemy.orm import Session

from app.mapicons.models import MapIcon


def create_icon(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    title: str,
    category: str,
    s3_key: str,
    content_type: str,
) -> MapIcon:
    icon = MapIcon(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        title=title,
        category=category,
        s3_key=s3_key,
        content_type=content_type,
        created_by=created_by,
    )
    session.add(icon)
    session.flush()
    session.refresh(icon)
    return icon


def list_icons(session: Session, *, tenant_id: str) -> list[MapIcon]:
    return list(
        session.scalars(
            select(MapIcon).where(MapIcon.tenant_id == tenant_id).order_by(MapIcon.title)
        ).all()
    )


def get_icon(session: Session, *, tenant_id: str, icon_id: str) -> MapIcon | None:
    return session.scalar(
        select(MapIcon).where(MapIcon.tenant_id == tenant_id, MapIcon.id == icon_id)
    )


def is_used_by_public_item(
    session: Session,
    *,
    tenant_id: str,
    icon_id: str,
    only_item_ids: frozenset[str] | None = None,
) -> bool:
    """Une version courante de config d'un item public/publié cite l'id de l'icône.
    Avec `only_item_ids` (jeton invité, REV-367 b) : seuls ces items comptent,
    publics ou non — l'icône doit être liée à la ressource partagée.
    ponytail: recherche de sous-chaîne dans le JSON (id uuid, faux positif négligeable),
    balayage des configs publiques du tenant ; index/table d'usage si ça devient lent."""
    from app.configs.models import Config, ConfigRevision
    from app.items.models import Item

    scope = (
        Config.item_id.in_(only_item_ids)
        if only_item_ids is not None
        else (Item.is_public.is_(True)) | (Item.is_published.is_(True))
    )
    return (
        session.scalar(
            select(Config.id)
            .join(
                ConfigRevision,
                (ConfigRevision.config_id == Config.id)
                & (ConfigRevision.version == Config.current_version),
            )
            .join(Item, Item.id == Config.item_id)
            .where(
                Config.tenant_id == tenant_id,
                scope,
                cast(ConfigRevision.data, Text).contains(icon_id),
            )
            .limit(1)
        )
        is not None
    )


def delete_icon(session: Session, icon: MapIcon) -> None:
    session.delete(icon)
    session.flush()
