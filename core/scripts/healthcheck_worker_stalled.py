# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité pour worker/export-worker : détecte un job resté en
'doing' plus longtemps qu'un seuil, contrairement à `procrastinate
healthchecks` (connexion+schéma seulement) — même limite documentée que
pour cdc-worker avant sa propre sonde dédiée (GAP-76, SP-49).

`JobManager.get_stalled_jobs` est `async def` sur la version verrouillée de
procrastinate (3.9.0, `core/uv.lock`) — vérifié par introspection en session
(`inspect.iscoroutinefunction`), aucune variante synchrone n'est exposée
pour cette méthode précise (contrairement à `list_jobs`/`list_jobs_async`
qui viennent en paire). `app.jobs.app` utilise `PsycopgConnector` (async,
requis par le CLI procrastinate — cf. commentaire d'`app/jobs/__init__.py`),
donc `app.open_async()`/`await` est la voie correcte ici, pas `app.open()`.

Usage (healthcheck docker) : `python -m scripts.healthcheck_worker_stalled`
Variables :
  HEALTHCHECK_STALLED_SECONDS (def. 3600, aligné sur _RUNNING_RECLAIM_MINUTES/
    _PENDING_RECLAIM_MINUTES déjà utilisés ailleurs dans ce dépôt pour la
    même notion de « probablement planté »).
  HEALTHCHECK_QUEUE (optionnelle, filtre une seule file — utilisée par
    export-worker pour ne surveiller que la file `export`).
Sortie 0 = sain, 1 = pas sain (ou sonde elle-même en échec)."""

import asyncio
import os
import sys

from app.jobs import app


async def _fetch_stalled(threshold_seconds: int, queue: str | None) -> list:
    async with app.open_async():
        return list(
            await app.job_manager.get_stalled_jobs(nb_seconds=threshold_seconds, queue=queue)
        )


def main() -> int:
    threshold = int(os.environ.get("HEALTHCHECK_STALLED_SECONDS", "3600"))
    queue = os.environ.get("HEALTHCHECK_QUEUE") or None
    try:
        stalled = asyncio.run(_fetch_stalled(threshold, queue))
    except Exception as exc:  # une sonde ne doit jamais lever, seulement échouer
        print(f"sonde worker en échec : {exc}", file=sys.stderr)
        return 1
    if stalled:
        print(
            f"{len(stalled)} job(s) bloqué(s) en 'doing' depuis plus de {threshold}s",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
