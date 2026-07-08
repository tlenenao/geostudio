import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tenants.models import Tenant

DEFAULT_TENANT_SLUG = "default"


def get_or_create_default_tenant(session: Session) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    if tenant is not None:
        return tenant
    tenant = Tenant(id=uuid.uuid4().hex, slug=DEFAULT_TENANT_SLUG, name="Default")
    session.add(tenant)
    session.flush()
    session.refresh(tenant)
    return tenant
