# SPDX-License-Identifier: Apache-2.0
"""Garde de licences des dépendances Python installées (AUD-111).

GPL/AGPL : refusées. LGPL : refusée sauf entrée datée de `license-exceptions.json`
(`{"<paquet>": "raison"}`) — lien dynamique d'une bibliothèque, pas d'incorporation.
Usage : `uv run python scripts/check_licenses.py [license-exceptions.json]`."""

import json
import re
import sys
from importlib import metadata
from pathlib import Path

_BAD = re.compile(r"\b(A|L)?GPL\b|GNU (Affero |Lesser )?General Public", re.I)
_LESSER = re.compile(r"\bLGPL\b|Lesser", re.I)
# "GPL" dans "... with GCC exception" etc. reste signalé : une exception se déclare.


def license_text(dist: metadata.Distribution) -> str:
    md = dist.metadata
    parts = [md.get("License-Expression") or ""]
    parts += [c for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    if not parts[0]:  # champ `License` libre : souvent un texte entier, on borne
        parts.append((md.get("License") or "")[:200])
    return " | ".join(p for p in parts if p)


def violations(dists: list[tuple[str, str]], exceptions: dict[str, str]) -> list[str]:
    out = []
    for name, lic in dists:
        if name.lower() in exceptions or not _BAD.search(lic):
            continue
        kind = "LGPL sans exception" if _LESSER.search(lic) else "GPL/AGPL"
        out.append(f"{name}: {kind} ({lic.splitlines()[0][:80]})")
    return sorted(out)


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else "license-exceptions.json")
    exceptions = {k.lower(): v for k, v in json.loads(path.read_text()).items()}
    dists = [(d.metadata["Name"] or "?", license_text(d)) for d in metadata.distributions()]
    bad = violations(dists, exceptions)
    print("\n".join(bad) or f"licences : {len(dists)} paquets, aucune violation")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
