# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4).

Consomme les deux documents que `CLAUDE.md` oblige à mettre à jour à chaque
clôture de SP, sans les dupliquer :
- `docs/revue/2026-09-04-analyse-gaps.md` — depuis la mise à jour du
  2026-09-06, l'état des GAP vit dans **trois tableaux distincts sous des
  sous-titres H3 propres** : `### ✅ Fermé (nn)`, `### 🟡 Partiel (n)`,
  `### 🔴 Ouvert / non implémenté (n)`. Dans ces tableaux, la colonne 2 est
  une **prose de description** (« Manque », « Ce qui est fait/reste »),
  jamais un mot de statut : c'est la **section** qui fait foi, pas le
  contenu de la cellule. Une ligne peut couvrir une plage
  (`| GAP-16 à GAP-23 | … |`), qui est dépliée. Les lignes des sections
  Partiel et Ouvert comptent toutes comme ouvertes, par construction ; la
  section Fermé n'est jamais scannée.
- `docs/revue/2026-09-04-backlog.md` — une section `### REV-nnn — <sévérité> — …`
  par entrée, avec une ligne `- **État :** ouvert…` et une ligne
  `- **Preuve :** `chemin:lignes ; chemin:lignes``.

Pondération volontairement grossière (spec §6.2, « grossier, robuste ») :
critical −40, important −20, minor/observation −10, inconnu −20, plancher 0.
Les `GAP` n'exposent pas leur impact dans les tableaux d'état (il vit dans les
tableaux de détail, à un autre format par référentiel) : ils comptent tous
pour −20. Simplification assumée plutôt qu'un parseur fragile de trois
tableaux différents.

Limites assumées : le rattachement se fait par **chemin de fichier cité dans
la preuve** ; une entrée dont la preuve ne nomme aucun fichier ne pénalise
aucune fonctionnalité, et une entrée qui cite un fichier partagé pénalise
toutes les fonctionnalités qui le citent. `open_gaps` ne scanne que les
deux sections `### 🟡 Partiel` et `### 🔴 Ouvert / non implémenté`, chacune
bornée par le prochain titre `#`/`##`/`###` qui la suit — la section
`### ✅ Fermé` (et les tableaux de détail plus loin dans le document, qui
contiennent de la prose libre pouvant mentionner les mots « ouvert »/
« fermé » sans être une ligne de statut) sont ainsi exclus mécaniquement.
Si l'un des deux titres de section disparaît du document, la fonction ne
compte simplement aucune entrée pour cette section (silencieusement plus
étroit, pas une erreur) plutôt que d'échouer."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature, SubScore

GAPS_DOC = "docs/revue/2026-09-04-analyse-gaps.md"
BACKLOG_DOC = "docs/revue/2026-09-04-backlog.md"

_GAP_ROW_RE = re.compile(r"^\|\s*GAP-(\d+)(?:\s*à\s*GAP-(\d+))?\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6} .*$", re.MULTILINE)
_GAP_PARTIEL_SECTION_START_RE = re.compile(r"^### 🟡 Partiel\b.*$", re.MULTILINE)
_GAP_OUVERT_SECTION_START_RE = re.compile(r"^### 🔴 Ouvert\b.*$", re.MULTILINE)
_REV_HEADING_RE = re.compile(r"^### (REV-\d+)\s*—\s*([^—\n]*)", re.MULTILINE)
# Ligne « - **État :** … » (fermant `**` juste après les deux-points) OU
# « - **État : … **» (fermant `**` en fin d'état, avant une éventuelle
# annotation non grasse) — les deux formes sont réellement utilisées dans
# `docs/revue/2026-09-04-backlog.md`.
_REV_ETAT_RE = re.compile(
    r"^- \*\*État\s*:\*\*\s*(?P<inline>.+)$|^- \*\*État\s*:\s*(?P<wrapped>[^*\n]+)\*\*",
    re.MULTILINE,
)
_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}")
_SEVERITIES = ("critical", "important", "minor", "observation")
_PENALTY = {"critical": 40.0, "important": 20.0, "minor": 10.0, "observation": 10.0}
_DEFAULT_PENALTY = 20.0


def _section_text(text: str, start_pattern: re.Pattern[str]) -> str:
    """Texte d'une section H3, bornée par le prochain titre `#`/`##`/`###`.

    Renvoie une chaîne vide si le titre de section n'est pas trouvé — plus
    étroit silencieusement plutôt qu'une erreur (cf. docstring du module)."""
    start_match = start_pattern.search(text)
    if start_match is None:
        return ""
    start = start_match.end()
    end_match = _HEADING_RE.search(text, start)
    end = end_match.start() if end_match else len(text)
    return text[start:end]


@dataclasses.dataclass(frozen=True)
class DebtItem:
    identifier: str
    severity: str
    paths: tuple[str, ...]


def _gap_rows_from_section(section_text: str, items: dict[str, DebtItem]) -> None:
    """Chaque ligne `| GAP-nn |` d'une section Partiel/Ouvert est ouverte par
    construction — la section fait foi, pas le contenu de la colonne 2."""
    for match in _GAP_ROW_RE.finditer(section_text):
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        line_end = section_text.find("\n", match.end())
        row = section_text[match.end() : line_end if line_end != -1 else None]
        paths = tuple(dict.fromkeys(_PATH_RE.findall(row)))
        for number in range(first, last + 1):
            identifier = f"GAP-{number:02d}"
            items.setdefault(identifier, DebtItem(identifier, "gap", paths))


def open_gaps(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / GAPS_DOC).read_text(encoding="utf-8")
    items: dict[str, DebtItem] = {}
    _gap_rows_from_section(_section_text(text, _GAP_PARTIEL_SECTION_START_RE), items)
    _gap_rows_from_section(_section_text(text, _GAP_OUVERT_SECTION_START_RE), items)
    return tuple(items.values())


def open_revs(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / BACKLOG_DOC).read_text(encoding="utf-8")
    headings = list(_REV_HEADING_RE.finditer(text))
    items: list[DebtItem] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[match.end() : end]
        state = _REV_ETAT_RE.search(body)
        if state is None:
            continue
        state_text = state.group("inline") or state.group("wrapped")
        if not state_text.lower().startswith(("ouvert", "partiel")):
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
