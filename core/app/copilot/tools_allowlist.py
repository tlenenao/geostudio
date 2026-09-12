# SPDX-License-Identifier: Apache-2.0
"""Ensemble fermé des outils MCP que le copilote peut invoquer en loopback
(SP-20). Exclut délibérément save_app_config/set_sharing : le copilote
édite la config déjà ouverte dans le builder uniquement via des opérations
côté client (clientOps, jamais écrites en base pendant la conversation) ;
il peut CRÉER un nouvel item (create_item/create_form_app) via les mêmes
outils qu'un agent MCP externe, jamais muter un item existant directement.
generate_sql_query/generate_visual_query (GAP-17) sont des outils de
GÉNÉRATION : ils lisent un schéma de collection et appellent le LLM, ne
créent et n'écrivent jamais rien — un brouillon qu'ils produisent n'est
appliqué que via un outil CLIENT (applySqlDraft/applyVisualQueryDraft),
jamais exécuté côté serveur."""

ALLOWED_MCP_TOOL_NAMES = frozenset(
    {
        "search_catalog",
        "list_items",
        "explain_dataset",
        "run_analytics_query",
        "create_item",
        "create_form_app",
        "generate_sql_query",
        "generate_visual_query",
    }
)
