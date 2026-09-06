# SPDX-License-Identifier: Apache-2.0
"""Index AST des outils MCP (SP-61, spec §3.2).

Les 27 outils sont déclarés par `@server.tool()` sur une fonction imbriquée
dans la fonction d'enregistrement de chaque module de `core/app/mcp/tools/`.
`@server.resource(...)` (1 occurrence) n'est pas un outil et n'est pas indexé.

Limite assumée : un outil enregistré autrement qu'avec ce décorateur (appel
programmatique à `server.add_tool`) ne serait pas vu — aucun cas à `1516a3a1`."""

from __future__ import annotations

import ast
import pathlib


def index_mcp_tools(repo: pathlib.Path) -> tuple[str, ...]:
    names: set[str] = set()
    for path in sorted((repo / "core/app/mcp").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "tool"
                ):
                    names.add(node.name)
    return tuple(sorted(names))
