# SPDX-License-Identifier: Apache-2.0
"""API loopback du sidecar desktop-etl (design §4, roadmap §3.1) : rejoue
la forme des routes cœur (app.pipelines.routes) sans Postgres/auth/tenant —
mono-utilisateur, mono-process, 127.0.0.1 uniquement (jamais exposé sur
0.0.0.0, cf. Phase E du plan et l'entrypoint de la Tâche 4)."""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OP_KINDS, ops_catalog
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry

# Dupliqué de app.pipelines.routes._RUNS_MAX_LIMIT (pas importé : cet import
# entraînerait tout le graphe de app.pipelines.routes — jobs/notifications/
# observability/roles — dans le sidecar, à l'exact opposé du but de ce
# paquet, cf. docs/superpowers/specs/2026-09-18-desktop-etl-remaining-
# roadmap.md §2.4).
_RUNS_MAX_LIMIT = 1000

# session=None n'est vérifié sûr (design desktop-etl, Global Constraints du
# plan) que pour reader.file/writer.file et les op transform.* (aucune ne
# touche Session dans runtime.py) — reader.collection/writer.collection/
# writer.dataset/writer.export/reader.connector.* touchent Session et
# lèveraient une AttributeError interne si exposées ici (revue finale, Fix 2).
_SIDECAR_SAFE_OPS = frozenset(
    op
    for op, kind in OP_KINDS.items()
    if op in ("reader.file", "writer.file") or kind == "transform"
)


def create_sidecar_app(*, base_uri: str) -> FastAPI:
    # Actif par défaut côté sidecar desktop, jamais côté cœur (design §3) —
    # posé ici, pas supposé déjà présent dans l'environnement appelant.
    os.environ["CORE_PIPELINE_FILE_IO_ENABLED"] = "true"

    app = FastAPI()
    store = PipelineStore()
    registry = RunRegistry()

    @app.put("/pipelines/{item_id}", status_code=204)
    def put_pipeline(item_id: str, payload: PipelinePayload) -> Response:
        store.set(item_id, payload)
        return Response(status_code=204)

    @app.get("/pipelines/ops")
    def get_ops() -> dict:
        return {op: contract for op, contract in ops_catalog().items() if op in _SIDECAR_SAFE_OPS}

    @app.post("/pipelines/{item_id}/run", status_code=202)
    def run_pipeline_route(item_id: str) -> dict:
        run_id = start_run(store, registry, item_id, base_uri=base_uri)
        if run_id is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        return {"runId": run_id}

    @app.get("/pipelines/{item_id}/runs")
    def get_runs(
        item_id: str,
        limit: int = Query(100, ge=1),
        offset: int = Query(0, ge=0),
    ) -> list[dict]:
        limit = min(limit, _RUNS_MAX_LIMIT)
        return registry.list(item_id, limit=limit, offset=offset)

    @app.post("/pipelines/{item_id}/preview")
    def preview_pipeline_route(item_id: str, upTo: str = Query(...)) -> list[dict]:
        payload = store.get(item_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        try:
            return runtime.preview_pipeline(
                session=None,
                payload=payload,
                tenant_id="local",
                user=None,
                up_to=upTo,
                endpoint_url="",
                access_key="",
                secret_key="",
                base_uri=base_uri,
            )
        except (PipelineRuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
