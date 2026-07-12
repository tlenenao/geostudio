"""Parseurs GeoJSON et CSV+lat/lon (SP-6a) — pur Python, aucune dépendance
GDAL (réservée à SP-6b pour GeoPackage/Shapefile). Chaque parseur produit un
flux (géométrie shapely, propriétés) ; toute ligne/feature invalide lève
IngestionParseError immédiatement (fail-fast, §5 de la spec SP-6a) — pas
d'import partiel silencieux."""
import csv
import io
import json
from collections.abc import Iterator

from shapely.errors import ShapelyError
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry


class IngestionParseError(Exception):
    """Message affiché tel quel comme ingestion_jobs.error_message."""


_LAT_NAMES = {"lat", "latitude", "y"}
_LON_NAMES = {"lon", "lng", "longitude", "x"}


def detect_lat_lon_fields(fieldnames: list[str]) -> tuple[str, str] | None:
    by_lower = {name.lower(): name for name in fieldnames}
    lat = next((by_lower[n] for n in _LAT_NAMES if n in by_lower), None)
    lon = next((by_lower[n] for n in _LON_NAMES if n in by_lower), None)
    if lat is None or lon is None:
        return None
    return lat, lon


def parse_geojson(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestionParseError(f"JSON invalide : {exc}") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise IngestionParseError("le GeoJSON doit être une FeatureCollection")
    features = data.get("features", [])
    if not isinstance(features, list):
        raise IngestionParseError("le GeoJSON doit être une FeatureCollection")
    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise IngestionParseError(f"feature {i} : entrée invalide")
        geometry = feature.get("geometry")
        if geometry is None:
            raise IngestionParseError(f"feature {i} : géométrie manquante")
        try:
            geom = shape(geometry)
        except (ValueError, AttributeError, KeyError, TypeError, ShapelyError) as exc:
            raise IngestionParseError(f"feature {i} : géométrie invalide ({exc})") from exc
        if not geom.is_valid:
            raise IngestionParseError(f"feature {i} : géométrie invalide")
        properties = feature.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise IngestionParseError(f"feature {i} : properties invalide")
        yield geom, dict(properties or {})


def parse_csv_latlon(
    content: bytes, lat_field: str | None, lon_field: str | None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    try:
        fieldnames = reader.fieldnames or []
    except csv.Error as exc:
        raise IngestionParseError("en-tête CSV invalide ou mal formé") from exc
    if lat_field is None or lon_field is None:
        detected = detect_lat_lon_fields(fieldnames)
        if detected is None:
            raise IngestionParseError(
                "colonnes lat/lon introuvables automatiquement — précisez-les"
            )
        lat_field, lon_field = detected
    if lat_field not in fieldnames or lon_field not in fieldnames:
        raise IngestionParseError(f"colonnes '{lat_field}'/'{lon_field}' absentes du CSV")
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
            lat = float(row[lat_field])
            lon = float(row[lon_field])
        except (TypeError, ValueError):
            raise IngestionParseError(
                f"ligne {i} : lat/lon invalide "
                f"('{row.get(lat_field)}', '{row.get(lon_field)}')"
            )
        properties = {k: v for k, v in row.items() if k not in (lat_field, lon_field)}
        yield Point(lon, lat), properties
