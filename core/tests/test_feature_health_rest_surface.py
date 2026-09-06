# SPDX-License-Identifier: Apache-2.0
"""Index AST des routes REST et sous-score « garde » (SP-61, spec §3.3).

Le contre-témoin `openapi.json` est la propriété centrale de ce fichier : si le
résolveur compose mal un chemin, un chemin d'`openapi.json` cesse d'être
retrouvé et le test échoue bruyamment. C'est ce qui rend croyable un index
dérivé de l'AST plutôt que du framework lui-même."""

import json
import pathlib

from scripts.feature_health.model import Feature
from scripts.feature_health.rest_surface import (
    RouteFact,
    index_rest_routes,
    rest_surface_ids,
    score_guard,
    surface_id,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _openapi_operations() -> set[tuple[str, str]]:
    document = json.loads((REPO / "core/openapi.json").read_text(encoding="utf-8"))
    return {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    }


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="fonctionnalité de test",
        proofs=(),
        rest=(),
        mcp=(),
        shell=(),
        public=(),
        priority="moyenne",
        priority_source="declaree",
        raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_index_finds_every_declared_route():
    assert len(index_rest_routes(REPO)) == 147


def test_every_openapi_operation_is_resolved_by_the_index():
    """Contre-témoin. `/health` est déclaré par `@app.get` dans `main.py`,
    hors routeur et hors versionnement (SP-57b) : seule exception admise."""
    indexed = {(fact.method, fact.path) for fact in index_rest_routes(REPO)}
    unresolved = sorted(
        operation
        for operation in _openapi_operations()
        if operation not in indexed and operation[1] != "/health"
    )
    assert unresolved == []


def test_flagged_routes_are_indexed_although_absent_from_openapi():
    """`scripts/export_openapi.py` appelle `create_app()` flags éteints : les 7
    routeurs conditionnels de `main.py` ne figurent pas dans `openapi.json`.
    Un inventaire qui n'aurait dérivé ses surfaces que d'`openapi.json`
    ignorerait 26 routes réelles — dont tout le domaine Automatisation."""
    indexed = {(fact.method, fact.path) for fact in index_rest_routes(REPO)}
    flagged = sorted(indexed - _openapi_operations())
    assert len(flagged) == 26
    assert ("GET", "/v1/pipelines/{item_id}/runs") in flagged


def test_router_prefix_is_composed_with_the_v1_prefix():
    facts = {fact.path for fact in index_rest_routes(REPO)}
    assert "/v1/dcat/catalog" in facts
    assert "/v1/compliance/purges/{purge_id}" in facts


def test_capability_flag_is_resolved_from_main():
    by_module = {fact.module: fact.flag for fact in index_rest_routes(REPO)}
    assert by_module["app/pipelines/routes.py"] == "is_etl_enabled"
    assert by_module["app/collections/routes.py"] is None


def test_guard_called_directly_in_the_route_body_is_found():
    fact = next(
        f for f in index_rest_routes(REPO) if (f.method, f.path) == ("POST", "/v1/collections")
    )
    assert "require_privilege" in fact.guards


def test_guard_reached_through_a_same_module_helper_is_found():
    """`GET /v1/configs/{config_id}` → `get_config` → `_require_access`
    (`configs/routes.py:57`) → `can()`. Une résolution en profondeur 1
    classerait cette route « sans garde » — faux positif du type que le piège
    n°11 de CLAUDE.md décrit."""
    fact = next(
        f
        for f in index_rest_routes(REPO)
        if (f.method, f.path) == ("GET", "/v1/configs/{config_id}")
    )
    assert "can" in fact.guards


def test_public_by_design_routes_carry_no_guard():
    """Décompte par `(module, function)`, pas par le seul nom de fonction :
    `app/features/routes.py::conformance` (OGC Features) et
    `app/stac/routes.py::conformance` (OGC STAC) portent le même nom depuis
    SP-6/SP-12a — un décompte par nom seul les confond en une seule entrée
    (16 au lieu de 17), écart trouvé en exécutant (piège CLAUDE.md n°3),
    corrigé ici plutôt que dans le résolveur AST (les 17 routes distinctes
    sont bien retrouvées, cf. `index_rest_routes`)."""
    facts = [f for f in index_rest_routes(REPO) if not f.guards and f.auth == "none"]
    unguarded = {f.function for f in facts}
    assert {"public_sitemap", "public_robots", "get_public_item", "conformance"} <= unguarded
    assert len({(f.module, f.function) for f in facts}) == 17


def test_surface_id_is_method_space_path():
    fact = RouteFact(
        method="GET",
        path="/v1/items",
        module="app/items/routes.py",
        function="list_items",
        guards=frozenset(),
        auth="required",
        flag=None,
    )
    assert surface_id(fact) == "GET /v1/items"


def test_rest_surface_ids_feeds_the_reachability_facts():
    ids = rest_surface_ids(index_rest_routes(REPO))
    assert "GET /v1/items" in ids
    assert len(ids) == 147


def _fact(function, guards, auth):
    return RouteFact(
        method="GET",
        path=f"/v1/{function}",
        module="app/x/routes.py",
        function=function,
        guards=frozenset(guards),
        auth=auth,
        flag=None,
    )


def test_guard_score_is_hundred_with_an_authorization_guard():
    routes = (_fact("guarded", {"require_privilege"}, "required"),)
    assert score_guard(_feature(rest=("GET /v1/guarded",)), routes).value == 100.0


def test_guard_score_is_fifty_with_authentication_but_no_authorization():
    routes = (_fact("authed", set(), "required"),)
    assert score_guard(_feature(rest=("GET /v1/authed",)), routes).value == 50.0


def test_guard_score_is_zero_when_nothing_guards_an_undeclared_route():
    routes = (_fact("open", set(), "none"),)
    assert score_guard(_feature(rest=("GET /v1/open",)), routes).value == 0.0


def test_a_route_declared_public_by_design_is_not_penalised():
    routes = (_fact("open", set(), "none"),)
    feature = _feature(rest=("GET /v1/open",), public=("GET /v1/open",))
    score = score_guard(feature, routes)
    assert score.value == 100.0
    assert score.evidence["GET /v1/open"] == "publique par conception (déclarée)"


def test_guard_score_is_not_applicable_without_rest_surface():
    assert score_guard(_feature(shell=("/bookmarks",)), ()).value is None
