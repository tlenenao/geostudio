# SPDX-License-Identifier: Apache-2.0
"""AUD-136 : contrôle de fraîcheur des images de la stack locale."""

import runpy
from pathlib import Path

# run_path : pas de __pycache__ laissé sous scripts/ (hors .gitignore).
stale_services = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/check_image_freshness.py")
)["stale_services"]


def test_image_older_than_its_context_is_stale():
    images = {"core": 100.0, "shell": 300.0, "titiler": 200.0}
    contexts = {"core": 150.0, "shell": 250.0, "titiler": 200.0}
    assert stale_services(images, contexts) == ["core"]


def test_context_without_commit_is_never_stale():
    assert stale_services({"minio": 1.0}, {}) == []
