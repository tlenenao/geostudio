# SPDX-License-Identifier: Apache-2.0
"""AUD-118 : le catalogue MCP documenté est celui du registre réel (pas de dérive)."""

import pathlib

from scripts.gen_mcp_catalog import render

DOC = pathlib.Path(__file__).resolve().parents[2] / "docs/guides/mcp-outils.md"


def test_committed_catalog_matches_registry():
    assert DOC.read_text(encoding="utf-8") == render(), (
        "docs/guides/mcp-outils.md périmé : cd core && PYTHONPATH=. uv run python "
        "scripts/gen_mcp_catalog.py ../docs/guides/mcp-outils.md"
    )
