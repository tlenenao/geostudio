# SPDX-License-Identifier: Apache-2.0
"""AUD-173 : l'exemple livré doit être accepté tel quel par le cœur."""

import json
from pathlib import Path

from app.extensions.schemas import ExtensionCreate

ROOT = Path(__file__).resolve().parents[2]


def test_example_manifest_is_accepted():
    manifest = json.loads((ROOT / "examples/external-widget/manifest.json").read_text())
    ExtensionCreate.model_validate(manifest)
