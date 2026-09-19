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
    assert len(index_rest_routes(REPO)) == 148


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
    ignorerait 27 routes réelles — dont tout le domaine Automatisation."""
    indexed = {(fact.method, fact.path) for fact in index_rest_routes(REPO)}
    flagged = sorted(indexed - _openapi_operations())
    assert len(flagged) == 27
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
    assert len(ids) == 148


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


def test_a_directly_called_collection_read_gate_is_recognised_as_a_guard():
    """`get_collection_tile` (`app/features/tiles.py`) appelle
    `get_readable_collection(...)` en corps de route — chokepoint d'autorisation
    des collections (GAP-19/22/50/60), qui recoupe avec `can()` en interne
    (`app/collections/routes.py`, vérifié). Absent de `GUARD_NAMES` jusqu'ici
    uniquement par omission — l'appel est déjà visible de `_called_names`."""
    fact = next(
        f
        for f in index_rest_routes(REPO)
        if (f.method, f.path) == ("GET", "/v1/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
    )
    assert "get_readable_collection" in fact.guards


def test_a_directly_called_pipeline_access_gate_is_recognised_as_a_guard():
    """`require_pipeline_access` (`app/pipelines/service.py`) appelle `can()` et
    lève 404/403 — vérifié par lecture directe. Trois routes l'appellent
    directement en corps (pas via une fonction de service intermédiaire, cf.
    Tâche 2 pour les trois autres)."""
    guarded_directly = {
        "GET /v1/pipelines/{item_id}/runs",
        "POST /v1/pipelines/{item_id}/preview",
        "GET /v1/pipelines/{item_id}/webhook-tokens",
    }
    by_id = {f"{f.method} {f.path}": f for f in index_rest_routes(REPO)}
    for surface in guarded_directly:
        assert "require_pipeline_access" in by_id[surface].guards, surface


def test_guard_reached_through_an_imported_service_function_is_found():
    """POST /v1/pipelines/{item_id}/run → run_pipeline_route → run_pipeline_service
    (importé d'app.pipelines.service) → require_pipeline_access(...) → can(). Avant
    ce volet, cette route ressortait « authentification seule » alors que la
    garde est réelle — vérifié par lecture directe de service.py:78-93."""
    by_id = {f"{f.method} {f.path}": f for f in index_rest_routes(REPO)}
    guarded_via_service = {
        "POST /v1/pipelines/{item_id}/run": "run_pipeline_service",
        "POST /v1/pipelines/{item_id}/webhook-tokens": "create_webhook_token_service",
        "DELETE /v1/pipelines/{item_id}/webhook-tokens/{token_id}": "revoke_webhook_token_service",
    }
    for surface in guarded_via_service:
        assert "require_pipeline_access" in by_id[surface].guards, surface


def test_import_resolution_does_not_invent_guards_on_an_unguarded_helper():
    """Non-régression : une fonction importée dont le corps n'appelle réellement
    aucun nom de GUARD_NAMES doit rester sans garde détecté — la résolution ne
    doit jamais sur-détecter."""
    fact = next(
        f for f in index_rest_routes(REPO) if (f.method, f.path) == ("GET", "/v1/pipelines/ops")
    )
    # /v1/pipelines/ops est déclarée publique par conception (feature.public) —
    # ce test vérifie l'index brut, pas score_guard : la fonction de route
    # elle-même n'appelle aucune garde, cross-module ou non.
    assert fact.guards == frozenset()


def test_a_declared_auto_scoped_surface_scores_100():
    """Une route authentifiée mais sans garde nommée reconnue peut être
    déclarée « auto-scopée » (tenant/utilisateur, ou donnée de référence
    sans propriétaire) — vérifié route par route avant déclaration, jamais
    un totem générique (SP « priorite-moyenne-sante-90 » Volet A.3)."""
    routes = (
        RouteFact(
            method="GET",
            path="/v1/notifications",
            module="app.notifications.routes",
            function="get_notifications",
            guards=frozenset(),
            auth="required",
            flag=None,
        ),
    )
    feature = _feature(
        rest=("GET /v1/notifications",),
        auto_scoped_guard=("GET /v1/notifications",),
    )
    score = score_guard(feature, routes)
    assert score.value == 100.0
    assert "auto-restreint" in score.evidence["GET /v1/notifications"]


def test_an_undeclared_authenticated_only_surface_still_scores_50():
    """Non-régression : ne pas déclarer une route dans `auto_scoped_guard`
    doit laisser le score existant (50) inchangé — la déclaration n'élève
    jamais un score par défaut, seulement une route vérifiée une à une."""
    routes = (
        RouteFact(
            method="GET",
            path="/v1/notifications",
            module="app.notifications.routes",
            function="get_notifications",
            guards=frozenset(),
            auth="required",
            flag=None,
        ),
    )
    feature = _feature(rest=("GET /v1/notifications",))
    assert score_guard(feature, routes).value == 50.0


def test_the_real_inventory_declares_the_six_auto_scoped_features_correctly():
    """Contre-témoin sur le dépôt réel : les 6 fonctionnalités visées par le
    Volet A.3 atteignent bien 100 de garde une fois déclarées — pas une
    fixture, le vrai `docs/revue/inventaire-fonctionnalites.jsonl` et le vrai
    index de routes."""
    from scripts.feature_health.model import load_inventory

    features = {
        f.identifier: f
        for f in load_inventory(REPO / "docs/revue/inventaire-fonctionnalites.jsonl")
    }
    routes = index_rest_routes(REPO)
    targeted = [
        "automatisation-marquer-une-ou-toutes-les-notifications-comme-lues",
        "automatisation-choisir-sa-preference-de-notification-toutes-echecs-seulement-auc",
        "automatisation-etre-notifie-dans-une-cloche-persistante-du-shell-des-jobs-en-ech",
        "cartographie-uploader-une-icone-svg-personnalisee-dans-une-bibliotheque-d-icones",
        "administration-copilote-ia-dans-le-builder-d-app-orchestrant-des-outils-mcp-reel",
        "catalogue-metadonnees-catalogue-curate-de-licences-frequences-langues",
    ]
    for identifier in targeted:
        feature = features[identifier]
        assert feature.auto_scoped_guard, identifier
        assert score_guard(feature, routes).value == 100.0, identifier


def test_auto_scoped_guard_declarations_are_real_and_authenticated_routes():
    """`auto_scoped_guard` n'est pas mécaniquement détectable comme `public`
    (aucun signal AST pour « correctement scopé par la logique applicative »)
    — pas de test de bijection possible ici, contrairement à
    `test_publiques_declaration_matches_the_ast_unguarded_set`. Mais un
    invariant plus faible reste vérifiable et réel : chaque surface déclarée
    `auto_scoped_guard`, toutes fonctionnalités de l'inventaire réel
    confondues, doit être (a) une route qui existe bel et bien dans l'index
    AST réel, et (b) authentifiée (`auth in ("required", "optional")`) — le
    hatch ne doit jamais pouvoir accorder 100 à une route absente (typo, route
    renommée) ni à une route réellement publique/non authentifiée. Trouvé et
    corrigé par la revue finale de branche : `score_guard` accordait 100 à
    toute surface déclarée avant même de vérifier ces deux points."""
    from scripts.feature_health.model import load_inventory

    features = load_inventory(REPO / "docs/revue/inventaire-fonctionnalites.jsonl")
    routes = index_rest_routes(REPO)
    by_id = {surface_id(fact): fact for fact in routes}
    declared = {
        (feature.identifier, surface)
        for feature in features
        for surface in feature.auto_scoped_guard
    }
    missing = sorted(
        f"{identifier} → {surface}" for identifier, surface in declared if surface not in by_id
    )
    unauthenticated = sorted(
        f"{identifier} → {surface}"
        for identifier, surface in declared
        if surface in by_id and by_id[surface].auth not in ("required", "optional")
    )
    assert not missing and not unauthenticated, (
        "auto_scoped_guard déclare une route absente de l'index AST réel, ou "
        "réellement non authentifiée — le hatch de score_guard accorderait "
        "alors 100 à tort.\n"
        f"Absentes de l'index : {missing}\n"
        f"Non authentifiées : {unauthenticated}"
    )
