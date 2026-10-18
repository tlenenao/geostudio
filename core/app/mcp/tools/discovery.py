# SPDX-License-Identifier: Apache-2.0
"""Découvrabilité MCP (AUD-105) : deux outils de lecture jumeaux de routes REST
(`GET /v1/pipelines/ops`, `GET /v1/configs/{id}/revisions`) et quelques prompts
réutilisables côté client agent. Aucune écriture."""

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.configs import repository as configs_repo
from app.db import request_scoped_session
from app.mcp.tools.identity import require_access, resolve_actor
from app.pipelines.ops.contracts import ops_catalog


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def list_pipeline_ops(ctx: Context) -> dict:
        """List the pipeline operations available on this instance (catalogue with
        parameter schemas) — mirrors GET /v1/pipelines/ops. Read it before drafting a
        pipeline node so parameters match the schema."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            resolve_actor(session, access_token)  # authentifie, comme la route
        return ops_catalog()

    @server.tool()
    async def get_config_history(ctx: Context, itemId: str) -> list[dict]:
        """List the saved versions of an item's config (version number and date) —
        mirrors GET /v1/configs/{id}/revisions. Use it to pick an `expectedVersion`
        or to tell the user what a rollback would restore."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=itemId, action="read")
            config = configs_repo.get_config_by_item(session, itemId)
            if config is None:
                raise ValueError("config not found")
            return [
                {"version": r.version, "createdAt": r.created_at.isoformat()}
                for r in configs_repo.list_revisions(session, config.id)
            ]

    @server.prompt()
    def review_app_config(itemId: str) -> str:
        """Review an app/dashboard config for problems before publishing."""
        return (
            f"Lis la configuration de l'item {itemId} avec get_app_config, puis relève : "
            "sources de données absentes ou illisibles, widgets sans titre, expressions CEL "
            "suspectes, filtres incohérents. Ne modifie rien : propose une liste de corrections."
        )

    @server.prompt()
    def explain_collection(collectionId: str) -> str:
        """Describe a collection's fields and propose useful analyses."""
        return (
            f"Décris la collection {collectionId} (search_collections puis explain_dataset si "
            "un dataset existe) : champs, types, valeurs notables. Propose 3 analyses "
            "pertinentes exprimables avec run_analytics_query, sans les exécuter sans demande."
        )
