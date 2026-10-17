# SPDX-License-Identifier: Apache-2.0
"""Message d'erreur montré à l'utilisateur pour un job (AUD-100) : le détail
d'une exception inattendue (SQL, schéma, endpoint interne) reste dans les
journaux serveur. Module racine hors contrat de couches (comme app.errors)."""

INTERNAL_ERROR_MESSAGE = "erreur interne : le détail est consigné dans les journaux du serveur"


def public_error(exc: BaseException, *, user_errors: tuple[type[BaseException], ...] = ()) -> str:
    if user_errors and isinstance(exc, user_errors):
        return str(exc)[:500]
    return INTERNAL_ERROR_MESSAGE
