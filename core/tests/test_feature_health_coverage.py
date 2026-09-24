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

# `core/coverage.xml` n'existe qu'à la sortie du process qui le produit
# (`--cov-report=xml`, hook `pytest_sessionfinish`) : dans le job CI `core`
# lui-même, qui invoque ces tests DANS ce même process, le fichier n'existe
# jamais encore — ce n'est pas un flake, c'est structurel (poule et œuf).
# `shell/coverage/coverage-summary.json` n'existe carrément jamais dans ce
# job (produit par le job `shell`, un runner distinct). Les deux assertions
# réelles sont exercées par le job CI `feature-health`, qui télécharge les
# deux artefacts après coup et rejoue explicitement ce fichier (cf.
# `.github/workflows/ci.yml`) — jamais absorbées silencieusement, juste
# déplacées là où les deux fichiers coexistent réellement.
_CORE_COVERAGE_MISSING = not (REPO / "core/coverage.xml").exists()
_SHELL_COVERAGE_MISSING = not (REPO / "shell/coverage/coverage-summary.json").exists()


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


@pytest.mark.skipif(
    _CORE_COVERAGE_MISSING,
    reason="core/coverage.xml pas encore écrit dans ce process — lancer "
    "`uv run pytest --cov=app --cov-report=xml` puis rejouer ce test seul, "
    "ou voir le job CI `feature-health` qui l'exerce pour de vrai",
)
def test_core_rates_are_keyed_on_repo_relative_paths():
    """Piège de la spec §3.1 : `filename` est relatif à `core/app/`. Avec le
    mauvais préfixe, le rattachement tombe à 165/304 au lieu de 256/304."""
    rates = core_line_rates(REPO)
    assert "core/app/collections/routes.py" in rates
    assert 0.0 <= rates["core/app/collections/routes.py"] <= 100.0


@pytest.mark.skipif(
    _SHELL_COVERAGE_MISSING,
    reason="shell/coverage/coverage-summary.json produit par un job CI "
    "distinct (`shell`), jamais présent dans le job `core` — voir le job "
    "CI `feature-health` qui l'exerce pour de vrai",
)
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


def test_deployability_rules_follow_a_chain_of_divisions_not_just_one_hop():
    """`POSTGIS_DOCKERFILE = REPO / "deploy" / "postgis" / "Dockerfile"`
    (core/tests/test_deployability.py, ligne 79) est une chaîne à 3 segments —
    un détecteur limité à un seul saut la manque entièrement. Utilisée par un
    test réel de ce même fichier
    (`test_postgis_dockerfile_uses_multiarch_base_with_pgdg_packages`)."""
    rules = deployability_rules(REPO)
    assert "deploy/postgis/Dockerfile" in rules


def test_deployability_rules_scan_test_files_beyond_test_deployability_py():
    """Généralise REV-189 (`docs/revue/2026-09-04-backlog.md`) : un test réel
    qui ne vit pas dans le seul `core/tests/test_deployability.py` (ici
    `deploy/backup/test_retention.py`) était invisible à ce mécanisme."""
    rules = deployability_rules(REPO)
    assert rules["deploy/backup/retention.py"] == ("référence littérale dans test_retention.py",)


def test_deployability_rules_fall_back_to_a_literal_path_reference():
    """`deploy/backup/test_retention.py` n'est jamais nommé par une constante
    `REPO / "..."` où que ce soit dans `core/tests/` — seule sa mention
    littérale dans le docstring de `core/tests/test_restore_script.py`
    ("deploy/backup/test_retention.py ne l'est pas [ramassé par la CI]")
    le rend détectable par le mécanisme de repli."""
    rules = deployability_rules(REPO)
    assert "deploy/backup/test_retention.py" in rules


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
