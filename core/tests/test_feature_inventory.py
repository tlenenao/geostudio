# SPDX-License-Identifier: Apache-2.0
"""Garde-fou d'inventaire (SP-61, spec §6.1).

Le geste qu'on veut rendre impossible : livrer une surface sans la déclarer.
Sans ce test, l'inventaire repérit exactement comme la matrice SP-42 l'a fait —
17 SP pendant lesquels rien ne signalait sa péremption (piège n°12).

Ce fichier teste le **dépôt**, pas `core/app/` : même entorse assumée que
`core/tests/test_deployability.py`, et pour la même raison — `core/` est le
seul répertoire du dépôt qui possède un runner Python dans la CI."""

import pathlib

from scripts.feature_health.mcp_surface import index_mcp_tools
from scripts.feature_health.model import load_inventory
from scripts.feature_health.reachability import declared_shell_routes
from scripts.feature_health.rest_surface import index_rest_routes, surface_id

REPO = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = REPO / "docs/revue/inventaire-fonctionnalites.jsonl"


def _declared():
    features = load_inventory(INVENTORY)
    return (
        {surface for feature in features for surface in feature.rest},
        {tool for feature in features for tool in feature.mcp},
        {route for feature in features for route in feature.shell},
    )


def test_every_rest_route_is_claimed_by_an_inventory_entry():
    declared_rest, _, _ = _declared()
    missing = sorted(
        surface_id(fact)
        for fact in index_rest_routes(REPO)
        if surface_id(fact) not in declared_rest
    )
    assert missing == [], (
        "Routes REST non inventoriées — ajouter chacune à la ligne de "
        f"docs/revue/inventaire-fonctionnalites.jsonl qui la porte : {missing}"
    )


def test_every_mcp_tool_is_claimed_by_an_inventory_entry():
    _, declared_mcp, _ = _declared()
    missing = sorted(tool for tool in index_mcp_tools(REPO) if tool not in declared_mcp)
    assert missing == [], f"Outils MCP non inventoriés : {missing}"


def test_every_shell_route_is_claimed_by_an_inventory_entry():
    _, _, declared_shell = _declared()
    missing = sorted(route for route in declared_shell_routes(REPO) if route not in declared_shell)
    assert missing == [], f"Routes shell non inventoriées : {missing}"


def test_no_inventory_entry_claims_an_unknown_surface():
    """Le sens inverse : une surface déclarée mais retirée du code (route
    supprimée, outil renommé) doit être nettoyée, pas laissée à pourrir."""
    declared_rest, declared_mcp, declared_shell = _declared()
    known_rest = {surface_id(fact) for fact in index_rest_routes(REPO)}
    known_mcp = set(index_mcp_tools(REPO))
    known_shell = set(declared_shell_routes(REPO))
    unknown = sorted(
        (declared_rest - known_rest) | (declared_mcp - known_mcp) | (declared_shell - known_shell)
    )
    assert unknown == [], f"Surfaces déclarées mais absentes du code : {unknown}"


def test_every_proof_path_still_exists():
    """L'ancrage par chemin de fichier tient (294/304 mesuré à l'amorçage) —
    il ne tient que si on le vérifie."""
    dead = sorted(
        f"{feature.identifier} → {proof}"
        for feature in load_inventory(INVENTORY)
        for proof in feature.proofs
        if not (REPO / proof).exists()
    )
    assert dead == [], f"Chemins de preuve morts : {dead}"


def test_every_entry_has_at_least_one_proof():
    empty = sorted(
        feature.identifier for feature in load_inventory(INVENTORY) if not feature.proofs
    )
    assert empty == [], f"Entrées sans aucune preuve : {empty}"
