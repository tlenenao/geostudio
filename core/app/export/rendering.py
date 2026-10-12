# SPDX-License-Identifier: Apache-2.0
"""Fonction de rendu pure (SP-17a) : ne connaît rien de Playwright, de S3 ni
de la navigation — prend une page déjà navigée/prête et produit des octets.
Testable avec un faux `page` (Protocol), le lancement du vrai navigateur
Chromium vit dans app.export.jobs (tâche 6), seul endroit qui a besoin d'un
Playwright réel installé."""

import base64
from typing import Literal, Protocol

from app.configs.schemas import PrintLayout

# Budget total d'un rendu (navigation + prêt + capture) — ARC-16.
RENDER_TIMEOUT_MS = 120_000

# Pixels CSS (96 dpi) d'une page portrait : A4 = 210x297 mm, A3 = 297x420 mm.
_PAGE_PX = {"a4": (794, 1123), "a3": (1123, 1587)}


def page_pixels(layout: PrintLayout | None) -> tuple[int, int]:
    """Taille (largeur, hauteur) de la page en pixels CSS, orientation incluse :
    le worker y cale le viewport pour que la mise en page du shell remplisse
    exactement la feuille."""
    layout = layout or PrintLayout()
    w, h = _PAGE_PX[layout.pageSize]
    return (h, w) if layout.orientation == "landscape" else (w, h)


class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(
        self,
        *,
        format: str,
        landscape: bool,
        print_background: bool,
        display_header_footer: bool,
        footer_template: str,
    ) -> bytes: ...


_FOOTER_TEMPLATE = (
    '<div style="font-size:8px; width:100%; text-align:center; color:#666;">'
    'Généré le <span class="date"></span></div>'
)


def render_export(
    page: RenderPage,
    *,
    format: Literal["png", "pdf", "svg"],
    print_layout: PrintLayout | None,
) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    if format == "svg":
        # ponytail : SVG « enveloppe » — la capture raster de la page insérée
        # dans un <svg> aux dimensions de la feuille (Chromium n'exporte pas de
        # SVG vectoriel d'une page HTML/WebGL). Un SVG vectoriel exigerait un
        # rendu cartographique côté serveur (cf. ARC-20/ARC-28).
        w, h = page_pixels(print_layout)
        b64 = base64.b64encode(page.screenshot(full_page=True)).decode("ascii")
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<image width="{w}" height="{h}" xlink:href="data:image/png;base64,{b64}"/></svg>'
        )
        return svg.encode("utf-8")
    layout = print_layout or PrintLayout()
    return page.pdf(
        format=layout.pageSize.upper(),
        landscape=layout.orientation == "landscape",
        print_background=True,
        # display_header_footer/footer_template (SP-17b) : seul morceau
        # d'"en-tête/pied" retenu dans le périmètre resserré du design — pas
        # de numérotation de section, une seule page source par export.
        # <span class="date"> est une classe Chromium native, remplie
        # automatiquement à la date du rendu — rien à calculer côté Python.
        display_header_footer=True,
        footer_template=_FOOTER_TEMPLATE,
    )
