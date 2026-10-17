# SPDX-License-Identifier: Apache-2.0
"""Catalogues curatés pour les métadonnées de Collection/Item (chantier 4.9,
docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md §2).
Zéro dépendance interne (même discipline que app.roles.privileges) : ce
module est placé au-dessus de app.auth et app.users dans le contrat de
couches (core/pyproject.toml), ce qui permet à app.catalog.routes
d'importer depuis app.auth et app.users. Il reste importable sans exemption
par app.collections, app.items, app.dcat et app.stac."""

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


@dataclass(frozen=True)
class InspireTheme:
    id: str
    label: str
    iso_category: str  # MD_TopicCategoryCode (ISO 19115) associé

    @property
    def uri(self) -> str:
        return f"http://inspire.ec.europa.eu/theme/{self.id}"


# Les 34 thèmes des annexes I-III de la directive INSPIRE (registre inspire.ec.europa.eu).
INSPIRE_THEMES: list[InspireTheme] = [
    InspireTheme("ad", "Adresses", "location"),
    InspireTheme("au", "Unités administratives", "boundaries"),
    InspireTheme("cp", "Parcelles cadastrales", "planningCadastre"),
    InspireTheme("gg", "Systèmes de maillage géographique", "location"),
    InspireTheme("gn", "Dénominations géographiques", "location"),
    InspireTheme("hy", "Hydrographie", "inlandWaters"),
    InspireTheme("ps", "Sites protégés", "environment"),
    InspireTheme("rs", "Référentiels de coordonnées", "location"),
    InspireTheme("tn", "Réseaux de transport", "transportation"),
    InspireTheme("el", "Altitude", "elevation"),
    InspireTheme("ge", "Géologie", "geoscientificInformation"),
    InspireTheme("lc", "Occupation des terres", "imageryBaseMapsEarthCover"),
    InspireTheme("oi", "Ortho-imagerie", "imageryBaseMapsEarthCover"),
    InspireTheme("af", "Installations agricoles et aquacoles", "farming"),
    InspireTheme(
        "am",
        "Zones de gestion, de restriction ou de réglementation et unités de déclaration",
        "planningCadastre",
    ),
    InspireTheme("ac", "Conditions atmosphériques", "climatologyMeteorologyAtmosphere"),
    InspireTheme("br", "Régions biogéographiques", "biota"),
    InspireTheme("bu", "Bâtiments", "structure"),
    InspireTheme("er", "Sources d'énergie", "economy"),
    InspireTheme("ef", "Installations de suivi environnemental", "structure"),
    InspireTheme("hb", "Habitats et biotopes", "biota"),
    InspireTheme("hh", "Santé et sécurité des personnes", "health"),
    InspireTheme("lu", "Usage des sols", "planningCadastre"),
    InspireTheme(
        "mf", "Caractéristiques géographiques météorologiques", "climatologyMeteorologyAtmosphere"
    ),
    InspireTheme("mr", "Ressources minérales", "economy"),
    InspireTheme("nz", "Zones à risque naturel", "geoscientificInformation"),
    InspireTheme("of", "Caractéristiques géographiques océanographiques", "oceans"),
    InspireTheme("pd", "Répartition de la population — démographie", "society"),
    InspireTheme("pf", "Lieux de production et sites industriels", "structure"),
    InspireTheme("sr", "Régions maritimes", "oceans"),
    InspireTheme("so", "Sols", "geoscientificInformation"),
    InspireTheme("sd", "Répartition des espèces", "biota"),
    InspireTheme("su", "Unités statistiques", "boundaries"),
    InspireTheme("us", "Services d'utilité publique et services publics", "utilitiesCommunication"),
]

INSPIRE_THEME_IDS: frozenset[str] = frozenset(t.id for t in INSPIRE_THEMES)
_INSPIRE_BY_ID: dict[str, InspireTheme] = {t.id: t for t in INSPIRE_THEMES}


def resolve_inspire_theme(theme_id: str) -> InspireTheme | None:
    return _INSPIRE_BY_ID.get(theme_id)


def validate_inspire_theme_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in INSPIRE_THEME_IDS:
        raise ValueError(f"unknown INSPIRE theme id: {value!r}")
    return value


# ISO 639-2/B (gmd:LanguageCode des fiches ISO 19139 INSPIRE) — clés = LANGUAGE_IDS.
ISO639_2B: dict[str, str] = {"fr": "fre", "en": "eng", "de": "ger", "es": "spa", "it": "ita"}
