#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Vérifie que toutes les images de la matrice `_build-and-push.yml`
existent réellement sur GHCR sous un tag donné — cf.
core/tests/test_check_published_images.py pour le contexte (geostudio-
titiler, déclaré dans la matrice mais jamais publié, trouvé en
déploiement réel). Fonctionne sans secret pour un package public
(le token d'échange OAuth2 de Docker Distribution ne nécessite aucune
authentification dans ce cas) ; si la variable d'environnement
GITHUB_TOKEN est présente, elle est envoyée en Basic auth sur l'endpoint
de token — nécessaire pour distinguer une image jamais publiée d'une
image publiée mais encore privée (GHCR crée tout nouveau package en
visibilité privée par défaut ; les deux cas renvoient le même 403 en
anonyme, vérifié empiriquement contre le vrai registre)."""

import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BUILD_AND_PUSH = REPO / ".github/workflows/_build-and-push.yml"
OWNER = "tlenenao"


def release_images() -> list[str]:
    doc = yaml.safe_load(BUILD_AND_PUSH.read_text())
    matrix = doc["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]
    return [entry["image"] for entry in matrix]


def _fetch_token(image: str) -> str:
    url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{OWNER}/{image}:pull"
    request = urllib.request.Request(url)  # noqa: S310
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        actor = os.environ.get("GITHUB_ACTOR", OWNER)
        credentials = base64.b64encode(f"{actor}:{github_token}".encode()).decode()
        request.add_header("Authorization", f"Basic {credentials}")
    with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310
        return json.load(resp)["token"]


def image_exists(image: str, tag: str) -> bool:
    try:
        token = _fetch_token(image)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError):
        return False
    request = urllib.request.Request(  # noqa: S310
        f"https://ghcr.io/v2/{OWNER}/{image}/manifests/{tag}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json",
        },
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            return True
    except urllib.error.URLError:
        return False


def check_all(images: list[str], tag: str, *, checker=image_exists) -> list[str]:
    return [image for image in images if not checker(image, tag)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Tag à vérifier sur ghcr.io/tlenenao/<image>")
    args = parser.parse_args()

    images = release_images()
    missing = check_all(images, args.tag)

    if missing:
        print(
            f"✗ {len(missing)}/{len(images)} image(s) absente(s) sous le tag "
            f"'{args.tag}' : {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    print(f"✓ Les {len(images)} images existent sous le tag '{args.tag}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
