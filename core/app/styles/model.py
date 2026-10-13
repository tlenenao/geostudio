# SPDX-License-Identifier: Apache-2.0
"""Style déclaratif -> règles plates (ARC-28, ADR 0020).

`LayerSymbology` (JSON du shell, `shell/src/builder/widgets/mapSymbology.ts`) est
projeté sur une liste de règles `Rule` (filtre + symbole, couleurs RÉSOLUES) :
représentation intermédiaire commune à l'export SLD et au renderer WMS/WMTS.
Entrée non fiable (corps de requête ou config d'item) : tout est validé ici,
une valeur invalide retombe sur le défaut au lieu de lever. Sous-ensemble assumé :
les modes avancés (bivarié, densité de points…), icônes, étiquettes et effets ne
sont pas rendus côté serveur. Une rampe continue est discrétisée en `RAMP_CLASSES`
classes (SLD 1.1 sait interpoler, mais pas le renderer raster)."""

import re
from dataclasses import dataclass
from typing import Any, Literal

GeometryKind = Literal["point", "line", "polygon"]

DEFAULT_COLOR = "#3b82f6"  # gs-raw-color-ok: couleur de repli d'un style sans encodage
DEFAULT_STROKE = "#1e3a8a"  # gs-raw-color-ok: contour par défaut des polygones
RAMP_CLASSES = 7
MAX_CLASSES = 200  # bornes anti-DoS : taille du SLD / nombre de règles évaluées par entité
RADIUS_MIN, RADIUS_MAX = 4.0, 24.0
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Miroir de shell/src/builder/widgets/palette.ts (pin dans tests/test_styles.py).
# `theme-primary` dépend du thème de l'app : repli sur sequential-blue côté serveur.
# gs-raw-color-ok-begin: palettes curatées
CATEGORICAL = {
    "categorical-a": [
        "#2563eb",
        "#dc2626",
        "#16a34a",
        "#d97706",
        "#7c3aed",
        "#0891b2",
        "#db2777",
        "#65a30d",
    ],
    "categorical-b": [
        "#0f766e",
        "#b45309",
        "#4338ca",
        "#be123c",
        "#3f6212",
        "#a21caf",
        "#0369a1",
        "#854d0e",
    ],
}
SEQUENTIAL = {
    "sequential-blue": ("#dbeafe", "#1e3a8a"),
    "sequential-warm": ("#fef3c7", "#7c2d12"),
}
# gs-raw-color-ok-end


@dataclass(frozen=True)
class Rule:
    title: str
    # None = toujours ; ("eq", champ, texte) ; ("range", champ, lo|None, hi|None) avec
    # lo <= v < hi ; ("else",) = repli (règle terminale, SLD ElseFilter).
    test: tuple | None
    fill: str
    fill_opacity: float
    stroke: str | None
    stroke_width: float
    dash: tuple[float, ...] | None
    radius: float


@dataclass(frozen=True)
class Style:
    geometry_kind: GeometryKind
    rules: tuple[Rule, ...]


def _color(v: Any, default: str) -> str:
    return v if isinstance(v, str) and _HEX.match(v) else default


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return float(v) if v == v and abs(v) != float("inf") else None


def _lerp(low: str, high: str, t: float) -> str:
    a, b = int(low[1:], 16), int(high[1:], 16)
    ch = [round(((a >> s) & 255) + (((b >> s) & 255) - ((a >> s) & 255)) * t) for s in (16, 8, 0)]
    return "#{:02x}{:02x}{:02x}".format(*ch)


def _ramp(palette: str, n: int) -> list[str]:
    if palette in CATEGORICAL:
        cols = CATEGORICAL[palette]
        return [cols[i % len(cols)] for i in range(n)]
    low, high = SEQUENTIAL.get(palette, SEQUENTIAL["sequential-blue"])
    return [low] if n == 1 else [_lerp(low, high, i / (n - 1)) for i in range(n)]


def _fmt(v: float) -> str:
    return f"{v:g}"


def _range_rules(field: str, edges: list[float]) -> list[tuple[str, tuple]]:
    """Classes [edges[i], edges[i+1][ ; première/dernière ouvertes (sémantique `step`)."""
    n = len(edges) - 1
    return [
        (
            f"{_fmt(edges[i])} - {_fmt(edges[i + 1])}",
            ("range", field, None if i == 0 else edges[i], None if i == n - 1 else edges[i + 1]),
        )
        for i in range(n)
    ]


def _color_classes(color: dict) -> list[tuple[str, tuple, str]]:
    """[(titre, test, couleur)] d'un encodage couleur classé ; [] si inutilisable
    (mêmes garde-fous que `normalizeDomain` côté shell : domaine vide/dégénéré)."""
    field = color.get("field")
    domain = color.get("domain")
    palette = color.get("palette")
    palette = palette if isinstance(palette, str) else "categorical-a"
    if not isinstance(field, str) or not field or not isinstance(domain, dict):
        return []
    kind = domain.get("kind")
    if kind == "categorical":
        raw = domain.get("values")
        values = (
            [str(v) for v in raw if isinstance(v, str | int | float)]
            if isinstance(raw, list)
            else []
        )
        values = values[:MAX_CLASSES]
        if not values:
            return []
        cols = _ramp(palette if palette in CATEGORICAL else "categorical-a", len(values))
        out = [(v, ("eq", field, v), cols[i]) for i, v in enumerate(values)]
        return [*out, ("autres", ("else",), cols[0])]  # MapLibre `match` : défaut = 1re couleur
    if kind == "numeric-classed":
        raw = domain.get("breaks")
        nums = [_num(b) for b in raw] if isinstance(raw, list) else []
        if len(nums) < 3 or len(nums) > MAX_CLASSES + 1 or any(b is None for b in nums):
            return []
        breaks = [b for b in nums if b is not None]
        if any(b2 <= b1 for b1, b2 in zip(breaks, breaks[1:], strict=False)):
            return []
        cols = _ramp(palette, len(breaks) - 1)
        return [(t, f, cols[i]) for i, (t, f) in enumerate(_range_rules(field, breaks))]
    if kind == "numeric":
        lo, hi = _num(domain.get("min")), _num(domain.get("max"))
        if lo is None or hi is None or hi <= lo:
            return []
        edges = [lo + (hi - lo) * i / RAMP_CLASSES for i in range(RAMP_CLASSES + 1)]
        cols = _ramp(palette if palette in SEQUENTIAL else "sequential-blue", RAMP_CLASSES)
        return [(t, f, cols[i]) for i, (t, f) in enumerate(_range_rules(field, edges))]
    return []


def style_from_symbology(symbology: Any, geometry_kind: GeometryKind) -> Style:
    sym = symbology if isinstance(symbology, dict) else {}
    opacity = _num(sym.get("opacity"))
    alpha = min(max(opacity / 100, 0.0), 1.0) if opacity is not None else None
    fill_alpha = alpha if alpha is not None else (0.6 if geometry_kind == "polygon" else 1.0)

    stroke_color: str | None = DEFAULT_STROKE if geometry_kind == "polygon" else None
    stroke_width, dash = (2.0 if geometry_kind == "line" else 1.0), None
    stroke = sym.get("stroke")
    if isinstance(stroke, dict) and geometry_kind != "line":
        c = stroke.get("color")
        if isinstance(c, dict) and "fixed" in c:  # contour piloté par un champ : non rendu
            stroke_color = _color(c["fixed"], DEFAULT_STROKE)
        w = stroke.get("width")
        wv = _num(w.get("fixed")) if isinstance(w, dict) else None
        if wv is not None:
            stroke_width = min(max(wv, 0.0), 20.0)
        dash = {"dashed": (2.0, 2.0), "dotted": (1.0, 2.0)}.get(str(stroke.get("style")))

    def rule(title: str, test: tuple | None, fill: str, radius: float = 6.0) -> Rule:
        return Rule(title, test, fill, fill_alpha, stroke_color, stroke_width, dash, radius)

    color = sym.get("color")
    classes = _color_classes(color) if isinstance(color, dict) else []
    if classes:
        return Style(geometry_kind, tuple(rule(t, f, c) for t, f, c in classes))

    size = sym.get("size")
    if geometry_kind == "point" and isinstance(size, dict):
        field, dom = size.get("field"), size.get("domain")
        lo = _num(dom.get("min")) if isinstance(dom, dict) else None
        hi = _num(dom.get("max")) if isinstance(dom, dict) else None
        if isinstance(field, str) and field and lo is not None and hi is not None and hi > lo:
            edges = [lo + (hi - lo) * i / 5 for i in range(6)]
            return Style(
                geometry_kind,
                tuple(
                    rule(
                        t, f, DEFAULT_COLOR, RADIUS_MIN + (RADIUS_MAX - RADIUS_MIN) * (i + 0.5) / 5
                    )
                    for i, (t, f) in enumerate(_range_rules(field, edges))
                ),
            )
    return Style(geometry_kind, (rule("default", None, DEFAULT_COLOR),))


def default_style(geometry_kind: GeometryKind) -> Style:
    return style_from_symbology(None, geometry_kind)


def kind_of_geometry_type(geometry_type: str | None) -> GeometryKind:
    t = (geometry_type or "").upper()
    if "POINT" in t:
        return "point"
    if "LINE" in t:
        return "line"
    return "polygon"


def _rule_matches(rule: Rule, props: dict) -> bool:
    t = rule.test
    if t is None:
        return True
    if t[0] == "eq":
        v = props.get(t[1])
        if v is None:
            return False
        return (str(v).lower() if isinstance(v, bool) else str(v)) == t[2]
    if t[0] == "range":
        v = _num(props.get(t[1]))
        return v is not None and (t[2] is None or v >= t[2]) and (t[3] is None or v < t[3])
    return False  # "else" : géré par select_rule


def select_rule(style: Style, props: dict) -> Rule | None:
    """Première règle satisfaite ; sinon la règle `else`."""
    fallback = None
    for r in style.rules:
        if r.test and r.test[0] == "else":
            fallback = r
        elif _rule_matches(r, props):
            return r
    return fallback
