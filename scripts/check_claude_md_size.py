"""Garde-fou de taille pour CLAUDE.md.

Empêche la dérive vécue entre le 2026-08-27 et le 2026-09-17 : la règle
« une ligne par chantier sous ### Livré, le récit va dans l'archive » existait
déjà en prose dans CLAUDE.md et a été ignorée pendant ~35 SP d'affilée (voir
docs/superpowers/2026-08-27-historique-execution-continu.md, ~1670 lignes de
récit d'exécution recollées directement dans le fichier chargé à chaque
session). Deux vérifications, aucune ne nécessite de dépendance :

1. Le fichier entier ne dépasse pas un plancher de lignes (mesuré, pas
   arrondi à la hausse — doctrine .coverage-threshold/.bundle-size-threshold).
2. Aucune entrée `- **NOM** — ...` sous ### Livré ne dépasse MAX_ENTRY_LINES
   lignes : c'est le signal direct qu'un récit long est en train d'y être
   recollé plutôt que condensé en une ligne, avec le détail versé dans
   l'archive.
"""

import sys

MAX_ENTRY_LINES = 12


def _section_bounds(lines: list[str], start_prefix: str, end_prefixes: tuple[str, ...]) -> tuple[int, int]:
    start = next(i for i, line in enumerate(lines) if line.startswith(start_prefix))
    end = next(
        i for i, line in enumerate(lines) if i > start and line.startswith(end_prefixes)
    )
    return start, end


def _entry_sizes(section: list[str]) -> list[tuple[int, str]]:
    """Retourne [(nombre de lignes, nom du chantier)] pour chaque entrée `- **...**`."""
    entries: list[tuple[int, str]] = []
    current_len = 0
    current_name = ""
    for line in section:
        if line.startswith("- **"):
            if current_name:
                entries.append((current_len, current_name))
            current_name = line.split("**")[1] if "**" in line else line.strip()
            current_len = 1
        elif current_name:
            if line.strip() == "":
                entries.append((current_len, current_name))
                current_name = ""
                current_len = 0
            else:
                current_len += 1
    if current_name:
        entries.append((current_len, current_name))
    return entries


def main(claude_md_path: str, threshold_path: str) -> int:
    with open(claude_md_path, encoding="utf-8") as f:
        lines = f.readlines()

    with open(threshold_path, encoding="utf-8") as f:
        threshold = int(f.read().strip())

    total = len(lines)
    print(f"{claude_md_path} : {total} lignes (plancher : {threshold})")

    failures = []
    if total > threshold:
        failures.append(f"ÉCHEC : {claude_md_path} fait {total} lignes > plancher {threshold}.")

    livre_start, livre_end = _section_bounds(
        lines, "### Livré", ("### Conventions", "### Suivis", "## ")
    )
    entries = _entry_sizes(lines[livre_start + 1 : livre_end])
    oversized = [(n, size) for size, n in entries if size > MAX_ENTRY_LINES]
    if oversized:
        for name, size in oversized:
            failures.append(
                f"ÉCHEC : entrée « {name} » sous ### Livré fait {size} lignes "
                f"> {MAX_ENTRY_LINES} — condenser à une ligne et verser le récit "
                "dans docs/superpowers/2026-08-27-historique-execution-continu.md."
            )

    if failures:
        for msg in failures:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
