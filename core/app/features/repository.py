"""Lecture des features : SQL brut paramétré, identifiants quotés. Les
fonctions supposent que l'appelant a posé rls_scope() — elles ne gèrent ni
rôle ni tenant. fid et filtres arrivent en str (URL) et sont coercés selon
le type introspecté."""
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
    return [c for c in info.columns
            if c.name not in (info.pk_column, "tenant_id", info.geometry_column)]


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


def _where(session: Session, info: TableInfo, bbox, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (name, raw) in enumerate(sorted(filters.items())):
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            clauses.append(f"{quote_ident(session, name)} = :f{i}")
            params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(f"{g} && ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, :bsrid)")
        params.update({"bx0": bbox[0], "by0": bbox[1], "bx1": bbox[2],
                       "by1": bbox[3], "bsrid": info.srid or 4326})
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
    return {"type": "Feature", "id": m[info.pk_column],
            "geometry": geometry, "properties": props}


def select_features(session: Session, info: TableInfo, *, limit: int, offset: int,
                    bbox=None, filters=None) -> FeaturePage:
    t = quote_ident(session, info.table_name)
    where, params = _where(session, info, bbox, filters)
    matched = session.execute(
        text(f"SELECT count(*) FROM public.{t}{where}"), params).scalar()
    rows = session.execute(text(
        f"SELECT {_select_list(session, info)} FROM public.{t}{where} "
        f"ORDER BY {quote_ident(session, info.pk_column)} LIMIT :__l OFFSET :__o"
    ), {**params, "__l": limit, "__o": offset}).all()
    features = [_row_to_feature(info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched,
                       number_returned=len(features))


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
    row = session.execute(text(
        f"SELECT {_select_list(session, info)} FROM public.{t} "
        f"WHERE {quote_ident(session, info.pk_column)} = :fid"
    ), {"fid": value}).one_or_none()
    return _row_to_feature(info, row) if row else None
