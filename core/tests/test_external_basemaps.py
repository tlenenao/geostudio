# SPDX-License-Identifier: Apache-2.0
"""AUD-122 : un déploiement souverain coupe tout fond de carte tiers par défaut."""

from app.auth.dependency import is_external_basemaps_enabled
from app.ingestion.importer import default_basemap_style
from app.instance.routes import get_instance_info


def test_default_is_external(monkeypatch):
    monkeypatch.delenv("CORE_EXTERNAL_BASEMAPS_ENABLED", raising=False)
    assert is_external_basemaps_enabled() is True
    assert default_basemap_style().startswith("https://")
    assert get_instance_info()["externalBasemapsEnabled"] is True


def test_sovereign_mode_uses_local_blank_style(monkeypatch):
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")
    assert is_external_basemaps_enabled() is False
    assert default_basemap_style() == "/basemaps/blank.json"
    assert get_instance_info()["externalBasemapsEnabled"] is False
