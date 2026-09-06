# SPDX-License-Identifier: Apache-2.0
"""Index AST des routes REST du cœur, et sous-score « garde » (SP-61, spec §3.3).

Pourquoi l'AST plutôt qu'`openapi.json` : (1) `openapi.json` est produit par
`create_app()` avec les flags de capacité **éteints**, donc les 7 routeurs
conditionnels de `main.py` (pipelines, export, appexport, tileset3d, terrain3d,
copilot, admin_tools) n'y figurent pas — 26 routes réelles, tout le domaine
Automatisation compris ; (2) les gardes d'autorisation de ce dépôt ne sont pas
des dépendances FastAPI, elles sont appelées dans le **corps** de la fonction de
route, donc invisibles de toute lecture de signature.

`openapi.json` reste le **contre-témoin** : tout chemin qu'il déclare (sauf
`/health`) doit être retrouvé par cet index, sinon la composition de préfixes
est fausse (test dédié).

Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- la résolution de garde s'arrête au **même module** : un helper importé d'un
  autre module et qui porterait la garde n'est pas suivi (aucun cas réel à
  `1516a3a1`, mais rien ne l'empêche d'apparaître) ;
- profondeur 2 exactement : route → helper → garde. Une chaîne plus longue
  n'est pas suivie ;
- une garde présente mais inopérante (mauvais privilège, condition toujours
  vraie) compte comme une garde : ce sous-score mesure la **présence** d'un
  point de contrôle, jamais sa justesse ;
- un chemin construit dynamiquement (`@router.get(SOME_CONSTANT)`) n'est pas
  vu ; le contre-témoin `openapi.json` le ferait échouer si le cas apparaissait
  sur un routeur non flaggé."""

from __future__ import annotations

import ast
import dataclasses
import pathlib

from scripts.feature_health.model import Feature, SubScore

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
V1_PREFIX = "/v1"
GUARD_NAMES = frozenset(
    {
        "require_privilege",
        "require_any_privilege",
        "has_privilege",
        "can",
        "rls_scope",
        "assert_egress_allowed",
    }
)
AUTH_REQUIRED = "get_current_user"
AUTH_OPTIONAL = "get_current_user_optional"


@dataclasses.dataclass(frozen=True)
class RouteFact:
    method: str
    path: str
    module: str
    function: str
    guards: frozenset[str]
    auth: str  # "required" | "optional" | "none"
    flag: str | None


def surface_id(fact: RouteFact) -> str:
    return f"{fact.method} {fact.path}"


def rest_surface_ids(routes: tuple[RouteFact, ...]) -> frozenset[str]:
    return frozenset(surface_id(fact) for fact in routes)


def _router_modules(repo: pathlib.Path) -> list[pathlib.Path]:
    """Tout module de `core/app` qui construit un `APIRouter`, sauf `main.py`.

    Un glob sur `routes.py` en manquerait deux, mesurés : `app/features/tiles.py`
    (la route `.mvt`) et `app/schemas_routes.py`."""
    modules = []
    for path in sorted((repo / "core/app").rglob("*.py")):
        if path.name == "main.py":
            continue
        if "APIRouter(" in path.read_text(encoding="utf-8"):
            modules.append(path)
    return modules


def _router_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "router":
            continue
        if isinstance(node.value, ast.Call):
            for keyword in node.value.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    return str(keyword.value.value)
    return ""


def _route_decorators(node: ast.AST) -> list[ast.Call]:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return []
    found = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "router"
            and func.attr in HTTP_METHODS
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            found.append(decorator)
    return found


def _called_names(node: ast.AST) -> set[str]:
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _depends_names(node: ast.AST) -> set[str]:
    """Les fonctions passées à `Depends(...)` — elles ne sont pas *appelées*
    dans le corps, seules `Depends` l'est."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id != "Depends":
                continue
            for argument in child.args:
                if isinstance(argument, ast.Name):
                    names.add(argument.id)
                elif isinstance(argument, ast.Attribute):
                    names.add(argument.attr)
    return names


def _capability_flags(repo: pathlib.Path) -> dict[str, str]:
    """`{"pipelines_routes": "is_etl_enabled", …}` depuis les `if is_*_enabled():`
    de `create_app()`, plus la table d'alias d'import
    (`from app.pipelines import routes as pipelines_routes`) pour retomber sur
    un chemin de module."""
    main = repo / "core/app/main.py"
    tree = ast.parse(main.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for name in node.names:
                if name.asname:
                    aliases[name.asname] = f"{node.module}.{name.name}".replace(".", "/") + ".py"
    flags: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
            continue
        test = node.test.func
        flag = test.id if isinstance(test, ast.Name) else getattr(test, "attr", None)
        if not flag:
            continue
        for called in ast.walk(node):
            if not isinstance(called, ast.Call):
                continue
            func = called.func
            if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
                continue
            for argument in called.args:
                if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name):
                    module = aliases.get(argument.value.id)
                    if module:
                        flags[module] = flag
    return flags


def index_rest_routes(repo: pathlib.Path) -> tuple[RouteFact, ...]:
    flags = _capability_flags(repo)
    facts: list[RouteFact] = []
    for path in _router_modules(repo):
        module = path.relative_to(repo / "core").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = _router_prefix(tree)
        local_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for node in ast.walk(tree):
            for decorator in _route_decorators(node):
                called = _called_names(node)
                dependencies = _depends_names(node)
                guards = called & GUARD_NAMES
                for name in called | dependencies:
                    helper = local_functions.get(name)
                    if helper is not None and helper is not node:
                        guards |= _called_names(helper) & GUARD_NAMES
                if AUTH_REQUIRED in dependencies:
                    auth = "required"
                elif AUTH_OPTIONAL in dependencies:
                    auth = "optional"
                else:
                    auth = "none"
                facts.append(
                    RouteFact(
                        method=decorator.func.attr.upper(),
                        path=V1_PREFIX + prefix + decorator.args[0].value,
                        module=module,
                        function=node.name,
                        guards=frozenset(guards),
                        auth=auth,
                        flag=flags.get(module),
                    )
                )
    return tuple(facts)


def score_guard(feature: Feature, routes: tuple[RouteFact, ...]) -> SubScore:
    by_id = {surface_id(fact): fact for fact in routes}
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for surface in feature.rest:
        if surface in feature.public:
            scores.append(100.0)
            evidence[surface] = "publique par conception (déclarée)"
            continue
        fact = by_id.get(surface)
        if fact is None:
            scores.append(0.0)
            evidence[surface] = "route introuvable dans l'index"
        elif fact.guards:
            scores.append(100.0)
            evidence[surface] = sorted(fact.guards)
        elif fact.auth in ("required", "optional"):
            scores.append(50.0)
            evidence[surface] = "authentification seule, aucune garde d'autorisation"
        else:
            scores.append(0.0)
            evidence[surface] = "ni authentification ni garde, non déclarée publique"
    if not scores:
        return SubScore(None, {"raison": "aucune surface REST déclarée"})
    return SubScore(sum(scores) / len(scores), evidence)
