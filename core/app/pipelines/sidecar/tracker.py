# SPDX-License-Identifier: Apache-2.0
"""Suivi de run en mémoire (design desktop-etl §4) : implémente le
Protocol RunTracker (app.pipelines.jobs) sans Postgres, pour le sidecar
desktop. Un process, un utilisateur — un verrou global suffit, pas besoin
d'un verrou par item_id (design §1, non-but multi-utilisateur)."""

import threading
import uuid
from datetime import UTC, datetime


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, list[dict]] = {}

    def create(self, item_id: str) -> str:
        run_id = uuid.uuid4().hex
        record = {
            "id": run_id,
            "status": "queued",
            "startedAt": None,
            "finishedAt": None,
            "error": None,
            "nodeStats": {},
        }
        with self._lock:
            self._records.setdefault(item_id, []).insert(0, record)
        return run_id

    def tracker_for(self, item_id: str, run_id: str) -> "InMemoryRunTracker":
        return InMemoryRunTracker(self, item_id=item_id, run_id=run_id)

    def list(self, item_id: str, *, limit: int, offset: int) -> list[dict]:
        with self._lock:
            records = [
                {**record, "nodeStats": dict(record["nodeStats"])}
                for record in self._records.get(item_id, [])
            ]
        return records[offset : offset + limit]

    def _update(self, item_id: str, run_id: str, **fields: object) -> None:
        with self._lock:
            for record in self._records.get(item_id, []):
                if record["id"] == run_id:
                    record.update(fields)
                    return


class InMemoryRunTracker:
    def __init__(self, registry: RunRegistry, *, item_id: str, run_id: str) -> None:
        self._registry = registry
        self._item_id = item_id
        self._run_id = run_id

    def mark_running(self) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="running",
            startedAt=datetime.now(UTC).isoformat(),
        )

    def mark_succeeded(self, node_stats: dict) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="succeeded",
            finishedAt=datetime.now(UTC).isoformat(),
            nodeStats=node_stats,
        )

    def mark_failed(self, error: str) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="failed",
            finishedAt=datetime.now(UTC).isoformat(),
            error=error,
        )
