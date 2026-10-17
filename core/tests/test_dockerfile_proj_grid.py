# SPDX-License-Identifier: Apache-2.0
"""AUD-127 : l'image core (et donc worker) embarque la grille NTF->RGF93."""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def test_image_syncs_ntf_grid_before_chown():
    text = DOCKERFILE.read_text()
    sync = text.index("pyproj sync --file fr_ign_gr3df97a.tif")
    assert sync < text.index("chown -R app:app /opt/geostudio-home")
