# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine secrets : delete_secret (SP-A6/D05). Garde
strictement identique à DELETE /secrets/{id} (app/secrets/routes.py) —
REV-009 : ne jamais rouvrir côté MCP un trou fermé côté REST."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.mcp.tools.identity import http_exception_to_value_error, resolve_actor
from app.mcp.tools.write_tools import write_tool
from app.roles.guards import require_any_privilege
from app.roles.privileges import Privilege
from app.secrets import repository as repo


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    @write_tool
    async def delete_secret(ctx: Context, secret_id: str) -> None:
        """Delete a connector secret — mirrors DELETE /secrets/{id}."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                require_any_privilege(
                    session,
                    user,
                    [
                        Privilege.ADMIN_SECRETS_MANAGE.value,
                        Privilege.AUTOMATION_SECRETS_MANAGE.value,
                    ],
                )
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            secret = repo.get_secret(session, tenant_id=user.tenant_id, secret_id=secret_id)
            if secret is None:
                raise ValueError("secret not found")
            name, kind = secret.name, secret.kind
            repo.delete_secret(session, secret)
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="secret.delete",
                object_type="secret",
                object_id=secret_id,
                payload={"name": name, "kind": kind},
            )
