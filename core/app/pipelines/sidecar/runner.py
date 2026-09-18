# SPDX-License-Identifier: Apache-2.0
"""Exécution d'un pipeline sans Postgres/procrastinate (design desktop-etl
§4) : réutilise app.pipelines.runtime.run_pipeline() tel quel (session=None
— sûr uniquement pour reader.file/transform/writer.file, cf. Global
Constraints du plan), dans un thread daemon, avec le RunTracker en mémoire
de sidecar.tracker. Ce n'est PAS run_pipeline_task (jobs.py) : ce dernier
est câblé en dur à Postgres/S3/notifications (chargement de la config,
utilisateur, tracker), rien de tout cela n'a de sens ici — seul l'appel au
moteur (runtime.run_pipeline) est partagé."""

import threading

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.sidecar.tracker import RunRegistry


class PipelineStore:
    def __init__(self) -> None:
        self._payloads: dict[str, PipelinePayload] = {}

    def set(self, item_id: str, payload: PipelinePayload) -> None:
        self._payloads[item_id] = payload

    def get(self, item_id: str) -> PipelinePayload | None:
        return self._payloads.get(item_id)


def _execute(
    registry: RunRegistry, item_id: str, run_id: str, payload: PipelinePayload, base_uri: str
) -> None:
    tracker = registry.tracker_for(item_id, run_id)
    tracker.mark_running()
    try:
        stats = runtime.run_pipeline(
            None,
            payload=payload,
            tenant_id="local",
            user=None,
            endpoint_url="",
            access_key="",
            secret_key="",
            base_uri=base_uri,
        )
    except (PipelineRuntimeError, ValueError) as exc:
        tracker.mark_failed(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — même patron que jobs.py:run_pipeline_task
        tracker.mark_failed(f"erreur interne : {exc}")
        return
    tracker.mark_succeeded({s.nodeId: s.to_dict() for s in stats})


def start_run(
    store: PipelineStore, registry: RunRegistry, item_id: str, *, base_uri: str
) -> str | None:
    payload = store.get(item_id)
    if payload is None:
        return None
    run_id = registry.create(item_id)
    thread = threading.Thread(
        target=_execute, args=(registry, item_id, run_id, payload, base_uri), daemon=True
    )
    thread.start()
    return run_id
