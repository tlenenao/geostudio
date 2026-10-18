# SPDX-License-Identifier: Apache-2.0
"""i18n du cœur (AUD-115) : langue d'un utilisateur, erreurs HTTP et e-mails traduits.

Module feuille (aucun import de domaine). Le texte source des erreurs reste l'anglais : il n'est
traduit que si le client le demande (`Accept-Language`) ET que le message est au catalogue ; le
membre `code` (slug du texte source) est le contrat stable, `detail` n'est qu'un libellé.
ponytail: dictionnaires en code, pas de gettext ; passer à .po si une 3e langue arrive."""

import os
import re

SUPPORTED_LOCALES = ("fr", "en")


def normalize_locale(raw: str | None) -> str | None:
    """`fr-FR`, `EN_us`... vers `fr`/`en` ; None si langue non prise en charge."""
    if not raw:
        return None
    lang = re.split(r"[-_]", raw.strip().lower(), maxsplit=1)[0]
    return lang if lang in SUPPORTED_LOCALES else None


def negotiate_locale(accept_language: str | None) -> str | None:
    """Première langue prise en charge de l'en-tête, par q décroissant ; None sinon."""
    if not accept_language:
        return None
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(accept_language.split(",")):
        tag, _, params = part.strip().partition(";")
        q = 1.0
        match = re.search(r"q=([0-9.]+)", params)
        if match:
            try:
                q = float(match.group(1))
            except ValueError:
                q = 0.0
        locale = normalize_locale(tag)
        if locale and q > 0:
            ranked.append((-q, index, locale))
    return min(ranked)[2] if ranked else None


def default_locale() -> str:
    return normalize_locale(os.environ.get("CORE_DEFAULT_LOCALE")) or "fr"


# --- erreurs ---------------------------------------------------------------------------------

_NOUNS_FR = {
    "item": "Élément",
    "config": "Configuration",
    "collection": "Collection",
    "pipeline": "Pipeline",
    "job": "Tâche",
    "feature": "Entité",
    "harvest source": "Source de moissonnage",
    "export job": "Export",
    "dataset": "Jeu de données",
    "role": "Rôle",
    "group": "Groupe",
    "attachment": "Pièce jointe",
    "arcgis layer": "Couche ArcGIS",
    "relation": "Relation",
    "alert rule": "Règle d'alerte",
    "site": "Site",
    "secret": "Secret",
    "run": "Exécution",
    "record": "Enregistrement",
    "raster": "Raster",
    "tile": "Tuile",
    "user": "Utilisateur",
    "terrain": "Relief",
    "tileset": "Tileset",
}

_DETAILS_FR = {
    "not found": "Introuvable",
    "write access required": "Droit d'écriture requis",
    "not allowed": "Action non autorisée",
    "not allowed to share this item": "Partage de cet élément non autorisé",
    "not allowed to modify this item": "Modification de cet élément non autorisée",
    "missing bearer token": "Jeton d'authentification manquant",
    "invalid or expired share link": "Lien de partage invalide ou expiré",
    "invalid upload key": "Clé de téléversement invalide",
    "upload key already used": "Clé de téléversement déjà utilisée",
    "invalid export token": "Jeton d'export invalide",
    "file too large": "Fichier trop volumineux",
    "collection is not editable": "Cette collection n'est pas modifiable",
    "feature conflicts with an existing row": "Entité en conflit avec une ligne existante",
    "too many entities matched, refine your filters": "Trop d'entités, affinez les filtres",
    "bbox must be minx,miny,maxx,maxy": "bbox doit valoir minx,miny,maxx,maxy",
    "harvest source already exists": "Cette source de moissonnage existe déjà",
    "user not found in this tenant": "Utilisateur introuvable dans ce tenant",
    "user already erased": "Utilisateur déjà anonymisé",
    "submission link expired or revoked": "Lien de soumission expiré ou révoqué",
    "submission already moderated": "Soumission déjà modérée",
    "arcgis service unavailable": "Service ArcGIS indisponible",
    "no thumbnail": "Aucune miniature",
    "validation failed": "Échec de la validation",
    "request failed": "Échec de la requête",
    "backing table not found": "Table de la collection introuvable",
    "unknown tile matrix set": "Matrice de tuiles inconnue",
}

_TITLES_FR = {
    400: "Requête invalide",
    401: "Non authentifié",
    403: "Accès refusé",
    404: "Introuvable",
    405: "Méthode non autorisée",
    409: "Conflit",
    410: "Disparu",
    412: "Précondition échouée",
    413: "Contenu trop volumineux",
    422: "Entité non traitable",
    429: "Trop de requêtes",
    500: "Erreur interne",
    502: "Mauvaise passerelle",
    503: "Service indisponible",
}

_NOT_FOUND = re.compile(r"^(.+) not found$")


def translate_detail(detail: str, locale: str | None) -> str:
    """Traduit un `detail` source anglais ; le texte est rendu tel quel s'il est inconnu."""
    if locale != "fr":
        return detail
    detail_key = detail.lower()  # Starlette émet « Not Found » ; le catalogue est en minuscules
    if detail_key in _DETAILS_FR:
        return _DETAILS_FR[detail_key]
    match = _NOT_FOUND.match(detail_key)
    if match and match.group(1) in _NOUNS_FR:
        return f"{_NOUNS_FR[match.group(1)]} introuvable"
    return detail


def translate_title(status: int, phrase: str, locale: str | None) -> str:
    return _TITLES_FR.get(status, phrase) if locale == "fr" else phrase


def error_code(detail: str) -> str:
    """Slug stable du texte source (ex. `tile_not_found`), identique quelle que soit la langue."""
    return re.sub(r"[^a-z0-9]+", "_", detail.lower()).strip("_")[:64] or "error"


# --- e-mails ---------------------------------------------------------------------------------

_MAILS = {
    "fr": {
        "alert.subject": "[GeoStudio] {rule} : {state}",
        "report.subject": "[GeoStudio] Rapport : {title}",
        "report.body": "Rapport « {title} » : {status}.",
        "report.link": " Lien : {url}",
        "report.error": " Erreur : {error}",
    },
    "en": {
        "alert.subject": "[GeoStudio] {rule}: {state}",
        "report.subject": "[GeoStudio] Report: {title}",
        "report.body": 'Report "{title}": {status}.',
        "report.link": " Link: {url}",
        "report.error": " Error: {error}",
    },
}


def tr(key: str, locale: str | None, **values: object) -> str:
    return _MAILS[locale or default_locale()][key].format(**values)
