# SPDX-License-Identifier: Apache-2.0
"""Génère le catalogue des outils MCP (AUD-118) depuis le registre réel, pour que la doc
ne dérive pas. Usage (depuis core/) : `PYTHONPATH=. uv run python scripts/gen_mcp_catalog.py
../docs/guides/mcp-outils.md` ; sans argument, écrit sur la sortie standard."""

import asyncio
import os
import sys

HEADER = """# Catalogue des outils MCP

> Fichier **généré** par `core/scripts/gen_mcp_catalog.py` depuis le registre du cœur
> (`app/mcp/tools`) — ne pas l'éditer à la main ; un test échoue s'il est périmé.
> Les outils d'écriture sont refusés quand `CORE_READ_ONLY_MODE=true`.

| Outil | Accès | Description |
|---|---|---|
"""


def render() -> str:
    from app.mcp.server import create_mcp_server
    from app.mcp.tools.write_tools import WRITE_TOOL_NAMES

    # Catalogue complet : les outils de pipeline ne sont enregistrés que si CORE_ETL_ENABLED.
    previous = os.environ.get("CORE_ETL_ENABLED")
    os.environ["CORE_ETL_ENABLED"] = "true"
    try:
        server = create_mcp_server("http://localhost:8200", lambda: None)
    finally:  # ne pas fuir le drapeau dans le process appelant (tests)
        if previous is None:
            del os.environ["CORE_ETL_ENABLED"]
        else:
            os.environ["CORE_ETL_ENABLED"] = previous
    tools = sorted(asyncio.run(server.list_tools()), key=lambda t: t.name)
    rows = []
    for t in tools:
        text = " ".join((t.description or "").split())  # docstring sur une ligne, bornée
        first = (text if len(text) <= 180 else text[:177].rsplit(" ", 1)[0] + "…").replace(
            "|", "\\|"
        )
        access = "écriture" if t.name in WRITE_TOOL_NAMES else "lecture"
        rows.append(f"| `{t.name}` | {access} | {first} |")
    return HEADER + "\n".join(rows) + "\n"


if __name__ == "__main__":
    out = render()
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
