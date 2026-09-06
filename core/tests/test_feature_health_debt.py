# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4)."""

import pathlib

import pytest

from scripts.feature_health.debt import (
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
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert "GAP-08" in identifiers  # « Géocodage BAN non traité »
    assert "GAP-05" not in identifiers  # fermé par SP-55
    assert "GAP-44" not in identifiers  # fermé par SP-53


def test_open_gaps_expands_a_range_row():
    """`| GAP-16 à GAP-23 | Ouvert | … |` compte pour huit entrées."""
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert {"GAP-16", "GAP-20", "GAP-23"} <= identifiers


def test_open_gaps_ignores_prose_mentions_outside_the_status_table():
    """Les tableaux de détail plus loin dans le document contiennent de la
    prose libre qui mentionne "ouvert"/"fermé" sans être une ligne de statut
    (ex. "l'ouverture de SP-42", "8 ont été refermés", "non couvert par aucun
    test", "déjà couvert GAP-40") — GAP-03/39/46/47/67 sont réellement
    **Fermé** dans le tableau d'état et ne doivent pas ressortir comme
    ouverts."""
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert identifiers.isdisjoint({"GAP-03", "GAP-39", "GAP-46", "GAP-47", "GAP-67"})


def test_open_revs_reads_the_etat_line():
    items = {item.identifier: item for item in open_revs(REPO)}
    assert "REV-001" in items
    assert items["REV-001"].severity == "critical"
    assert "REV-165" not in items or items["REV-165"].severity in {
        "critical",
        "important",
        "minor",
        "observation",
        "inconnu",
    }


def test_open_revs_carries_the_proof_paths():
    items = {item.identifier: item for item in open_revs(REPO)}
    assert "core/app/pipelines/jobs.py" in items["REV-001"].paths


def test_open_revs_includes_rev_164_despite_alternate_etat_bold_wrapping():
    """`- **État : partiellement fermé par SP-59** (2026-09-06) — …` referme
    le `**` en fin d'état, pas juste après les deux-points comme la forme
    habituelle `- **État :** …` — REV-164 doit rester comptée comme ouverte
    (son propre corps dit « Reste ouvert » sur le volet OIDC)."""
    identifiers = {item.identifier for item in open_revs(REPO)}
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
