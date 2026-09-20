# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import retry_on_sqlite_row_corruption
from app.tenants.models import Tenant

DEFAULT_TENANT_SLUG = "default"


def get_or_create_default_tenant(session: Session) -> Tenant:
    tenant = retry_on_sqlite_row_corruption(
        lambda: session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    )
    if tenant is not None:
        return tenant
    # Décision 2026-07-10 (spec SP-3, notes de revue SP-3a) : tenants.id est un
    # identifiant lisible IMMUABLE (= slug à la création), aligné sur le seed de
    # la migration 0002. La RLS des données métier compare cet id
    # (SET LOCAL app.tenant_id) et le DDL le stampe en DEFAULT — un id uuid ici
    # rendrait toutes les lignes invisibles sous RLS sur une base non seedée.
    new_tenant = Tenant(id=DEFAULT_TENANT_SLUG, slug=DEFAULT_TENANT_SLUG, name="Default")
    try:
        # Deux requêtes concurrentes peuvent toutes deux lire « aucun tenant »
        # avant que l'une des deux n'ait committé son insert (TOCTOU, observé
        # en CI : IntegrityError sur tenants.slug dans test_copilot_routes.py
        # ::test_synchronous_provider_call_does_not_block_the_event_loop,
        # dont le commentaire documente déjà cette course). Un SAVEPOINT
        # borne le rollback au seul insert perdant, sans annuler d'éventuelles
        # écritures déjà en attente ailleurs dans la même transaction de
        # requête — jamais `session.rollback()` en entier, ce qui purgerait
        # tout le reste du travail de la requête (get_current_user résout le
        # tenant avant que le handler n'écrive quoi que ce soit, mais rien ne
        # garantit que ça reste vrai partout où cette fonction est appelée).
        with session.begin_nested():
            session.add(new_tenant)
            session.flush()
    except IntegrityError:
        tenant = retry_on_sqlite_row_corruption(
            lambda: session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
        )
        if tenant is None:
            raise
        return tenant
    session.refresh(new_tenant)
    return new_tenant
