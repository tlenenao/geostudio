# SPDX-License-Identifier: Apache-2.0
"""AUD-115 : négociation de langue, traduction des erreurs, gabarits d'e-mail."""

import pytest

from app.i18n_core import (
    error_code,
    negotiate_locale,
    normalize_locale,
    tr,
    translate_detail,
    translate_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("fr", "fr"), ("fr-FR", "fr"), ("EN_us", "en"), ("de", None), ("", None), (None, None)],
)
def test_normalize_locale(raw, expected):
    assert normalize_locale(raw) == expected


def test_negotiate_locale_honours_q_values_and_falls_back():
    assert negotiate_locale("en;q=0.5, fr;q=0.9") == "fr"
    assert negotiate_locale("de, en-GB;q=0.8") == "en"
    assert negotiate_locale("de") is None  # aucune langue prise en charge : pas de traduction
    assert negotiate_locale(None) is None


def test_translate_detail_known_pattern_and_unknown_passthrough():
    assert translate_detail("tile not found", "fr") == "Tuile introuvable"
    assert translate_detail("pipeline not found", "fr") == "Pipeline introuvable"
    assert translate_detail("something never catalogued", "fr") == "something never catalogued"
    assert translate_detail("tile not found", "en") == "tile not found"
    assert translate_detail("tile not found", None) == "tile not found"


def test_error_code_is_a_stable_slug_of_the_source_detail():
    assert error_code("tile not found") == "tile_not_found"
    assert error_code("bbox must be minx,miny,maxx,maxy") == "bbox_must_be_minx_miny_maxx_maxy"
    assert error_code("") == "error"


def test_translate_title_uses_http_phrase():
    assert translate_title(404, "Not Found", "fr") == "Introuvable"
    assert translate_title(404, "Not Found", None) == "Not Found"


def test_tr_templates_and_default_locale(monkeypatch):
    assert tr("alert.subject", "fr", rule="R", state="firing") == "[GeoStudio] R : firing"
    assert tr("report.subject", "en", title="T") == "[GeoStudio] Report: T"
    monkeypatch.setenv("CORE_DEFAULT_LOCALE", "en")
    assert tr("report.subject", None, title="T") == "[GeoStudio] Report: T"
    monkeypatch.delenv("CORE_DEFAULT_LOCALE")
    assert tr("report.subject", None, title="T") == "[GeoStudio] Rapport : T"


def test_with_default_tz_fills_only_when_absent():
    from app.analytics.aggregate import AggregateRequestBody
    from app.i18n_core import with_default_tz

    body = AggregateRequestBody(agg="count")
    assert with_default_tz(body, "Europe/Paris").timeZone == "Europe/Paris"
    assert with_default_tz(body, None).timeZone is None
    explicit = AggregateRequestBody(agg="count", timeZone="Asia/Tokyo")
    assert with_default_tz(explicit, "Europe/Paris").timeZone == "Asia/Tokyo"


def test_format_local_and_export_tz():
    from datetime import UTC, datetime

    from app.analytics.export import _xlsx_cell_value, export_filename
    from app.i18n_core import format_local

    moment = datetime(2026, 1, 15, 23, 30, tzinfo=UTC)
    assert format_local(moment, "Europe/Paris", "fr") == "2026-01-16 00:30 (Europe/Paris)"
    assert format_local(moment.replace(tzinfo=None), None, "fr") == "2026-01-15 23:30 (UTC)"
    assert _xlsx_cell_value(moment, "Europe/Paris") == datetime(2026, 1, 16, 0, 30)
    assert _xlsx_cell_value(moment) == datetime(2026, 1, 15, 23, 30)
    assert export_filename("A", format="csv", tz="Asia/Tokyo").startswith("a-")
