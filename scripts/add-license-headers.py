#!/usr/bin/env python3
"""Insère un en-tête SPDX Apache-2.0 dans les fichiers source applicatifs.

Idempotent : ignore les fichiers qui portent déjà l'en-tête. Usage ponctuel,
pas un hook ni un job CI — voir
docs/superpowers/specs/2026-07-15-sp9-gouvernance-legale-design.md.
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

HEADER_BY_SUFFIX = {
    ".py": "# SPDX-License-Identifier: Apache-2.0\n",
    ".ts": "// SPDX-License-Identifier: Apache-2.0\n",
    ".tsx": "// SPDX-License-Identifier: Apache-2.0\n",
}

TARGET_GLOBS = [
    ("core/app", "**/*.py"),
    ("core/tests", "**/*.py"),
    ("shell/src", "**/*.ts"),
    ("shell/src", "**/*.tsx"),
]

EXCLUDE_DIRS = [REPO_ROOT / "shell" / "src" / "api" / "generated"]


def iter_target_files() -> "set[pathlib.Path]":
    found: set[pathlib.Path] = set()
    for base, pattern in TARGET_GLOBS:
        for path in (REPO_ROOT / base).glob(pattern):
            if any(excluded in path.parents for excluded in EXCLUDE_DIRS):
                continue
            found.add(path)
    return found


def add_header(path: pathlib.Path) -> str:
    header = HEADER_BY_SUFFIX[path.suffix]
    text = path.read_text(encoding="utf-8")
    if header.strip() in text.splitlines()[:3]:
        return "skipped"
    lines = text.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("#!") else 0
    lines.insert(insert_at, header)
    path.write_text("".join(lines), encoding="utf-8")
    return "updated"


def main() -> int:
    counts = {"updated": 0, "skipped": 0}
    for path in sorted(iter_target_files()):
        counts[add_header(path)] += 1
    print(f"{counts['updated']} fichier(s) mis à jour, {counts['skipped']} déjà à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
