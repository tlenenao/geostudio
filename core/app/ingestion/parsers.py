# SPDX-License-Identifier: Apache-2.0
"""Parseurs GeoJSON, CSV+lat/lon (SP-6a) et GeoPackage/Shapefile zippé
(SP-6b, via pyogrio — wheels manylinux, GDAL/GEOS/PROJ embarqués, aucun
paquet système requis). Chaque parseur produit un flux (géométrie shapely,
propriétés) ; toute ligne/feature/entité invalide lève IngestionParseError
immédiatement (fail-fast) — pas d'import partiel silencieux. Les géométries
invalides réparables sont réparées (make_valid, AUD-129)."""

import csv
import datetime
import io
import json
import math
import re
import tempfile
import warnings
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import defusedxml.ElementTree
import geopandas as gpd
import numpy as np
import pyarrow.parquet
import pyogrio
import pyproj
import shapely
from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pyogrio.errors import DataLayerError, DataSourceError
from pyproj.exceptions import ProjError
from pyproj.transformer import TransformerGroup
from shapely.errors import ShapelyError
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

from app.cell_safety import unsanitize_cell


class IngestionParseError(Exception):
    """Message affiché tel quel comme ingestion_jobs.error_message."""


_DIM = {
    "Point": 0,
    "MultiPoint": 0,
    "LineString": 1,
    "MultiLineString": 1,
    "Polygon": 2,
    "MultiPolygon": 2,
}


def _repair_geometry(geom: BaseGeometry, where: str) -> BaseGeometry:
    """AUD-129 : une géométrie invalide (nœud papillon, auto-intersection) est réparée
    par make_valid au lieu de faire échouer tout le fichier. make_valid peut renvoyer une
    GeometryCollection mêlant dimensions : on ne garde que les parties de la dimension
    d'origine. Résultat vide/dégénéré -> rejet explicite (pas de perte silencieuse)."""
    if geom.is_valid:
        return geom
    dim = _DIM.get(geom.geom_type, 0)
    fixed = shapely.make_valid(geom)
    if fixed.geom_type == "GeometryCollection":
        parts = [p for p in shapely.get_parts(fixed) if _DIM.get(p.geom_type, 0) == dim]
        fixed = unary_union(parts) if parts else fixed
    if fixed.is_empty or _DIM.get(fixed.geom_type, 0) != dim or not fixed.is_valid:
        raise IngestionParseError(f"{where} : géométrie invalide")
    return fixed


_LAT_NAMES = {"lat", "latitude", "y"}
_LON_NAMES = {"lon", "lng", "longitude", "x"}
_WGS84 = pyproj.CRS.from_epsg(4326)
_OGR_ERRORS = (DataSourceError, DataLayerError)
# Message GDAL brut volontairement écarté (chemin temporaire serveur, jargon).
_UNREADABLE = (
    "fichier illisible ou format non reconnu — vérifiez que le fichier n'est pas vide ni corrompu"
)
_XLSX_ERRORS = (zipfile.BadZipFile, InvalidFileException)
# pyarrow.lib.ArrowIOError hérite d'OSError, pas d'ArrowException (vérifié par
# exécution réelle — les deux hiérarchies divergent) : les deux sont
# nécessaires pour couvrir aussi bien un fichier tronqué/illisible qu'un
# fichier qui n'est structurellement pas un Parquet.
_PARQUET_ERRORS = (pyarrow.lib.ArrowException, OSError)


def detect_lat_lon_fields(fieldnames: list[str]) -> tuple[str, str] | None:
    by_lower = {name.lower(): name for name in fieldnames}
    lat = next((by_lower[n] for n in _LAT_NAMES if n in by_lower), None)
    lon = next((by_lower[n] for n in _LON_NAMES if n in by_lower), None)
    if lat is None or lon is None:
        return None
    return lat, lon


@dataclass(frozen=True)
class GeometryMode:
    """Résolu une fois par import (jamais recalculé ligne à ligne) — kind
    fixe la stratégie, les champs optionnels portent les noms de colonnes
    déjà résolus (auto-détection ou choix explicite de l'utilisateur, faits
    en amont par l'appelant, jamais par extract_geometry elle-même)."""

    kind: Literal["latlon", "wkt", "none"]
    lat_field: str | None = None
    lon_field: str | None = None
    wkt_field: str | None = None


def _resolve_latlon_mode_from_fields(mode: GeometryMode, fieldnames: list[str]) -> GeometryMode:
    """Résout l'auto-détection lat/lon demandée par l'appelant (mode.kind ==
    "latlon" avec lat_field/lon_field absents, cas envoyé par le shell dès
    qu'il détecte lui-même des colonnes lat/lon-like et saute l'étape
    manuelle selecting-geometry) en un GeometryMode concret, via
    detect_lat_lon_fields sur `fieldnames`. Ne modifie rien pour un mode
    déjà résolu (lat_field/lon_field fournis) ni pour wkt/none — c'est le
    seul point de résolution, jamais fait par extract_geometry elle-même
    (cf. sa docstring). Partagé par parse_csv_latlon/parse_xlsx_sheet
    (revue finale GAP-29, C1) et par parse_jsonlines/parse_xml_generic/
    parse_parquet_tabular, qui n'avaient auparavant aucune étape de
    résolution — passaient le mode brut (lat_field=None) directement à
    extract_geometry, qui échouait alors sur toute ligne avec
    `IngestionParseError("lat/lon invalide ('None', 'None')")`."""
    if mode.kind == "latlon" and (mode.lat_field is None or mode.lon_field is None):
        detected = detect_lat_lon_fields(fieldnames)
        if detected is None:
            raise IngestionParseError(
                "colonnes lat/lon introuvables automatiquement — précisez-les"
            )
        lat_field, lon_field = detected
        return GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)
    return mode


def _to_coord(raw) -> float:
    """Accepte la virgule décimale française ('48,85') ; refuse NaN/inf
    (float('nan') passerait sinon les bornes ci-dessous, comparaisons fausses)."""
    value = float(raw.replace(",", ".")) if isinstance(raw, str) else float(raw)
    if not math.isfinite(value):
        raise ValueError(raw)
    return value


def sniff_delimiter(text: str) -> str:
    """Séparateur CSV (',' ';' tab '|') deviné sur la ligne d'en-tête ;
    ',' par défaut. Même heuristique côté shell (ImportFileButton)."""
    # entre guillemets : un en-tête "Nom, Prénom";Age ne doit pas voter ','
    first = re.sub(r'"[^"]*"', "", text.split("\n", 1)[0])
    best = max(",;\t|", key=first.count)
    return best if first.count(best) else ","


def extract_geometry(row: dict, mode: GeometryMode) -> tuple[BaseGeometry | None, dict]:
    """Retourne (géométrie ou None, propriétés restantes — colonnes de
    géométrie retirées). Lève IngestionParseError sans contexte de ligne :
    l'appelant (qui seul connaît l'index de ligne) re-lève avec son propre
    contexte, cf. parse_csv_latlon/parse_xlsx_sheet."""
    if mode.kind == "none":
        return None, dict(row)
    if mode.kind == "latlon":
        raw_lat, raw_lon = row.get(mode.lat_field), row.get(mode.lon_field)
        try:
            lat, lon = _to_coord(raw_lat), _to_coord(raw_lon)
        except (TypeError, ValueError):
            raise IngestionParseError(f"lat/lon invalide ('{raw_lat}', '{raw_lon}')") from None
        if not -90.0 <= lat <= 90.0:
            raise IngestionParseError(f"latitude hors de [-90, 90] : '{raw_lat}'")
        if not -180.0 <= lon <= 180.0:
            raise IngestionParseError(f"longitude hors de [-180, 180] : '{raw_lon}'")
        rest = {k: v for k, v in row.items() if k not in (mode.lat_field, mode.lon_field)}
        return Point(lon, lat), rest
    # mode.kind == "wkt"
    raw_wkt = row.get(mode.wkt_field)
    if raw_wkt is None or (isinstance(raw_wkt, str) and raw_wkt.strip() == ""):
        raise IngestionParseError(f"WKT invalide ('{raw_wkt}') : valeur manquante")
    try:
        geom = shapely.from_wkt(raw_wkt)
    except (ShapelyError, TypeError) as exc:
        raise IngestionParseError(f"WKT invalide ('{raw_wkt}') : {exc}") from exc
    rest = {k: v for k, v in row.items() if k != mode.wkt_field}
    return geom, rest


_JSON_WS = json.decoder.WHITESPACE  # type: ignore[attr-defined]


def _iter_geojson_features(text: str) -> Iterator[object]:
    """AUD-014 : parcourt la FeatureCollection sans construire l'arbre JSON entier. Les
    valeurs de premier niveau autres que `features` sont décodées (petites : crs, name…),
    puis chaque élément de `features` un à un (raw_decode). JSON invalide ->
    json.JSONDecodeError ; objet qui n'est pas une FeatureCollection ->
    IngestionParseError, au plus tard en fin de parcours (l'import analyse tout le
    fichier avant d'écrire quoi que ce soit, cf. importer._open_rows)."""
    dec = json.JSONDecoder()
    not_fc = IngestionParseError("le GeoJSON doit être une FeatureCollection")

    def ws(p: int) -> int:
        return _JSON_WS.match(text, p).end()

    def expect(p: int, ch: str) -> int:
        p = ws(p)
        if text[p : p + 1] != ch:
            raise json.JSONDecodeError(f"'{ch}' attendu", text, p)
        return p + 1

    pos = ws(0)
    if text[pos : pos + 1] != "{":
        dec.raw_decode(text, pos)  # JSON invalide -> JSONDecodeError
        raise not_fc
    pos = ws(pos + 1)
    kind = None
    if text[pos : pos + 1] == "}":
        raise not_fc
    while True:
        key, pos = dec.raw_decode(text, ws(pos))
        if not isinstance(key, str):
            raise json.JSONDecodeError("clé attendue", text, pos)
        pos = ws(expect(pos, ":"))
        if key == "features" and text[pos : pos + 1] == "[":
            if kind not in (None, "FeatureCollection"):
                raise not_fc
            pos = ws(pos + 1)
            if text[pos : pos + 1] == "]":
                pos += 1
            else:
                while True:
                    feature, pos = dec.raw_decode(text, pos)
                    yield feature
                    pos = ws(pos)
                    if text[pos : pos + 1] == ",":
                        pos = ws(pos + 1)
                        continue
                    pos = expect(pos, "]")
                    break
        else:
            value, pos = dec.raw_decode(text, pos)
            if key == "type":
                kind = value
            elif key == "features":  # présent mais pas une liste
                raise not_fc
        pos = ws(pos)
        if text[pos : pos + 1] == ",":
            pos += 1
            continue
        pos = expect(pos, "}")
        break
    if ws(pos) != len(text):
        raise json.JSONDecodeError("données en trop", text, ws(pos))
    if kind != "FeatureCollection":
        raise not_fc


def _geojson_feature(i: int, feature: object) -> tuple[BaseGeometry, dict]:
    if not isinstance(feature, dict):
        raise IngestionParseError(f"feature {i} : entrée invalide")
    geometry = feature.get("geometry")
    if geometry is None:
        raise IngestionParseError(f"feature {i} : géométrie manquante")
    try:
        geom = shape(geometry)
    except (ValueError, AttributeError, KeyError, TypeError, ShapelyError) as exc:
        raise IngestionParseError(f"feature {i} : géométrie invalide ({exc})") from exc
    geom = _repair_geometry(geom, f"feature {i}")
    properties = feature.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise IngestionParseError(f"feature {i} : properties invalide")
    return geom, dict(properties or {})


def parse_geojson(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    try:
        for i, feature in enumerate(_iter_geojson_features(text)):
            yield _geojson_feature(i, feature)
    except json.JSONDecodeError as exc:
        raise IngestionParseError(f"JSON invalide : {exc}") from exc


def parse_csv_latlon(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter=sniff_delimiter(text))
    try:
        fieldnames = [unsanitize_cell(f) for f in reader.fieldnames or []]
        reader.fieldnames = fieldnames
    except csv.Error as exc:
        raise IngestionParseError("en-tête CSV invalide ou mal formé") from exc
    effective_mode = _resolve_latlon_mode_from_fields(mode, fieldnames)
    if effective_mode.kind == "latlon" and (
        effective_mode.lat_field not in fieldnames or effective_mode.lon_field not in fieldnames
    ):
        raise IngestionParseError(
            f"colonnes '{effective_mode.lat_field}'/'{effective_mode.lon_field}' absentes du CSV"
        )
    i = 0
    row_iter = iter(reader)
    while True:
        try:
            row = next(row_iter)
        except StopIteration:
            break
        except csv.Error as exc:
            raise IngestionParseError(
                f"ligne {i + 1} : champ CSV trop volumineux ou mal formé"
            ) from exc
        i += 1
        try:
            yield extract_geometry({k: unsanitize_cell(v) for k, v in row.items()}, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def _xlsx_cell_value(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return unsanitize_cell(value)


def _xlsx_header(name: object) -> str:
    return str(unsanitize_cell(name)) if name is not None else ""


def parse_xlsx_sheet(
    content: bytes,
    sheet_name: str | None,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    if sheet_name is not None:
        try:
            ws = wb[sheet_name]
        except KeyError:
            raise IngestionParseError(f"feuille '{sheet_name}' introuvable") from None
    else:
        ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise IngestionParseError("classeur XLSX vide") from None
    fieldnames = [_xlsx_header(name) for name in header_row]
    effective_mode = _resolve_latlon_mode_from_fields(mode, fieldnames)
    if effective_mode.kind == "latlon" and (
        effective_mode.lat_field not in fieldnames or effective_mode.lon_field not in fieldnames
    ):
        raise IngestionParseError(
            f"colonnes '{effective_mode.lat_field}'/'{effective_mode.lon_field}' absentes du XLSX"
        )
    for i, row in enumerate(rows_iter, start=1):
        row_dict = {
            name: _xlsx_cell_value(row[j] if j < len(row) else None)
            for j, name in enumerate(fieldnames)
        }
        try:
            yield extract_geometry(row_dict, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def read_xlsx_header_fields(content: bytes, sheet_name: str | None = None) -> list[str]:
    """Lit uniquement la première ligne (en-têtes) d'une feuille XLSX, sans
    charger tout le classeur — utilisé par POST /uploads/inspect. `sheet_name`
    précise la feuille (2e appel d'inspection après choix en selecting-layer,
    cf. Task 5) ; None lit la feuille active (comportement mono-feuille
    inchangé)."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    if sheet_name is not None:
        try:
            ws = wb[sheet_name]
        except KeyError:
            raise IngestionParseError(f"feuille '{sheet_name}' introuvable") from None
    else:
        ws = wb.active
    try:
        header_row = next(ws.iter_rows(max_row=1, values_only=True))
    except StopIteration:
        raise IngestionParseError("classeur XLSX vide") from None
    return [_xlsx_header(name) for name in header_row]


@dataclass
class LayerInfo:
    name: str
    feature_count: int
    geometry_type: str


def list_xlsx_sheets(content: bytes) -> list[LayerInfo]:
    """Une entrée par feuille du classeur — même dataclass LayerInfo que
    GPKG/KML, pour réutiliser telle quelle la phase selecting-layer côté
    shell (GAP-29). geometry_type="Tabular" : une feuille Excel n'a pas de
    type de géométrie OGC, cette valeur n'est jamais interprétée ailleurs
    que par le libellé de l'option dans le sélecteur (qui n'affiche pas
    geometryType)."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        # ws.max_row peut être imprécis en mode read_only avant itération
        # complète (comportement documenté d'openpyxl) — compter par
        # itération plutôt que faire confiance à max_row, aucun volume
        # important n'est visé par ce chantier (GAP-29, anticipation
        # générique).
        row_count = sum(1 for _ in ws.iter_rows(values_only=True))
        feature_count = max(row_count - 1, 0)  # moins la ligne d'en-tête
        sheets.append(
            LayerInfo(name=str(name), feature_count=feature_count, geometry_type="Tabular")
        )
    return sheets


# Extensions autorisées comme suffixe de fichier temporaire. Liste fermée
# plutôt qu'une validation par motif : les cinq formats qui ont besoin d'un
# fichier sur disque (GDAL/pyogrio ne lisent pas depuis la mémoire) sont
# connus, et une liste se relit sans avoir à raisonner sur une regex.
_ALLOWED_TEMP_SUFFIXES = frozenset(
    {".gpkg", ".zip", ".kml", ".kmz", ".parquet", ".gml", ".dxf", ".dgn", ".fgb"}
)
_SQLITE_MAGIC = b"SQLite format 3\x00"
_FGB_MAGIC = b"fgb"  # AUD-143 : FlatGeobuf = « fgb » + version + « fgb » + 0
_MAX_ZIP_UNCOMPRESSED = 2 * 1024**3  # garde anti zip-bomb (ARC-23)
_GDB_DIR_RE = re.compile(r"^[\w. -]+\.gdb$")


def _reject_vrt_and_check_signature(content: bytes, suffix: str) -> None:
    """REV-333 : pyogrio choisit le driver sur le contenu, pas sur l'extension —
    un VRT OGR déguisé référence des fichiers du serveur. Refusé par signature
    (en-tête) et, pour un zip, par nom de membre. GPKG : en-tête SQLite exigé."""
    if b"ogrvrtdatasource" in content[:4096].lower():
        raise IngestionParseError("fichier VRT refusé")
    if suffix == ".gpkg" and not content.startswith(_SQLITE_MAGIC):
        raise IngestionParseError(_UNREADABLE)
    if suffix == ".fgb" and not content.startswith(_FGB_MAGIC):
        raise IngestionParseError(_UNREADABLE)
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                infos = z.infolist()
        except zipfile.BadZipFile as exc:
            raise IngestionParseError(_UNREADABLE) from exc
        if any(i.filename.lower().endswith(".vrt") for i in infos):
            raise IngestionParseError("fichier VRT refusé")
        if sum(i.file_size for i in infos) > _MAX_ZIP_UNCOMPRESSED:
            raise IngestionParseError("archive trop volumineuse une fois décompressée")


def _zip_dataset_path(tmp_path: str, content: bytes, *, require_gdb: bool = False) -> str:
    """Chemin GDAL d'un zip : racine, ou le dossier `X.gdb` de premier niveau
    (FileGDB, que GDAL n'ouvre pas depuis la racine du zip)."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        tops = {n.split("/", 1)[0] for n in z.namelist() if "/" in n}
    gdbs = sorted(t for t in tops if _GDB_DIR_RE.match(t))
    if gdbs:  # ponytail: un seul .gdb par archive (le premier), pas de .gdb imbriqué
        return f"/vsizip/{tmp_path}/{gdbs[0]}"
    if require_gdb:
        raise IngestionParseError("aucun dossier .gdb à la racine de l'archive")
    return f"/vsizip/{tmp_path}"


@contextmanager
def _temp_file(content: bytes, suffix: str) -> Iterator[str]:
    """Écrit `content` dans un fichier temporaire portant `suffix` — GDAL
    sélectionne son driver depuis l'extension, d'où le besoin d'un vrai
    fichier nommé.

    `suffix` est validé contre une liste fermée : c'est le point de passage
    UNIQUE du domaine où un suffixe devient un chemin réel, et
    `tempfile.NamedTemporaryFile` ne filtre rien du tout — un suffixe
    contenant « / » écrit hors du répertoire temporaire. Aucun appelant
    actuel ne peut y faire entrer une telle valeur (tous passent un
    littéral), ce garde est là pour que le prochain ne le puisse pas
    silencieusement."""
    if suffix not in _ALLOWED_TEMP_SUFFIXES:
        raise ValueError(f"suffixe de fichier temporaire non autorisé : {suffix!r}")
    _reject_vrt_and_check_signature(content, suffix)
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        yield tmp.name


_NTF_GEODETIC = {4275, 4807}  # NTF, NTF (Paris)


def _is_ntf(crs: pyproj.CRS) -> bool:
    geodetic = crs.geodetic_crs
    return geodetic is not None and geodetic.to_epsg() in _NTF_GEODETIC


def _ntf_transform(src: pyproj.CRS):
    """AUD-127 : NTF -> RGF93 exige la grille IGN fr_ign_gr3df97a.tif. Sans elle, PROJ
    retombe en silence sur un Helmert (~2 m vers 4326) ou un « ballpark » (vers 4171) :
    on exige la grille vers RGF93 v1 (EPSG:4171), puis RGF93 -> WGS84."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyproj avertit quand une grille manque
        group = TransformerGroup(src, 4171, always_xy=True)
    if not group.best_available or not group.transformers:
        raise IngestionParseError(
            "Données en NTF : grille IGN fr_ign_gr3df97a.tif absente de l'installation PROJ, "
            "transformation métrique impossible (python -m pyproj sync --file fr_ign_gr3df97a.tif)"
        )
    to_rgf93 = group.transformers[0]
    to_wgs84 = pyproj.Transformer.from_crs(4171, _WGS84, always_xy=True)

    def transform(x, y, z=None):
        lon, lat = to_rgf93.transform(x, y)
        return to_wgs84.transform(lon, lat)

    return transform


def _crs_transform(crs: str | None):
    try:
        src = pyproj.CRS.from_user_input(crs)
    except ProjError as exc:
        raise IngestionParseError(f"CRS manquant ou non reconnu : {crs!r}") from exc
    if src == _WGS84:
        return None
    if _is_ntf(src):
        return _ntf_transform(src)
    try:
        transformer = pyproj.Transformer.from_crs(src, _WGS84, always_xy=True)
    except ProjError as exc:
        raise IngestionParseError(f"CRS non transformable vers WGS84 : {crs!r}") from exc
    return transformer.transform


def _native_value(value):
    if isinstance(value, np.ndarray | list | tuple):
        # champs multivalués (GML complexe : StringList/IntegerList) -> texte JSON
        return json.dumps([_native_value(v) for v in value], ensure_ascii=False)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _read_features(
    path: str, layer_name: str | None, *, cad: bool = False
) -> Iterator[tuple[BaseGeometry, dict]]:
    """`cad` (DXF/DGN, sans CRS dans le fichier) : coordonnées lues en WGS84 si
    elles en respectent l'étendue, sinon refus (CRS requis) ; entités sans
    géométrie (textes, blocs) ignorées."""
    try:
        raw_layers = pyogrio.list_layers(path)
    except _OGR_ERRORS as exc:
        raise IngestionParseError(_UNREADABLE) from exc
    available = [str(name) for name, _geom_type in raw_layers]
    if layer_name is None:
        if len(available) != 1:
            raise IngestionParseError(
                f"plusieurs couches disponibles ({', '.join(available)}) — précisez layerName"
            )
        layer_name = available[0]
    elif layer_name not in available:
        raise IngestionParseError(
            f"couche '{layer_name}' introuvable — couches disponibles : {', '.join(available)}"
        )
    try:
        # pyogrio/numpy émet un DeprecationWarning interne ("generic unit for
        # NumPy timedelta") sur des champs datetime NaT (rencontré en
        # pratique sur les champs begin/end du schéma KML par défaut) —
        # vérifié par exécution réelle (SP-56), quirk de la bibliothèque
        # tierce, sans rapport avec la validité des données lues.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*generic.*unit for NumPy timedelta.*",
                category=DeprecationWarning,
            )
            meta, _index, geometry, field_data = pyogrio.raw.read(
                path, layer=layer_name, force_2d=True
            )
    except _OGR_ERRORS as exc:
        raise IngestionParseError(f"couche '{layer_name}' illisible") from exc

    crs = meta["crs"] or ("EPSG:4326" if cad else None)
    transform = _crs_transform(crs)
    fields = list(meta["fields"])

    for i, wkb in enumerate(geometry):
        if wkb is None and cad:
            continue
        if wkb is None:
            raise IngestionParseError(f"entité {i} : géométrie manquante")
        try:
            geom = shapely.from_wkb(wkb)
        except ShapelyError as exc:
            raise IngestionParseError(f"entité {i} : géométrie invalide ({exc})") from exc
        if cad and not meta["crs"]:
            minx, miny, maxx, maxy = geom.bounds
            if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
                raise IngestionParseError(
                    f"entité {i} : CRS absent et coordonnées hors étendue WGS84 "
                    "(CAO en repère local non supporté)"
                )
        if transform is not None:
            geom = shapely_transform(transform, geom)
        geom = _repair_geometry(geom, f"entité {i}")
        properties = {field: _native_value(field_data[j][i]) for j, field in enumerate(fields)}
        yield geom, properties


def parse_gpkg(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".gpkg") as path:
        yield from _read_features(path, layer_name)


def parse_flatgeobuf(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    """AUD-143 : FlatGeobuf (une seule couche, lue par le driver GDAL/pyogrio)."""
    with _temp_file(content, ".fgb") as path:
        yield from _read_features(path, layer_name)


def parse_shapefile_zip(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".zip") as path:
        yield from _read_features(_zip_dataset_path(path, content), layer_name)


def parse_filegdb_zip(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    """File Geodatabase (OpenFileGDB, lecture seule) : zip d'un dossier `X.gdb`."""
    with _temp_file(content, ".zip") as path:
        yield from _read_features(_zip_dataset_path(path, content, require_gdb=True), layer_name)


def parse_dxf(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".dxf") as path:
        for geom, props in _read_features(path, layer_name, cad=True):
            yield geom, _rename_reserved_property_keys(props, "dxf")


def parse_dgn(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]:
    """DGN v7 uniquement (le V8 n'a pas de driver libre)."""
    with _temp_file(content, ".dgn") as path:
        for geom, props in _read_features(path, layer_name, cad=True):
            yield geom, _rename_reserved_property_keys(props, "dgn")


# Le driver KML de GDAL impose un schéma de champs fixe sur TOUT Placemark,
# y compris un champ nommé "id" (l'attribut XML id="..." du Placemark, vide
# sinon) — vérifié par exécution réelle : même un KML minimal à un seul
# Placemark sans schéma personnalisé le produit. Ce nom entre en collision
# avec la colonne "id" (clé primaire serial) que run_import pose sur toute
# table importée ; sans renommage, TOUT import KML échouerait à la création
# de table ("column id specified more than once"), pas seulement un cas
# limite de nommage utilisateur. Renommé plutôt que supprimé pour ne pas
# perdre l'attribut id du Placemark quand il est renseigné.
_RESERVED_PROPERTY_NAMES = {"id", "tenant_id", "geom"}


def _rename_reserved_property_keys(props: dict, prefix: str) -> dict:
    """Toute source de données peut légitimement porter une colonne nommée
    id/tenant_id/geom, en collision avec les colonnes fixes que run_import
    pose sur chaque table (id serial PRIMARY KEY, tenant_id, geom) — pour
    KML, cette collision est garantie à 100% (le driver GDAL impose un
    champ id sur tout Placemark, SP-56). Fonction générique, préfixe fourni
    par l'appelant : parse_kml (préfixe "kml", inchangé), parse_gml
    ("gml"), parse_jsonlines ("jsonl"), parse_xml_generic ("xml")."""
    return {
        (f"{prefix}_{key}" if key in _RESERVED_PROPERTY_NAMES else key): value
        for key, value in props.items()
    }


def parse_kml(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    # Un .kmz est un zip contenant un doc.kml, mais GDAL/pyogrio le détecte
    # et le lit DIRECTEMENT sur l'extension .kmz elle-même — PAS de préfixe
    # /vsizip/ ici, contrairement à parse_shapefile_zip (.zip) : ce préfixe
    # casserait la lecture ("n'est pas un fichier kmz valide"), vérifié par
    # exécution réelle avant d'écrire ce code (spec SP-56 §Contexte). Le
    # suffixe temporaire distingue .kml/.kmz uniquement pour que GDAL
    # sélectionne le bon driver depuis l'extension.
    suffix = ".kmz" if _looks_like_zip(content) else ".kml"
    with _temp_file(content, suffix) as path:
        for geom, props in _read_features(path, layer_name):
            yield geom, _rename_reserved_property_keys(props, "kml")


def _looks_like_zip(content: bytes) -> bool:
    return content[:2] == b"PK"


# Vérifié empiriquement sur archsites.gml (EPSG:26713, driver GML de GDAL) :
# contrairement à KML, ce driver n'expose PAS de champ "id" — l'attribut
# gml:id du Placemark est déjà nommé "gml_id" en sortie de
# pyogrio.raw.read()/read_info() (champs observés : gml_id, lowerCorner,
# upperCorner, cat, str1 — pas de préfixe de namespace "og:"). Aucune
# collision avec la colonne "id" (PK serial) de run_import : le renommage
# _rename_reserved_property_keys ci-dessous est appliqué par défense en
# profondeur (une autre source GML pourrait légitimement porter un champ
# "id"), sans effet réel sur ce fixture.
def parse_gml(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    """GML/INSPIRE traité exactement comme KML (GAP-29, §2.6 de la spec) :
    réutilisation brute de _read_features, aucune logique spécifique au
    schéma INSPIRE. Pas de variante zip (contrairement à KML/KMZ) — un seul
    suffixe possible."""
    with _temp_file(content, ".gml") as path:
        for geom, props in _read_features(path, layer_name):
            yield geom, _rename_reserved_property_keys(props, "gml")


def parse_jsonlines(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    """Une ligne = un objet JSON. Valeurs imbriquées (dict/list) sérialisées
    en JSON compact plutôt que déposées telles quelles (sinon un repr()
    Python implicite via str() en aval, pas du JSON valide) ; collision
    réservée (id/tenant_id/geom) renommée avec le préfixe "jsonl", même
    patron que parse_kml/parse_gml (GAP-29). Auto-détection lat/lon (mode
    "latlon" sans lat_field/lon_field, cas envoyé par le shell) résolue
    contre les clés (déjà renommées) du premier objet JSON valide rencontré
    — revue finale GAP-29, C1 : avant ce correctif, le mode brut était passé
    tel quel à extract_geometry, qui échouait systématiquement
    ("lat/lon invalide ('None', 'None')") sur ce chemin, le plus courant en
    pratique."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    effective_mode: GeometryMode | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionParseError(f"ligne {i} : JSON invalide ({exc})") from exc
        if not isinstance(row, dict):
            raise IngestionParseError(f"ligne {i} : chaque ligne doit être un objet JSON")
        row = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in row.items()
        }
        row = _rename_reserved_property_keys(row, "jsonl")
        if effective_mode is None:
            effective_mode = _resolve_latlon_mode_from_fields(mode, list(row.keys()))
        try:
            yield extract_geometry(row, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def read_jsonlines_header_fields(content: bytes, sample_lines: int = 20) -> list[str]:
    """Union des clés des N premières lignes non vides — jamais tout le
    fichier (utilisé par POST /uploads/inspect uniquement ; le job d'import
    réel, parse_jsonlines, traite lui la totalité des lignes).

    Applique `_rename_reserved_property_keys` à chaque ligne échantillonnée,
    comme parse_jsonlines le fait déjà — sans quoi le sélecteur de champ de
    l'UI pouvait proposer une clé brute (« geom », « id »…) que le parseur
    réel a déjà renommée en jsonl_geom/jsonl_id au moment où
    extract_geometry s'exécute, faisant échouer le choix de l'utilisateur
    avec un « valeur manquante » incompréhensible (revue finale GAP-29,
    I1). Ne délègue PAS à parse_jsonlines (qui traite tout le fichier) :
    l'échantillonnage à `sample_lines` reste un choix de perf documenté et
    distinct, propre à cette fonction d'inspection."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    fields: dict[str, None] = {}
    seen = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionParseError(f"JSON invalide dans l'échantillon : {exc}") from exc
        if isinstance(row, dict):
            row = _rename_reserved_property_keys(row, "jsonl")
            for key in row:
                fields.setdefault(key, None)
        seen += 1
        if seen >= sample_lines:
            break
    return list(fields.keys())


def parse_geoparquet(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    # PAS pyogrio : pyogrio.list_drivers()["Parquet"] vaut None dans ce build
    # (aucun driver OGR Parquet) — vérifié par exécution réelle (spec SP-56
    # §3). geopandas.read_parquet() lit correctement un GeoParquet 1.0,
    # y compris celui produit par app.cdc.parquet_writer.write_geoparquet
    # (SP-11). Un seul fichier, pas de concept de couches multiples ici :
    # ce format ne passe jamais par list_layers()/l'étape d'inspection.
    with _temp_file(content, ".parquet") as path:
        gdf = gpd.read_parquet(path)
        transform = None
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            if _is_ntf(gdf.crs):  # AUD-127 : même exigence de grille que _crs_transform
                transform = _ntf_transform(gdf.crs)
            else:
                gdf = gdf.to_crs(epsg=4326)
        geom_col = gdf.geometry.name
        for i, row in gdf.iterrows():
            geom = row[geom_col]
            # Une géométrie manquante revient de geopandas.read_parquet en
            # NaN (float), pas None — vérifié par exécution réelle (écart
            # avec le pseudo-code de la spec SP-56 §3.1, corrigé ici).
            if geom is None or (isinstance(geom, float) and math.isnan(geom)):
                raise IngestionParseError(f"entité {i} : géométrie manquante")
            if transform is not None:
                geom = shapely_transform(transform, geom)
            props = {k: _native_value(v) for k, v in row.items() if k != geom_col}
            yield geom, props


def _is_geoparquet(path: str) -> bool:
    """Sniffe la clé "geo" des métadonnées Parquet (spec GeoParquet 1.0) —
    lit le footer via read_schema, jamais les données."""
    try:
        schema = pyarrow.parquet.read_schema(path)
    except _PARQUET_ERRORS as exc:
        raise IngestionParseError(f"fichier Parquet illisible : {exc}") from exc
    return b"geo" in (schema.metadata or {})


def _is_geoparquet_from_bytes(content: bytes) -> bool:
    """Variante bytes de _is_geoparquet, pour tout appelant qui n'a pas déjà
    de fichier temporaire ouvert sur ce contenu — routes.py (POST
    /uploads/inspect) et, depuis la revue finale GAP-29 (M5), run_import
    lui-même : ce dernier ouvrait auparavant son propre fichier temporaire
    rien que pour le sniff puis appelait _is_geoparquet(path), alors que le
    parseur choisi ensuite (parse_geoparquet/parse_parquet_tabular) en
    rouvre de toute façon un second sur le même `content` — appeler
    directement cette fonction est identique en coût et plus simple (évite
    d'importer _is_geoparquet/_temp_file, privés à ce module, dans
    importer.py)."""
    with _temp_file(content, ".parquet") as path:
        return _is_geoparquet(path)


def parse_parquet_tabular(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    with _temp_file(content, ".parquet") as path:
        try:
            pf = pyarrow.parquet.ParquetFile(path)
            # Auto-détection lat/lon résolue une fois, contre le schéma (mêmes noms que
            # read_parquet_header_fields), AVANT la boucle par ligne (revue finale GAP-29,
            # C1) ; lecture par lots (AUD-014) au lieu de read_table().to_pylist().
            effective_mode = _resolve_latlon_mode_from_fields(mode, list(pf.schema_arrow.names))
            for batch in pf.iter_batches(batch_size=10_000):
                for row in batch.to_pylist():
                    row = {
                        k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in row.items()
                    }
                    yield extract_geometry(row, effective_mode)
        except _PARQUET_ERRORS as exc:
            raise IngestionParseError(f"fichier Parquet illisible : {exc}") from exc


def read_parquet_header_fields(content: bytes) -> list[str]:
    with _temp_file(content, ".parquet") as path:
        try:
            schema = pyarrow.parquet.read_schema(path)
        except _PARQUET_ERRORS as exc:
            raise IngestionParseError(f"fichier Parquet illisible : {exc}") from exc
        return list(schema.names)


def _local_name(tag: str) -> str:
    """Retire un préfixe d'espace de noms ('{uri}local' -> 'local') —
    ElementTree qualifie les tags par l'URI complète dès qu'un xmlns est
    déclaré."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_repeated_element(root):
    """BFS (ordre du document) — le premier parent dont un même nom
    d'enfant apparaît >= 2 fois gagne. Retourne (parent, tag_repete) ou
    (None, None) si aucun ne qualifie."""
    from collections import Counter, deque

    queue = deque([root])
    while queue:
        parent = queue.popleft()
        counts = Counter(_local_name(child.tag) for child in parent)
        repeated = next((tag for tag, n in counts.items() if n >= 2), None)
        if repeated is not None:
            return parent, repeated
        queue.extend(parent)
    return None, None


def parse_xml_generic(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    """Aucun schéma n'est supposé : le premier élément dont un même nom
    d'enfant se répète (>= 2 fois) est considéré comme « un enregistrement »
    (_find_repeated_element, BFS). Seuls les enfants feuilles (sans propre
    enfant) deviennent des propriétés scalaires — un enfant structuré
    (imbriqué) est ignoré, pas aplati. `defusedxml.ElementTree` est
    obligatoire ici (jamais `xml.etree.ElementTree` bare) : c'est le seul
    parseur de ce module qui lit du XML non fiable sans GDAL en dessous,
    risque XXE réel sur un contenu uploadé par un utilisateur.

    `defusedxml.ElementTree.ParseError` est en réalité le même objet que
    `xml.etree.ElementTree.ParseError` (ré-exporté tel quel, vérifié par
    exécution réelle) — mais une entité externe (XXE) ou un DOCTYPE interdit
    lève `defusedxml.common.DefusedXmlException` (hérite de `ValueError`,
    PAS de `ParseError`), sans quoi une charge XXE traverserait cette
    fonction sans jamais devenir un IngestionParseError propre."""
    try:
        root = defusedxml.ElementTree.fromstring(content)
    except (defusedxml.ElementTree.ParseError, DefusedXmlException) as exc:
        raise IngestionParseError(f"XML invalide : {exc}") from exc
    parent, tag = _find_repeated_element(root)
    if parent is None:
        raise IngestionParseError("aucun élément répété détecté — format non reconnu")
    matching = [e for e in parent if _local_name(e.tag) == tag]
    effective_mode: GeometryMode | None = None
    for i, elem in enumerate(matching, start=1):
        row: dict = dict(elem.attrib)
        for child in elem:
            if len(child) == 0:  # feuille texte, pas un sous-élément structuré
                row[_local_name(child.tag)] = (child.text or "").strip()
        row = _rename_reserved_property_keys(row, "xml")
        # Auto-détection lat/lon résolue contre les clés (déjà renommées) du
        # premier élément répété — même correctif que parse_jsonlines
        # (revue finale GAP-29, C1) : mode.kind="latlon" sans lat_field/
        # lon_field échouait sur toute ligne avant cette résolution.
        if effective_mode is None:
            effective_mode = _resolve_latlon_mode_from_fields(mode, list(row.keys()))
        try:
            yield extract_geometry(row, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def read_xml_header_fields(content: bytes) -> list[str]:
    fields: dict[str, None] = {}
    for _geom, props in parse_xml_generic(content, GeometryMode(kind="none")):
        for key in props:
            fields.setdefault(key, None)
    return list(fields.keys())


def list_layers(content: bytes, filename: str) -> list[LayerInfo]:
    lower = filename.lower()
    if lower.endswith(".gpkg"):
        suffix, wrap = ".gpkg", (lambda p: p)
    elif lower.endswith(".fgb"):
        suffix, wrap = ".fgb", (lambda p: p)
    elif lower.endswith(".zip"):
        suffix, wrap = ".zip", None
    elif lower.endswith((".dxf", ".dgn")):
        suffix, wrap = (".dxf" if lower.endswith(".dxf") else ".dgn"), (lambda p: p)
    elif lower.endswith((".kml", ".kmz", ".gml")):
        # Identité : PAS le wrap /vsizip/ de la branche .zip ci-dessus, cf.
        # parse_kml/parse_gml — un .kmz ou un .gml se lit tel quel.
        #
        # Trois littéraux explicites, et non `lower[lower.rfind("."):]` comme
        # auparavant : le résultat était en pratique toujours ".kml", ".kmz"
        # ou ".gml" (le dernier point est forcément celui de l'extension,
        # puisque cette branche est gardée par endswith), donc non
        # exploitable — mais c'était un flux « nom de fichier fourni par
        # l'appelant → chemin du système de fichiers » que rien dans le code
        # ne bornait, et que CodeQL signalait à juste titre comme
        # py/path-injection. Même forme que parse_kml/parse_gml ci-dessus.
        if lower.endswith(".kmz"):
            suffix = ".kmz"
        elif lower.endswith(".gml"):
            suffix = ".gml"
        else:
            suffix = ".kml"
        wrap = lambda p: p  # noqa: E731 — cohérent avec la forme déjà en vigueur ici
    else:
        raise ValueError(f"format non concerné par l'inspection : {filename}")
    with _temp_file(content, suffix) as tmp_path:
        path = _zip_dataset_path(tmp_path, content) if wrap is None else wrap(tmp_path)
        try:
            raw_layers = pyogrio.list_layers(path)
        except _OGR_ERRORS as exc:
            raise IngestionParseError(_UNREADABLE) from exc
        layers = []
        for name, _geom_type in raw_layers:
            try:
                info = pyogrio.read_info(path, layer=name)
            except _OGR_ERRORS as exc:
                raise IngestionParseError(f"couche '{name}' illisible") from exc
            layers.append(
                LayerInfo(
                    name=str(name),
                    feature_count=int(info["features"]),
                    geometry_type=str(info["geometry_type"] or "Unknown"),
                )
            )
        if not layers:
            raise IngestionParseError("aucune couche trouvée dans le fichier")
        return layers
