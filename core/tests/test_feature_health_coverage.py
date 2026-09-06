# SPDX-License-Identifier: Apache-2.0
"""Sous-score « tests » (SP-61, spec §3.1)."""

import pathlib

import pytest

from scripts.feature_health.coverage_facts import (
    CoverageFacts,
    collect_coverage_facts,
    core_line_rates,
    deployability_rules,
    score_tests,
    shell_line_rates,
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


def test_core_rates_are_keyed_on_repo_relative_paths():
    """Piège de la spec §3.1 : `filename` est relatif à `core/app/`. Avec le
    mauvais préfixe, le rattachement tombe à 165/304 au lieu de 256/304."""
    rates = core_line_rates(REPO)
    assert "core/app/collections/routes.py" in rates
    assert 0.0 <= rates["core/app/collections/routes.py"] <= 100.0


def test_shell_rates_are_relativised_on_the_shell_segment():
    """Les clés du JSON sont des chemins absolus produits par une autre
    machine (ou un autre worktree) : on relativise sur le segment `shell/`,
    jamais en comparant à la racine du dépôt courant."""
    rates = shell_line_rates(REPO)
    assert "shell/src/pages/CatalogPage.tsx" in rates
    assert "total" not in rates


def test_deployability_rules_map_infra_paths_to_test_functions():
    rules = deployability_rules(REPO)
    assert len(rules["docker-compose.yml"]) >= 10
    assert "deploy/backup/restore.sh" in rules


def test_score_uses_the_line_rate_of_each_proof_file():
    facts = CoverageFacts(
        core_rates={"core/app/items/routes.py": 94.2},
        shell_rates={},
        e2e_specs={},
        deployability_rules={},
    )
    score = score_tests(_feature(proofs=("core/app/items/routes.py",)), facts)
    assert score.value == pytest.approx(94.2)


def test_score_of_an_infra_proof_is_binary_on_deployability_rules():
    facts = CoverageFacts(
        core_rates={},
        shell_rates={},
        e2e_specs={},
        deployability_rules={"docker-compose.yml": ("test_a", "test_b")},
    )
    covered = score_tests(_feature(proofs=("docker-compose.yml",)), facts)
    uncovered = score_tests(_feature(proofs=("deploy/postgis/Dockerfile",)), facts)
    assert covered.value == 100.0
    assert uncovered.value == 0.0


def test_a_shell_surface_adds_an_e2e_component_to_the_average():
    """Une fonctionnalité visible sans spec E2E ne peut pas obtenir 100 :
    « chaque feature visible a sa spec E2E Playwright » (CLAUDE.md)."""
    facts = CoverageFacts(
        core_rates={},
        shell_rates={"shell/src/pages/BookmarksPage.tsx": 100.0},
        e2e_specs={"/bookmarks": ()},
        deployability_rules={},
    )
    score = score_tests(
        _feature(proofs=("shell/src/pages/BookmarksPage.tsx",), shell=("/bookmarks",)),
        facts,
    )
    assert score.value == pytest.approx(50.0)
    assert score.evidence["e2e"] == "aucune spec E2E ne cite /bookmarks"


def test_score_is_not_applicable_without_any_attachable_proof():
    facts = CoverageFacts({}, {}, {}, {})
    assert score_tests(_feature(proofs=("docs/vision/quelque-chose.md",)), facts).value is None


def test_collect_refuses_to_degrade_silently_when_an_artefact_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="coverage.xml"):
        collect_coverage_facts(tmp_path)
