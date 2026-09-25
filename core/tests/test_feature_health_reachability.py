# SPDX-License-Identifier: Apache-2.0
"""Sous-score « atteignabilité » (SP-61, spec §3.2).

Ces tests s'exécutent contre le **dépôt réel**, comme
`core/tests/test_deployability.py` : c'est la seule façon de vérifier qu'un
calcul d'atteignabilité dit la vérité sur ce dépôt-ci. Deux ancres de
falsification sont des faits mesurés, pas des fixtures — si l'une d'elles
change, c'est le dépôt qui a bougé et il faut relire, pas le test qu'il faut
assouplir."""

import json
import pathlib

import pytest

from scripts.feature_health.model import Feature, load_inventory
from scripts.feature_health.reachability import (
    ReachabilityFacts,
    collect_reachability_facts,
    collect_shell_inbound,
    declared_shell_routes,
    route_prefix,
    score_reachability,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="fonctionnalité de test",
        proofs=("shell/src/pages/CatalogPage.tsx",),
        rest=(),
        mcp=(),
        shell=(),
        public=(),
        priority="moyenne",
        priority_source="amorcage-sp42",
        raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_declared_shell_routes_lists_every_route_of_routes_tsx():
    routes = declared_shell_routes(REPO)
    # 28 → 29 (GAP-19) : nouvelle route publique /embed/:token
    # (shell/src/shell/routes.tsx) — canari volontairement en dur (même
    # patron que le catalogue de widgets SP-52) pour forcer une décision
    # consciente à chaque route ajoutée, jamais un décompte automatique.
    assert len(routes) == 29
    assert "/bookmarks" in routes
    assert "/public/datasets/:collectionId" in routes


@pytest.mark.parametrize(
    "route,expected",
    [
        ("/apps/:pk/edit", "/apps"),
        ("/reports/new", "/reports/new"),
        ("/apps/:pk/:pageId?", "/apps"),
        ("/", "/"),
    ],
)
def test_route_prefix_cuts_at_the_first_parameter(route, expected):
    assert route_prefix(route) == expected


def test_bookmarks_has_an_inbound_link():
    """GAP-80, fermé par le plan `2026-09-24-vague-a-bloquants-decouvrabilite.md`
    (commit `de52497f`) : `CatalogPage.tsx` porte désormais un `<Link
    to="/bookmarks">` réel quand le catalogue est sur le type `bookmark`."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/pages/CatalogPage.tsx" in inbound["/bookmarks"]


def test_sql_lab_has_an_inbound_link():
    """Même classe que GAP-80, fermée par le même plan (commit `de52497f`) :
    `CatalogPage.tsx` porte désormais un `<Link to="/analytics/sql">` réel,
    affiché quand l'utilisateur porte `analytics.sql_lab.access`."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/pages/CatalogPage.tsx" in inbound["/analytics/sql"]


def test_admin_collections_has_an_inbound_link():
    """La fusion Paramètres/Administration a déplacé ce lien : il ne vit
    plus dans `AdminExtensionsPage.tsx` (qui ne fait plus que rendre
    `SettingsNav`) mais dans `SettingsNav.tsx`, le point d'entrée unique
    partagé par les sept pages admin."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/shell/chrome/SettingsNav.tsx" in inbound["/admin/collections"]


def test_rest_url_built_by_interpolation_is_not_counted_as_an_inbound_link():
    """`fetch(`${coreUrl}/analytics/sql`)` (api/domains/exportsIngestion.ts)
    est une URL d'API, pas un lien de navigation : le littéral n'est pas
    précédé d'un guillemet ouvrant, donc la règle ne le compte pas."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/api/domains/exportsIngestion.ts" not in inbound["/analytics/sql"]


def test_i18n_catalog_is_never_an_inbound_link():
    """Le catalogue i18n contient des libellés, pas des liens."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    for files in inbound.values():
        assert not any(f.startswith("shell/src/i18n/") for f in files)


def test_score_is_zero_for_a_shell_surface_without_inbound_link():
    """Facts synthétiques (pas le dépôt réel, cf. `/bookmarks`/`/analytics/sql`
    désormais atteignables depuis le plan `2026-09-24-vague-a-
    bloquants-decouvrabilite.md`) : ce test vérifie le calcul de
    `score_reachability`, pas un fait du dépôt à un instant donné."""
    facts = ReachabilityFacts(
        shell_routes=("/orphan",),
        shell_inbound={"/orphan": ()},
        rest_paths=frozenset(),
        mcp_tools=frozenset(),
    )
    score = score_reachability(_feature(shell=("/orphan",)), facts)
    assert score.value == 0.0
    assert score.evidence["/orphan"] == "aucun lien entrant"


def test_score_is_hundred_for_a_shell_surface_with_an_inbound_link():
    facts = collect_reachability_facts(REPO, rest_paths=frozenset(), mcp_tools=frozenset())
    assert score_reachability(_feature(shell=("/admin/collections",)), facts).value == 100.0


def test_score_averages_every_declared_surface():
    facts = ReachabilityFacts(
        shell_routes=("/a", "/b"),
        shell_inbound={"/a": ("x.tsx",), "/b": ()},
        rest_paths=frozenset({"GET /v1/items"}),
        mcp_tools=frozenset({"query_features"}),
    )
    score = score_reachability(
        _feature(shell=("/a", "/b"), rest=("GET /v1/items",), mcp=("query_features",)),
        facts,
    )
    assert score.value == pytest.approx(75.0)


def test_score_is_not_applicable_without_any_technical_surface():
    """Undo/redo du builder, symbologie catégorielle : aucune route, aucun
    outil. Non applicable ≠ zéro — un 0 ici serait un mensonge pondéré."""
    facts = collect_reachability_facts(REPO, rest_paths=frozenset(), mcp_tools=frozenset())
    score = score_reachability(_feature(), facts)
    assert score.value is None


def test_load_inventory_rejects_a_duplicated_identifier(tmp_path):
    row = {
        "id": "dup",
        "domaine": "D",
        "fonctionnalite": "F",
        "preuve": ["core/app/items/routes.py"],
        "surfaces": {},
        "priorite": "basse",
    }
    path = tmp_path / "inv.jsonl"
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="identifiants dupliqués : dup"):
        load_inventory(path)


def test_load_inventory_rejects_a_missing_required_key(tmp_path):
    path = tmp_path / "inv.jsonl"
    path.write_text(json.dumps({"id": "x", "domaine": "D"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clés manquantes"):
        load_inventory(path)
