# SPDX-License-Identifier: Apache-2.0
"""Valeurs des filtres `<champ>__in` (REV-313) — module bas niveau, sans dépendance
`app.*` (même statut que `app.sql_ident`), partagé par les 3 constructeurs de
WHERE (features/OGC+export+MCP, agrégats DuckDB, requêtes live de moissonnage)
et par les points d'entrée qui collectent les filtres.

Format des valeurs, documenté :

- paramètre RÉPÉTÉ (`?note__in=Paris, France&note__in=Lyon`) : chaque occurrence
  est UNE valeur littérale, virgules comprises ;
- occurrence unique : liste séparée par des virgules (ancien format, conservé en
  alias — `note__in=a,b`) ; une virgule littérale s'écrit `\\,` et un antislash
  littéral `\\\\`.

En interne un filtre reste un `dict[str, str]` : les occurrences répétées sont
repliées en une chaîne où virgules et antislashs des valeurs sont échappés, que
`split_in_values` redécoupe sans perte."""

from collections.abc import Iterable, Mapping
from typing import Any


def escape_in_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,")


def split_in_values(raw: str) -> list[str]:
    """Découpe sur les virgules non échappées ; `\\,` -> `,` et `\\\\` -> `\\`."""
    values: list[str] = []
    current: list[str] = []
    chars = iter(raw)
    for ch in chars:
        if ch == "\\":
            current.append(next(chars, "\\"))
        elif ch == ",":
            values.append("".join(current))
            current = []
        else:
            current.append(ch)
    values.append("".join(current))
    return values


def fold_query_filters(
    items: Iterable[tuple[str, str]], reserved: Iterable[str] = ()
) -> dict[str, str]:
    """Filtres d'une query string (`request.query_params.multi_items()`) -> dict.
    Un paramètre `__in` répété est replié avec échappement ; les autres gardent
    la dernière valeur (comportement historique de `dict(items())`)."""
    skip = set(reserved)
    seen: dict[str, list[str]] = {}
    for key, value in items:
        if key not in skip:
            seen.setdefault(key, []).append(value)
    return {
        key: (
            ",".join(escape_in_value(v) for v in values)
            if key.endswith("__in") and len(values) > 1
            else values[-1]
        )
        for key, values in seen.items()
    }


def normalize_filters(filters: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Filtres structurés (MCP, JSON) -> dict[str, str] : une liste devient un
    `__in` à valeurs littérales (échappées)."""
    if not filters:
        return None
    return {
        key: ",".join(escape_in_value(str(v)) for v in value)
        if isinstance(value, list | tuple)
        else str(value)
        for key, value in filters.items()
    }
