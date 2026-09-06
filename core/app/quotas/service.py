# SPDX-License-Identifier: Apache-2.0
"""Compteurs et mesure d'usage par tenant (SP-58, GAP-73/GAP-11).

Module volontairement bas dans le contrat de couches (juste après
app.configs — cf. pyproject.toml, contrat "layered architecture") : il doit
pouvoir importer les modèles de presque tout le reste de l'application
(items, collections, users, export, appexport) pour compter/sommer, et doit
être importable par les points de création (configs/collections/attachments/
tileset3d/terrain3d/ingestion routes)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.items.models import Item
from app.users.models import User


def count_items_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(select(func.count()).select_from(Item).where(Item.tenant_id == tenant_id))
        or 0
    )


def count_collections_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Collection).where(Collection.tenant_id == tenant_id)
        )
        or 0
    )


def count_users_for_tenant(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant_id))
        or 0
    )
