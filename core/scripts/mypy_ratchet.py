# SPDX-License-Identifier: Apache-2.0
"""Cliquet mypy (AUD-125) : `mypy app/` ne doit jamais avoir plus d'erreurs par fichier que
`.mypy-baseline.json`. Usage :
`uv run mypy app/ | python scripts/mypy_ratchet.py .mypy-baseline.json`
(`--write` réécrit la base, à faire quand le compte baisse)."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

_ERR = re.compile(r"^(?P<file>[^:\n]+\.pyi?):\d+(?::\d+)?: error:", re.M)


def count_errors(output: str) -> dict[str, int]:
    return dict(Counter(m["file"] for m in _ERR.finditer(output)))


def regressions(current: dict[str, int], baseline: dict[str, int]) -> list[str]:
    return [
        f"{f}: {n} erreurs (base : {baseline.get(f, 0)})"
        for f, n in sorted(current.items())
        if n > baseline.get(f, 0)
    ]


def main(argv: list[str]) -> int:
    write = "--write" in argv
    path = Path([a for a in argv if not a.startswith("--")][0])
    current = count_errors(sys.stdin.read())
    if write:
        path.write_text(json.dumps(dict(sorted(current.items())), indent=1) + "\n")
        print(f"base réécrite : {sum(current.values())} erreurs / {len(current)} fichiers")
        return 0
    bad = regressions(current, json.loads(path.read_text()))
    print("\n".join(bad) or f"mypy : {sum(current.values())} erreurs, aucune régression")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
