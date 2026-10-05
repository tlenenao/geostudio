# SPDX-License-Identifier: Apache-2.0
"""Lecture et écriture des features : SQL brut paramétré, identifiants
quotés. Les fonctions supposent que l'appelant a posé rls_scope() — elles ne
gèrent ni rôle ni tenant (sauf le stampage explicite du tenant à l'insert).
fid et filtres arrivent en str (URL) et sont coercés selon le type
introspecté. Les colonnes de type "unsupported" sont read-only (contrat de
validation.py) : jamais écrites ici."""

import base64
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.collections.introspection import ColumnInfo, TableInfo
from app.sql_ident import quote_ident


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int | None
    number_returned: int
    next_cursor: str | None = None
    number_matched_lower_bound: bool = False


# REV-279a : au-delà, number_matched est une borne basse (count(*) borné).
EXACT_COUNT_CAP = 100_000


class CursorError(ValueError):
    """Curseur keyset mal formé ou invalide pour le type de PK (→ 400 invalid_cursor)."""


def encode_cursor(pk: Any) -> str:
    raw = json.dumps({"pk": pk}, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str) -> Any:
    try:
        pad = "=" * (-len(value) % 4)
        return json.loads(base64.urlsafe_b64decode(value + pad))["pk"]
    except Exception as exc:  # noqa: BLE001 - tout échec de décodage = curseur invalide
        raise CursorError("invalid cursor") from exc


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
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
            if col.type in ("unsupported", "list"):
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
            elif suffix == "__lte" and col.type == "datetime" and _DATE_ONLY.match(raw):
                # P25.12 : borne haute « YYYY-MM-DD » = tout ce jour (sinon la
                # comparaison tombe à minuit et exclut les événements du jour).
                try:
                    date.fromisoformat(raw)  # « 2026-13-45 » : 400, pas une DataError 500
                except ValueError:
                    raise FilterError(name, f"cannot parse '{raw}' as datetime") from None
                clauses.append(f"{ident} < CAST(:f{i} AS timestamptz) + INTERVAL '1 day'")
                params[f"f{i}"] = raw
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
    after: str | None = None,
    count_mode: Literal["exact", "capped", "none"] = "exact",
) -> FeaturePage:
    if after is not None and offset > 0:
        raise CursorError("after and offset are mutually exclusive")
    t = quote_ident(session, info.table_name)
    pk = quote_ident(session, info.pk_column)
    where, params = _where(session, info, bbox, geom_intersects, filters)
    page_where, page_params = where, dict(params)
    if after is not None:
        value = _coerce_fid(info, str(decode_cursor(after)))
        if value is None:
            raise CursorError("invalid cursor")
        page_where += (" AND " if where else " WHERE ") + f"{pk} > :__after"
        page_params["__after"] = value
    page_sql = text(
        f"SELECT {_select_list(session, info)} FROM public.{t}{page_where} "
        f"ORDER BY {pk} LIMIT :__l OFFSET :__o"
    )
    page_args = {**page_params, "__l": limit + 1, "__o": offset}
    if after is None:
        rows = session.execute(page_sql, page_args).all()
    else:
        # Valeur de curseur inadaptée au type de PK (hors int8, non-UUID…) :
        # DataError PG → 400. SAVEPOINT pour garder transaction et GUC RLS sains.
        try:
            with session.begin_nested():
                rows = session.execute(page_sql, page_args).all()
        except DataError as exc:
            raise CursorError("invalid cursor") from exc
    has_more = len(rows) > limit
    features = [_row_to_feature(info, r) for r in rows[:limit]]
    next_cursor = encode_cursor(features[-1]["id"]) if has_more else None
    lower_bound = False
    if after is not None:
        matched = None  # le total d'une page keyset n'est pas calculé
    elif not has_more and (features or offset == 0):
        # Page courte : le total est connu sans count(*) (P24.09). Exact.
        matched = offset + len(features)
    elif count_mode == "none":
        matched = None  # l'appelant (export) ne consomme pas le total
    elif count_mode == "none":
        matched = None  # l'appelant (export) ne consomme pas le total
    elif count_mode == "capped":
        n = session.execute(
            text(f"SELECT count(*) FROM (SELECT 1 FROM public.{t}{where} LIMIT :__cap) q"),
            {**params, "__cap": EXACT_COUNT_CAP + 1},
        ).scalar()
        lower_bound = n > EXACT_COUNT_CAP
        matched = EXACT_COUNT_CAP if lower_bound else n
    else:
        matched = session.execute(text(f"SELECT count(*) FROM public.{t}{where}"), params).scalar()
    return FeaturePage(
        features=features,
        number_matched=matched,
        number_returned=len(features),
        next_cursor=next_cursor,
        number_matched_lower_bound=lower_bound,
    )


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


def insert_features(
    session: Session, info: TableInfo, rows: list[tuple[dict, dict | None]]
) -> None:
    """Insertion groupée (executemany, un seul aller-retour par lot) de lignes
    (properties, geometry) déjà validées. Contrairement à insert_feature, toutes
    les lignes du lot partagent les colonnes de la première (clés absentes →
    NULL, pas le défaut de colonne) : réservé aux producteurs à schéma uniforme
    (pipelines, t03b-001)."""
    if not rows:
        return
    t = quote_ident(session, info.table_name)
    cols, values = ["tenant_id"], ["current_setting('app.tenant_id')"]
    keys: dict[str, str] = {}  # paramètre -> nom de colonne
    for i, col in enumerate(_property_columns(info)):
        if col.type != "unsupported" and col.name in rows[0][0]:
            cols.append(quote_ident(session, col.name))
            values.append(f":p{i}")
            keys[f"p{i}"] = col.name
    if info.geometry_column:
        cols.append(quote_ident(session, info.geometry_column))
        values.append(
            f"CASE WHEN CAST(:__geom AS text) IS NULL THEN NULL ELSE {_geometry_sql(info)} END"
        )
    params = []
    for properties, geometry in rows:
        p = {k: properties.get(n) for k, n in keys.items()}
        if info.geometry_column:
            p.update(
                __geom=json.dumps(geometry) if geometry is not None else None,
                __srid=info.srid or 4326,
            )
        params.append(p)
    session.execute(
        text(f"INSERT INTO public.{t} ({', '.join(cols)}) VALUES ({', '.join(values)})"), params
    )


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
