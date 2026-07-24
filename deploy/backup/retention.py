# SPDX-License-Identifier: Apache-2.0
"""Sélectionne les archives de sauvegarde à supprimer selon la politique de
rétention (spec SP-Deploy §4.1) : 7 quotidiennes + 4 hebdomadaires. Fonction
pure sur des noms de fichiers (aucun accès disque/réseau) — appelée depuis
`backup.sh` à la fois pour la rotation locale (`/backup/archives`) et
hors-site (sortie de `mc ls`), sur la même politique."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

_NAME_RE = re.compile(r"^(\d{8})-(\d{6})\.tar\.gz\.age$")


def _parse(filename: str) -> datetime | None:
    match = _NAME_RE.match(filename)
    if not match:
        return None
    return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")


def select_files_to_delete(
    filenames: list[str],
    now: datetime,
    daily_count: int = 7,
    weekly_count: int = 4,
) -> list[str]:
    dated = [(f, _parse(f)) for f in filenames]
    dated = [(f, d) for f, d in dated if d is not None]
    dated.sort(key=lambda pair: pair[1], reverse=True)

    daily_cutoff = now - timedelta(days=daily_count)
    keep: set[str] = set()
    older: list[tuple[str, datetime]] = []
    for filename, d in dated:
        if d >= daily_cutoff:
            keep.add(filename)
        else:
            older.append((filename, d))

    # Une sauvegarde par semaine ISO distincte parmi les plus anciennes, les
    # `weekly_count` semaines les plus récentes (older est trié décroissant
    # -> la première rencontrée pour chaque semaine est la plus récente).
    seen_weeks: dict[tuple[int, int], str] = {}
    for filename, d in older:
        week_key = d.isocalendar()[:2]
        if week_key not in seen_weeks and len(seen_weeks) < weekly_count:
            seen_weeks[week_key] = filename
    keep.update(seen_weeks.values())

    return [f for f, _ in dated if f not in keep]


def _main() -> None:
    """CLI utilisée par `backup.sh` (Step 6) : `python3 retention.py "$(ls
    ...)"` — une liste de noms de fichiers séparés par des espaces/retours
    à la ligne en argument unique, une suppression suggérée par ligne de
    sortie."""
    import sys

    filenames = sys.argv[1].split() if len(sys.argv) > 1 and sys.argv[1] else []
    for name in select_files_to_delete(filenames, datetime.utcnow()):
        print(name)


if __name__ == "__main__":
    _main()
