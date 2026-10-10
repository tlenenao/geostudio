# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GroupMember(Base):
    __tablename__ = "group_members"
    # PK = (group_id, user_id) : sans cet index, `WHERE user_id = ?` (can(),
    # catalogue) fait un Seq Scan (REV-279 c, trouvé au rejeu sur Postgres réel).
    __table_args__ = (Index("ix_group_members_user_id", "user_id"),)

    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)


_ROLE_CHECK = "role IN ('viewer', 'editor', 'manager')"


class ItemShare(Base):
    __tablename__ = "item_shares"
    __table_args__ = (CheckConstraint(_ROLE_CHECK, name="ck_item_shares_role"),)

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "viewer" | "editor" | "manager"


class ShareLink(Base):
    """Lien de partage à échéance (GAP-12, chantier 4.23) — jeton révocable
    présenté à un tiers externe, distinct du partage groupe/rôle plat
    (ItemShare) : cf. app/sharing/share_links.py pour le jeton lui-même."""

    __tablename__ = "share_link"
    __table_args__ = (Index("ix_share_link_tenant_item", "tenant_id", "item_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class CollectionGeoLimit(Base):
    """Limite géographique de lecture/écriture (GAP-27, REV-121) : géométrie
    GeoJSON (Polygon/MultiPolygon, 4326) attachée à (collection × rôle|groupe).
    Cf. docs/superpowers/specs/2026-10-10-sp-geo-limits-design.md."""

    __tablename__ = "collection_geo_limits"
    __table_args__ = (
        UniqueConstraint("collection_id", "target_type", "target_id", name="uq_geo_limit_target"),
        Index("ix_geo_limits_tenant_collection", "tenant_id", "collection_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String, nullable=False)  # "role" | "group"
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )


class CollectionShare(Base):
    __tablename__ = "collection_shares"
    __table_args__ = (CheckConstraint(_ROLE_CHECK, name="ck_collection_shares_role"),)

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "viewer" | "editor" | "manager"
