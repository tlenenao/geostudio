# SPDX-License-Identifier: Apache-2.0
"""Reprise des portes de qualité existantes (SP-61, spec §5).

**Aucun calcul neuf, aucune note.** Le bilan affiche des faits déjà écrits
ailleurs, gratuits à lire, et discriminants par module ou par fichier :
- `mypy --strict` ne couvre que 6 modules sur 42 (`.github/workflows/ci.yml`) ;
- chaque exemption `ignore_imports` de `core/pyproject.toml` nomme une arête
  précise, avec sa justification ;
- 10 fichiers de `shell/src` portent un `eslint-disable` ;
- 7 portent un `@ts-expect-error` ou un `: any`.

Ces reprises **n'entrent pas dans la santé** : sinon ajouter une exemption
légitime et documentée ferait échouer la build, ce qui punirait exactement le
geste honnête qu'on veut encourager (spec §5)."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature

_MYPY_RE = re.compile(r"mypy --strict ((?:app/\S+\s*)+)")
_IGNORE_BLOCK_RE = re.compile(r"ignore_imports = \[(.*?)\]", re.DOTALL)
_EXEMPTION_RE = re.compile(r'"([^"]+->[^"]+)"')


@dataclasses.dataclass(frozen=True)
class QualityFacts:
    mypy_strict_modules: tuple[str, ...]
    layer_exemptions: tuple[str, ...]
    eslint_disabled: frozenset[str]
    typing_escapes: frozenset[str]


def collect_quality_facts(repo: pathlib.Path) -> QualityFacts:
    ci = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = _MYPY_RE.search(ci)
    modules = tuple(match.group(1).split()) if match else ()
    pyproject = (repo / "core/pyproject.toml").read_text(encoding="utf-8")
    block = _IGNORE_BLOCK_RE.search(pyproject)
    exemptions = tuple(_EXEMPTION_RE.findall(block.group(1))) if block else ()
    eslint, typing = set(), set()
    for path in sorted((repo / "shell/src").rglob("*.ts*")):
        blob = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo).as_posix()
        if "eslint-disable" in blob:
            eslint.add(relative)
        if "@ts-expect-error" in blob or ": any" in blob:
            typing.add(relative)
    return QualityFacts(modules, exemptions, frozenset(eslint), frozenset(typing))


def quality_for(feature: Feature, facts: QualityFacts) -> dict[str, object]:
    core_proofs = [proof for proof in feature.proofs if proof.startswith("core/app/")]
    strict = bool(core_proofs) and all(
        any(proof.startswith(f"core/{module}/") for module in facts.mypy_strict_modules)
        for proof in core_proofs
    )
    modules = {"app." + proof[len("core/app/") :].split("/", 1)[0] for proof in core_proofs}
    return {
        "typage_strict": strict if core_proofs else None,
        "exemptions_de_couches": [
            exemption
            for exemption in facts.layer_exemptions
            if any(exemption.startswith(module) for module in modules)
        ],
        "eslint_disable": sorted(set(feature.proofs) & facts.eslint_disabled),
        "echappatoires_de_typage": sorted(set(feature.proofs) & facts.typing_escapes),
    }
