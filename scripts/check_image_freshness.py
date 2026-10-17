#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""AUD-136 : signale les images locales construites AVANT le dernier commit
qui touche leur contexte de build (la stack sert alors un code en retard sur
HEAD, sans que rien ne le dise).

Usage (à la racine du dépôt, mêmes arguments que `docker compose`) :
    python3 scripts/check_image_freshness.py [-f docker-compose.yml ...] [--profile export]
Sortie 1 si une image est périmée ou absente : `docker compose build <service>`.
Les modifications non commitées ne sont pas prises en compte.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def stale_services(images: dict[str, float], contexts: dict[str, float]) -> list[str]:
    """Services dont l'image (date de création) précède le dernier commit de son contexte."""
    return sorted(s for s, built in images.items() if built < contexts.get(s, 0))


def _created(image: str) -> float | None:
    r = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Created}}", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    # RFC 3339 à la nanoseconde : fromisoformat n'accepte que 6 décimales.
    raw = re.sub(r"(\.\d{6})\d*", r"\1", r.stdout.strip()).replace("Z", "+00:00")
    return datetime.fromisoformat(raw).timestamp()


def _last_commit(*paths: str) -> float:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", *paths],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(out or 0)


def main(compose_args: list[str]) -> int:
    config = json.loads(
        subprocess.run(
            ["docker", "compose", *compose_args, "config", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    images, contexts, missing = {}, {}, []
    for name, svc in config["services"].items():
        build = svc.get("build")
        if not build:
            continue
        image = svc.get("image") or f"{config['name']}-{name}"
        context = Path(build["context"])
        dockerfile = context / build.get("dockerfile", "Dockerfile")
        contexts[name] = _last_commit(str(context), str(dockerfile))
        created = _created(image)
        if created is None:
            missing.append(name)
        else:
            images[name] = created
    stale = stale_services(images, contexts)
    for name in stale:
        print(f"périmée : {name} (image antérieure au dernier commit de son contexte)")
    for name in missing:
        print(f"absente : {name}")
    if stale or missing:
        print(
            "→ "
            + " ".join(["docker", "compose", *compose_args, "build", *stale, *missing])
        )
        return 1
    print(f"{len(images)} image(s) à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
