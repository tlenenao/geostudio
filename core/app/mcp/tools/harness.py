# SPDX-License-Identifier: Apache-2.0
"""Enveloppe commune de tous les tools MCP (audit P23).

`instrument(server, session_factory)` renvoie un proxy dont `.tool()` enregistre
chaque tool derrière une enveloppe unique qui :
- l'exécute hors de la boucle asyncio (thread + boucle dédiée) : les corps de
  tools font des I/O synchrones (SQLAlchemy, DuckDB, httpx.Client) et gelaient
  tout le process, /health compris (c02-009) ;
- remplace une erreur SQL brute par un message générique, sans requête ni nom
  de table physique (j11-002) ;
- laisse une ligne `audit_log` `mcp.tool_call` par appel (acteur, outil, cibles,
  issue, origine copilote/agent externe) — c01-009, j11-011."""

import asyncio
import functools
import logging
from typing import Any

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx
from sqlalchemy.exc import SQLAlchemyError

from app.audit.writer import write_audit
from app.db import request_scoped_session
from app.mcp.tools.identity import McpToolError, resolve_actor

logger = logging.getLogger(__name__)

ORIGIN_HEADER = "x-geostudio-origin"


def _origin() -> str:
    """`copilot` quand l'appel vient du loopback du copilote, sinon `agent`.
    Simple étiquette d'audit (le jeton MCP reste celui de l'utilisateur) :
    un client externe peut s'en réclamer, ce n'est pas une frontière de sécurité."""
    try:
        request = request_ctx.get().request
        if request is not None and request.headers.get(ORIGIN_HEADER) == "copilot":
            return "copilot"
    except LookupError:
        pass
    return "agent"


def _targets(kwargs: dict[str, Any]) -> dict[str, str]:
    return {k: v[:64] for k, v in kwargs.items() if k.lower().endswith("id") and isinstance(v, str)}


def _audit(session_factory, name: str, kwargs: dict[str, Any], outcome: str) -> None:
    token = get_access_token()
    if token is None:
        return
    try:
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, token)
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="mcp.tool_call",
                object_type="mcp_tool",
                object_id=name,
                payload={"origin": _origin(), "outcome": outcome, "targets": _targets(kwargs)},
            )
    except Exception:  # best-effort : une trace manquée ne casse jamais l'outil
        logger.exception("mcp audit failed for %s", name)


class _InstrumentedServer:
    def __init__(self, server: FastMCP, session_factory) -> None:
        self._server = server
        self._session_factory = session_factory

    def __getattr__(self, attr: str):
        return getattr(self._server, attr)

    def tool(self, *args, **kwargs):
        register = self._server.tool(*args, **kwargs)

        def decorator(fn):
            @functools.wraps(fn)
            async def run(*a, **kw):
                def in_thread():
                    try:
                        result = asyncio.run(fn(*a, **kw))
                    except SQLAlchemyError as exc:
                        logger.warning("mcp tool %s: %s", fn.__name__, exc)
                        _audit(self._session_factory, fn.__name__, kw, "error")
                        raise McpToolError(
                            500, "erreur de base de données (détail masqué)"
                        ) from None
                    except Exception:
                        _audit(self._session_factory, fn.__name__, kw, "error")
                        raise
                    _audit(self._session_factory, fn.__name__, kw, "ok")
                    return result

                return await anyio.to_thread.run_sync(in_thread)

            register(run)
            return fn

        return decorator


def instrument(server: FastMCP, session_factory) -> Any:
    return _InstrumentedServer(server, session_factory)
