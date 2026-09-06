# SPDX-License-Identifier: Apache-2.0
"""Sous-score « atteignabilité » (SP-61, spec §3.2).

Une surface montée mais qu'aucun lien n'atteint est morte pour l'utilisateur.
C'est ce calcul, fait à la main une fois par huit agents en SP-42, qui a
produit les 13 lignes `inerte` — et, refait mécaniquement, `/bookmarks`
(GAP-80) puis `/analytics/sql` qu'ils avaient tous deux manqués.

Règle : un lien entrant est une occurrence du **littéral de chemin précédée
d'un guillemet ouvrant** (`"`, `'` ou backtick) dans un fichier de
`shell/src`, hors `routes.tsx` (sa propre déclaration), hors fichiers de test,
hors `shell/src/i18n/` (des libellés, pas des liens). Exiger le guillemet
ouvrant est ce qui distingue un lien de navigation d'une URL d'API
interpolée (`fetch(`${coreUrl}/analytics/sql`)`) — vérifié sur les 28 chemins
réels.

Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- un lien construit par concaténation à partir d'un préfixe variable
  (``navigate(`${base}/bookmarks`)``) n'est pas vu : la règle exige le
  guillemet ouvrant immédiatement avant le chemin ;
- un lien présent mais rendu inatteignable par une garde de privilège n'est
  pas distingué d'un lien réellement offert ;
- inversement, une occurrence du littéral dans un commentaire ou une chaîne
  qui n'est pas un lien compte comme un lien entrant (faux négatif de
  détection d'inertie) ;
- la réciproque côté REST/MCP n'est pas mesurée ici : « montée » veut dire
  présente dans l'index de surfaces, pas « appelée par le shell »."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature, SubScore

ROUTES_TSX = "shell/src/shell/routes.tsx"
_ROUTE_PATH_RE = re.compile(r'path="([^"]+)"')
_EXCLUDED_INBOUND_PREFIXES = ("shell/src/i18n/",)
_TEST_MARKERS = (".test.", ".spec.", "__tests__/")


def declared_shell_routes(repo: pathlib.Path) -> tuple[str, ...]:
    """Les chemins déclarés par `routes.tsx`, dans l'ordre du fichier."""
    source = (repo / ROUTES_TSX).read_text(encoding="utf-8")
    return tuple(dict.fromkeys(_ROUTE_PATH_RE.findall(source)))


def route_prefix(route_path: str) -> str:
    """`/apps/:pk/edit` → `/apps` : la partie littérale, avant tout paramètre."""
    segments: list[str] = []
    for segment in route_path.split("/"):
        if segment.startswith(":") or segment.startswith("*"):
            break
        segments.append(segment)
    return "/".join(segments) or "/"


def _searchable_files(repo: pathlib.Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for path in sorted((repo / "shell/src").rglob("*.ts*")):
        relative = path.relative_to(repo).as_posix()
        if relative == ROUTES_TSX:
            continue
        if any(marker in relative for marker in _TEST_MARKERS):
            continue
        if any(relative.startswith(prefix) for prefix in _EXCLUDED_INBOUND_PREFIXES):
            continue
        files.append((relative, path.read_text(encoding="utf-8")))
    return files


def collect_shell_inbound(
    repo: pathlib.Path, routes: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    files = _searchable_files(repo)
    inbound: dict[str, tuple[str, ...]] = {}
    for route in routes:
        prefix = route_prefix(route)
        if prefix == "/":
            inbound[route] = ("<racine, atteignable par construction>",)
            continue
        needles = (f'"{prefix}', f"'{prefix}", f"`{prefix}")
        inbound[route] = tuple(
            relative for relative, blob in files if any(needle in blob for needle in needles)
        )
    return inbound


@dataclasses.dataclass(frozen=True)
class ReachabilityFacts:
    shell_routes: tuple[str, ...]
    shell_inbound: dict[str, tuple[str, ...]]
    rest_paths: frozenset[str]
    mcp_tools: frozenset[str]


def collect_reachability_facts(
    repo: pathlib.Path, *, rest_paths: frozenset[str], mcp_tools: frozenset[str]
) -> ReachabilityFacts:
    routes = declared_shell_routes(repo)
    return ReachabilityFacts(
        shell_routes=routes,
        shell_inbound=collect_shell_inbound(repo, routes),
        rest_paths=rest_paths,
        mcp_tools=mcp_tools,
    )


def score_reachability(feature: Feature, facts: ReachabilityFacts) -> SubScore:
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for route in feature.shell:
        hits = facts.shell_inbound.get(route, ())
        scores.append(100.0 if hits else 0.0)
        evidence[route] = list(hits) if hits else "aucun lien entrant"
    for surface in feature.rest:
        mounted = surface in facts.rest_paths
        scores.append(100.0 if mounted else 0.0)
        evidence[surface] = "montée" if mounted else "absente de l'index des routes"
    for tool in feature.mcp:
        declared = tool in facts.mcp_tools
        scores.append(100.0 if declared else 0.0)
        evidence[tool] = "déclaré" if declared else "absent de l'index des outils MCP"
    if not scores:
        return SubScore(None, {"raison": "aucune surface technique déclarée"})
    return SubScore(sum(scores) / len(scores), evidence)
