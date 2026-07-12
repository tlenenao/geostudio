"""Pipeline d'import (SP-6a) : table PostGIS + collection + item carte, à
partir d'un flux de (géométrie, propriétés) déjà parsé (app.ingestion.parsers).
Séparé de tasks.py pour rester testable sans procrastinate ni S3 (postgis
seulement) — mêmes fonctions internes qu'un admin enregistrant une collection
à la main (app.collections.routes.register_collection)."""
import math
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.ddl import apply_collection_ddl, quote_ident
from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapLayer, MapView
from app.ingestion.parsers import IngestionParseError, parse_csv_latlon, parse_geojson
from app.items import repository as items_repo

# Doit rester synchronisé avec shell/src/map/basemaps.ts DEFAULT_BASEMAP.style.
_DEFAULT_BASEMAP_STYLE = "https://demotiles.maplibre.org/style.json"

_GEOM_TYPE_MAP = {
    "Point": "Point", "MultiPoint": "MultiPoint",
    "LineString": "LineString", "MultiLineString": "MultiLineString",
    "Polygon": "Polygon", "MultiPolygon": "MultiPolygon",
}


@dataclass
class ImportResult:
    collection_id: str
    item_id: str


def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    raise IngestionParseError(f"format non supporté : {filename}")


def _sql_type_for(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "bigint"
    if isinstance(value, float):
        return "double precision"
    return "text"


def _zoom_for_extent(bbox: list[float]) -> float:
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.0001)
    # Approximation grossière (span=360° → zoom 0, chaque doublement du zoom
    # réduit le span de moitié) : suffisant pour un centrage initial
    # raisonnable, l'utilisateur ajuste ensuite dans l'éditeur de carte.
    return max(0.0, min(18.0, math.log2(360.0 / span)))


def run_import(
    session: Session, *, tenant_id: str, created_by: str, filename: str,
    content: bytes, collection_title: str,
    lat_field: str | None, lon_field: str | None,
) -> ImportResult:
    fmt = _pick_format(filename)
    if fmt == "geojson":
        rows = list(parse_geojson(content))
    else:
        rows = list(parse_csv_latlon(content, lat_field, lon_field))
    if not rows:
        raise IngestionParseError("le fichier ne contient aucune entité")

    # Colonnes : union des clés de propriétés rencontrées, type déduit de la
    # première valeur non nulle vue pour chaque clé (repli "text" si toujours
    # nulle). Propriétés nommées "id" ou "geom" entreraient en collision avec
    # les colonnes fixes ci-dessous — cas non géré en v1 (hors périmètre SP-6a).
    columns: dict[str, str] = {}
    for _geom, props in rows:
        for key, value in props.items():
            if key in columns or value is None:
                continue
            columns[key] = _sql_type_for(value)
    for _geom, props in rows:
        for key in props:
            columns.setdefault(key, "text")

    geom_types = {geom.geom_type for geom, _props in rows}
    single_type = next(iter(geom_types)) if len(geom_types) == 1 else None
    pg_geom_type = _GEOM_TYPE_MAP.get(single_type, "Geometry") if single_type else "Geometry"

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
    create_sql += f", geom geometry({pg_geom_type}, 4326))"
    session.execute(text(create_sql))

    col_names = list(columns.keys())
    insert_cols = ", ".join(quote_ident(session, name) for name in col_names)
    insert_cols_full = "tenant_id, " + (insert_cols + ", " if insert_cols else "") + "geom"
    placeholders = ", ".join(f":{name}" for name in col_names)
    values_clause = ":tenant_id, " + (placeholders + ", " if placeholders else "") + "ST_GeomFromText(:geom_wkt, 4326)"
    insert_sql = f"INSERT INTO public.{t} ({insert_cols_full}) VALUES ({values_clause})"
    params = []
    for geom, props in rows:
        row_params = {name: props.get(name) for name in col_names}
        row_params["tenant_id"] = tenant_id
        row_params["geom_wkt"] = geom.wkt
        params.append(row_params)
    session.execute(text(insert_sql), params)

    info = introspect_table(session, table_name)
    apply_collection_ddl(session, table_name)
    col = collections_repo.create_collection(
        session, tenant_id=tenant_id, owner_id=created_by, table_name=table_name,
        title=collection_title, description="", is_public=False,
        pk_column=info.pk_column, geometry_column=info.geometry_column,
        geometry_type=info.geometry_type, srid=info.srid,
    )
    write_audit(
        session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
        action="collection.create", object_type="collection", object_id=col.id,
        payload={"tableName": col.table_name},
    )

    bbox = table_extent(session, info)
    if bbox:
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        zoom = _zoom_for_extent(bbox)
    else:
        center, zoom = (2.4, 46.6), 5.0

    core_base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=created_by,
        resource_type="map", title=collection_title,
    )
    write_audit(
        session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
        action="item.create", object_type="item", object_id=item.id,
        payload={"title": collection_title},
    )
    config = BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style=_DEFAULT_BASEMAP_STYLE),
            view=MapView(center=center, zoom=zoom),
            layers=[MapLayer(
                id=str(uuid.uuid4()), title=collection_title, visible=True,
                kind="feature", url=f"{core_base_url}/collections/{col.id}/items",
            )],
        ),
    )
    configs_repo.create_config(session, config, item_id=item.id)

    return ImportResult(collection_id=col.id, item_id=item.id)
