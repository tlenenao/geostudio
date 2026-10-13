# SPDX-License-Identifier: Apache-2.0
"""Import XLSForm (ARC-27) : classeur `survey`/`choices`/`settings` -> plan de collecte.

Fichier NON fiable : bornes de taille décompressée, de feuilles, de lignes, de colonnes et de
longueur de cellule ; `data_only=True` (jamais de formule évaluée) ; XML lu par openpyxl, qui
délègue à `defusedxml` (installé : pas de XXE). Rien n'est perdu en silence : tout élément non
porté (ou approximé) figure dans `report`."""

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.cell_safety import unsanitize_cell
from app.collections.domains import cel_syntax_error

MAX_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED = 30 * 1024 * 1024
MAX_SHEETS = 20
MAX_SURVEY_ROWS = 1000
MAX_CHOICE_ROWS = 10_000
MAX_COLUMNS = 60
MAX_CELL = 2000
_MAX_NAME = 59


class XlsFormError(Exception):
    """Classeur inexploitable (message affichable tel quel)."""


@dataclass
class ReportItem:
    code: str  # not_ported | approximated | renamed | ignored
    message: str
    row: int | None = None
    name: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "row": self.row, "name": self.name}


@dataclass
class XlsFormPlan:
    title: str
    columns: list[dict] = field(default_factory=list)  # {name, sqlType}
    geometry_type: str | None = None
    attachment_fields: list[dict] = field(default_factory=list)  # {key, label}
    field_domains: dict[str, dict] = field(default_factory=dict)
    attribute_rules: list[dict] = field(default_factory=list)
    form_fields: list[dict] = field(default_factory=list)
    report: list[ReportItem] = field(default_factory=list)


_SQL = {
    "text": ("text", "string"),
    "integer": ("integer", "integer"),
    "int": ("integer", "integer"),
    "decimal": ("double precision", "number"),
    "date": ("date", "date"),
    "datetime": ("timestamptz", "datetime"),
    "acknowledge": ("boolean", "boolean"),
    "barcode": ("text", "string"),
    "time": ("text", "string"),
}
_APPROX = {
    "time": "heure stockée comme texte",
    "barcode": "code-barres saisi comme texte",
}
_GEO = {"geopoint": "Point", "geotrace": "LineString", "geoshape": "Polygon"}
_FILES = {"image", "photo", "audio", "video", "file"}
_METADATA = {
    "start",
    "end",
    "today",
    "deviceid",
    "subscriberid",
    "simserial",
    "phonenumber",
    "username",
    "email",
    "audit",
}
_RESERVED = {"id", "tenant_id", "geom"}
_UNSUPPORTED_COLS = (
    "default",
    "appearance",
    "choice_filter",
    "read_only",
    "repeat_count",
    "parameters",
)


# ------------------------------------------------------------------ conversion XPath -> CEL

_TOKEN = re.compile(
    r"""
    (?P<str>'[^']*'|"[^"]*")
  | (?P<ref>\$\{[^}]+\})
  | (?P<word>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<dot>(?<![\w.])\.(?![\w.]))
  | (?P<op>!=|<=|>=|=|<|>|\(|\)|,|\+|-|\*)
  | (?P<ws>\s+)
    """,
    re.VERBOSE,
)


class _Unsupported(Exception):
    pass


def to_cel(expr: str, names: dict[str, str], *, current: str | None = None) -> str:
    """Traduit le sous-ensemble utile d'une expression XPath XLSForm en CEL (champs = noms de
    colonnes). Lève _Unsupported pour tout le reste : jamais d'approximation silencieuse."""
    out: list[str] = []
    pos = 0
    toks: list[tuple[str, str]] = []
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise _Unsupported(f"caractère non pris en charge : {expr[pos]!r}")
        pos = m.end()
        if m.lastgroup != "ws":
            toks.append((m.lastgroup or "", m.group()))
    i = 0
    while i < len(toks):
        kind, tok = toks[i]
        nxt = toks[i + 1][1] if i + 1 < len(toks) else ""
        if kind == "ref":
            name = tok[2:-1].strip()
            if name not in names:
                raise _Unsupported(f"champ inconnu : {name}")
            out.append(names[name])
        elif kind == "dot":
            if current is None:
                raise _Unsupported("'.' hors contrainte")
            out.append(current)
        elif kind == "word":
            low = tok.lower()
            if low in ("and", "or"):
                out.append("&&" if low == "and" else "||")
            elif low == "not" and nxt == "(":
                out.append("!")
            elif low in ("true", "false") and nxt == "(":
                # true() / false() : on saute le couple de parenthèses
                if toks[i + 2][1] != ")":
                    raise _Unsupported(f"{tok}() avec arguments")
                out.append(low)
                i += 2
            elif low == "selected" and nxt == "(":
                # selected(${f}, 'v') ; valide seulement pour select_one (valeur unique)
                try:
                    ref, comma, lit, close = (toks[i + 2], toks[i + 3], toks[i + 4], toks[i + 5])
                except IndexError as exc:
                    raise _Unsupported("selected() mal formé") from exc
                if ref[0] != "ref" or comma[1] != "," or lit[0] != "str" or close[1] != ")":
                    raise _Unsupported("selected() mal formé")
                name = ref[1][2:-1].strip()
                if name not in names:
                    raise _Unsupported(f"champ inconnu : {name}")
                out.append(f"({names[name]} == {lit[1]})")
                i += 5
            elif low == "mod":
                out.append("%")
            elif low == "div":
                raise _Unsupported("opérateur div")
            elif nxt == "(":
                raise _Unsupported(f"fonction {tok}()")
            else:
                raise _Unsupported(f"mot non pris en charge : {tok}")
        elif kind == "op":
            out.append("==" if tok == "=" else tok)
        else:  # str, num
            out.append(tok)
        i += 1
    cel = " ".join(out).replace("! (", "!(").replace("( ", "(").replace(" )", ")")
    if not cel.strip():
        raise _Unsupported("expression vide")
    if err := cel_syntax_error(cel):
        raise _Unsupported(f"CEL invalide ({err})")
    return cel


# ------------------------------------------------------------------ lecture du classeur


def _cell(value: Any, row: int, col: str) -> str:
    if value is None:
        return ""
    s = str(unsanitize_cell(value) if isinstance(value, str) else value).strip()
    if len(s) > MAX_CELL:
        raise XlsFormError(f"cellule trop longue (ligne {row}, colonne {col})")
    return s


def _read_sheet(wb, name: str, max_rows: int) -> list[tuple[int, dict[str, str]]]:
    if name not in wb.sheetnames:
        return []
    rows = wb[name].iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return []
    cols = [str(h).strip().lower() if h is not None else "" for h in header[:MAX_COLUMNS]]
    if len(header) > MAX_COLUMNS and any(h is not None for h in header[MAX_COLUMNS:]):
        raise XlsFormError(f"feuille {name} : plus de {MAX_COLUMNS} colonnes")
    out: list[tuple[int, dict[str, str]]] = []
    for idx, raw in enumerate(rows, start=2):
        if idx - 1 > max_rows:
            raise XlsFormError(f"feuille {name} : plus de {max_rows} lignes")
        rec = {c: _cell(v, idx, c) for c, v in zip(cols, raw, strict=False) if c}
        if any(rec.values()):
            out.append((idx, rec))
    return out


def _label(rec: dict[str, str]) -> str:
    if rec.get("label"):
        return rec["label"]
    for k, v in rec.items():
        if k.startswith("label::") and v:
            return v
    return ""


def _sanitize_name(raw: str) -> str:
    n = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if not n or n[0].isdigit():
        n = "q_" + n
    if n in _RESERVED:
        n += "_q"
    return n[:_MAX_NAME]


def _truthy(v: str) -> bool:
    return v.strip().lower() in {"yes", "true", "true()", "1"}


def parse_xlsform(content: bytes) -> XlsFormPlan:
    if len(content) > MAX_BYTES:
        raise XlsFormError("fichier trop volumineux")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
                raise XlsFormError("classeur trop volumineux une fois décompressé")
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError) as exc:
        raise XlsFormError("fichier XLSX illisible") from exc
    if len(wb.sheetnames) > MAX_SHEETS:
        raise XlsFormError(f"plus de {MAX_SHEETS} feuilles")
    if "survey" not in wb.sheetnames:
        raise XlsFormError("feuille « survey » absente : ce n'est pas un XLSForm")

    survey = _read_sheet(wb, "survey", MAX_SURVEY_ROWS)
    choices_rows = _read_sheet(wb, "choices", MAX_CHOICE_ROWS)
    settings = _read_sheet(wb, "settings", 5)
    choices: dict[str, list[str]] = {}
    for _, c in choices_rows:
        if c.get("list_name") and c.get("name"):
            choices.setdefault(c["list_name"], []).append(c["name"])

    title = (settings[0][1].get("form_title") if settings else "") or "Formulaire XLSForm"
    plan = XlsFormPlan(title=title)
    rep = plan.report

    # 1re passe : noms de colonnes finaux (les expressions y font référence).
    names: dict[str, str] = {}
    used: set[str] = set()
    for _, q in survey:
        raw = q.get("name", "")
        typ = q.get("type", "").split(" ")[0].lower()
        if raw and typ not in ("end", "end_group", "end_repeat", "begin", "note", "calculate"):
            n = _sanitize_name(raw)
            base, k = n, 2
            while n in used:
                n = f"{base[: _MAX_NAME - 3]}_{k}"
                k += 1
            used.add(n)
            names[raw] = n

    depth_repeat = 0
    order = 0
    for row, q in survey:
        parts = q.get("type", "").split()
        typ = parts[0].lower() if parts else ""
        raw = q.get("name", "")
        if typ in ("begin_repeat", "begin repeat"):
            depth_repeat += 1
            rep.append(ReportItem("not_ported", "répétition (repeat) non portée", row, raw))
            continue
        if typ in ("end_repeat", "end repeat"):
            depth_repeat = max(0, depth_repeat - 1)
            continue
        if depth_repeat:
            rep.append(
                ReportItem("not_ported", "question dans une répétition non portée", row, raw)
            )
            continue
        if typ in ("begin_group", "begin group"):
            rep.append(ReportItem("approximated", "groupe aplati (ordre conservé)", row, raw))
            continue
        if typ in ("end_group", "end group", ""):
            continue
        if typ in _METADATA:
            rep.append(ReportItem("ignored", f"métadonnée {typ} non portée", row, raw))
            continue
        if typ == "note":
            rep.append(ReportItem("not_ported", "note (affichage seul) non portée", row, raw))
            continue
        if typ == "calculate":
            rep.append(ReportItem("not_ported", "calculate non porté", row, raw))
            continue
        if not raw or raw not in names:
            rep.append(ReportItem("not_ported", "question sans nom", row, raw or None))
            continue
        name = names[raw]
        if name != raw:
            rep.append(ReportItem("renamed", f"renommé en {name}", row, raw))
        label = _label(q) or raw
        for k in q:
            if k.startswith("label::") and q[k] and q.get("label"):
                rep.append(ReportItem("ignored", f"traduction {k} ignorée", row, raw))
        for c in _UNSUPPORTED_COLS:
            if q.get(c):
                rep.append(ReportItem("not_ported", f"colonne {c} non portée", row, raw))

        entry: dict[str, Any] = {
            "name": name,
            "label": label,
            "order": order,
            "hidden": False,
            "required": _truthy(q.get("required", "")),
        }
        if q.get("hint"):
            entry["hint"] = q["hint"]

        if typ in _GEO:
            if plan.geometry_type is None:
                plan.geometry_type = _GEO[typ]
                if q.get("required") and _truthy(q["required"]):
                    rep.append(
                        ReportItem("approximated", "géométrie requise non imposée", row, raw)
                    )
            else:
                rep.append(
                    ReportItem("not_ported", "2e géométrie : une seule par collection", row, raw)
                )
            order += 1
            continue
        if typ in _FILES:
            plan.attachment_fields.append({"key": name, "label": label})
            entry["type"] = "attachment"
        elif typ in ("select_one", "select_multiple", "rank"):
            lst = parts[1] if len(parts) > 1 else ""
            values = choices.get(lst)
            if not values:
                rep.append(
                    ReportItem("not_ported", f"liste de choix {lst!r} absente ou vide", row, raw)
                )
                continue
            if typ == "select_one":
                plan.columns.append({"name": name, "sqlType": "text"})
                plan.field_domains[name] = {"type": "list", "values": values}
                entry["type"] = "string"
            else:
                plan.columns.append({"name": name, "sqlType": "text"})
                entry["type"] = "string"
                rep.append(
                    ReportItem(
                        "approximated",
                        "choix multiple saisi comme texte libre (valeurs séparées par un espace)",
                        row,
                        raw,
                    )
                )
        elif typ in _SQL:
            sql, ftype = _SQL[typ]
            plan.columns.append({"name": name, "sqlType": sql})
            entry["type"] = ftype
            if typ in _APPROX:
                rep.append(ReportItem("approximated", _APPROX[typ], row, raw))
        else:
            rep.append(ReportItem("not_ported", f"type {typ!r} non pris en charge", row, raw))
            continue

        if q.get("relevant"):
            try:
                entry["visibleWhen"] = to_cel(q["relevant"], names)
            except _Unsupported as exc:
                rep.append(ReportItem("not_ported", f"relevant non porté ({exc})", row, raw))
        if q.get("constraint") and entry["type"] != "attachment":
            try:
                expr = to_cel(q["constraint"], names, current=name)
                plan.attribute_rules.append(
                    {
                        "id": f"xf-{len(plan.attribute_rules) + 1}-{name.lower()}"[:64],
                        "kind": "constraint",
                        "field": name,
                        "expression": expr,
                        "message": q.get("constraint_message") or "Valeur invalide",
                    }
                )
            except _Unsupported as exc:
                rep.append(ReportItem("not_ported", f"constraint non portée ({exc})", row, raw))
        plan.form_fields.append(entry)
        order += 1

    if not plan.form_fields and plan.geometry_type is None:
        raise XlsFormError("aucune question exploitable dans la feuille survey")
    return plan
