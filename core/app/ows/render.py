# SPDX-License-Identifier: Apache-2.0
"""Rasterisation PNG de features GeoJSON selon un `Style` (ARC-20, ADR 0020).

Pur calcul : reçoit des features DÉJÀ lues par la porte de lecture (RLS, masquage,
limites géographiques) et ne touche jamais la base. Les géométries arrivent déjà
dans le CRS de la requête (`out_srid`), la projection vers le pixel est donc affine.
Pillow (HPND), pas d'antialiasing : sous-ensemble assumé (un trait de 256 px < 300 ms)."""

import io

from PIL import Image, ImageDraw

from app.styles.model import Rule, Style, select_rule

MAX_DIM = 2048  # côté max (px) et surface max d'une image : anti-DoS
MAX_PIXELS = 4_000_000
_CLAMP = 1e6  # coordonnées pixel bornées (une géométrie énorme ne doit pas déborder Pillow)


def _rgba(hexcolor: str, alpha: float) -> tuple[int, int, int, int]:
    n = int(hexcolor[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255, round(min(max(alpha, 0.0), 1.0) * 255)


class _Canvas:
    def __init__(self, bbox, width: int, height: int):
        self.minx, self.miny, self.maxx, self.maxy = bbox
        self.w, self.h = width, height
        self.kx = width / (self.maxx - self.minx)
        self.ky = height / (self.maxy - self.miny)
        self.img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)

    def px(self, coords) -> list[tuple[float, float]]:
        out = []
        for c in coords:
            x = (c[0] - self.minx) * self.kx
            y = (self.maxy - c[1]) * self.ky
            out.append((min(max(x, -_CLAMP), _CLAMP), min(max(y, -_CLAMP), _CLAMP)))
        return out

    def _polygon(self, rings: list, rule: Rule) -> None:
        pts = [self.px(r) for r in rings if len(r) >= 3]
        if not pts:
            return
        fill = _rgba(rule.fill, rule.fill_opacity)
        ext = pts[0]
        xs, ys = [p[0] for p in ext], [p[1] for p in ext]
        if max(xs) < 0 or min(xs) > self.w or max(ys) < 0 or min(ys) > self.h:
            return
        if len(pts) == 1:
            self.draw.polygon(ext, fill=fill)
        else:  # trous : masque binaire limité à l'emprise (bornée à l'image) de l'extérieur
            x0, y0 = max(int(min(xs)), 0), max(int(min(ys)), 0)
            x1, y1 = min(int(max(xs)) + 1, self.w), min(int(max(ys)) + 1, self.h)
            mask = Image.new("L", (max(x1 - x0, 1), max(y1 - y0, 1)), 0)
            md = ImageDraw.Draw(mask)
            for i, ring in enumerate(pts):
                md.polygon([(x - x0, y - y0) for x, y in ring], fill=255 if i == 0 else 0)
            self.img.paste(Image.new("RGBA", mask.size, fill), (x0, y0), mask)
        if rule.stroke and rule.stroke_width > 0:
            sc = _rgba(rule.stroke, 1.0)
            for ring in pts:
                self.draw.line([*ring, ring[0]], fill=sc, width=max(round(rule.stroke_width), 1))

    def _line(self, coords: list, rule: Rule) -> None:
        if len(coords) >= 2:
            self.draw.line(
                self.px(coords),
                fill=_rgba(rule.fill, rule.fill_opacity),
                width=max(round(rule.stroke_width), 1),
                joint="curve",
            )

    def _point(self, c: list, rule: Rule) -> None:
        (x, y), r = self.px([c])[0], rule.radius
        if -r <= x <= self.w + r and -r <= y <= self.h + r:
            self.draw.ellipse(
                (x - r, y - r, x + r, y + r),
                fill=_rgba(rule.fill, rule.fill_opacity),
                outline=_rgba(rule.stroke, 1.0) if rule.stroke else None,
                width=max(round(rule.stroke_width), 1),
            )

    def geometry(self, geom: dict, rule: Rule) -> None:
        t, c = geom.get("type"), geom.get("coordinates")
        if t == "Point":
            self._point(c, rule)
        elif t == "MultiPoint":
            for p in c:
                self._point(p, rule)
        elif t == "LineString":
            self._line(c, rule)
        elif t == "MultiLineString":
            for ln in c:
                self._line(ln, rule)
        elif t == "Polygon":
            self._polygon(c, rule)
        elif t == "MultiPolygon":
            for poly in c:
                self._polygon(poly, rule)


def draw_features(canvas: _Canvas, features: list[dict], style: Style) -> None:
    for f in features:
        g = f.get("geometry")
        if not g:
            continue
        rule = select_rule(style, f.get("properties") or {})
        if rule is not None:
            canvas.geometry(g, rule)


def new_canvas(bbox, width: int, height: int) -> _Canvas:
    return _Canvas(bbox, width, height)


def to_png(canvas: _Canvas, bgcolor: tuple[int, int, int] | None) -> bytes:
    """`bgcolor` None = fond transparent (TRANSPARENT=TRUE)."""
    img = canvas.img
    if bgcolor is not None:
        img = Image.alpha_composite(Image.new("RGBA", img.size, (*bgcolor, 255)), img).convert(
            "RGB"
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


LEGEND_ROW = 20
LEGEND_WIDTH = 200
LEGEND_MAX_ROWS = 100


def legend_png(style: Style) -> bytes:
    """Une ligne de 20 px par règle : pastille selon la géométrie + titre (AUD-045)."""
    rules = style.rules[:LEGEND_MAX_ROWS]
    img = Image.new("RGBA", (LEGEND_WIDTH, LEGEND_ROW * max(len(rules), 1)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, rule in enumerate(rules):
        y = i * LEGEND_ROW
        fill = _rgba(rule.fill, rule.fill_opacity)
        if style.geometry_kind == "point":
            draw.ellipse((4, y + 4, 16, y + 16), fill=fill)
        elif style.geometry_kind == "line":
            line = _rgba(rule.stroke or rule.fill, 1.0)
            draw.line((2, y + 10, 18, y + 10), fill=line, width=max(int(rule.stroke_width), 1))
        else:
            draw.rectangle((2, y + 3, 18, y + 17), fill=fill)
        # police bitmap par défaut de Pillow : latin-1 seulement
        label = rule.title.encode("latin-1", "replace").decode("latin-1")
        draw.text((24, y + 4), label, fill=(0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
