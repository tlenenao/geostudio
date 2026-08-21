# SPDX-License-Identifier: Apache-2.0
"""Lecture et écriture des features : SQL brut paramétré, identifiants
quotés. Les fonctions supposent que l'appelant a posé rls_scope() — elles ne
gèrent ni rôle ni tenant (sauf le stampage explicite du tenant à l'insert).
fid et filtres arrivent en str (URL) et sont coercés selon le type
introspecté. Les colonnes de type "unsupported" sont read-only (contrat de
validation.py) : jamais écrites ici."""

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import ColumnInfo, TableInfo


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int
    number_returned: int


class FilterError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _property_columns(info: TableInfo) -> list[ColumnInfo]:
    return [
        c for c in info.columns if c.name not in (info.pk_column, "tenant_id", info.geometry_column)
    ]


def _coerce(col: ColumnInfo, raw: str):
    try:
        if col.type == "integer":
            return int(raw)
        if col.type == "number":
            return float(raw)
        if col.type == "boolean":
            if raw.lower() in ("true", "t", "1"):
                return True
            if raw.lower() in ("false", "f", "0"):
                return False
            raise ValueError(raw)
        return raw  # string/enum/date/datetime : PG caste text implicitement
    except ValueError:
        raise FilterError(col.name, f"cannot parse '{raw}' as {col.type}") from None


_RANGE_OPS = {"__gte": ">=", "__lte": "<="}


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None


def _where(session: Session, info: TableInfo, bbox, geom_intersects, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (raw_name, raw) in enumerate(sorted(filters.items())):
            name, suffix = _split_filter_key(raw_name)
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            ident = quote_ident(session, name)
            if suffix == "__in":
                values = raw.split(",")
                placeholders = []
                for j, value in enumerate(values):
                    key = f"f{i}_{j}"
                    params[key] = _coerce(col, value)
                    placeholders.append(f":{key}")
                clauses.append(f"{ident} IN ({', '.join(placeholders)})")
            elif suffix in _RANGE_OPS:
                clauses.append(f"{ident} {_RANGE_OPS[suffix]} :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
            else:
                clauses.append(f"{ident} = :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(
            f"{g} && ST_Transform(ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, 4326), :bsrid)"
        )
        params.update(
            {
                "bx0": bbox[0],
                "by0": bbox[1],
                "bx1": bbox[2],
                "by1": bbox[3],
                "bsrid": info.srid or 4326,
            }
        )
    if geom_intersects is not None:
        # SP-14n : intersection géométrique exacte (ST_Intersects), complément
        # précis du bbox && ci-dessus (chevauchement d'enveloppes uniquement).
        if info.geometry_column is None:
            raise FilterError("geom_intersects", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(
            f"ST_Intersects({g}, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:gi), 4326), :gisrid))"
        )
        params.update({"gi": json.dumps(geom_intersects), "gisrid": info.srid or 4326})
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _select_list(session: Session, info: TableInfo) -> str:
    cols = [quote_ident(session, info.pk_column)]
    cols += [quote_ident(session, c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"ST_AsGeoJSON({quote_ident(session, info.geometry_column)}) AS __geo")
    return ", ".join(cols)


def _row_to_feature(info: TableInfo, row) -> dict:
    m = row._mapping
    props = {c.name: m[c.name] for c in _property_columns(info)}
    geometry = None
    if info.geometry_column and m.get("__geo"):
        geometry = json.loads(m["__geo"])
    return {"type": "Feature", "id": m[info.pk_column], "geometry": geometry, "properties": props}


def select_features(
    session: Session,
    info: TableInfo,
    *,
    limit: int,
    offset: int,
    bbox=None,
    geom_intersects=None,
    filters=None,
) -> FeaturePage:
    t = quote_ident(session, info.table_name)
    where, params = _where(session, info, bbox, geom_intersects, filters)
    matched = session.execute(text(f"SELECT count(*) FROM public.{t}{where}"), params).scalar()
    rows = session.execute(
        text(
            f"SELECT {_select_list(session, info)} FROM public.{t}{where} "
            f"ORDER BY {quote_ident(session, info.pk_column)} LIMIT :__l OFFSET :__o"
        ),
        {**params, "__l": limit, "__o": offset},
    ).all()
    features = [_row_to_feature(info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched, number_returned=len(features))


def _coerce_fid(info: TableInfo, fid: str):
    pk = next((c for c in info.columns if c.name == info.pk_column), None)
    if pk is not None and pk.type == "integer":
        try:
            return int(fid)
        except ValueError:
            return None
    return fid


def get_feature(session: Session, info: TableInfo, *, fid: str) -> dict | None:
    value = _coerce_fid(info, fid)
    if value is None:
        return None
    t = quote_ident(session, info.table_name)
    row = session.execute(
        text(
            f"SELECT {_select_list(session, info)} FROM public.{t} "
            f"WHERE {quote_ident(session, info.pk_column)} = :fid"
        ),
        {"fid": value},
    ).one_or_none()
    return _row_to_feature(info, row) if row else None


def _geometry_sql(info: TableInfo) -> str:
    return "ST_SetSRID(ST_GeomFromGeoJSON(:__geom), :__srid)"


def insert_feature(session: Session, info: TableInfo, *, properties: dict, geometry: dict | None):
    t = quote_ident(session, info.table_name)
    cols, values, params = ["tenant_id"], ["current_setting('app.tenant_id')"], {}
    for i, col in enumerate(_property_columns(info)):
        if col.type == "unsupported":  # read-only (contrat de validation.py)
            continue
        if col.name in properties:
            cols.append(quote_ident(session, col.name))
            values.append(f":p{i}")
            params[f"p{i}"] = properties[col.name]
    if geometry is not None and info.geometry_column:
        cols.append(quote_ident(session, info.geometry_column))
        values.append(_geometry_sql(info))
        params.update(__geom=json.dumps(geometry), __srid=info.srid or 4326)
    fid = session.execute(
        text(
            f"INSERT INTO public.{t} ({', '.join(cols)}) VALUES ({', '.join(values)}) "
            f"RETURNING {quote_ident(session, info.pk_column)}"
        ),
        params,
    ).scalar()
    return fid


def replace_feature(
    session: Session, info: TableInfo, *, fid: str, properties: dict, geometry: dict | None
) -> bool:
    value = _coerce_fid(info, fid)
    if value is None:
        return False
    t = quote_ident(session, info.table_name)
    sets, params = [], {"__fid": value}
    for i, col in enumerate(_property_columns(info)):
        if col.type == "unsupported":  # read-only (contrat de validation.py) : intouchée
            continue
        sets.append(f"{quote_ident(session, col.name)} = :p{i}")
        params[f"p{i}"] = properties.get(col.name)  # absent → NULL (remplacement complet)
    if info.geometry_column:
        if geometry is not None:
            sets.append(f"{quote_ident(session, info.geometry_column)} = {_geometry_sql(info)}")
            params.update(__geom=json.dumps(geometry), __srid=info.srid or 4326)
        else:
            sets.append(f"{quote_ident(session, info.geometry_column)} = NULL")
    r = session.execute(
        text(
            f"UPDATE public.{t} SET {', '.join(sets)} "
            f"WHERE {quote_ident(session, info.pk_column)} = :__fid"
        ),
        params,
    )
    return r.rowcount == 1


def delete_feature(session: Session, info: TableInfo, *, fid: str) -> bool:
    value = _coerce_fid(info, fid)
    if value is None:
        return False
    t = quote_ident(session, info.table_name)
    r = session.execute(
        text(f"DELETE FROM public.{t} WHERE {quote_ident(session, info.pk_column)} = :__fid"),
        {"__fid": value},
    )
    return r.rowcount == 1


def delete_all_features(session: Session, info: TableInfo) -> int:
    t = quote_ident(session, info.table_name)
    result = session.execute(text(f"DELETE FROM public.{t}"))
    return result.rowcount
