# SPDX-License-Identifier: Apache-2.0
"""Régénère deploy/qgis-worker/allowlist.txt (un id par ligne) depuis la
même liste ALLOWLIST_IDS que scripts/generate_qgis_algorithm_schemas.py —
dupliquée ici plutôt qu'importée (le sidecar ne dépend jamais de core/,
design SP-15d §3/§4 : isolation totale). Relancer si l'allowlist change,
en même temps que generate_qgis_algorithm_schemas.py."""
from pathlib import Path

from generate_qgis_algorithm_schemas import ALLOWLIST_IDS

OUTPUT_PATH = Path(__file__).parent.parent / "deploy" / "qgis-worker" / "allowlist.txt"


def main() -> None:
    OUTPUT_PATH.write_text("\n".join(sorted(ALLOWLIST_IDS)) + "\n")
    print(f"wrote {len(ALLOWLIST_IDS)} ids to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
