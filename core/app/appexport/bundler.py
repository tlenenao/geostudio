# SPDX-License-Identifier: Apache-2.0
"""Assemble le zip d'export Statique : runtime prébâti (Task 10, jamais
reconstruit par ce job) + config gelée (Task 5) sérialisée en JSON, lue au
runtime par shell/src/staticExport/entry.tsx via un fetch relatif — aucune
invocation Node/Vite ici."""
import io
import os
import zipfile

from app.configs.schemas import BuilderConfig


def build_bundle_zip(config: BuilderConfig, *, runtime_dir: str) -> bytes:
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
    return buf.getvalue()
