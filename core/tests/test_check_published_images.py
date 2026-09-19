# SPDX-License-Identifier: Apache-2.0
"""§2 de la spec 2026-09-19 : porte de complétude — un job release.yml
pouvait déclarer une image dans sa matrice sans jamais réellement la
publier (geostudio-titiler, trouvé en déploiement réel : 404 anonyme sur
GHCR, pas un problème de visibilité). `test_deployability.py` compare déjà
compose ↔ matrice déclarée, mais jamais matrice déclarée ↔ registre réel
— c'est ce que ce script comble, à exécuter en CI après chaque publication."""

import base64
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.check_published_images import (  # noqa: E402
    _fetch_token,
    check_all,
    release_images,
)


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


class _FakeTokenResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return b'{"token": "fake-token"}'


def test_fetch_token_sends_basic_auth_when_github_token_is_set(monkeypatch):
    """Un package GHCR jamais publié ET un package privé renvoient le même
    403 anonyme (vérifié empiriquement contre le vrai registre) — un
    nouveau package GHCR naît privé par défaut, donc la porte de
    complétude doit s'authentifier pour distinguer les deux cas."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("GITHUB_ACTOR", "some-actor")
    captured: dict = {}

    def fake_urlopen(request, timeout=10):
        captured["headers"] = dict(request.header_items())
        return _FakeTokenResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    token = _fetch_token("geostudio-core")

    assert token == "fake-token"
    expected_credentials = base64.b64encode(b"some-actor:test-token-value").decode()
    assert captured["headers"]["Authorization"] == f"Basic {expected_credentials}"


def test_fetch_token_stays_anonymous_when_github_token_is_unset(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured: dict = {}

    def fake_urlopen(request, timeout=10):
        captured["headers"] = dict(request.header_items())
        return _FakeTokenResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    token = _fetch_token("geostudio-core")

    assert token == "fake-token"
    assert "Authorization" not in captured["headers"]
