# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4)."""

import pathlib
import tempfile

import pytest

from scripts.feature_health.debt import (
    BACKLOG_DOC,
    GAPS_DOC,
    DebtItem,
    collect_debt_facts,
    open_gaps,
    open_revs,
    score_debt,
)
from scripts.feature_health.model import Feature

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="f",
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


def test_open_gaps_excludes_closed_ones():
    """Synthétique : le document réel évolue à chaque clôture de SP, un test
    ancré sur un identifiant réel casse à chaque fois (CI rouge 2026-10-07)."""
    with tempfile.TemporaryDirectory() as raw_repo:
        repo = pathlib.Path(raw_repo)
        doc = repo / GAPS_DOC
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            "### ✅ Fermé (1)\n\n| GAP-05 | fermé |\n\n"
            "### 🟡 Partiel (1)\n\n| GAP-29 | partiel |\n\n"
            "### 🔴 Ouvert / non implémenté (1)\n\n| GAP-03 | ouvert |\n\n"
            "## Suite\n",
            encoding="utf-8",
        )
        identifiers = {item.identifier for item in open_gaps(repo)}
    assert identifiers == {"GAP-29", "GAP-03"}


def test_open_gaps_expands_a_range_row():
    """`| GAP-16 à GAP-23 | … |` sous une section ouverte/partielle compte pour
    huit entrées.

    Le document réel ne contient plus aujourd'hui de ligne de plage dans ses
    tableaux (vérifié : aucune ligne `| GAP-nn à GAP-mm |` sous
    `### 🟡 Partiel`/`### 🔴 Ouvert` de `docs/revue/2026-09-04-analyse-gaps.md`,
    seulement de la prose hors tableau qui les mentionne) — ce test isole donc
    le mécanisme de dépliage sur un document minimal plutôt que de dépendre
    d'un exemple réel qui n'existe plus, pour ne pas se re-casser au prochain
    remaniement du document. `tmp_path` (pytest) n'est pas utilisable dans cet
    environnement (`/tmp/pytest-of-*` appartient à un autre utilisateur) —
    répertoire temporaire construit directement via `tempfile`."""
    with tempfile.TemporaryDirectory() as raw_repo:
        repo = pathlib.Path(raw_repo)
        doc = repo / GAPS_DOC
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            "### 🔴 Ouvert / non implémenté (1)\n\n"
            "| GAP | Manque |\n"
            "|---|---|\n"
            "| GAP-16 à GAP-23 | Plage synthétique de test |\n\n"
            "## Référentiel suivant\n",
            encoding="utf-8",
        )
        identifiers = {item.identifier for item in open_gaps(repo)}
    assert {"GAP-16", "GAP-20", "GAP-23"} <= identifiers
    assert len(identifiers) == 8  # GAP-16..GAP-23 inclus


def test_open_gaps_ignores_prose_mentions_outside_the_status_table():
    """Les tableaux de détail plus loin dans le document contiennent de la
    prose libre qui mentionne "ouvert"/"fermé" sans être une ligne de statut
    (ex. "l'ouverture de SP-42", "8 ont été refermés", "non couvert par aucun
    test", "déjà couvert GAP-40") — GAP-03/39/46/47/67 sont réellement
    **Fermé** dans le tableau d'état et ne doivent pas ressortir comme
    ouverts."""
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert identifiers.isdisjoint({"GAP-03", "GAP-39", "GAP-46", "GAP-47", "GAP-67"})


def _backlog_repo(raw_repo: str) -> pathlib.Path:
    repo = pathlib.Path(raw_repo)
    doc = repo / BACKLOG_DOC
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "### REV-001 — minor — coût 1\n\n- **État :** **fermé par SP-43**\n"
        "- **Preuve :** `core/app/closed.py:1`\n\n"
        "### REV-002 — minor — coût 1\n\n- **État :** partiellement fermé\n"
        "- **Preuve :** `core/app/mcp/tools.py:10`\n",
        encoding="utf-8",
    )
    return repo


def test_open_revs_reads_the_etat_line():
    """Synthétique (cf. `test_open_gaps_excludes_closed_ones`)."""
    with tempfile.TemporaryDirectory() as raw_repo:
        items = {item.identifier: item for item in open_revs(_backlog_repo(raw_repo))}
    assert set(items) == {"REV-002"}
    assert items["REV-002"].severity == "minor"


def test_open_revs_carries_the_proof_paths():
    with tempfile.TemporaryDirectory() as raw_repo:
        items = {item.identifier: item for item in open_revs(_backlog_repo(raw_repo))}
    assert items["REV-002"].paths == ("core/app/mcp/tools.py",)


def test_open_revs_includes_rev_164_despite_alternate_etat_bold_wrapping():
    """`- **État : partiellement fermé par SP-59** (2026-09-06) — …` referme
    le `**` en fin d'état, pas juste après les deux-points comme la forme
    habituelle `- **État :** …` — REV-164 doit rester comptée comme ouverte
    (son propre corps dit « Reste ouvert » sur le volet OIDC)."""
    with tempfile.TemporaryDirectory() as raw_repo:
        repo = pathlib.Path(raw_repo)
        doc = repo / BACKLOG_DOC
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            "### REV-164 — minor — coût 1\n\n"
            "- **État : partiellement fermé par SP-59** (2026-09-06) — reste OIDC\n",
            encoding="utf-8",
        )
        identifiers = {item.identifier for item in open_revs(repo)}
    assert "REV-164" in identifiers


def test_score_is_hundred_without_any_open_item():
    assert score_debt(_feature(proofs=("core/app/items/routes.py",)), ()).value == 100.0


def test_score_drops_by_severity():
    items = (
        DebtItem("REV-900", "critical", ("core/app/x.py",)),
        DebtItem("REV-901", "minor", ("core/app/x.py",)),
    )
    score = score_debt(_feature(proofs=("core/app/x.py",)), items)
    assert score.value == pytest.approx(50.0)  # 100 - 40 - 10
    assert score.evidence["REV-900"] == "critical"


def test_score_never_goes_below_zero():
    items = tuple(DebtItem(f"REV-{n}", "critical", ("core/app/x.py",)) for n in range(5))
    assert score_debt(_feature(proofs=("core/app/x.py",)), items).value == 0.0


def test_an_item_that_cites_another_file_does_not_count():
    items = (DebtItem("REV-900", "critical", ("core/app/other.py",)),)
    assert score_debt(_feature(proofs=("core/app/x.py",)), items).value == 100.0


def test_collect_returns_both_families():
    identifiers = {item.identifier for item in collect_debt_facts(REPO)}
    assert any(i.startswith("GAP-") for i in identifiers)
    assert any(i.startswith("REV-") for i in identifiers)
