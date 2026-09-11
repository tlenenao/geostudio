# SPDX-License-Identifier: Apache-2.0
"""Registre auto-entretenu des tools MCP d'écriture (REV-008).

Remplace l'ensemble littéral `READ_ONLY_TOOLS` écrit à la main
(`app/mcp/tools/__init__.py`), qui pouvait dériver silencieusement du code
réel : rien n'empêchait un 11e tool d'écriture d'être ajouté au registre MCP
sans que quiconque pense à l'ajouter à cette liste distante — déjà arrivé
sur ce dépôt (SP-30g, SP-30i, cf. le commentaire de
`tests/test_mcp_read_only_mode.py::test_read_only_tools_constant_matches_the_ten_write_tools`).

Chaque fonction de tool d'écriture porte désormais `@write_tool`, posé au
point même de sa définition, à côté de `@server.tool()` — peu importe
l'ordre des deux décorateurs : `FastMCP.tool()` (mcp.server.fastmcp,
vérifié par lecture de sa source) enregistre `fn` comme effet de bord
(`self.add_tool(fn, ...)`) puis renvoie `fn` **inchangée** ; `write_tool`
fait de même (effet de bord + renvoie `fn` inchangée). Les deux décorateurs
commutent donc sans risque de casser l'enregistrement réel du tool auprès
de FastMCP.

`WRITE_TOOL_NAMES` est un ensemble module-global, jamais réinitialisé :
additif au fil du process. Chaque fois que `register(server,
session_factory)` d'un domaine s'exécute (y compris pour un domaine gardé
par une capacité — `pipelines.py`/`is_etl_enabled()` : ses tools d'écriture
ne sont *définis* que si la capacité est active, donc leur `@write_tool` ne
s'exécute que dans ce cas, exactement comme leur enregistrement FastMCP
réel), les noms qu'il porte rejoignent le registre. Ce module ne fait
aucune hypothèse sur *quand* `register()` est appelé — voir
`test_mcp_read_only_mode.py` pour comment le test d'inventaire force un
état déterministe plutôt que de dépendre de l'ordre d'exécution des autres
tests de la session.

Ce décorateur est un pur outil d'inventaire : il ne fait AUCUNE vérification
`is_read_only_mode()` à la place du corps de la fonction — ce garde reste
écrit à la main dans chaque fonction, comme avant. `write_tool` ne
remplace donc pas cette discipline, il la rend seulement auditable : un
tool d'écriture oublié (ni le garde, ni le décorateur) reste indétectable
par ce mécanisme seul — cf. la note de falsification dans
`test_mcp_read_only_mode.py`."""

WRITE_TOOL_NAMES: set[str] = set()


def write_tool[F](fn: F) -> F:
    """Marque `fn` comme un tool MCP d'écriture : ajoute `fn.__name__` à
    `WRITE_TOOL_NAMES`. Ne modifie ni le nom ni le comportement de `fn` —
    renvoyée telle quelle, comme `FastMCP.tool()`."""
    WRITE_TOOL_NAMES.add(fn.__name__)  # type: ignore[attr-defined]
    return fn
