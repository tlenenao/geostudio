# SPDX-License-Identifier: Apache-2.0
"""AUD-028 : reprise des jobs procrastinate dont le worker est mort (OOM, SIGKILL,
nœud perdu). procrastinate 3.9 élague le worker sans battement au démarrage suivant
(worker_id -> NULL) mais ne termine jamais son job : il reste 'doing' et son `lock`
(cdc_compaction, run_snapshot_cycle…) bloque toute la file. Ici, le job est terminé en
'failed' (verrou libéré) ; les lignes métier sont reprises par les balayages de domaine
existants (runs, imports, exports…). Toutes les files sont couvertes (`export` comprise),
même si la tâche elle-même tourne sur `etl`."""

import logging

from procrastinate.jobs import Status

from app.jobs import app

logger = logging.getLogger(__name__)

# > stalled_worker_timeout de procrastinate (30 s) et < seuil de la sonde (300 s).
# ponytail: un worker dont la boucle d'événements est bloquée plus de 120 s (tâche async
# CPU) voit son job terminé alors qu'il tourne encore ; la sonde (300 s) le signale.
# Un job sans worker (worker_id NULL, élagué au démarrage d'un autre worker après 30 s
# sans battement) est repris sans délai : c'est le cas nominal du worker mort, mais
# aussi celui d'une boucle gelée plus de 30 s pendant ce démarrage (revue finale L1b,
# M1). Les tâches du dépôt sont synchrones (fil dédié) : le battement n'en dépend pas.
STALLED_HEARTBEAT_S = 120


async def recover_stalled_jobs(
    job_manager, *, seconds_since_heartbeat: float = STALLED_HEARTBEAT_S
) -> list[int]:
    recovered = []
    for job in await job_manager.get_stalled_jobs(seconds_since_heartbeat=seconds_since_heartbeat):
        try:
            await job_manager.finish_job_by_id_async(job.id, status=Status.FAILED, delete_job=False)
        except Exception:  # noqa: BLE001 — terminé entre-temps (plus 'doing') : rien à faire
            logger.warning("job %s : reprise impossible (déjà terminé ?)", job.id, exc_info=True)
            continue
        logger.warning(
            "job %s (%s, verrou %s) d'un worker sans battement terminé en échec",
            job.id,
            job.task_name,
            job.lock,
        )
        recovered.append(job.id)
    return recovered


@app.periodic(cron="* * * * *")
@app.task(queue="etl", queueing_lock="recover_stalled_jobs_task")
async def recover_stalled_jobs_task(timestamp: int) -> None:
    await recover_stalled_jobs(app.job_manager)
