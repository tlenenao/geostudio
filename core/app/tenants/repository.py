# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tenants.models import Tenant

DEFAULT_TENANT_SLUG = "default"


def get_or_create_default_tenant(session: Session) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    if tenant is not None:
        return tenant
    # Décision 2026-07-10 (spec SP-3, notes de revue SP-3a) : tenants.id est un
    # identifiant lisible IMMUABLE (= slug à la création), aligné sur le seed de
    # la migration 0002. La RLS des données métier compare cet id
    # (SET LOCAL app.tenant_id) et le DDL le stampe en DEFAULT — un id uuid ici
    # rendrait toutes les lignes invisibles sous RLS sur une base non seedée.
    tenant = Tenant(id=DEFAULT_TENANT_SLUG, slug=DEFAULT_TENANT_SLUG, name="Default")
    session.add(tenant)
    session.flush()
    session.refresh(tenant)
    return tenant
