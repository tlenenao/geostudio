# SPDX-License-Identifier: Apache-2.0
"""Matérialisation dlt des deux op reader.connector.* (design SP-15f §3) —
chaque appel exécute un vrai pipeline dlt vers un fichier DuckDB scratch
dédié, l'ATTACH en lecture seule dans la connexion du runtime, sélectionne
la table racine "records" en TEMP TABLE, puis nettoie (finally). Aucun état
dlt ne survit à un appel (destination ET pipelines_dir scratch, supprimés
ensemble)."""
import os

# Doit précéder `import dlt` : la télémétrie anonyme de dlt est activée par
# défaut (design SP-15f Global Constraints) — un worker ne doit jamais
# téléphoner à l'extérieur par variable d'environnement oubliée.
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")

import shutil
import tempfile
import uuid

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import (
    APIKeyAuth,
    BearerTokenAuth,
    HttpBasicAuth,
    OAuth2ClientCredentials,
)
from dlt.sources.helpers.rest_client.paginators import (
    JSONResponseCursorPaginator,
    OffsetPaginator,
    PageNumberPaginator,
    SinglePagePaginator,
)
from sqlalchemy.orm import Session

from app.pipelines.egress import build_guarded_session
from app.pipelines.ops.schemas import ReaderConnectorRestParams
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SecretPayload

_REST_SECRET_KINDS = {"api_key", "bearer_token", "basic_auth", "oauth2_client_credentials"}


def _qi(name: str) -> str:
    # Duplication délibérée (3e copie du dépôt) — cf. runtime.py, même
    # rationale : helper de 2 lignes, pas un import inter-module d'un nom
    # `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


class ConnectorRuntimeError(Exception):
    """Traduite en PipelineRuntimeError par runtime.py (Task 5) — définie
    ici plutôt qu'importée de runtime.py pour éviter un import circulaire
    (runtime.py importe ce module)."""


def _resolve_secret(session: Session, tenant_id: str, secret_name: str | None) -> SecretPayload | None:
    if secret_name is None:
        return None
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=secret_name)
    if payload is None:
        raise ConnectorRuntimeError(f"secret '{secret_name}' not found")
    return payload


def _build_auth(payload: SecretPayload | None):
    if payload is None:
        return None
    if payload.kind not in _REST_SECRET_KINDS:
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.rest "
            f"(expected one of {sorted(_REST_SECRET_KINDS)})"
        )
    if payload.kind == "bearer_token":
        return BearerTokenAuth(token=payload.token)
    if payload.kind == "api_key":
        return APIKeyAuth(name=payload.key, api_key=payload.value, location=payload.location)
    if payload.kind == "basic_auth":
        return HttpBasicAuth(payload.username, payload.password)
    return OAuth2ClientCredentials(
        access_token_url=payload.tokenUrl, client_id=payload.clientId, client_secret=payload.clientSecret,
        # `session=` est indispensable ici : sans lui, dlt retombe sur son
        # propre `requests.session` par défaut (non gardé) pour l'échange de
        # jeton dans `obtain_token()` — seul des 4 kinds de secret REST à
        # faire sa propre requête plutôt que d'ajouter des en-têtes/paramètres
        # à la session déjà gardée passée à `RESTClient` (design SP-15f §5.1).
        session=build_guarded_session(),
    )


def _build_paginator(paginator: str, config: dict):
    if paginator == "none":
        # Passer un paginateur explicite plutôt que None : sans lui, dlt
        # retombe sur sa détection automatique à la première page et logge
        # un WARNING ("Fallback paginator used...") à chaque appel — bruit
        # de log pur puisqu'on sait déjà qu'il n'y a qu'une page (design §2,
        # paginator="none" est le défaut explicite du modèle de paramètres).
        return SinglePagePaginator()
    if paginator == "page_number":
        # `total_path` par défaut de dlt ("total") suppose un corps de
        # réponse en objet JSON avec un champ de total — nos réponses REST
        # sont des tableaux JSON bruts (design §2, `recordsPath` seulement
        # pour les corps enveloppés). Sans total_path, dlt s'appuie sur
        # `stop_after_empty_page` (défaut True) : une page vide arrête la
        # pagination — c'est le contrat qu'on veut ici.
        return PageNumberPaginator(
            base_page=config.get("basePage", 1), page_param=config.get("pageParam", "page"),
            maximum_page=config.get("maximumPage"), total_path=None,
        )
    if paginator == "offset":
        return OffsetPaginator(
            limit=config["limit"], offset_param=config.get("offsetParam", "offset"),
            limit_param=config.get("limitParam", "limit"), total_path=config.get("totalPath"),
        )
    if paginator == "cursor":
        return JSONResponseCursorPaginator(
            cursor_path=config.get("cursorPath", "cursors.next"), cursor_param=config.get("cursorParam", "cursor"),
        )
    raise ConnectorRuntimeError(f"unknown paginator '{paginator}'")


def _run_dlt_and_attach(conn, resource, *, node_id: str, view_name: str) -> None:
    scratch_dir = tempfile.mkdtemp(prefix=f"sp15f-{node_id}-")
    db_path = f"{scratch_dir}/extract.duckdb"
    try:
        pipeline = dlt.pipeline(
            pipeline_name=f"sp15f-{node_id}-{uuid.uuid4().hex}",
            destination=dlt.destinations.duckdb(db_path),
            dataset_name="pipeline_dataset",
            pipelines_dir=f"{scratch_dir}/dlt-home",
        )
        pipeline.run(resource)
        conn.execute(f"ATTACH '{db_path}' AS dlt_extract (READ_ONLY)")
        try:
            cols = [
                d[0] for d in conn.execute(
                    "SELECT * FROM dlt_extract.pipeline_dataset.records LIMIT 0"
                ).description
                if d[0] not in {"_dlt_id", "_dlt_load_id"}
            ]
            select_list = ", ".join(_qi(c) for c in cols)
            conn.execute(
                f"CREATE TEMP TABLE {_qi(view_name)} AS "
                f"SELECT {select_list} FROM dlt_extract.pipeline_dataset.records"
            )
        finally:
            conn.execute("DETACH dlt_extract")
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def materialize_rest_connector(
    conn, *, session: Session, tenant_id: str, node_id: str,
    params: ReaderConnectorRestParams, view_name: str,
) -> None:
    payload = _resolve_secret(session, tenant_id, params.secretName)
    auth = _build_auth(payload)
    client = RESTClient(
        base_url=params.baseUrl, headers=params.headers or None, auth=auth,
        paginator=_build_paginator(params.paginator, params.paginatorConfig),
        data_selector=params.recordsPath, session=build_guarded_session(),
    )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        for page in client.paginate(params.path, method=params.method, params=params.query or None):
            yield page

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
