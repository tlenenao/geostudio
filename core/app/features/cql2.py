# SPDX-License-Identifier: Apache-2.0
"""CQL2-text (OGC API Features Part 3) -> fragment SQL PARAMÉTRÉ (ARC-12).

Sous-ensemble : comparaisons, AND/OR/NOT, LIKE, IN, BETWEEN, IS NULL, CASEI,
littéraux DATE/TIMESTAMP, S_* (WKT, BBOX, GeoJSON) et T_BEFORE/AFTER/EQUALS/
DURING/INTERSECTS. Aucune interpolation : les valeurs sont des paramètres liés,
les noms de colonnes viennent du schéma introspecté (donc déjà amputé des
champs sensibles côté masqué) et sont quotés par `sql_ident`. Toute erreur de
syntaxe/type lève `FilterError(code="invalid_filter")` (-> 400)."""

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime

from shapely import wkt as shapely_wkt
from shapely.geometry import shape as shapely_shape
from sqlalchemy.orm import Session

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.repository import FilterError, _coerce, _int8, _property_columns
from app.sql_ident import quote_ident

MAX_FILTER_LEN = 100_000
MAX_DEPTH = 32
MAX_IN_ITEMS = 1000
_WKT_TYPES = {
    "POINT",
    "LINESTRING",
    "POLYGON",
    "MULTIPOINT",
    "MULTILINESTRING",
    "MULTIPOLYGON",
    "GEOMETRYCOLLECTION",
}
_SPATIAL = {
    "S_INTERSECTS": "ST_Intersects",
    "S_WITHIN": "ST_Within",
    "S_CONTAINS": "ST_Contains",
    "S_DISJOINT": "ST_Disjoint",
    "S_TOUCHES": "ST_Touches",
    "S_CROSSES": "ST_Crosses",
    "S_OVERLAPS": "ST_Overlaps",
    "S_EQUALS": "ST_Equals",
}
_CMP = {"=": "=", "<>": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
_TEMPORAL = {"T_BEFORE", "T_AFTER", "T_EQUALS", "T_DURING", "T_INTERSECTS"}
_TOKEN = re.compile(
    r"""\s*(?:
    (?P<str>'(?:[^']|'')*')
   |(?P<qid>"(?:[^"]|"")+")
   |(?P<num>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
   |(?P<id>[A-Za-z_][A-Za-z0-9_]*)
   |(?P<op><>|<=|>=|=|<|>)
   |(?P<p>[(),])
   |(?P<json>\{)
   )""",
    re.X,
)
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err(message: str) -> FilterError:
    return FilterError("filter", message, "invalid_filter")


@dataclass(frozen=True)
class _Tok:
    kind: str  # str qid num id op p json
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class _Op:
    """Opérande : propriété, littéral, ou CASEI(...) d'un opérande."""

    kind: str  # prop | str | num | bool | date | timestamp | casei
    value: object = None
    col: ColumnInfo | None = None
    inner: "_Op | None" = None

    @property
    def column(self) -> ColumnInfo | None:
        return self.col if self.kind == "prop" else self.inner.column if self.inner else None


def _tokenize(src: str) -> list[_Tok]:
    if len(src) > MAX_FILTER_LEN:
        raise _err("filter too long")
    toks, pos = [], 0
    while True:
        if not src[pos:].strip():
            return toks
        m = _TOKEN.match(src, pos)
        if m is None:
            raise _err(f"unexpected character near position {pos}")
        kind = m.lastgroup or ""
        if kind == "json":
            start = m.start("json")
            end = _json_end(src, start)
            toks.append(_Tok("json", src[start:end], start, end))
            pos = end
            continue
        raw = m.group(kind)
        toks.append(_Tok(kind, raw, m.start(kind), m.end(kind)))
        pos = m.end()


def _json_end(src: str, start: int) -> int:
    depth, i, in_str = 0, start, False
    while i < len(src):
        ch = src[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise _err("unterminated GeoJSON literal")


class _Compiler:
    def __init__(self, session: Session, info: TableInfo, src: str, srid: int):
        self.session, self.info, self.src, self.srid = session, info, src, srid
        self.toks = _tokenize(src)
        self.i = 0
        self.depth = 0
        self.params: dict = {}
        self.cols = {c.name: c for c in _property_columns(info)}
        self.cols.update({c.name: c for c in info.columns if c.name == info.pk_column})

    # --- jetons -----------------------------------------------------------
    def peek(self, k: int = 0) -> _Tok | None:
        return self.toks[self.i + k] if self.i + k < len(self.toks) else None

    def next(self) -> _Tok:
        t = self.peek()
        if t is None:
            raise _err("unexpected end of filter")
        self.i += 1
        return t

    def kw(self, *words: str) -> bool:
        """Consomme le(s) mot(s)-clés (insensible à la casse) s'ils suivent."""
        for k, w in enumerate(words):
            t = self.peek(k)
            if t is None or t.kind != "id" or t.value.upper() != w:
                return False
        self.i += len(words)
        return True

    def expect(self, value: str) -> None:
        t = self.next()
        if t.kind not in ("p", "op") or t.value != value:
            raise _err(f"expected '{value}'")

    def param(self, value) -> str:
        key = f"__c{len(self.params)}"
        self.params[key] = value
        return f":{key}"

    def q(self, name: str) -> str:
        return quote_ident(self.session, name)

    # --- grammaire booléenne ---------------------------------------------
    def compile(self) -> str:
        sql = self.or_expr()
        if self.peek() is not None:
            raise _err(f"unexpected token '{self.peek().value}'")  # type: ignore[union-attr]
        return sql

    def or_expr(self) -> str:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise _err("filter too deeply nested")
        parts = [self.and_expr()]
        while self.kw("OR"):
            parts.append(self.and_expr())
        self.depth -= 1
        return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"

    def and_expr(self) -> str:
        parts = [self.not_expr()]
        while self.kw("AND"):
            parts.append(self.not_expr())
        return parts[0] if len(parts) == 1 else "(" + " AND ".join(parts) + ")"

    def not_expr(self) -> str:
        if self.kw("NOT"):
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise _err("filter too deeply nested")
            inner = self.not_expr()
            self.depth -= 1
            return f"(NOT {inner})"
        return self.predicate()

    def predicate(self) -> str:
        t = self.peek()
        if t is None:
            raise _err("unexpected end of filter")
        if t.kind == "p" and t.value == "(":
            self.i += 1
            sql = self.or_expr()
            self.expect(")")
            return sql
        name = t.value.upper() if t.kind == "id" else ""
        nxt = self.peek(1)
        is_call = nxt is not None and nxt.kind == "p" and nxt.value == "("
        if name in _SPATIAL and is_call:
            self.i += 1
            return self.spatial(_SPATIAL[name])
        if name in _TEMPORAL and is_call:
            self.i += 1
            return self.temporal(name)
        if name in ("TRUE", "FALSE") and not (nxt and nxt.kind == "op"):
            self.i += 1
            return name
        left = self.operand()
        t = self.peek()
        if t is not None and t.kind == "op":
            self.i += 1
            right = self.operand()
            return self.compare(left, _CMP[t.value], right)
        negate = self.kw("NOT")
        if self.kw("LIKE"):
            sql = self.like(left)
        elif self.kw("IN"):
            sql = self.in_list(left)
        elif self.kw("BETWEEN"):
            sql = self.between(left)
        elif not negate and self.kw("IS"):
            neg = self.kw("NOT")
            if not self.kw("NULL"):
                raise _err("expected NULL")
            return f"{self.render(left, None)} IS {'NOT ' if neg else ''}NULL"
        elif not negate:
            if left.kind == "prop" and left.col and left.col.type == "boolean":
                return self.render(left, None)  # propriété booléenne seule
            raise _err("expected a comparison")
        else:
            raise _err("expected LIKE, IN or BETWEEN after NOT")
        return f"(NOT {sql})" if negate else sql

    # --- opérandes --------------------------------------------------------
    def prop(self, name: str) -> _Op:
        col = self.cols.get(name)
        if col is None:
            if name == self.info.geometry_column:
                raise _err("geometry property only allowed in S_* functions")
            raise _err(f"unknown property '{name}'")
        if col.type in ("unsupported", "list"):
            raise _err(f"property '{name}' not filterable")
        return _Op("prop", name, col)

    def string_arg(self, what: str) -> str:
        self.expect("(")
        t = self.next()
        if t.kind != "str":
            raise _err(f"{what} expects a string")
        self.expect(")")
        return t.value[1:-1].replace("''", "'")

    def operand(self) -> _Op:
        t = self.next()
        if t.kind == "str":
            return _Op("str", t.value[1:-1].replace("''", "'"))
        if t.kind == "num":
            v = float(t.value)
            if not math.isfinite(v):
                raise _err("invalid number")
            return _Op("num", int(t.value) if re.fullmatch(r"[+-]?\d+", t.value) else v)
        if t.kind == "qid":
            return self.prop(t.value[1:-1].replace('""', '"'))
        if t.kind != "id":
            raise _err(f"unexpected token '{t.value}'")
        up = t.value.upper()
        nxt = self.peek()
        is_call = nxt is not None and nxt.kind == "p" and nxt.value == "("
        if up in ("TRUE", "FALSE") and not is_call:
            return _Op("bool", up == "TRUE")
        if up == "DATE" and is_call:
            return self.date_lit(self.string_arg("DATE"), is_date=True)
        if up == "TIMESTAMP" and is_call:
            return self.date_lit(self.string_arg("TIMESTAMP"), is_date=False)
        if up == "CASEI" and is_call:
            self.expect("(")
            inner = self.operand()
            self.expect(")")
            return _Op("casei", inner=inner)
        if is_call:
            raise _err(f"unsupported function '{t.value}'")
        return self.prop(t.value)

    def date_lit(self, raw: str, *, is_date: bool) -> _Op:
        try:
            if is_date:
                return _Op("date", date.fromisoformat(raw))
            return _Op("timestamp", datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            raise _err(f"cannot parse '{raw}' as a date") from None

    def render(self, op: _Op, other: ColumnInfo | None) -> str:
        """SQL d'un opérande ; les littéraux sont liés selon le type de la colonne
        comparée (`other`) — même coercition que les filtres d'égalité classiques."""
        if op.kind == "prop":
            return self.q(op.value)  # type: ignore[arg-type]
        if op.kind == "casei":
            return f"lower({self.render(op.inner, other)})"  # type: ignore[arg-type]
        t = other.type if other else None
        if op.kind == "date":
            if t not in ("date", "datetime"):
                raise _err("date literal compared to a non-temporal property")
            return f"CAST({self.param(op.value)} AS date)"
        if op.kind == "timestamp":
            if t not in ("date", "datetime"):
                raise _err("timestamp literal compared to a non-temporal property")
            return f"CAST({self.param(op.value)} AS timestamptz)"
        if op.kind == "bool":
            if t != "boolean":
                raise _err("boolean literal compared to a non-boolean property")
            return self.param(op.value)
        if op.kind == "num":
            if t not in ("integer", "number"):
                raise _err("number compared to a non-numeric property")
            if isinstance(op.value, int):
                try:
                    _int8(str(op.value))
                except ValueError:
                    raise _err("integer out of range") from None
            return self.param(op.value)
        # chaîne : coercée selon la colonne (entier/nombre/booléen/date)
        s = str(op.value)
        try:
            if t in ("integer", "number", "boolean"):
                return self.param(_coerce(other, s))  # type: ignore[arg-type]
            if t == "date":
                return f"CAST({self.param(date.fromisoformat(s))} AS date)"
            if t == "datetime":
                parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return f"CAST({self.param(parsed)} AS timestamptz)"
        except (FilterError, ValueError):
            raise _err(f"cannot parse '{s}' as {t}") from None
        return self.param(s)

    # --- prédicats --------------------------------------------------------
    def compare(self, left: _Op, op: str, right: _Op) -> str:
        lc, rc = left.column, right.column
        if lc is None and rc is None:
            raise _err("comparison needs a property")
        return f"{self.render(left, rc)} {op} {self.render(right, lc)}"

    def like(self, left: _Op) -> str:
        col = left.column
        if col is None or col.type not in ("string", "enum"):
            raise _err("LIKE needs a text property")
        t = self.next()
        if t.kind != "str":
            raise _err("LIKE expects a string pattern")
        pattern = t.value[1:-1].replace("''", "'")
        return f"{self.render(left, None)} LIKE {self.param(pattern)}"

    def in_list(self, left: _Op) -> str:
        col = left.column
        if col is None:
            raise _err("IN needs a property")
        self.expect("(")
        items = [self.render(self.operand(), col)]
        while self.peek() is not None and self.peek().value == ",":  # type: ignore[union-attr]
            self.i += 1
            items.append(self.render(self.operand(), col))
            if len(items) > MAX_IN_ITEMS:
                raise _err("too many IN values")
        self.expect(")")
        return f"{self.render(left, None)} IN ({', '.join(items)})"

    def between(self, left: _Op) -> str:
        col = left.column
        if col is None:
            raise _err("BETWEEN needs a property")
        lo = self.render(self.operand(), col)
        if not self.kw("AND"):
            raise _err("expected AND in BETWEEN")
        hi = self.render(self.operand(), col)
        return f"{self.render(left, None)} BETWEEN {lo} AND {hi}"

    # --- spatial ----------------------------------------------------------
    def geom_arg(self) -> str:
        """SQL d'un argument géométrique : colonne géométrie ou littéral (WKT,
        BBOX, GeoJSON) validé en Python avant d'être lié."""
        t = self.next()
        target = self.info.srid or 4326
        if t.kind in ("id", "qid"):
            name = t.value[1:-1] if t.kind == "qid" else t.value
            up = t.value.upper()
            if up == "BBOX" and t.kind == "id":
                return self.bbox_lit(target)
            if up in _WKT_TYPES:
                return self.wkt_lit(t, target)
            if self.info.geometry_column and name in (self.info.geometry_column, "geometry"):
                return self.q(self.info.geometry_column)
            raise _err(f"'{name}' is not the geometry property")
        if t.kind == "json":
            try:
                obj = json.loads(t.value)
                if not isinstance(obj, dict) or "type" not in obj or "coordinates" not in obj:
                    raise ValueError("geometry")
                geom = shapely_shape(obj)
                if not geom.is_valid:
                    raise ValueError("invalid")
            except Exception:  # noqa: BLE001 - toute GeoJSON invalide = 400
                raise _err("invalid GeoJSON geometry") from None
            p = self.param(t.value)
            return f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON({p}), {self.srid}), {target})"
        raise _err("expected a geometry")

    def wkt_lit(self, first: _Tok, target: int) -> str:
        last = first
        while (t := self.peek()) is not None and t.kind == "id":  # Z / M / ZM / EMPTY
            self.i += 1
            last = t
        t = self.peek()
        if t is not None and t.value == "(":
            depth = 0
            while True:
                t = self.next()
                if t.kind not in ("num", "p"):
                    raise _err("invalid WKT")
                depth += (t.value == "(") - (t.value == ")")
                last = t
                if depth == 0:
                    break
        text_ = self.src[first.start : last.end]
        try:
            geom = shapely_wkt.loads(text_)
            if not geom.is_valid:
                raise ValueError("invalid")
        except Exception:  # noqa: BLE001 - tout WKT invalide = 400
            raise _err("invalid WKT geometry") from None
        return f"ST_Transform(ST_GeomFromText({self.param(text_)}, {self.srid}), {target})"

    def bbox_lit(self, target: int) -> str:
        self.expect("(")
        nums = []
        while True:
            t = self.next()
            if t.kind != "num":
                raise _err("BBOX expects numbers")
            nums.append(float(t.value))
            sep = self.next()
            if sep.value == ")":
                break
            if sep.value != ",":
                raise _err("BBOX expects comma-separated numbers")
        if len(nums) != 4 or not all(math.isfinite(n) for n in nums):
            raise _err("BBOX expects 4 numbers")
        ps = ", ".join(self.param(n) for n in nums)
        return f"ST_Transform(ST_MakeEnvelope({ps}, {self.srid}), {target})"

    def spatial(self, fn: str) -> str:
        if self.info.geometry_column is None:
            raise _err("collection has no geometry")
        self.expect("(")
        a = self.geom_arg()
        self.expect(",")
        b = self.geom_arg()
        self.expect(")")
        g = self.q(self.info.geometry_column)
        if (a == g) == (b == g):
            raise _err("spatial function needs exactly one geometry property")
        return f"{fn}({a}, {b})"

    # --- temporel ---------------------------------------------------------
    def instant(self, col: ColumnInfo) -> str:
        op = self.operand()
        if op.kind not in ("str", "date", "timestamp"):
            raise _err("expected an instant")
        return self.render(op, col)

    def temporal(self, name: str) -> str:
        self.expect("(")
        left = self.operand()
        col = left.column
        if left.kind != "prop" or col is None or col.type not in ("date", "datetime"):
            raise _err(f"{name} needs a temporal property")
        self.expect(",")
        ident = self.render(left, None)
        if name in ("T_DURING", "T_INTERSECTS") and self.kw("INTERVAL"):
            self.expect("(")
            bounds = []
            for k in range(2):
                t = self.peek()
                if t is not None and t.kind == "str" and t.value == "'..'":
                    self.i += 1
                    bounds.append(None)
                else:
                    bounds.append(self.instant(col))
                self.expect("," if k == 0 else ")")
            clauses = [f"{ident} {o} {b}" for o, b in zip((">=", "<="), bounds, strict=True) if b]
            sql = " AND ".join(clauses) or f"{ident} IS NOT NULL"
        else:
            op = {"T_BEFORE": "<", "T_AFTER": ">"}.get(name, "=")
            sql = f"{ident} {op} {self.instant(col)}"
        self.expect(")")
        return f"({sql})"


def compile_cql2(
    session: Session, info: TableInfo, expression: str, *, srid: int = 4326
) -> tuple[str, dict]:
    """(fragment SQL, paramètres liés). `srid` = CRS des géométries littérales."""
    if not expression.strip():
        raise _err("empty filter")
    c = _Compiler(session, info, expression, srid)
    return c.compile(), c.params
