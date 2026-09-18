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
from app.pipelines.ops.contracts import ops_catalog
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry


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
        return ops_catalog()

    @app.post("/pipelines/{item_id}/run", status_code=202)
    def run_pipeline_route(item_id: str) -> dict:
        run_id = start_run(store, registry, item_id, base_uri=base_uri)
        if run_id is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        return {"runId": run_id}

    @app.get("/pipelines/{item_id}/runs")
    def get_runs(item_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
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
        except PipelineRuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
