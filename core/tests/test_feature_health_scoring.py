# SPDX-License-Identifier: Apache-2.0
"""Santé pondérée, priorité, reprise qualité, journal (SP-61, spec §3-§5, §7.2)."""

import json
import pathlib

import pytest

from scripts.feature_health.history import append_snapshot, last_snapshot
from scripts.feature_health.model import Feature, SubScore
from scripts.feature_health.quality import collect_quality_facts, quality_for
from scripts.feature_health.scoring import (
    load_thresholds,
    priority_rank,
    weighted_health,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="f",
        proofs=("core/app/auth/routes.py",),
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


WEIGHTS = {"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20}


def test_weighted_health_is_the_weighted_mean_of_applicable_subscores():
    # Vérifié indépendamment (piège CLAUDE.md n°3, le texte littéral d'un
    # plan est parfois faux) : 0.30*80 + 0.25*100 + 0.25*50 + 0.20*100 = 81.5,
    # pas 82.5 — la formule de weighted_health est confirmée correcte par
    # ailleurs (le test de renormalisation ci-dessous calcule juste avec la
    # même fonction et son 88.0 attendu est, lui, exact).
    subscores = {
        "tests": SubScore(80.0, {}),
        "atteignabilite": SubScore(100.0, {}),
        "garde": SubScore(50.0, {}),
        "dette": SubScore(100.0, {}),
    }
    assert weighted_health(subscores, WEIGHTS) == pytest.approx(81.5)


def test_a_non_applicable_subscore_is_excluded_and_the_weights_renormalise():
    """Un widget builtin n'a ni route ni outil : lui coller 0 de « garde »
    serait un mensonge pondéré (spec §3)."""
    subscores = {
        "tests": SubScore(80.0, {}),
        "atteignabilite": SubScore(None, {}),
        "garde": SubScore(None, {}),
        "dette": SubScore(100.0, {}),
    }
    assert weighted_health(subscores, WEIGHTS) == pytest.approx(88.0)


def test_health_is_none_when_no_subscore_is_applicable():
    subscores = {name: SubScore(None, {}) for name in WEIGHTS}
    assert weighted_health(subscores, WEIGHTS) is None


def test_priority_rank_sorts_what_matters_most_and_goes_worst():
    """`priorité × (100 − santé)` — aucune moyenne des deux axes n'est
    jamais calculée (spec §4)."""
    assert priority_rank(_feature(priority="haute"), 40.0) == pytest.approx(180.0)
    assert priority_rank(_feature(priority="basse"), 40.0) == pytest.approx(60.0)
    assert priority_rank(_feature(priority="haute"), 100.0) == 0.0


def test_thresholds_are_loaded_from_the_versioned_json():
    thresholds = load_thresholds(REPO / "core/scripts/feature_health_thresholds.json")
    assert set(thresholds.weights) == {"tests", "atteignabilite", "garde", "dette"}
    assert sum(thresholds.weights.values()) == pytest.approx(1.0)
    assert 0 < thresholds.floor_high_priority <= 100
    assert 0 < thresholds.floor_median <= 100


def test_quality_facts_read_the_real_repository():
    facts = collect_quality_facts(REPO)
    assert "app/auth" in facts.mypy_strict_modules
    assert len(facts.mypy_strict_modules) == 6
    assert any("->" in exemption for exemption in facts.layer_exemptions)
    assert len(facts.eslint_disabled) == 10
    assert len(facts.typing_escapes) == 7


def test_quality_for_reports_facts_without_any_note():
    facts = collect_quality_facts(REPO)
    reported = quality_for(_feature(proofs=("core/app/auth/routes.py",)), facts)
    assert reported["typage_strict"] is True
    assert "note" not in reported
    assert "score" not in reported


def test_quality_is_never_part_of_the_health_score():
    """Sinon ajouter une exemption `ignore_imports` légitime et documentée
    ferait échouer la build — cela punirait le geste honnête (spec §5)."""
    from scripts.feature_health import scoring

    source = pathlib.Path(scoring.__file__).read_text(encoding="utf-8")
    assert "quality" not in source.split("def weighted_health")[1].split("def ")[0]


def test_snapshot_is_appended_never_rewritten(tmp_path):
    journal = tmp_path / "historique-sante.jsonl"
    append_snapshot(journal, [("f1", 50.0, {})], commit="aaa", date="2026-09-07")
    append_snapshot(journal, [("f1", 62.0, {})], commit="bbb", date="2026-09-08")
    lines = journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["commit"] == "aaa"
    assert last_snapshot(journal) == {"f1": 62.0}


def test_last_snapshot_of_an_absent_journal_is_empty(tmp_path):
    assert last_snapshot(tmp_path / "absent.jsonl") == {}
