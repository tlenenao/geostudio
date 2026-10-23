# SPDX-License-Identifier: Apache-2.0
"""Pipeline d'import (SP-6a) : table PostGIS + collection + item carte, à
partir d'un flux de (géométrie, propriétés) déjà parsé (app.ingestion.parsers).
Séparé de tasks.py pour rester testable sans procrastinate ni S3 (postgis
seulement) — mêmes fonctions internes qu'un admin enregistrant une collection
à la main (app.collections.routes.register_collection)."""

import datetime
import math
import os
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from shapely import force_2d
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import is_external_basemaps_enabled
from app.collections import repository as collections_repo
from app.collections.ddl import apply_collection_ddl
from app.collections.domains import with_attribute_rules
from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.schemas import BaseMap, BuilderConfig, DatasetPayload, MapConfig, MapLayer, MapView
from app.features.repository import insert_features
from app.features.rls import rls_scope
from app.features.validation import validate_for_write
from app.ingestion.parsers import (
    GeometryMode,
    IngestionParseError,
    _is_geoparquet_from_bytes,
    _rename_reserved_property_keys,
    parse_csv_latlon,
    parse_dgn,
    parse_dxf,
    parse_filegdb_zip,
    parse_flatgeobuf,
    parse_geojson,
    parse_geoparquet,
    parse_gml,
    parse_gpkg,
    parse_jsonlines,
    parse_kml,
    parse_parquet_tabular,
    parse_shapefile_zip,
    parse_xlsx_sheet,
    parse_xml_generic,
    sniff_delimiter,
)
from app.items import repository as items_repo
from app.quotas.service import check_quota_or_raise
from app.relations.service import check_rows
from app.sharing.authorization import can
from app.sharing.geo_limits import resolve_geo_limits
from app.sql_ident import quote_ident

# Doit rester synchronisé avec shell/src/map/basemaps.ts (DEFAULT_BASEMAP / BLANK_BASEMAP).
_EXTERNAL_BASEMAP_STYLE = "https://demotiles.maplibre.org/style.json"
BLANK_BASEMAP_STYLE = "/basemaps/blank.json"


def default_basemap_style() -> str:
    return _EXTERNAL_BASEMAP_STYLE if is_external_basemaps_enabled() else BLANK_BASEMAP_STYLE


_GEOM_TYPE_MAP = {
    "Point": "Point",
    "MultiPoint": "MultiPoint",
    "LineString": "LineString",
    "MultiLineString": "MultiLineString",
    "Polygon": "Polygon",
    "MultiPolygon": "MultiPolygon",
}


@dataclass
class ImportResult:
    collection_id: str
    item_id: str | None
    # REV-282b : "map" (géométrie -> carte) ou "dataset" (tabulaire) ; le shell
    # et la notification choisissent l'éditeur à ouvrir sur ce type.
    item_resource_type: str | None = None


def _resolve_geometry_mode(
    *,
    lat_field: str | None,
    lon_field: str | None,
    wkt_field: str | None,
    geometry_mode: str | None,
) -> GeometryMode:
    if geometry_mode == "wkt":
        return GeometryMode(kind="wkt", wkt_field=wkt_field)
    if geometry_mode == "none":
        return GeometryMode(kind="none")
    return GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)


def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".gpkg"):
        return "gpkg"
    if lower.endswith(".fgb"):
        return "flatgeobuf"
    if lower.endswith(".gdb.zip"):
        return "filegdb"
    if lower.endswith(".zip"):
        return "shapefile"
    if lower.endswith(".dxf"):
        return "dxf"
    if lower.endswith(".dgn"):
        return "dgn"
    if lower.endswith((".kml", ".kmz")):
        return "kml"
    if lower.endswith(".gml"):
        return "gml"
    if lower.endswith(".jsonl"):
        return "jsonlines"
    if lower.endswith(".xml"):
        return "xml_generic"
    if lower.endswith(".parquet"):
        return "parquet"  # désambiguïsé par contenu, cf. run_import
    raise IngestionParseError(f"format non supporté : {filename}")


_INT_RE = re.compile(
    r"^-?(0|[1-9]\d{0,17})$"
)  # pas de zéro de tête (codes postaux), tient en bigint
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
# REV-282c : virgule décimale (export FR), seulement hors séparateur « , » ;
# 1 ou 2 décimales — « 1,234 » (milliers ou décimale ?) reste du texte.
_DECIMAL_COMMA_RE = re.compile(r"^-?\d+,\d{1,2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # fromisoformat seul accepte aussi « 2026-W01-1 »


def _convert_csv_value(value: str, kind: str):
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value.replace(",", "."))
    return datetime.date.fromisoformat(value)


_CSV_SQL_TYPES = {"int": "bigint", "float": "double precision", "date": "date"}


def _is_iso_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


class _CsvKinds:
    """P28.07 en un passage (AUD-014) : une colonne CSV dont toutes les valeurs non vides
    sont entières / décimales / dates ISO est typée. Les candidats sont éliminés valeur
    par valeur au lieu de garder toutes les valeurs en mémoire. Colonnes mixtes : texte."""

    def __init__(self, decimal_comma: bool = False) -> None:
        self.decimal_comma = decimal_comma
        self._candidates: dict[str, set[str]] = {}
        self._seen: set[str] = set()
        self._not_text: set[str] = set()

    def add(self, props: dict) -> None:
        for key, raw in props.items():
            cand = self._candidates.setdefault(key, {"int", "float", "date"})
            if raw is None:
                continue
            if not isinstance(raw, str):
                self._not_text.add(key)
                continue
            value = raw.strip()
            if not value:
                continue
            self._seen.add(key)
            if not _INT_RE.match(value):
                cand.discard("int")
                if not (
                    _FLOAT_RE.match(value)
                    or (self.decimal_comma and _DECIMAL_COMMA_RE.match(value))
                ):
                    cand.discard("float")
            if "date" in cand and not _is_iso_date(value):
                cand.discard("date")

    def kinds(self) -> dict[str, str]:
        out = {}
        for key, cand in self._candidates.items():
            if key in self._not_text or key not in self._seen:
                continue
            kind = next((k for k in ("int", "float", "date") if k in cand), None)
            if kind is not None:
                out[key] = kind
        return out


def _csv_column_kind(values: list[str], decimal_comma: bool = False) -> str | None:
    kinds = _CsvKinds(decimal_comma)
    for value in values:
        kinds.add({"v": value})
    return kinds.kinds().get("v")


def _sql_type_for(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, datetime.date):
        return "date"
    if isinstance(value, int):
        return "bigint"
    if isinstance(value, float):
        return "double precision"
    return "text"


_RENDER_HINTS = {
    "point": ("point", "circle"),
    "line": ("line", "line"),
    "polygon": ("polygon", "fill"),
}


def _render_hints(geom_types: set[str]) -> dict:
    kinds = {t.removeprefix("Multi").replace("LineString", "line").lower() for t in geom_types}
    if len(kinds) != 1 or not kinds <= _RENDER_HINTS.keys():
        return {}
    geometry_kind, render_as = _RENDER_HINTS[kinds.pop()]
    return {"geometryKind": geometry_kind, "renderAs": render_as}


def _zoom_for_extent(bbox: list[float]) -> float:
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.0001)
    # Approximation grossière (span=360° → zoom 0, chaque doublement du zoom
    # réduit le span de moitié) : suffisant pour un centrage initial
    # raisonnable, l'utilisateur ajuste ensuite dans l'éditeur de carte.
    return max(0.0, min(18.0, math.log2(360.0 / span)))


_INSERT_BATCH = 10_000  # AUD-014 : 50k entités = 5 INSERT (plafond de test_ingestion_importer_perf)


@dataclass
class _Scan:
    """Premier passage (AUD-014) : tout ce qu'il faut savoir avant le CREATE TABLE."""

    columns: dict[str, str]
    geom_types: set[str]
    has_geometry: bool
    count: int


def _open_rows(
    filename: str,
    content: bytes,
    *,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None,
    wkt_field: str | None,
    geometry_mode: str | None,
) -> tuple[_Scan, Callable[[], Iterator[tuple[BaseGeometry | None, dict]]]]:
    """AUD-014 : le fichier est parcouru deux fois EN FLUX (aucune liste complète) — un
    passage d'analyse (colonnes, types CSV, géométries, compte), puis une fabrique de
    second passage qui rend les lignes typées pour l'insertion par lots.
    ponytail: le parse (et la réparation make_valid) est payé deux fois ; un seul passage
    exigerait une table de transit retypée après coup."""
    mode = _resolve_geometry_mode(
        lat_field=lat_field, lon_field=lon_field, wkt_field=wkt_field, geometry_mode=geometry_mode
    )
    fmt = _pick_format(filename)
    if fmt == "parquet":
        if _is_geoparquet_from_bytes(content):
            parse = lambda: parse_geoparquet(content)  # noqa: E731
        else:
            parse = lambda: parse_parquet_tabular(content, mode)  # noqa: E731
    else:
        parse = {
            "geojson": lambda: parse_geojson(content),
            "csv": lambda: parse_csv_latlon(content, mode),
            "xlsx": lambda: parse_xlsx_sheet(content, layer_name, mode),
            "gpkg": lambda: parse_gpkg(content, layer_name),
            "flatgeobuf": lambda: parse_flatgeobuf(content, layer_name),
            "shapefile": lambda: parse_shapefile_zip(content, layer_name),
            "filegdb": lambda: parse_filegdb_zip(content, layer_name),
            "dxf": lambda: parse_dxf(content, layer_name),
            "dgn": lambda: parse_dgn(content, layer_name),
            "kml": lambda: parse_kml(content, layer_name),
            "gml": lambda: parse_gml(content, layer_name),
            "jsonlines": lambda: parse_jsonlines(content, mode),
            "xml_generic": lambda: parse_xml_generic(content, mode),
        }[fmt]

    def normalized() -> Iterator[tuple[BaseGeometry | None, dict]]:
        # REV-350 : id/tenant_id/geom entreraient en collision avec les colonnes fixes de
        # la table ; un seul point pour tous les formats. REV-351 : colonnes créées en 2D,
        # une coordonnée Z ferait échouer l'INSERT (import comme ajout).
        for geom, props in parse():
            yield (
                None if geom is None else force_2d(geom),
                _rename_reserved_property_keys(props, fmt),
            )

    decimal_comma = False
    if fmt == "csv":
        try:
            decimal_comma = sniff_delimiter(content.decode("utf-8-sig")) != ","
        except UnicodeDecodeError:
            pass  # parse_csv_latlon lève le message utilisateur au premier passage
    csv_kinds = _CsvKinds(decimal_comma)
    # Type d'une colonne = celui de sa première valeur non nulle, colonnes rangées dans
    # l'ordre de cette première valeur ; toujours nulles : « text », en fin (même ordre
    # qu'avant AUD-014). Colonne CSV typée : sa première valeur NON VIDE (le vide y
    # devient NULL). Positions (ligne, rang) gardées pour les deux cas, choisies à la fin.
    first_any: dict[str, tuple[tuple[int, int], str]] = {}
    first_filled: dict[str, tuple[int, int]] = {}
    keys: dict[str, None] = {}
    geom_types: set[str] = set()
    count = 0
    for geom, props in normalized():
        count += 1
        if geom is not None:
            geom_types.add(geom.geom_type)
        if fmt == "csv":
            csv_kinds.add(props)
        for j, (key, value) in enumerate(props.items()):
            keys.setdefault(key)
            if value is None:
                continue
            if key not in first_any:
                first_any[key] = ((count, j), _sql_type_for(value))
            if key not in first_filled and not (isinstance(value, str) and not value.strip()):
                first_filled[key] = (count, j)
    if count == 0:
        raise IngestionParseError("le fichier ne contient aucune entité")
    kinds = csv_kinds.kinds()
    placed = {
        key: (first_filled[key], _CSV_SQL_TYPES[kinds[key]]) if key in kinds else first_any[key]
        for key in first_any
    }
    columns = {
        key: sql_type for key, (_pos, sql_type) in sorted(placed.items(), key=lambda kv: kv[1][0])
    }
    for key in keys:
        columns.setdefault(key, "text")

    def typed_rows() -> Iterator[tuple[BaseGeometry | None, dict]]:
        for geom, props in normalized():
            for key, kind in kinds.items():
                v = props.get(key)
                props[key] = (
                    None if v is None or v.strip() == "" else _convert_csv_value(v.strip(), kind)
                )
            yield geom, props

    return _Scan(columns, geom_types, bool(geom_types), count), typed_rows


def run_import(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    filename: str,
    content: bytes,
    collection_title: str,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None = None,
    wkt_field: str | None = None,
    geometry_mode: str | None = None,
) -> ImportResult:
    scan, typed_rows = _open_rows(
        filename,
        content,
        lat_field=lat_field,
        lon_field=lon_field,
        layer_name=layer_name,
        wkt_field=wkt_field,
        geometry_mode=geometry_mode,
    )
    columns = scan.columns
    # has_geometry : un seul mode de géométrie par import (jamais mixte) — soit toutes
    # les lignes portent une géométrie, soit aucune (geometry_mode="none").
    has_geometry = scan.has_geometry
    geom_types = scan.geom_types
    single_type = next(iter(geom_types)) if len(geom_types) == 1 else None
    pg_geom_type = _GEOM_TYPE_MAP.get(single_type, "Geometry") if single_type else "Geometry"

    # Échec rapide avant le CREATE TABLE + INSERT massif (P26.03) : collection
    # puis items (carte + dataset) sont de toute façon recontrôlés au point
    # de création (create_collection/create_item).
    check_quota_or_raise(session, tenant_id=tenant_id, kind="collections")
    check_quota_or_raise(session, tenant_id=tenant_id, kind="items")
    table_name = f"ingest_{uuid.uuid4().hex[:12]}"
    t = quote_ident(session, table_name)
    col_defs = ", ".join(
        f"{quote_ident(session, name)} {sql_type}" for name, sql_type in columns.items()
    )
    # tenant_id est déclaré ici (et rempli à l'INSERT) plutôt que laissé à
    # apply_collection_ddl ci-dessous : ce dernier ne fait qu'un
    # ADD COLUMN IF NOT EXISTS ... DEFAULT 'default' (no-op si la colonne
    # existe déjà) — s'il posait la colonne après coup, les lignes qu'on
    # vient d'insérer hériteraient toutes du littéral 'default' au lieu du
    # tenant réel de l'uploader, les rendant invisibles à travers RLS pour
    # tout tenant dont l'id n'est pas "default" (bug de cloisonnement).
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL"
    if col_defs:
        create_sql += f", {col_defs}"
    if has_geometry:
        create_sql += f", geom geometry({pg_geom_type}, 4326))"
    else:
        create_sql += ")"
    session.execute(text(create_sql))

    col_names = list(columns.keys())
    insert_cols = ", ".join(quote_ident(session, name) for name in col_names)
    if has_geometry:
        insert_cols_full = "tenant_id, " + (insert_cols + ", " if insert_cols else "") + "geom"
    else:
        insert_cols_full = "tenant_id" + (", " + insert_cols if insert_cols else "")
    # REV-349 : paramètres positionnels, indépendants du nom de colonne (un en-tête
    # « Code postal » ou « a-b » n'est pas un identifiant de paramètre lié valide).
    placeholders = ", ".join(f":p{i}" for i in range(len(col_names)))
    if has_geometry:
        values_clause = (
            ":tenant_id, "
            + (placeholders + ", " if placeholders else "")
            + "ST_GeomFromText(:geom_wkt, 4326)"
        )
    else:
        values_clause = ":tenant_id" + (", " + placeholders if placeholders else "")
    insert_sql = f"INSERT INTO public.{t} ({insert_cols_full}) VALUES ({values_clause})"
    batch: list[dict] = []
    for geom, props in typed_rows():
        row_params = {f"p{i}": props.get(name) for i, name in enumerate(col_names)}
        row_params["tenant_id"] = tenant_id
        if has_geometry:
            # has_geometry vrai => geom non-None sur toute ligne (mode unique par import).
            row_params["geom_wkt"] = geom.wkt if geom is not None else None
        batch.append(row_params)
        if len(batch) >= _INSERT_BATCH:
            session.execute(text(insert_sql), batch)
            batch = []
    if batch:
        session.execute(text(insert_sql), batch)

    info = introspect_table(session, table_name)
    apply_collection_ddl(session, table_name, tenant_id=tenant_id)
    col = collections_repo.create_collection(
        session,
        tenant_id=tenant_id,
        owner_id=created_by,
        table_name=table_name,
        title=collection_title,
        description="",
        is_public=False,
        pk_column=info.pk_column,
        geometry_column=info.geometry_column,
        geometry_type=info.geometry_type,
        srid=info.srid,
        feature_count=scan.count,
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=created_by,
        actor_kind="user",
        action="collection.create",
        object_type="collection",
        object_id=col.id,
        payload={"tableName": col.table_name},
    )

    if not has_geometry:
        # Pas de géométrie => pas de carte à afficher : aucun Item/Config
        # créé (JSON Lines/Parquet/XML génériques en geometry_mode="none",
        # GAP-29 Task 11) — seule la collection tabulaire existe.
        # P28.06 : ... mais un item « dataset » la rend atteignable depuis le
        # catalogue « Données » du créateur (l'item dataset est renvoyé avec son
        # type, REV-282b : le shell ouvre /datasets/{id}/edit).
        ds_item = items_repo.create_item(
            session,
            tenant_id=tenant_id,
            owner_id=created_by,
            resource_type="dataset",
            title=collection_title,
        )
        write_audit(
            session,
            tenant_id=tenant_id,
            actor_id=created_by,
            actor_kind="user",
            action="item.create",
            object_type="item",
            object_id=ds_item.id,
            payload={"title": collection_title},
        )
        configs_repo.create_config(
            session,
            BuilderConfig(
                kind="dataset",
                dataset=DatasetPayload(source="collection", collectionId=col.id),
            ),
            item_id=ds_item.id,
            tenant_id=tenant_id,
        )
        return ImportResult(collection_id=col.id, item_id=ds_item.id, item_resource_type="dataset")

    bbox = table_extent(session, info)
    if bbox:
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        zoom = _zoom_for_extent(bbox)
    else:
        center, zoom = (2.4, 46.6), 5.0

    # /v1 explicite : cette URL est écrite telle quelle dans MapLayer.url et
    # fetchée directement par le navigateur (shell/src/map/MapView.tsx,
    # data: layer.url) — jamais recomposée depuis coreUrl côté shell.
    # isHostedCoreUrl() (même fichier) compare cette URL au coreUrl versionné
    # du shell pour décider d'attacher le jeton d'auth (piège SP-24 C1) ;
    # sans /v1 ici, une collection non publique redeviendrait illisible.
    core_base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200") + "/v1"
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=created_by,
        resource_type="map",
        title=collection_title,
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=created_by,
        actor_kind="user",
        action="item.create",
        object_type="item",
        object_id=item.id,
        payload={"title": collection_title},
    )
    # P29.01 : une couche « feature » (GeoJSON /items) est plafonnée à une page
    # (100 entités) ; avec une géométrie on sert donc la collection en tuiles
    # MVT, sans plafond de page. Sans géométrie, l'ancienne forme est conservée.
    if col.geometry_column:
        source: dict = {
            "kind": "vector",
            "tilesUrl": f"{core_base_url}/collections/{col.id}/tiles/{{z}}/{{x}}/{{y}}.mvt",
            "sourceLayer": col.id,
            "pkColumn": col.pk_column,
        }
    else:
        source = {"kind": "feature", "url": f"{core_base_url}/collections/{col.id}/items"}
    config = BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style=default_basemap_style()),
            view=MapView(center=center, zoom=zoom),
            layers=[
                MapLayer(
                    id=str(uuid.uuid4()),
                    title=collection_title,
                    visible=True,
                    **source,
                    # P28.04/05 : collectionId -> emprise de l'item (bbox) ;
                    # geometryKind/renderAs -> rendu correct (sinon « fill »,
                    # invisible pour des points).
                    collectionId=col.id,
                    **_render_hints(geom_types),
                )
            ],
        ),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)

    return ImportResult(collection_id=col.id, item_id=item.id, item_resource_type="map")


REPORT_SAMPLE_MAX = 1000
_APPEND_BATCH = 2000


def _coerce_for_column(col, value):
    """Types CSV déduits ≠ type cible : ramène au type de la colonne si sans perte."""
    if value is None:
        return None
    if col.type == "string" and not isinstance(value, str):
        return str(value)
    if col.type == "integer" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def run_append(
    session: Session,
    *,
    tenant_id: str,
    user,
    collection_id: str,
    filename: str,
    content: bytes,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None = None,
    wkt_field: str | None = None,
    geometry_mode: str | None = None,
) -> dict:
    """ARC-13 : ajoute les lignes d'un fichier à une collection EXISTANTE. Chaque ligne passe
    par `validate_for_write` (domaines, sous-types, règles) comme une écriture REST ; les
    lignes refusées ne sont pas insérées et figurent dans le rapport (échantillon plafonné).
    Rapport : {inserted, rejectedCount, rejected: [{row, errors}], ignoredColumns}."""
    col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
    if col is None:
        raise IngestionParseError(f"collection '{collection_id}' introuvable")
    if not col.editable or not can(
        session,
        user_id=user.id,
        action="write",
        item=collections_repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.acts_as_admin(),
    ):
        raise IngestionParseError(f"collection '{collection_id}' non modifiable")
    info = with_attribute_rules(introspect_table(session, col.table_name), col)
    _scan, typed_rows = _open_rows(
        filename,
        content,
        lat_field=lat_field,
        lon_field=lon_field,
        layer_name=layer_name,
        wkt_field=wkt_field,
        geometry_mode=geometry_mode,
    )
    writable = {
        c.name: c
        for c in info.columns
        if c.name not in (info.pk_column, "tenant_id", info.geometry_column)
        and c.type != "unsupported"
    }
    ignored: dict[str, None] = {}
    rejected: list[dict] = []
    rejected_count = inserted = 0
    batch: list[tuple[dict, dict | None, int]] = []  # (propriétés, géométrie, n° de ligne)
    geo_limits = resolve_geo_limits(session, tenant_id=tenant_id, user_id=user.id)

    def _scope(sess, tid, masked=False):
        return rls_scope(sess, tid, masked=masked, geo_limits=geo_limits)

    def flush() -> None:
        nonlocal inserted, rejected_count
        if not batch:
            return
        # AUD-165 : clé étrangère logique des relations (check_write ne couvrait que la route
        # REST). Hors `rls_scope` : la lecture des parents ouvre le sien (un scope imbriqué
        # rendrait le rôle propriétaire à la fin du scope interne).
        bad = check_rows(session, user, col, [b[0] for b in batch], _scope, new_rows=True)
        keep = []
        for i, (props, geometry, number) in enumerate(batch):
            if i in bad:
                rejected_count += 1
                if len(rejected) < REPORT_SAMPLE_MAX:
                    e = bad[i]
                    rejected.append(
                        {
                            "row": number,
                            "errors": [
                                {k: e[k] for k in ("field", "code", "message")},
                            ],
                        }
                    )
            else:
                keep.append((props, geometry))
        if keep:
            with rls_scope(session, tenant_id, geo_limits=geo_limits):
                insert_features(session, info, keep)
            inserted += len(keep)
        batch.clear()

    for number, (geom, props) in enumerate(typed_rows(), start=1):
        clean = {}
        for key, value in props.items():
            if key in writable:
                clean[key] = _coerce_for_column(writable[key], value)
            else:
                ignored.setdefault(key)
        geometry = mapping(geom) if geom is not None and info.geometry_column else None
        feature = {"type": "Feature", "properties": clean, "geometry": geometry}
        if errors := validate_for_write(info, feature):
            rejected_count += 1
            if len(rejected) < REPORT_SAMPLE_MAX:
                rejected.append({"row": number, "errors": errors})
            continue
        batch.append((feature["properties"], geometry, number))
        if len(batch) >= _APPEND_BATCH:
            flush()
    flush()
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.append_import",
        object_type="collection",
        object_id=col.id,
        payload={"filename": filename, "inserted": inserted, "rejected": rejected_count},
    )
    return {
        "inserted": inserted,
        "rejectedCount": rejected_count,
        "rejected": rejected,
        "ignoredColumns": list(ignored),
    }
