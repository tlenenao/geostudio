# SPDX-License-Identifier: Apache-2.0
"""Injection de formule (CSV/XLSX) : point unique de neutralisation à l'export
(`sanitize_cell`) et son inverse à l'import (`unsanitize_cell`), pour qu'un
export re-importé round-trippe. Seules les `str` sont traitées : un nombre
typé négatif (-5) reste numérique ; le texte "-5" devient "'-5" (convention OWASP)."""

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def unsanitize_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith("'") and value[1:].startswith(_DANGEROUS):
        return value[1:]
    return value
