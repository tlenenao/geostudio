# SPDX-License-Identifier: Apache-2.0
"""Ensemble fermé des outils MCP que le copilote peut invoquer en loopback
(SP-20). Exclut délibérément save_app_config/set_sharing : le copilote
édite la config déjà ouverte dans le builder uniquement via des opérations
côté client (clientOps, jamais écrites en base pendant la conversation) ;
il peut CRÉER un nouvel item (create_item/create_form_app) via les mêmes
outils qu'un agent MCP externe, jamais muter un item existant directement."""

ALLOWED_MCP_TOOL_NAMES = frozenset({
    "search_catalog",
    "list_items",
    "explain_dataset",
    "run_analytics_query",
    "create_item",
    "create_form_app",
})
