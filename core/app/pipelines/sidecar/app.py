# SPDX-License-Identifier: Apache-2.0
"""API loopback du sidecar desktop-etl (design §4, roadmap §3.1) : rejoue
la forme des routes cœur (app.pipelines.routes) sans Postgres/auth/tenant —
mono-utilisateur, mono-process, 127.0.0.1 uniquement (jamais exposé sur
0.0.0.0, cf. Phase E du plan et l'entrypoint de la Tâche 4).

Phase G (docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md, Tâche 1) :
`token` ferme le DNS rebinding ; il est obligatoire depuis AUD-158 (plus de
mode sans authentification)."""

import hmac

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OP_KINDS, ops_catalog
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry


class _PreviewBody(BaseModel):
    pipeline: PipelinePayload | None = None


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
# REV-329 : les transform à egress réseau (appel HTTP/MCP, géocodage, routage, images,
# jointure base distante) sont exclues tant que le modèle de menace desktop n'est pas écrit.
_SIDECAR_EGRESS_OPS = frozenset(
    {
        "transform.httpCall",
        "transform.mcpCall",
        "transform.geocode",
        "transform.route",
        "transform.isochrone",
        "transform.imageFetch",
        "transform.databaseJoin",
    }
)
_SIDECAR_SAFE_OPS = frozenset(
    op
    for op, kind in OP_KINDS.items()
    if (op in ("reader.file", "writer.file") or kind == "transform")
    and op not in _SIDECAR_EGRESS_OPS
)


_ALLOWED_ORIGINS = ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost")


def _check_pipeline_ops(payload: PipelinePayload) -> None:
    """AUD-160 : l'allowlist d'op vaut au PUT, pas seulement dans le catalogue."""
    bad = sorted({n.op for n in payload.nodes if n.op not in _SIDECAR_SAFE_OPS})
    if bad:
        raise HTTPException(status_code=422, detail=f"op non autorisée dans le sidecar : {bad}")


def create_sidecar_app(*, base_uri: str, token: str) -> FastAPI:
    # CORE_PIPELINE_FILE_IO_ENABLED est posé par le point d'entrée du process
    # (scripts/pipeline_sidecar.py), plus ici : écrire os.environ à la construction
    # fuyait entre tests et vers tout appelant du module (REV-328).
    # AUD-158 : jeton obligatoire, Host contrôlé sans condition, Origin hors allowlist rejetée.
    if not token:
        raise ValueError("un jeton de sidecar est obligatoire")

    app = FastAPI()
    store = PipelineStore()
    registry = RunRegistry()

    expected_authorization = f"Bearer {token}"

    @app.middleware("http")
    async def _enforce_loopback_auth(request: Request, call_next):
        host_header = request.headers.get("host")
        if host_header is None or host_header.rsplit(":", 1)[0] != "127.0.0.1":
            return Response(status_code=400, content="invalid Host header")
        origin = request.headers.get("origin")
        if origin is not None and origin not in _ALLOWED_ORIGINS:
            return Response(status_code=403, content="origin not allowed")
        authorization = request.headers.get("authorization")
        if authorization is None:
            return Response(status_code=401, content="missing or invalid bearer token")
        # Encode both sides to bytes to avoid TypeError on non-ASCII characters
        # (Starlette decodes HTTP headers as latin-1, so any byte sequence is
        # valid as a str; hmac.compare_digest rejects non-ASCII in str comparison).
        try:
            if not hmac.compare_digest(
                authorization.encode("utf-8"),
                expected_authorization.encode("utf-8"),
            ):
                return Response(status_code=401, content="missing or invalid bearer token")
        except UnicodeEncodeError:
            return Response(status_code=401, content="missing or invalid bearer token")
        return await call_next(request)

    # CORS : la webview Tauri (Windows, origine http(s)://tauri.localhost)
    # appelle ce process en cross-origin (127.0.0.1:<port> != tauri.localhost)
    # — sans ceci, chaque fetch() est bloqué côté navigateur avant même
    # d'atteindre les routes ci-dessous, ce qui laisse React Query en
    # attente indéfiniment sans jamais lever d'erreur visible ("Chargement…"
    # perpétuel — trouvé en vérification Windows réelle, Tâche 6 du plan
    # Phase F+G). Ajouté APRÈS _enforce_loopback_auth ci-dessus : chez
    # Starlette, le middleware ajouté en dernier devient la couche la plus
    # externe (vérifié empiriquement — un ordre inverse fait échouer le
    # préflight OPTIONS en 401, l'auth le voyant avant CORS) ; c'est donc
    # CORSMiddleware qui doit être ajouté en dernier pour intercepter les
    # préflights OPTIONS (jamais porteurs d'Authorization) avant l'auth.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_ALLOWED_ORIGINS),
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.put("/pipelines/{item_id}", status_code=204)
    def put_pipeline(item_id: str, payload: PipelinePayload) -> Response:
        _check_pipeline_ops(payload)
        store.set(item_id, payload)
        return Response(status_code=204)

    @app.get("/pipelines/ops")
    def get_ops() -> dict:
        return {op: contract for op, contract in ops_catalog().items() if op in _SIDECAR_SAFE_OPS}

    @app.post("/pipelines/{item_id}/run", status_code=202)
    def run_pipeline_route(item_id: str) -> dict:
        stored = store.get(item_id)
        if stored is not None:
            _check_pipeline_ops(stored)
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
    def preview_pipeline_route(
        item_id: str, upTo: str = Query(...), body: _PreviewBody | None = None
    ) -> list[dict]:
        # AUD-162 : le brouillon envoyé par l'éditeur prime sur la version stockée.
        payload = body.pipeline if body and body.pipeline is not None else store.get(item_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        _check_pipeline_ops(payload)
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
