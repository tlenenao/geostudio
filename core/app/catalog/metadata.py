# SPDX-License-Identifier: Apache-2.0
"""Catalogues curatés pour les métadonnées de Collection/Item (chantier 4.9,
docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md §2).
Zéro dépendance interne (même discipline que app.roles.privileges) : ce
module est placé tout en bas du contrat de couches (core/pyproject.toml),
importable par app.collections, app.items, app.dcat et app.stac sans
exemption."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LicenseEntry:
    id: str
    label: str
    dcat_uri: str | None  # None = pas d'URI DCAT-AP dédiée (proprietary/other)
    spdx_id: str


LICENSES: list[LicenseEntry] = [
    LicenseEntry(
        id="etalab-2.0",
        label="Licence Ouverte / Open Licence 2.0 (Etalab)",
        dcat_uri="https://spdx.org/licenses/etalab-2.0.html",
        spdx_id="etalab-2.0",
    ),
    LicenseEntry(
        id="cc0-1.0",
        label="CC0 1.0 Universal",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC0",
        spdx_id="CC0-1.0",
    ),
    LicenseEntry(
        id="cc-by-4.0",
        label="Creative Commons Attribution 4.0",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC_BY",
        spdx_id="CC-BY-4.0",
    ),
    LicenseEntry(
        id="cc-by-sa-4.0",
        label="Creative Commons Attribution-ShareAlike 4.0",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC_BY_SA",
        spdx_id="CC-BY-SA-4.0",
    ),
    LicenseEntry(
        id="odbl-1.0",
        label="Open Database License 1.0",
        dcat_uri="https://spdx.org/licenses/ODbL-1.0.html",
        spdx_id="ODbL-1.0",
    ),
    LicenseEntry(
        id="proprietary",
        label="Propriétaire (aucune réutilisation)",
        dcat_uri=None,
        spdx_id="proprietary",
    ),
    LicenseEntry(id="other", label="Autre (URI à saisir)", dcat_uri=None, spdx_id="other"),
]

LICENSE_IDS: frozenset[str] = frozenset(entry.id for entry in LICENSES)
_LICENSES_BY_ID: dict[str, LicenseEntry] = {entry.id: entry for entry in LICENSES}


def resolve_license(license_id: str) -> LicenseEntry | None:
    return _LICENSES_BY_ID.get(license_id)


def validate_license_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in LICENSE_IDS:
        raise ValueError(f"unknown license id: {value!r}")
    return value


@dataclass(frozen=True)
class FrequencyEntry:
    id: str
    label: str
    mdr_freq_uri: str


FREQUENCIES: list[FrequencyEntry] = [
    FrequencyEntry(
        id="continuous",
        label="Continue",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/CONT",
    ),
    FrequencyEntry(
        id="daily",
        label="Quotidienne",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/DAILY",
    ),
    FrequencyEntry(
        id="weekly",
        label="Hebdomadaire",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/WEEKLY",
    ),
    FrequencyEntry(
        id="monthly",
        label="Mensuelle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/MONTHLY",
    ),
    FrequencyEntry(
        id="quarterly",
        label="Trimestrielle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/QUARTERLY",
    ),
    FrequencyEntry(
        id="annual",
        label="Annuelle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/ANNUAL",
    ),
    FrequencyEntry(
        id="irregular",
        label="Irrégulière",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/IRREG",
    ),
]

FREQUENCY_IDS: frozenset[str] = frozenset(entry.id for entry in FREQUENCIES)
_FREQUENCIES_BY_ID: dict[str, FrequencyEntry] = {entry.id: entry for entry in FREQUENCIES}


def resolve_frequency(frequency_id: str) -> FrequencyEntry | None:
    return _FREQUENCIES_BY_ID.get(frequency_id)


def validate_frequency_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in FREQUENCY_IDS:
        raise ValueError(f"unknown update_frequency id: {value!r}")
    return value


@dataclass(frozen=True)
class LanguageEntry:
    id: str
    label: str
    alpha3: str  # code de la table d'autorité UE (majuscules)


LANGUAGES: list[LanguageEntry] = [
    LanguageEntry("fr", "Français", "FRA"),
    LanguageEntry("en", "Anglais", "ENG"),
    LanguageEntry("de", "Allemand", "DEU"),
    LanguageEntry("es", "Espagnol", "SPA"),
    LanguageEntry("it", "Italien", "ITA"),
]

LANGUAGE_IDS: frozenset[str] = frozenset(entry.id for entry in LANGUAGES)
_LANGUAGES_BY_ID: dict[str, LanguageEntry] = {entry.id: entry for entry in LANGUAGES}


def resolve_language(language_id: str) -> LanguageEntry:
    # Toujours résolu : language n'est jamais vide (défaut "fr", modèle
    # Collection/Item) et les seules valeurs acceptées en écriture sont
    # celles de LANGUAGE_IDS (validate_language_id).
    return _LANGUAGES_BY_ID[language_id]


def validate_language_id(value: str | None) -> str | None:
    if value is not None and value not in LANGUAGE_IDS:
        raise ValueError(f"unknown language id: {value!r}")
    return value
