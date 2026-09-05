# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine pièces jointes : list_attachments (SP-43 Étape 8 —
extrait de app/mcp/tools.py, aucune couche de service à créer : réutilise
directement le repo app/attachments/, déjà séparé de toute route)."""

import json

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.attachments import repository as attachments_repo
from app.db import request_scoped_session
from app.mcp.tools.identity import require_collection_read, resolve_actor


def register(server: FastMCP, session_factory) -> None:
    @server.tool(structured_output=False)
    async def list_attachments(
        ctx: Context, collectionId: str, fid: str, fieldKey: str | None = None
    ) -> str:
        """List the metadata of files attached to one entity of a collection
        (chantier 4.12) — read-only, never returns file bytes. No fileUrl:
        the REST proxy-read it would point to
        (GET /collections/{id}/items/{fid}/attachments/{aid}/file) is
        gated by the shell's OIDC audience (CORE_OIDC_AUDIENCE), which an
        MCP-audienced token (CORE_MCP_AUDIENCE) never satisfies — same
        reason ItemRead.thumbnailUrl is omitted for MCP callers (SP-42,
        F-coeur-federation-08). Deliberately absent from the copilot's
        ALLOWED_MCP_TOOL_NAMES (app/copilot/tools_allowlist.py).

        Returns a JSON-encoded array (rather than a typed list[dict]) because
        FastMCP's unstructured-content conversion fragments a returned Python
        list into one content block per element instead of one block holding
        the whole array — verified empirically against mcp==1.29.1, not
        assumed. structured_output=False avoids a second, incompatible
        failure mode: the structured-output path would otherwise try to
        validate this pre-serialized string against a list[dict] schema."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_collection_read(session, user=user, collection_id=collectionId)
            rows = attachments_repo.list_attachments(
                session,
                tenant_id=user.tenant_id,
                collection_id=collectionId,
                fid=fid,
                field_key=fieldKey,
            )
            return json.dumps(
                [
                    {
                        "id": a.id,
                        "fieldKey": a.field_key,
                        "filename": a.filename,
                        "contentType": a.content_type,
                        "byteSize": a.byte_size,
                    }
                    for a in rows
                ]
            )
