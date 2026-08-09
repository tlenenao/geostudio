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
    def pdf(self, *, format: str, landscape: bool, print_background: bool) -> bytes: ...


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    # print_background=True (fix round, finding I5) : Playwright/Chromium
    # défaut à False, ce qui supprime tous les fonds CSS — y compris les
    # puces bg-white/90 qui rendent le titre/la légende/le cartouche lisibles
    # par-dessus la carte.
    return page.pdf(
        format=layout.pageSize.upper(), landscape=layout.orientation == "landscape", print_background=True,
    )
