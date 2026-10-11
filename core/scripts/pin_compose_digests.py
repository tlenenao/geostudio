#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Génère, au release, l'override compose qui épingle les images GeoStudio par digest
(ADR 0014) : `docker compose -f docker-compose.yml -f docker-compose.prod.yml
-f docker-compose.digests.yml up`. Les digests viennent des fichiers
`<image>.digest` écrits par `_build-and-push.yml` — jamais écrits à la main.

Usage : pin_compose_digests.py <docker-compose.prod.yml> <dossier digests> <sortie.yml>"""

import pathlib
import sys

import yaml

PREFIX = "ghcr.io/tlenenao/"


class _ComposeLoader(yaml.SafeLoader):
    """docker-compose.prod.yml utilise les tags de fusion Compose (`!reset`, `!override`)."""


_ComposeLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def load_compose(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(), Loader=_ComposeLoader)  # noqa: S506


def build_override(prod: dict, digests: dict[str, str]) -> str:
    services = {}
    for name, svc in prod["services"].items():
        image = svc.get("image", "")
        if image.startswith(PREFIX):
            base = image[len(PREFIX) :].split(":")[0]
            # KeyError voulu si un digest manque : jamais de repli silencieux sur le tag.
            services[name] = {"image": f"{PREFIX}{base}@{digests[base]}"}
    return yaml.safe_dump({"services": services}, sort_keys=True)


def main() -> int:
    compose, digests_dir, out = map(pathlib.Path, sys.argv[1:4])
    digests = {p.stem: p.read_text().strip() for p in digests_dir.glob("*.digest")}
    out.write_text(build_override(load_compose(compose), digests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
