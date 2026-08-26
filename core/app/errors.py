# SPDX-License-Identifier: Apache-2.0
"""Module bas de la pile (hors du contrat de couches import-linter, même
précédent que app.db/app.observability) : ValidationHTTPException est
importée à la fois par app.features et app.harvest, deux couches non
adjacentes du contrat — un module de contrat aurait dû se placer entre les
deux sans raison métier, donc il reste en dehors, comme app.db."""

from fastapi import HTTPException


class ValidationHTTPException(HTTPException):
    """HTTPException porteuse d'erreurs de validation structurées. Le corps
    RFC 7807 (main.py) les expose sous un membre d'extension `errors` au
    premier niveau — jamais imbriqué sous `detail`, qui reste une chaîne
    (design SP-26 §3.5a/§4.4, changement cassant assumé vis-à-vis de la
    forme précédente {"errors": [...]} nichée sous detail)."""

    def __init__(self, errors: list[dict], status_code: int = 400) -> None:
        super().__init__(status_code=status_code, detail="validation failed")
        self.errors = errors
