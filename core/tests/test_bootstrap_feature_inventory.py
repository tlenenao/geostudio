# SPDX-License-Identifier: Apache-2.0
"""Migration ponctuelle SP-42 → inventaire (SP-61, spec §8)."""

import json

import pytest

from scripts.bootstrap_feature_inventory import (
    bootstrap_priority,
    proof_paths,
    slug_for,
)


@pytest.mark.parametrize(
    "utility,expected",
    [(9, "haute"), (8, "haute"), (7, "moyenne"), (5, "moyenne"), (4, "basse"), (1, "basse")],
)
def test_bootstrap_priority_maps_the_sp42_utility_note(utility, expected):
    assert bootstrap_priority(utility) == expected


def test_proof_paths_keeps_the_path_and_drops_the_line_numbers():
    """L'ancrage par `chemin:ligne` ne tient pas deux jours (spec §8)."""
    raw = "shell/src/pages/AdminInfrastructurePage.tsx:70-79 ; docker-compose.yml:88-90"
    assert proof_paths(raw) == (
        "shell/src/pages/AdminInfrastructurePage.tsx",
        "docker-compose.yml",
    )


def test_slug_is_stable_and_ascii():
    assert slug_for("Administration", "Accéder à la console MinIO") == (
        "administration-acceder-a-la-console-minio"
    )


def test_slugs_are_deduplicated_by_suffix():
    from scripts.bootstrap_feature_inventory import unique_slugs

    assert unique_slugs(["a", "a", "b"]) == ["a", "a-2", "b"]


def test_generated_rows_load_back_through_the_inventory_loader(tmp_path):
    from scripts.bootstrap_feature_inventory import build_rows
    from scripts.feature_health.model import load_inventory

    source = tmp_path / "src.jsonl"
    source.write_text(
        json.dumps(
            {
                "domaine": "Catalogue",
                "fonctionnalite": "Lister les items",
                "description": "",
                "preuve": "core/app/items/routes.py:10-20",
                "note": "",
                "notes": {"utilite": 9},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "inv.jsonl"
    target.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in build_rows(source)) + "\n",
        encoding="utf-8",
    )
    features = load_inventory(target)
    assert features[0].identifier == "catalogue-lister-les-items"
    assert features[0].priority == "haute"
    assert features[0].priority_source == "amorcage-sp42"
