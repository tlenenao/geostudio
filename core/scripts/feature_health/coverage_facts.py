# SPDX-License-Identifier: Apache-2.0
"""Sous-score « tests » (SP-61, spec §3.1).

Trois familles de preuve, trois sources :
- `core/app/**` → `core/coverage.xml`. Ses `filename` sont relatifs à
  `core/app/` (`<sources><source>…/core/app</source></sources>`), pas à
  `core/` : le mauvais préfixe fait chuter le rattachement de 256/304 à
  165/304 (mesuré, spec §3.1).
- `shell/src/**` → `shell/coverage/coverage-summary.json`, dont les clés sont
  des chemins **absolus** de la machine qui a produit le fichier. On
  relativise sur le segment `shell/`, jamais par rapport à la racine du dépôt
  courant : le worktree d'exécution n'est presque jamais celui de la mesure.
- infrastructure (`docker-compose*.yml`, `deploy/`, `.github/`, `scripts/`) →
  aucune couverture possible ; le signal naturel est l'existence d'une règle de
  `core/tests/test_deployability.py` qui touche ce fichier.

Limites assumées, pas couvertes :
- la couverture de ligne d'un fichier n'est pas la couverture d'une
  fonctionnalité : un fichier partagé par cinq fonctionnalités leur donne à
  toutes le même chiffre ;
- le rattachement d'une règle de déployabilité passe par les **constantes de
  module** (`BASE = REPO / "docker-compose.yml"`) référencées nommément dans
  le corps d'un `test_*` ; une règle qui reçoit son chemin par un helper
  (`services(path)`) n'est comptée que si la constante apparaît malgré tout
  dans le test — le compte est donc un plancher, pas un total ;
- « une spec E2E cite ce chemin de route » ne prouve pas qu'elle exerce la
  fonctionnalité, seulement qu'elle y navigue."""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import re
import xml.etree.ElementTree as ET

from scripts.feature_health.model import Feature, SubScore

_INFRA_PREFIXES = ("docker-compose", "deploy/", ".github/", "scripts/", ".env")


def core_line_rates(repo: pathlib.Path) -> dict[str, float]:
    path = repo / "core/coverage.xml"
    if not path.exists():
        raise FileNotFoundError(f"{path} — lancer `uv run pytest --cov=app --cov-report=xml`")
    root = ET.parse(path).getroot()
    return {
        "core/app/" + element.attrib["filename"]: float(element.attrib["line-rate"]) * 100
        for element in root.findall(".//class")
    }


def shell_line_rates(repo: pathlib.Path) -> dict[str, float]:
    path = repo / "shell/coverage/coverage-summary.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} — lancer `npm run test -- --coverage` dans shell/")
    document = json.loads(path.read_text(encoding="utf-8"))
    rates: dict[str, float] = {}
    for key, summary in document.items():
        if key == "total" or "/shell/" not in key:
            continue
        relative = "shell/" + key.split("/shell/", 1)[1]
        rates[relative] = float(summary["lines"]["pct"])
    return rates


def e2e_specs(repo: pathlib.Path) -> dict[str, tuple[str, ...]]:
    """Route shell → specs E2E qui citent son littéral de chemin."""
    from scripts.feature_health.reachability import declared_shell_routes, route_prefix

    specs = [
        (path.relative_to(repo).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted((repo / "shell/e2e").glob("*.spec.ts"))
    ]
    found: dict[str, tuple[str, ...]] = {}
    for route in declared_shell_routes(repo):
        prefix = route_prefix(route)
        needles = (f'"{prefix}', f"'{prefix}", f"`{prefix}")
        found[route] = tuple(
            name for name, blob in specs if any(needle in blob for needle in needles)
        )
    return found


def _resolve_repo_relative(value: ast.expr) -> str | None:
    """Résout `REPO / "a" / "b" / ...` en chemin repo-relatif, en suivant une
    chaîne de divisions de profondeur arbitraire — pas seulement un saut.

    SP « priorite-moyenne-sante-90 » Volet A.1 : le détecteur d'origine ne
    reconnaissait qu'un seul `REPO / "chemin"` — `QGIS_DOCKERFILE = REPO /
    "deploy" / "qgis-worker" / "Dockerfile"` (`core/tests/test_deployability.py`)
    lui était invisible (vérifié : `deployability_rules()` renvoyait
    `AUCUNE RÈGLE` pour ce fichier malgré un test réel qui l'exerce)."""
    if isinstance(value, ast.Name) and value.id == "REPO":
        return ""
    if (
        isinstance(value, ast.BinOp)
        and isinstance(value.op, ast.Div)
        and isinstance(value.right, ast.Constant)
    ):
        base = _resolve_repo_relative(value.left)
        if base is None:
            return None
        segment = str(value.right.value)
        return f"{base}/{segment}" if base else segment
    return None


def _test_files(repo: pathlib.Path) -> list[pathlib.Path]:
    """Tout fichier `test_*.py` sous `core/tests/` ou `deploy/**`, à
    l'exception des tests du mécanisme de mesure lui-même
    (`test_feature_health*.py`) — généralise REV-189
    (`docs/revue/2026-09-04-backlog.md`, 2026-09-14) : un test réel qui ne
    vit pas dans le seul `core/tests/test_deployability.py` (par ex.
    `deploy/backup/test_retention.py`) était invisible à ce mécanisme.

    L'exclusion de `test_feature_health*.py` n'est pas cosmétique : ces
    fichiers citent en toutes lettres, dans leurs docstrings et assertions,
    des chemins d'infrastructure réels à titre d'exemple (cf. les tests du
    présent module) — sans elle, le repli par sous-chaîne littérale
    ci-dessous les confondrait avec une vraie preuve de test."""
    return sorted(
        path
        for path in repo.glob("core/tests/test_*.py")
        if not path.name.startswith("test_feature_health")
    ) + sorted(repo.glob("deploy/**/test_*.py"))


_PATH_LOOKALIKE = re.compile(r"(?:deploy|scripts|\.github)/[\w.\-/]+\.\w+")


def deployability_rules(repo: pathlib.Path) -> dict[str, tuple[str, ...]]:
    rules: dict[str, list[str]] = {}
    for path in _test_files(repo):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        constants: dict[str, str] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target, value = node.targets[0], node.value
            if not isinstance(target, ast.Name):
                continue
            candidate = _resolve_repo_relative(value)
            if candidate is not None and (repo / candidate).is_file():
                constants[target.id] = candidate
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            for constant, file_path in constants.items():
                if constant in names:
                    rules.setdefault(file_path, []).append(node.name)
        # Repli par sous-chaîne littérale (même esprit que `e2e_specs()`
        # ci-dessous) : un test qui exerce un fichier sans jamais construire
        # de constante `REPO / "..."` — import nu, chemin construit
        # dynamiquement — reste invisible au mécanisme ci-dessus. Si le
        # fichier de test le cite en toutes lettres (docstring/commentaire),
        # et que le chemin cité existe réellement, c'est une preuve valide.
        for match in sorted(set(_PATH_LOOKALIKE.findall(text))):
            if match not in rules and (repo / match).is_file():
                rules.setdefault(match, []).append(f"référence littérale dans {path.name}")
    return {key: tuple(value) for key, value in rules.items()}


@dataclasses.dataclass(frozen=True)
class CoverageFacts:
    core_rates: dict[str, float]
    shell_rates: dict[str, float]
    e2e_specs: dict[str, tuple[str, ...]]
    deployability_rules: dict[str, tuple[str, ...]]


def collect_coverage_facts(repo: pathlib.Path) -> CoverageFacts:
    return CoverageFacts(
        core_rates=core_line_rates(repo),
        shell_rates=shell_line_rates(repo),
        e2e_specs=e2e_specs(repo),
        deployability_rules=deployability_rules(repo),
    )


def score_tests(feature: Feature, facts: CoverageFacts) -> SubScore:
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for proof in feature.proofs:
        if proof in facts.core_rates:
            rate = facts.core_rates[proof]
        elif proof in facts.shell_rates:
            rate = facts.shell_rates[proof]
        elif proof.startswith(_INFRA_PREFIXES):
            covering = facts.deployability_rules.get(proof, ())
            rate = 100.0 if covering else 0.0
            evidence[proof] = list(covering) or "aucune règle de test_deployability.py"
            scores.append(rate)
            continue
        else:
            evidence[proof] = "hors périmètre de mesure (ni couverture ni règle)"
            continue
        evidence[proof] = f"{rate:.1f} % de lignes couvertes"
        scores.append(rate)
    if feature.shell:
        citing = tuple(spec for route in feature.shell for spec in facts.e2e_specs.get(route, ()))
        scores.append(100.0 if citing else 0.0)
        evidence["e2e"] = (
            sorted(set(citing)) if citing else "aucune spec E2E ne cite " + ", ".join(feature.shell)
        )
    if not scores:
        return SubScore(None, {"raison": "aucune preuve mesurable", **evidence})
    return SubScore(sum(scores) / len(scores), evidence)
