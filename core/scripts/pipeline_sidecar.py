# SPDX-License-Identifier: Apache-2.0
"""Point d'entrée réel du sidecar desktop-etl (Phase E, design §2/§4).
Diffère de scripts/pipeline_sidecar_spike.py (spike de gel PyInstaller
D1, jamais mis à jour pour rester une preuve isolée) : ce script sert
l'API loopback complète (app.pipelines.sidecar.app), pas un seul appel de
contrôle. Gelé en binaire PyInstaller en Phase F/G, pas ici.

Handshake avec le futur process parent (Tauri, Phase G) : la toute
première ligne de stdout est "PORT=<n>\\n", où <n> est le port TCP
127.0.0.1 effectivement choisi par l'OS — même patron que `gh auth
login`/`aws sso login` pour un listener loopback (design §5)."""

import argparse
import os
import socket
import sys
import tempfile
from pathlib import Path

# Le futur process parent (Tauri, Phase G) spawnera ce script sans garantir
# PYTHONPATH=. (cf. CLAUDE.md § Commandes — "app" n'est importable qu'avec
# cette variable pour les autres scripts du dépôt) : on rend ce script
# autonome en ajoutant explicitement le répertoire `core/` (parent de
# `scripts/`) à sys.path, plutôt que de dépendre de l'environnement
# d'invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from app.pipelines.sidecar.app import create_sidecar_app  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-uri", default=None)
    args = parser.parse_args(argv)
    base_uri = args.base_uri or tempfile.mkdtemp(prefix="geostudio-sidecar-")
    token = os.environ.get("GEOSTUDIO_SIDECAR_TOKEN") or None

    app = create_sidecar_app(base_uri=base_uri, token=token)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    print(f"PORT={port}", flush=True)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
