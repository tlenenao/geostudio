# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "oidc_sub", name="uq_users_tenant_oidc_sub"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    oidc_sub: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, default="", server_default="")
    last_name: Mapped[str] = mapped_column(String, default="", server_default="")
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    # Colonne synchronisée, PAS une source de vérité indépendante : réglée
    # uniquement par get_or_create_user()/set_user_role() (app.users.repository),
    # toujours en même temps que role_id. ~20 lecteurs existants (decide(),
    # list_visible_collections(), app.mcp.tools, app.pipelines, app.dcat,
    # app.stac…) la consomment comme signal — préservée à l'identique pour ne
    # pas les toucher (design, résolution documentée en tête de ce plan).
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
