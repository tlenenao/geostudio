# SPDX-License-Identifier: Apache-2.0
"""Assemble le zip d'export : runtime prébâti (jamais reconstruit par ce
job) + config sérialisée en JSON, lue au runtime par
shell/src/staticExport/entry.tsx via un fetch relatif — aucune invocation
Node/Vite ici.

Mode Statique (SP-18a) : `connection=None`, le fichier geostudio-app-
config.json contient la config déjà gelée (freeze_config) par l'appelant.
Mode Connecté (SP-18b) : `connection={"coreUrl": ...}`, la config passée
n'est PAS gelée (elle garde ses DataSources "features"/"statistics"
d'origine) — un second fichier geostudio-connection.json embarque l'URL du
cœur d'origine ; sa présence/absence dans le zip est le seul signal dont
entry.tsx a besoin pour choisir createItemClient (réseau réel) vs
createStaticItemClient (aucun réseau)."""
import io
import json
import os
import zipfile

from app.configs.schemas import BuilderConfig


def build_bundle_zip(
    config: BuilderConfig, *, runtime_dir: str, connection: dict | None = None,
) -> bytes:
    entry_path = os.path.join(runtime_dir, "index.export.html")
    if not os.path.isfile(entry_path):
        raise FileNotFoundError(f"export runtime not found at {entry_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(entry_path, "rb") as f:
            zf.writestr("index.html", f.read())
        assets_dir = os.path.join(runtime_dir, "assets")
        if os.path.isdir(assets_dir):
            for name in os.listdir(assets_dir):
                with open(os.path.join(assets_dir, name), "rb") as f:
                    zf.writestr(f"assets/{name}", f.read())
        zf.writestr("geostudio-app-config.json", config.model_dump_json(by_alias=True))
        if connection is not None:
            zf.writestr("geostudio-connection.json", json.dumps(connection))
    return buf.getvalue()


_STANDALONE_COMPOSE = """\
services:
  app:
    image: ghcr.io/tlenenao/geostudio-appexport-standalone:latest
    ports:
      - "8090:8000"
    volumes:
      - ./data:/data:ro
    restart: unless-stopped
"""

_STANDALONE_README = """\
# App GeoStudio exportée (mode Autoporté)

## Démarrer

    docker compose up -d

Puis ouvrir http://localhost:8090

## Contenu

- `data/geostudio-app-config.json` : configuration de l'app (figée à l'export).
- `data/manifest.json` : métadonnées des collections figées.
- `data/snapshot/` : instantané des données au format GeoParquet.

Le conteneur est strictement en lecture seule : aucune donnée n'est jamais
écrite. Un ré-export manuel depuis GeoStudio est nécessaire pour rafraîchir
l'instantané.
"""


def build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes:
    if not os.path.isdir(snapshot_dir):
        raise FileNotFoundError(f"snapshot directory not found at {snapshot_dir}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/geostudio-app-config.json", config.model_dump_json(by_alias=True))
        for root, _dirs, files in os.walk(snapshot_dir):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, snapshot_dir)
                zf.write(full, arcname=f"data/{rel}")
        zf.writestr("docker-compose.yml", _STANDALONE_COMPOSE)
        zf.writestr("README.md", _STANDALONE_README)
    return buf.getvalue()
