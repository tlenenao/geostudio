# SPDX-License-Identifier: Apache-2.0
"""Routes REST du coffre de secrets (design SP-15e §6) — admin-only, ne
retourne jamais une valeur déchiffrée, un ciphertext ou un nonce."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.secrets import crypto
from app.secrets import repository as repo
from app.secrets.models import ConnectorSecret
from app.secrets.schemas import SecretCreate
from app.users.models import User

router = APIRouter()


class ConnectorSecretOut(BaseModel):
    id: str
    name: str
    kind: str
    createdAt: str
    updatedAt: str


def _to_response(secret: ConnectorSecret) -> ConnectorSecretOut:
    return ConnectorSecretOut(
        id=secret.id,
        name=secret.name,
        kind=secret.kind,
        createdAt=secret.created_at.isoformat(),
        updatedAt=secret.updated_at.isoformat(),
    )


@router.post("/secrets", status_code=201)
def create_secret_route(
    body: SecretCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConnectorSecretOut:
    require_privilege(session, user, Privilege.ADMIN_SECRETS_MANAGE.value)
    if repo.get_secret_by_name(session, tenant_id=user.tenant_id, name=body.name):
        raise HTTPException(status_code=409, detail="secret name already exists")
    ciphertext, nonce = crypto.encrypt(body.payload.model_dump())
    try:
        secret = repo.create_secret(
            session,
            tenant_id=user.tenant_id,
            created_by=user.id,
            name=body.name,
            kind=body.payload.kind,
            ciphertext=ciphertext,
            nonce=nonce,
        )
    except IntegrityError:
        # Race window between the pre-check above and this insert — the
        # uq_connector_secrets_tenant_name constraint is the real guard,
        # this just turns a concurrent duplicate into the same 409 the
        # pre-check gives in the common case (request_scoped_session rolls
        # back the failed flush; see app/db.py). `from None`, not `from exc`:
        # SQLAlchemy's IntegrityError repr includes bound parameters by
        # default (hide_parameters is not set in app/db.py), which here
        # would be the INSERT's ciphertext/nonce bytes — this module's own
        # module docstring promises it "ne retourne jamais [...] un
        # ciphertext ou un nonce", a promise chaining would risk breaking
        # the moment this exception reaches a traceback-capturing sink
        # (logs, Sentry/OTel) rather than just the HTTP response.
        raise HTTPException(status_code=409, detail="secret name already exists") from None
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="secret.create",
        object_type="secret",
        object_id=secret.id,
        payload={"name": secret.name, "kind": secret.kind},
    )
    return _to_response(secret)


@router.get("/secrets")
def list_secrets_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConnectorSecretOut]:
    require_privilege(session, user, Privilege.ADMIN_SECRETS_MANAGE.value)
    return [_to_response(s) for s in repo.list_secrets(session, tenant_id=user.tenant_id)]


@router.delete("/secrets/{secret_id}", status_code=204)
def delete_secret_route(
    secret_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    require_privilege(session, user, Privilege.ADMIN_SECRETS_MANAGE.value)
    secret = repo.get_secret(session, tenant_id=user.tenant_id, secret_id=secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="secret not found")
    name, kind = secret.name, secret.kind
    repo.delete_secret(session, secret)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="secret.delete",
        object_type="secret",
        object_id=secret_id,
        payload={"name": name, "kind": kind},
    )
