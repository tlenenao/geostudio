# SPDX-License-Identifier: Apache-2.0
"""§2 de la spec 2026-09-19 : porte de complétude — un job release.yml
pouvait déclarer une image dans sa matrice sans jamais réellement la
publier (geostudio-titiler, trouvé en déploiement réel : 404 anonyme sur
GHCR, pas un problème de visibilité). `test_deployability.py` compare déjà
compose ↔ matrice déclarée, mais jamais matrice déclarée ↔ registre réel
— c'est ce que ce script comble, à exécuter en CI après chaque publication."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.check_published_images import check_all, release_images  # noqa: E402


def test_release_images_lists_the_nine_matrix_images():
    images = release_images()
    assert images == [
        "geostudio-core",
        "geostudio-shell",
        "geostudio-postgis",
        "geostudio-titiler",
        "geostudio-appexport-standalone",
        "geostudio-export-worker",
        "geostudio-qgis-worker",
        "geostudio-appexport-runtime-builder",
        "geostudio-backup",
    ]


def test_check_all_reports_missing_images():
    def fake_checker(image: str, tag: str) -> bool:
        return image != "geostudio-titiler"

    missing = check_all(
        ["geostudio-core", "geostudio-titiler", "geostudio-shell"],
        "edge",
        checker=fake_checker,
    )

    assert missing == ["geostudio-titiler"]


def test_check_all_reports_nothing_when_everything_is_published():
    missing = check_all(["geostudio-core"], "edge", checker=lambda image, tag: True)

    assert missing == []
