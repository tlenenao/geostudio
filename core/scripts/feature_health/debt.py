# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4).

Consomme les deux documents que `CLAUDE.md` oblige à mettre à jour à chaque
clôture de SP, sans les dupliquer :
- `docs/revue/2026-09-04-analyse-gaps.md` — le tableau d'état, dont chaque
  ligne est `| GAP-nn | Ouvert \\| **Fermé** \\| **Partiel** | commentaire |`.
  Une ligne peut couvrir une plage (`| GAP-16 à GAP-23 | Ouvert | … |`), qui est
  dépliée. `**Partiel**` compte comme ouvert.
- `docs/revue/2026-09-04-backlog.md` — une section `### REV-nnn — <sévérité> — …`
  par entrée, avec une ligne `- **État :** ouvert…` et une ligne
  `- **Preuve :** `chemin:lignes ; chemin:lignes``.

Pondération volontairement grossière (spec §6.2, « grossier, robuste ») :
critical −40, important −20, minor/observation −10, inconnu −10, plancher 0.
Les `GAP` n'exposent pas leur impact dans le tableau d'état (il vit dans les
tableaux de détail, à un autre format par référentiel) : ils comptent tous
pour −20. Simplification assumée plutôt qu'un parseur fragile de trois
tableaux différents.

Limites assumées : le rattachement se fait par **chemin de fichier cité dans
la preuve** ; une entrée dont la preuve ne nomme aucun fichier ne pénalise
aucune fonctionnalité, et une entrée qui cite un fichier partagé pénalise
toutes les fonctionnalités qui le citent."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature, SubScore

GAPS_DOC = "docs/revue/2026-09-04-analyse-gaps.md"
BACKLOG_DOC = "docs/revue/2026-09-04-backlog.md"

_GAP_ROW_RE = re.compile(r"^\|\s*GAP-(\d+)(?:\s*à\s*GAP-(\d+))?\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
_REV_HEADING_RE = re.compile(r"^### (REV-\d+)\s*—\s*([^—\n]*)", re.MULTILINE)
_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}")
_SEVERITIES = ("critical", "important", "minor", "observation")
_PENALTY = {"critical": 40.0, "important": 20.0, "minor": 10.0, "observation": 10.0}
_DEFAULT_PENALTY = 20.0


@dataclasses.dataclass(frozen=True)
class DebtItem:
    identifier: str
    severity: str
    paths: tuple[str, ...]


def open_gaps(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / GAPS_DOC).read_text(encoding="utf-8")
    items: dict[str, DebtItem] = {}
    for match in _GAP_ROW_RE.finditer(text):
        status = match.group(3).lower()
        if "fermé" in status and "partiel" not in status:
            continue
        if "ouvert" not in status and "partiel" not in status:
            continue
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        line_end = text.find("\n", match.end())
        row = text[match.end() : line_end if line_end != -1 else None]
        paths = tuple(dict.fromkeys(_PATH_RE.findall(row)))
        for number in range(first, last + 1):
            identifier = f"GAP-{number:02d}"
            items.setdefault(identifier, DebtItem(identifier, "gap", paths))
    return tuple(items.values())


def open_revs(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / BACKLOG_DOC).read_text(encoding="utf-8")
    headings = list(_REV_HEADING_RE.finditer(text))
    items: list[DebtItem] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[match.end() : end]
        state = re.search(r"^- \*\*État :\*\*\s*(.+)$", body, re.MULTILINE)
        if state is None or not state.group(1).lower().startswith(("ouvert", "partiel")):
            continue
        label = match.group(2).strip().lower()
        severity = next((s for s in _SEVERITIES if s in label), "inconnu")
        proof = re.search(r"^- \*\*Preuve :\*\*\s*(.+)$", body, re.MULTILINE)
        paths = tuple(dict.fromkeys(_PATH_RE.findall(proof.group(1)))) if proof else ()
        items.append(DebtItem(match.group(1), severity, paths))
    return tuple(items)


def collect_debt_facts(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    return open_gaps(repo) + open_revs(repo)


def score_debt(feature: Feature, items: tuple[DebtItem, ...]) -> SubScore:
    proofs = set(feature.proofs)
    value = 100.0
    evidence: dict[str, object] = {}
    for item in items:
        if not proofs.intersection(item.paths):
            continue
        value -= _PENALTY.get(item.severity, _DEFAULT_PENALTY)
        evidence[item.identifier] = item.severity
    if not evidence:
        evidence["raison"] = "aucune entrée GAP/REV ouverte ne cite ces fichiers"
    return SubScore(max(0.0, value), evidence)
