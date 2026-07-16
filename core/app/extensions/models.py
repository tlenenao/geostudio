# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Extension(Base):
    __tablename__ = "extensions"

    # Clé primaire composite (id, tenant_id) : id = type du widget côté shell
    # (ex. "acme.gauge"), PAS unique seul — deux tenants peuvent enregistrer
    # le même type. Pas de surrogate séparé (contrairement à
    # Collection.id/table_name) : il n'y a ici aucune ressource physique
    # sous-jacente à découpler du nom d'enregistrement.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    module_url: Mapped[str] = mapped_column(String, nullable=False)
    props: Mapped[list] = mapped_column(JSON, nullable=False)
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    default_size: Mapped[dict] = mapped_column(JSON, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
