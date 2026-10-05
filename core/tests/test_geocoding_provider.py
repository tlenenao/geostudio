# SPDX-License-Identifier: Apache-2.0
"""Second fournisseur de géocodage Nominatim (REV-102) et sélecteur."""

import httpx
import pytest
from fastapi import HTTPException

from app.geocoding.egress import EgressBlockedError, build_guarded_client
from app.geocoding.provider import BanGeocoder, GeocodeResult, NominatimGeocoder, get_geocoder

URL = "https://nominatim.openstreetmap.org/search"


def _geocoder(handler):
    seen: list[httpx.Request] = []

    def recording(request):
        seen.append(request)
        return handler(request)

    g = NominatimGeocoder(
        URL, client_factory=lambda: httpx.Client(transport=httpx.MockTransport(recording))
    )
    return g, seen


def test_maps_string_coordinates_to_floats_and_sends_user_agent():
    g, seen = _geocoder(
        lambda r: httpx.Response(
            200, json=[{"display_name": "Tulle", "lat": "45.26", "lon": "1.77"}]
        )
    )
    assert g.search("tulle", 3) == [GeocodeResult(label="Tulle", lon=1.77, lat=45.26)]
    assert seen[0].headers["user-agent"] == "GeoStudio/1 (geocoding)"
    assert seen[0].url.params["q"] == "tulle" and seen[0].url.params["limit"] == "3"
    assert seen[0].url.params["format"] == "jsonv2"


def test_default_client_factory_is_the_guarded_one():
    assert NominatimGeocoder(URL)._client_factory is build_guarded_client


def test_egress_allowlist_blocks_foreign_host(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "data.geopf.fr")
    with pytest.raises(EgressBlockedError):
        NominatimGeocoder("http://127.0.0.1:1/search").search("tulle", 1)


def test_provider_selection(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_URL", URL)
    monkeypatch.delenv("CORE_GEOCODING_PROVIDER", raising=False)
    assert isinstance(get_geocoder(), BanGeocoder)
    monkeypatch.setenv("CORE_GEOCODING_PROVIDER", "nominatim")
    assert isinstance(get_geocoder(), NominatimGeocoder)


def test_unknown_provider_is_503_with_explicit_message(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_PROVIDER", "google")
    with pytest.raises(HTTPException) as exc:
        get_geocoder()
    assert exc.value.status_code == 503
    assert "google" in exc.value.detail
