# SPDX-License-Identifier: Apache-2.0
"""Fonction de rendu pure (SP-17a) : ne connaît rien de Playwright, de S3 ni
de la navigation — prend une page déjà navigée/prête et produit des octets.
Testable avec un faux `page` (Protocol), le lancement du vrai navigateur
Chromium vit dans app.export.jobs (tâche 6), seul endroit qui a besoin d'un
Playwright réel installé."""
from typing import Literal, Protocol

from app.configs.schemas import PrintLayout


class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(
        self, *, format: str, landscape: bool, print_background: bool,
        display_header_footer: bool, footer_template: str,
    ) -> bytes: ...


_FOOTER_TEMPLATE = (
    '<div style="font-size:8px; width:100%; text-align:center; color:#666;">'
    'Généré le <span class="date"></span></div>'
)


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(
        format=layout.pageSize.upper(), landscape=layout.orientation == "landscape", print_background=True,
        # display_header_footer/footer_template (SP-17b) : seul morceau
        # d'"en-tête/pied" retenu dans le périmètre resserré du design — pas
        # de numérotation de section, une seule page source par export.
        # <span class="date"> est une classe Chromium native, remplie
        # automatiquement à la date du rendu — rien à calculer côté Python.
        display_header_footer=True, footer_template=_FOOTER_TEMPLATE,
    )
