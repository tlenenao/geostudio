# SPDX-License-Identifier: Apache-2.0
"""Garde-fou d'inventaire (SP-61, spec §6.1).

Le geste qu'on veut rendre impossible : livrer une surface sans la déclarer.
Sans ce test, l'inventaire repérit exactement comme la matrice SP-42 l'a fait —
17 SP pendant lesquels rien ne signalait sa péremption (piège n°12).

Ce fichier teste le **dépôt**, pas `core/app/` : même entorse assumée que
`core/tests/test_deployability.py`, et pour la même raison — `core/` est le
seul répertoire du dépôt qui possède un runner Python dans la CI."""

import pathlib
import statistics

import pytest

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


def test_publiques_declaration_matches_the_ast_unguarded_set():
    """`score_guard` (rest_surface.py) donne 100.0 à toute surface qu'une
    entrée déclare dans `publiques`, sans jamais vérifier que cette route est
    *réellement* dépourvue de garde et d'authentification. Rien n'empêche
    aujourd'hui une future entrée de déclarer publique une route qui garde
    `has_privilege`/`require_privilege`/etc — le sous-score « garde »
    rapporterait alors une fiction, en silence.

    Ce test pin l'invariant qui rend cette déclaration honnête : l'ensemble
    des surfaces REST déclarées `publiques` (toutes entrées confondues) doit
    être **exactement** l'ensemble des routes que l'index AST trouve
    réellement sans aucune garde et sans authentification (`auth == "none"`,
    `guards` vide)."""
    features = load_inventory(INVENTORY)
    declared_public = {surface for feature in features for surface in feature.public}
    routes = index_rest_routes(REPO)
    actually_unguarded = {
        surface_id(fact) for fact in routes if not fact.guards and fact.auth == "none"
    }
    declared_but_guarded = sorted(declared_public - actually_unguarded)
    unguarded_but_undeclared = sorted(actually_unguarded - declared_public)
    assert not declared_but_guarded and not unguarded_but_undeclared, (
        "Divergence entre `publiques` (inventaire) et l'ensemble réellement non "
        "gardé (index AST) — le sous-score « garde » de rest_surface.py::"
        "score_guard mentirait sur au moins une de ces routes.\n"
        "Déclarées publiques mais en réalité gardées ou authentifiées "
        f"(retirer de `publiques`) : {declared_but_guarded}\n"
        "Réellement sans garde ni authentification mais non déclarées "
        f"publiques (ajouter à `publiques`) : {unguarded_but_undeclared}"
    )


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


COVERAGE_ARTEFACTS = (
    REPO / "core/coverage.xml",
    REPO / "shell/coverage/coverage-summary.json",
)


@pytest.mark.skipif(
    not all(path.exists() for path in COVERAGE_ARTEFACTS),
    reason=(
        "artefacts de couverture absents — le plancher de santé est vérifié en CI "
        "par le job `feature-health`, qui les récupère des jobs `core` et `shell`"
    ),
)
def test_health_floors_hold():
    """Plancher §6.2. Ce test ne peut pas tourner dans le job `core` de la CI :
    `coverage.xml` y est écrit à la fin du pytest qui l'exécuterait, et la
    couverture shell est produite sur une autre machine. Il tourne en local
    (où les deux artefacts existent) et dans le job dédié."""
    from scripts.feature_health_cli import compute

    rows, thresholds = compute(REPO)
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    low = sorted(
        (row["feature"].identifier, row["sante"])
        for row in rows
        if row["feature"].priority == "haute"
        and row["sante"] is not None
        and row["sante"] < thresholds.floor_high_priority
    )
    assert low == [], f"fonctionnalités de priorité haute sous le plancher : {low}"
    assert statistics.median(measured) >= thresholds.floor_median
