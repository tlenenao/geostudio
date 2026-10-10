# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
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
