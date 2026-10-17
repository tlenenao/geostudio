# SPDX-License-Identifier: Apache-2.0
"""app.compliance — anonymisation d'utilisateur + purge de tenant (RGPD,
SP-58, GAP-74).

PurgeReceipt : preuve d'effacement conservée HORS du périmètre du tenant
purgé. Aucun champ ne contient de donnée personnelle — tenant_slug et
requested_by_user_id sont des chaînes libres, SANS contrainte ForeignKey,
même rationale que AuditLog.actor_id (app/audit/models.py) : ces valeurs
doivent survivre à la disparition des lignes qu'elles désignent (le tenant
et l'utilisateur qui a demandé la purge sont tous deux supprimés par la
purge elle-même). `counts` est un JSON de comptages agrégés (nombre de
lignes supprimées par table, octets S3 libérés) — jamais de contenu."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class PurgeReceipt(Base):
    __tablename__ = "purge_receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False)
    # REV-344 : cycle de vie du reçu — créé `pending` par la route de déclenchement
    # (verrou d'idempotence), `running` au démarrage du job, `done`/`failed` à la fin.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="done", server_default=sa.text("'done'")
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    # AUD-121 : id interne du tenant purgé (≠ slug en général) — sans FK, comme tenant_slug —
    # pour que le rattrapage S3 retrouve les préfixes `{tenant_id}/` après la purge.
    purged_tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
