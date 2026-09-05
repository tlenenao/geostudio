# SPDX-License-Identifier: Apache-2.0
import pytest

from app.catalog import metadata as m


def test_license_ids_match_the_curated_list():
    assert m.LICENSE_IDS == {
        "etalab-2.0",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "odbl-1.0",
        "proprietary",
        "other",
    }


def test_frequency_ids_match_the_curated_list():
    assert m.FREQUENCY_IDS == {
        "continuous",
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "annual",
        "irregular",
    }


def test_language_ids_match_the_curated_list():
    assert m.LANGUAGE_IDS == {"fr", "en", "de", "es", "it"}


def test_resolve_license_returns_entry_with_dcat_and_spdx_ids():
    entry = m.resolve_license("etalab-2.0")
    assert entry is not None
    assert entry.dcat_uri == "https://spdx.org/licenses/etalab-2.0.html"
    assert entry.spdx_id == "etalab-2.0"


def test_resolve_license_unknown_id_returns_none():
    assert m.resolve_license("bogus") is None


def test_resolve_frequency_unknown_id_returns_none():
    assert m.resolve_frequency("bogus") is None


def test_resolve_language_is_always_resolvable_for_a_valid_id():
    assert m.resolve_language("fr").alpha3 == "FRA"


def test_validate_license_id_accepts_empty_string():
    assert m.validate_license_id("") == ""


def test_validate_license_id_accepts_none():
    assert m.validate_license_id(None) is None


def test_validate_license_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown license id"):
        m.validate_license_id("bogus")


def test_validate_frequency_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown update_frequency id"):
        m.validate_frequency_id("bogus")


def test_validate_language_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown language id"):
        m.validate_language_id("bogus")


def test_validate_language_id_rejects_empty_string():
    # Contrairement à license/frequency, "" n'est jamais un id de langue
    # valide : language a toujours une vraie valeur (défaut "fr").
    with pytest.raises(ValueError, match="unknown language id"):
        m.validate_language_id("")
