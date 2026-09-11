# SPDX-License-Identifier: Apache-2.0
"""Ensemble fermé des outils MCP que le copilote peut invoquer en loopback
(SP-20). Exclut délibérément save_app_config/set_sharing : le copilote
édite la config déjà ouverte dans le builder uniquement via des opérations
côté client (clientOps, jamais écrites en base pendant la conversation) ;
il peut CRÉER un nouvel item (create_item/create_form_app) via les mêmes
outils qu'un agent MCP externe, jamais muter un item existant directement.

Cette allowlist est désormais partagée entre les trois surfaces du
copilote (`CopilotTurnRequest.surface`, GAP-17 Tâche 1) : builder d'app,
SQL Lab et requête visuelle. Les outils de génération dédiés à ces deux
dernières surfaces (generate_sql_query/generate_visual_query) sont ajoutés
à cet ensemble par la Tâche 2 — ce fichier n'en gagne pas les noms ici."""

ALLOWED_MCP_TOOL_NAMES = frozenset(
    {
        "search_catalog",
        "list_items",
        "explain_dataset",
        "run_analytics_query",
        "create_item",
        "create_form_app",
    }
)
